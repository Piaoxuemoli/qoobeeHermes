import asyncio
import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image


class FakeFeature:
    pass


class FakeDirRule:
    def __init__(self, rule, base_dir=None, normalize_zh=None):
        self.rule_dsl = rule
        self.base_dir = base_dir
        self.normalize_zh = normalize_zh


class FakeJmOption:
    album = None
    received_extra = None

    def download_album(self, album_id, *args, **kwargs):
        type(self).received_extra = kwargs.get("extra")
        feature = kwargs.get("extra")
        feature.invoke(
            self,
            "download_album",
            "after_album",
            album=type(self).album,
            downloader=SimpleNamespace(),
        )
        return type(self).album, SimpleNamespace()


class FakeService:
    def __init__(self, *args, **kwargs):
        self.option = FakeJmOption()
        self.logger = MagicMock()

    async def download_album(self, album_id, ctx=None):
        self.option.download_album(album_id, downloader=object)
        return {
            "status": "success",
            "album_id": album_id,
            "title": self.option.album.name,
            "download_path": str(self.option.album.root),
            "error": None,
        }

    def get_client(self):
        return SimpleNamespace(get_album_detail=lambda album_id: self.option.album)


def load_wrapper():
    jmcomic = types.ModuleType("jmcomic")
    jmcomic.Feature = FakeFeature
    jmcomic.DirRule = FakeDirRule
    jmcomic.JmOption = FakeJmOption
    core = types.ModuleType("jmcomic_ai.core")
    core.JmcomicService = FakeService
    server = types.ModuleType("jmcomic_ai.mcp.server")
    server.run_server = lambda *args, **kwargs: None
    package = types.ModuleType("jmcomic_ai")
    mcp_package = types.ModuleType("jmcomic_ai.mcp")
    with patch.dict(
        sys.modules,
        {
            "jmcomic": jmcomic,
            "jmcomic_ai": package,
            "jmcomic_ai.core": core,
            "jmcomic_ai.mcp": mcp_package,
            "jmcomic_ai.mcp.server": server,
        },
    ):
        sys.modules.pop("hermes.scripts.jmai_pdf_mcp", None)
        return importlib.import_module("hermes.scripts.jmai_pdf_mcp")


class FakePhoto:
    def __init__(self, photo_id, name, expected, directory):
        self.photo_id = photo_id
        self.name = name
        self.expected = expected
        self.directory = directory

    def __len__(self):
        return self.expected


class FakeAlbum:
    def __init__(self, album_id, name, root, photos):
        self.album_id = album_id
        self.name = name
        self.title = name
        self.root = root
        self.photos = photos

    def __iter__(self):
        return iter(self.photos)


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.wrapper = load_wrapper()

    def make_incomplete_service(self, root):
        chapter = root / "chapter"
        chapter.mkdir(parents=True)
        Image.new("RGB", (10, 10)).save(chapter / "1.webp", "WEBP")
        photo = FakePhoto("p1", "第一話", 2, chapter)
        album = FakeAlbum("a1", "测试专辑", root, [photo])
        FakeJmOption.album = album
        service = FakeService()
        service.option.album = album
        service.option.decide_image_save_dir = lambda item: str(item.directory)
        return service, album

    def test_enforces_unique_runtime_directory_rule(self):
        option = SimpleNamespace(
            dir_rule=FakeDirRule("Bd_Pname", base_dir="/data", normalize_zh="zh-tw")
        )

        self.wrapper.ensure_unique_directory_rule(option)

        self.assertIn("{Pid}", option.dir_rule.rule_dsl)
        self.assertEqual(option.dir_rule.base_dir, "/data")
        self.assertEqual(option.dir_rule.normalize_zh, "zh-tw")

    def test_pads_extremely_narrow_images_for_valid_pdf_page_size(self):
        source = Image.new("RGB", (1, 100), color="black")

        normalized = self.wrapper._pad_min_dimension(source, minimum=8)

        self.assertEqual(normalized.size, (8, 100))

    def test_feature_returns_partial_without_outputs_for_incomplete_album(self):
        with tempfile.TemporaryDirectory() as tmp:
            service, album = self.make_incomplete_service(Path(tmp))
            feature = self.wrapper.ValidatedMobilePdfFeature(service)
            with patch.object(self.wrapper, "STATE_BASE", str(Path(tmp) / "state")):
                feature.invoke(
                    service.option,
                    "download_album",
                    "after_album",
                    album=album,
                    downloader=SimpleNamespace(),
                )

            self.assertEqual(feature.result["status"], "partial")
            self.assertEqual(feature.result["output_paths"], [])
            self.assertEqual(feature.result["valid_images"], 1)
            self.assertEqual(feature.result["expected_images"], 2)

    def test_recovery_resolves_lazy_photo_metadata_before_counting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lazy = SimpleNamespace(photo_id="lazy", name="惰性章节", page_arr=None)
            detailed = FakePhoto("lazy", "惰性章节", 3, root / "chapter")
            album = FakeAlbum("a1", "测试专辑", root, [lazy])
            service = FakeService()
            service.option.decide_image_save_dir = lambda item: str(item.directory)
            service.get_client = lambda: SimpleNamespace(
                get_photo_detail=lambda photo_id: detailed
            )

            specs = self.wrapper._chapter_specs(service, album)

            self.assertEqual(specs[0].expected_images, 3)
            self.assertEqual(specs[0].chapter_id, "lazy")

    def test_process_album_reuses_matching_persisted_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service, album = self.make_incomplete_service(root)
            state = root / "state"
            manifest_path = state / "a1" / "manifest.json"
            self.wrapper.build_manifest(
                "a1",
                album.name,
                [self.wrapper.ChapterSpec("p1", 1, "第一話", 2, root / "chapter")],
                manifest_path,
            )
            album.photos = [SimpleNamespace(photo_id="p1", name="第一話", page_arr=None)]
            service.get_client = lambda: (_ for _ in ()).throw(
                AssertionError("cache should avoid chapter detail requests")
            )

            with patch.object(self.wrapper, "STATE_BASE", str(state)):
                result = self.wrapper.process_album(service, album)

            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["metadata_source"], "manifest-cache")

    def test_zip_post_process_is_forced_through_validated_pdf_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = self.make_incomplete_service(Path(tmp))
            self.wrapper.patch_validated_pdf_pipeline()
            with patch.object(
                self.wrapper,
                "process_album",
                return_value={"status": "partial", "process_type": "img2pdf", "output_paths": []},
            ) as process:
                result = service.post_process("a1", "zip")

            process.assert_called_once()
            self.assertEqual(result["process_type"], "img2pdf")
            self.assertEqual(result["output_paths"], [])

    def test_download_injects_feature_and_overrides_false_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = self.make_incomplete_service(Path(tmp))
            self.wrapper.patch_validated_pdf_pipeline()
            with patch.object(self.wrapper, "STATE_BASE", str(Path(tmp) / "state")):
                result = asyncio.run(service.download_album("a1"))

            self.assertIsInstance(FakeJmOption.received_extra, self.wrapper.ValidatedMobilePdfFeature)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["output_paths"], [])

    def test_complete_album_generates_pdf_with_exact_total_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photos = []
            for chapter_index in range(1, 3):
                chapter = root / f"chapter-{chapter_index}"
                chapter.mkdir()
                for page_index in range(1, 3):
                    Image.new("RGB", (10, 12)).save(
                        chapter / f"{page_index}.webp", "WEBP"
                    )
                photos.append(FakePhoto(str(chapter_index), f"第{chapter_index}話", 2, chapter))
            album = FakeAlbum("a2", "完整专辑", root, photos)
            service = FakeService()
            service.option.album = album
            service.option.decide_image_save_dir = lambda item: str(item.directory)

            def write_test_pdf(image_paths, output_path):
                pages = [Image.open(path).convert("RGB") for path in image_paths]
                try:
                    pages[0].save(output_path, "PDF", save_all=True, append_images=pages[1:])
                finally:
                    for page in pages:
                        page.close()

            with (
                patch.object(self.wrapper, "STATE_BASE", str(root / "state")),
                patch.object(self.wrapper, "PDF_OUTPUT_BASE", str(root / "output")),
                patch.object(self.wrapper, "write_pdf", side_effect=write_test_pdf),
            ):
                result = self.wrapper.process_album(service, album)

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["expected_images"], 4)
            self.assertEqual(result["pdf_pages"], 4)
            self.assertTrue(all(Path(path).is_file() for path in result["output_paths"]))


if __name__ == "__main__":
    unittest.main()
