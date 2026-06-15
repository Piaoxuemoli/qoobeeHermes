#!/usr/bin/env python3
"""Smoke tests for jmai_pdf_mcp.py splitting logic.

Run in an environment where jmcomic-ai dependencies (img2pdf, Pillow) are
available. The real jmcomic_ai package is mocked so the tests run offline.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image

# Ensure the script under test can be imported.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# Mock jmcomic_ai before importing the module under test.
class _MockJmcomicService:
    pass

mock_jmcomic_ai = MagicMock()
mock_jmcomic_ai.core.JmcomicService = _MockJmcomicService
mock_jmcomic_ai.mcp.server.run_server = lambda *args, **kwargs: None
sys.modules["jmcomic_ai"] = mock_jmcomic_ai
sys.modules["jmcomic_ai.core"] = mock_jmcomic_ai.core
sys.modules["jmcomic_ai.mcp.server"] = mock_jmcomic_ai.mcp.server

import jmai_pdf_mcp as jmai


def _make_dummy_images(count: int, size: tuple[int, int], output_dir: Path) -> list[str]:
    paths: list[str] = []
    for i in range(count):
        path = output_dir / f"page_{i + 1:03d}.jpg"
        image = Image.new("RGB", size, color=(i % 256, (i * 2) % 256, (i * 3) % 256))
        # Add some noise to make JPEG less compressible.
        pixels = image.load()
        assert pixels is not None
        for y in range(0, size[1], 8):
            for x in range(0, size[0], 8):
                pixels[x, y] = ((x + y + i) % 256, (x + i) % 256, (y + i) % 256)
        image.save(path, "JPEG", quality=95)
        paths.append(str(path))
    return paths


class _FakeAlbum:
    def __init__(self, title: str, photos: list):
        self.title = title
        self._photos = photos

    def __iter__(self):
        return iter(self._photos)


def _build_mock_service(photo_dir: Path):
    service = jmai.JmcomicService()
    service.option = MagicMock()
    service.option.decide_image_save_dir.return_value = str(photo_dir)
    service.get_client = MagicMock()
    fake_album = _FakeAlbum("Test Album 测试", [SimpleNamespace()])
    service.get_client.return_value.get_album_detail.return_value = fake_album
    service.logger = MagicMock()
    return service


def test_single_pdf_under_limit():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()
        out_dir = tmp_path / "out"

        images = _make_dummy_images(5, (1200, 1800), photo_dir)

        with patch.object(jmai, "PDF_OUTPUT_BASE", str(out_dir)):
            with patch.object(jmai, "PDF_MAX_SIZE_MB", 28):
                service = _build_mock_service(photo_dir)
                paths = jmai._write_mobile_pdf(service, "12345")

        assert len(paths) == 1, paths
        assert Path(paths[0]).exists()
        assert Path(paths[0]).stat().st_size < 28 * 1024 * 1024


def test_auto_split_when_over_limit():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()
        out_dir = tmp_path / "out"

        # 30 reasonably large images will exceed a 5 MB limit and trigger splitting.
        images = _make_dummy_images(30, (1200, 1800), photo_dir)

        with patch.object(jmai, "PDF_OUTPUT_BASE", str(out_dir)):
            with patch.object(jmai, "PDF_MAX_SIZE_MB", 5):
                service = _build_mock_service(photo_dir)
                paths = jmai._write_mobile_pdf(service, "12345")

        assert len(paths) > 1, paths
        for path in paths:
            p = Path(path)
            assert p.exists(), path
            size = p.stat().st_size
            assert size <= 5 * 1024 * 1024, f"{path} is {size} bytes, over limit"


def test_post_process_returns_multiple_paths():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()
        out_dir = tmp_path / "out"

        images = _make_dummy_images(30, (1200, 1800), photo_dir)

        with patch.object(jmai, "PDF_OUTPUT_BASE", str(out_dir)):
            with patch.object(jmai, "PDF_MAX_SIZE_MB", 5):
                jmai.patch_pdf_only_post_process()
                service = _build_mock_service(photo_dir)
                result = service.post_process("12345", "img2pdf")

        assert result["status"] == "success", f"post_process failed: {result['message']}"
        assert len(result["output_paths"]) > 1
        assert result["output_path"] == result["output_paths"][0]
        assert "split into" in result["message"].lower() or "volume" in result["message"].lower()


if __name__ == "__main__":
    test_single_pdf_under_limit()
    print("test_single_pdf_under_limit passed")
    test_auto_split_when_over_limit()
    print("test_auto_split_when_over_limit passed")
    test_post_process_returns_multiple_paths()
    print("test_post_process_returns_multiple_paths passed")
    print("All tests passed")
