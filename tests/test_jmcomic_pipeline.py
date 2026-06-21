import tempfile
import types
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image

from hermes.scripts.jmcomic_pipeline import (
    ChapterPayload,
    ChapterSpec,
    RetrySnapshot,
    build_manifest,
    decide_retry,
    load_chapter_specs,
    plan_volumes,
    validate_pdf_pages,
    write_pdf,
)


def write_image(path: Path, image_format: str = "WEBP") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (12, 16), color=(30, 60, 90)).save(path, image_format)


class ManifestTests(unittest.TestCase):
    def test_recursively_discovers_nested_webp_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chapter = root / "秘密教學_第100話_-_標題"
            write_image(chapter / "nested" / "00001.webp")
            write_image(chapter / "nested" / "00002.webp")

            manifest = build_manifest(
                album_id="1",
                title="秘密教學",
                chapter_specs=[ChapterSpec("100", 100, "第100話", 2, chapter)],
            )

            self.assertEqual(manifest.valid_images, 2)
            self.assertEqual(manifest.status, "complete")
            self.assertEqual(
                [p.name for p in manifest.chapters[0].image_paths],
                ["00001.webp", "00002.webp"],
            )

    def test_parent_chapter_does_not_absorb_other_canonical_chapter_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            album_root = Path(tmp) / "album"
            child_chapter = album_root / "chapter-2"
            write_image(album_root / "direct.webp")
            write_image(child_chapter / "child.webp")

            manifest = build_manifest(
                album_id="1",
                title="嵌套章节",
                chapter_specs=[
                    ChapterSpec("1", 1, "第一話", 1, album_root),
                    ChapterSpec("2", 2, "第二話", 1, child_chapter),
                ],
            )

            self.assertEqual([len(ch.image_paths) for ch in manifest.chapters], [1, 1])
            self.assertEqual(manifest.valid_images, 2)
            self.assertEqual(manifest.status, "complete")

    def test_shared_chapter_directory_is_ambiguous_and_never_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            shared = Path(tmp) / "same-title"
            write_image(shared / "00001.webp")

            manifest = build_manifest(
                album_id="1",
                title="同名章节",
                chapter_specs=[
                    ChapterSpec("1", 1, "公告", 1, shared, ("00001.webp",)),
                    ChapterSpec("2", 2, "公告", 1, shared, ("00001.webp",)),
                ],
            )

            self.assertEqual(manifest.valid_images, 2)
            self.assertEqual(manifest.completed_chapters, 0)
            self.assertTrue(all(ch.ambiguous_directory for ch in manifest.chapters))
            self.assertEqual(manifest.status, "partial")

    def test_reports_empty_and_corrupt_images_as_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            chapter = Path(tmp) / "秘密教學114"
            write_image(chapter / "00001.webp")
            (chapter / "00002.webp").write_bytes(b"")
            (chapter / "00003.webp").write_bytes(b"not-an-image")

            manifest = build_manifest(
                album_id="1",
                title="秘密教學",
                chapter_specs=[ChapterSpec("114", 114, "第114話", 3, chapter)],
            )

            self.assertEqual(manifest.valid_images, 1)
            self.assertEqual(manifest.empty_images, 1)
            self.assertEqual(manifest.corrupt_images, 1)
            self.assertEqual(manifest.status, "partial")

    def test_preserves_api_order_and_non_numeric_chapters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notice = root / "秘密教學 連載調整告知"
            chapter = root / "秘密教學 10"
            write_image(notice / "00001.webp")
            write_image(chapter / "00001.webp")

            manifest = build_manifest(
                album_id="1",
                title="秘密教學",
                chapter_specs=[
                    ChapterSpec("notice", 1, "連載調整告知", 1, notice),
                    ChapterSpec("10", 2, "第10話", 1, chapter),
                ],
            )

            self.assertEqual([c.spec.chapter_id for c in manifest.chapters], ["notice", "10"])
            self.assertEqual(manifest.completed_chapters, 2)

    def test_one_missing_page_is_partial_without_tolerance(self):
        with tempfile.TemporaryDirectory() as tmp:
            chapter = Path(tmp) / "chapter"
            for index in range(99):
                write_image(chapter / f"{index:05d}.webp")

            manifest = build_manifest(
                album_id="1",
                title="严格校验",
                chapter_specs=[ChapterSpec("1", 1, "第一話", 100, chapter)],
            )

            self.assertEqual(manifest.expected_images, 100)
            self.assertEqual(manifest.valid_images, 99)
            self.assertEqual(manifest.missing_images, 1)
            self.assertEqual(manifest.status, "partial")

    def test_persisted_manifest_restores_expected_filenames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chapter = root / "chapter"
            write_image(chapter / "00001.webp")
            manifest_path = root / "state" / "manifest.json"
            build_manifest(
                album_id="1",
                title="缓存",
                chapter_specs=[
                    ChapterSpec("p1", 1, "第一話", 1, chapter, ("00001.webp",))
                ],
                manifest_path=manifest_path,
            )

            specs = load_chapter_specs(manifest_path)

            self.assertEqual(specs[0].expected_filenames, ("00001.webp",))
            self.assertEqual(specs[0].directory, chapter)


class VolumePlanningTests(unittest.TestCase):
    def test_splits_only_between_chapters(self):
        chapters = [
            ChapterPayload("1", 1, "第一話", ("1.jpg", "2.jpg"), 8, 2),
            ChapterPayload("2", 2, "第二話", ("3.jpg",), 7, 1),
            ChapterPayload("3", 3, "第三話", ("4.jpg", "5.jpg"), 5, 2),
        ]

        volumes = plan_volumes("秘密教學", chapters, limit_bytes=15)

        self.assertEqual(len(volumes), 2)
        self.assertEqual([c.chapter_id for c in volumes[0].chapters], ["1", "2"])
        self.assertEqual([c.chapter_id for c in volumes[1].chapters], ["3"])
        self.assertEqual(volumes[0].page_count, 3)
        self.assertEqual(volumes[0].output_name, "秘密教學_第001-002話.pdf")

    def test_rejects_a_chapter_larger_than_the_volume_limit(self):
        chapter = ChapterPayload("1", 1, "第一話", ("1.jpg",), 16, 1)

        with self.assertRaisesRegex(ValueError, "exceeds the volume limit"):
            plan_volumes("秘密教學", [chapter], limit_bytes=15)

    def test_validates_pdf_page_count_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "two-pages.pdf"
            pages = [Image.new("RGB", (12, 16)), Image.new("RGB", (12, 16))]
            pages[0].save(output, "PDF", save_all=True, append_images=pages[1:])

            self.assertEqual(validate_pdf_pages(output, expected_pages=2), 2)
            with self.assertRaisesRegex(RuntimeError, "page count mismatch"):
                validate_pdf_pages(output, expected_pages=3)

    def test_pdf_writer_forces_stable_dpi_layout(self):
        calls = {}
        layout = object()

        def convert(*images, outputstream=None, **kwargs):
            calls.update(kwargs)
            outputstream.write(b"pdf")

        fake_img2pdf = types.SimpleNamespace(
            get_fixed_dpi_layout_fun=lambda dpi: layout,
            convert=convert,
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output.pdf"
            with patch.dict("sys.modules", {"img2pdf": fake_img2pdf}):
                write_pdf(["page.jpg"], output)

        self.assertIs(calls["layout_fun"], layout)


class RetryPolicyTests(unittest.TestCase):
    def test_retries_when_progress_is_made(self):
        decision = decide_retry([RetrySnapshot(1, 100, 4), RetrySnapshot(2, 150, 6)])
        self.assertTrue(decision.should_retry)
        self.assertEqual(decision.delay_seconds, 30)

    def test_stops_after_two_consecutive_no_progress_rounds(self):
        decision = decide_retry(
            [
                RetrySnapshot(1, 100, 4),
                RetrySnapshot(2, 100, 4),
                RetrySnapshot(3, 100, 4),
            ]
        )
        self.assertFalse(decision.should_retry)
        self.assertEqual(decision.reason, "no-progress")

    def test_stops_at_five_attempts(self):
        decision = decide_retry([RetrySnapshot(i, i * 10, i) for i in range(1, 6)])
        self.assertFalse(decision.should_retry)
        self.assertEqual(decision.reason, "max-attempts")


if __name__ == "__main__":
    unittest.main()
