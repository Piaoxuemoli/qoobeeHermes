#!/usr/bin/env python3
"""Run jmcomic-ai MCP with PDF-only post-processing.

This wrapper keeps the upstream jmcomic-ai MCP server intact, but patches
JmcomicService.post_process so accidental zip requests become album-level PDF
generation. The Feishu mobile workflow cannot reliably handle zip archives.

To keep every attachment below Feishu's 30 MB file-message limit, long albums
are automatically split into multiple PDF volumes.
"""

from __future__ import annotations

import math
import os
import re
import tempfile
from pathlib import Path

from jmcomic_ai.core import JmcomicService
from jmcomic_ai.mcp.server import run_server


PDF_OUTPUT_BASE = os.environ.get("JMCOMIC_PDF_BASE_DIR", "/tmp/monitor_charts/jmcomic")
OPTION_PATH = os.environ.get("JM_OPTION_PATH", "/root/.jmcomic/option.yml")
PDF_MAX_SIDE = int(os.environ.get("JMCOMIC_PDF_MAX_SIDE", "1800"))
PDF_JPEG_QUALITY = int(os.environ.get("JMCOMIC_PDF_JPEG_QUALITY", "72"))
# Feishu bot file message hard limit is 30 MB; use a safe default margin.
PDF_MAX_SIZE_MB = int(os.environ.get("JMCOMIC_PDF_MAX_SIZE_MB", "28"))


def _safe_filename(value: str) -> str:
    value = re.sub(r'[\x00/\\:*?"<>|]+', "_", value).strip()
    return value or "album"


def _collect_downloaded_images(service: JmcomicService, album) -> list[str]:
    """Collect downloaded image paths, skipping empty or unreadable files."""
    from PIL import Image

    images: list[str] = []
    for photo in album:
        photo_dir = Path(service.option.decide_image_save_dir(photo))
        if not photo_dir.exists():
            continue
        for file in sorted(photo_dir.iterdir()):
            if not (
                file.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}
                and not file.name.startswith(".")
            ):
                continue
            if file.stat().st_size == 0:
                service.logger.warning("Skipping empty image file: %s", file)
                continue
            try:
                with Image.open(file) as image:
                    image.verify()
                images.append(str(file))
            except Exception as exc:
                service.logger.warning("Skipping unreadable image %s: %s", file, exc)
    return images


def _write_pdf_from_jpegs(jpeg_paths: list[str], output_path: Path) -> None:
    """Write a single PDF from a list of JPEG paths using img2pdf."""
    import img2pdf

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as pdf_file:
        pdf_file.write(img2pdf.convert(jpeg_paths))


def _resize_images_to_jpegs(images: list[str], tmp_dir: Path) -> list[str]:
    """Resize source images to temp JPEGs and return ordered paths."""
    from PIL import Image

    jpeg_paths: list[str] = []
    for index, image_path in enumerate(images, 1):
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            image.thumbnail((PDF_MAX_SIDE, PDF_MAX_SIDE), Image.Resampling.LANCZOS)
            jpeg_path = tmp_dir / f"{index:05d}.jpg"
            image.save(jpeg_path, "JPEG", quality=PDF_JPEG_QUALITY, optimize=True)
            jpeg_paths.append(str(jpeg_path))
    return jpeg_paths


def _estimate_volume_count(jpeg_paths: list[str], limit_bytes: int) -> int:
    """Estimate how many PDF volumes are needed to stay under the size limit.

    img2pdf embeds JPEGs with very little overhead, so total PDF size is
    roughly the sum of JPEG sizes. We use a 0.9 factor as a safety margin.
    """
    total_jpeg_bytes = sum(Path(p).stat().st_size for p in jpeg_paths)
    if total_jpeg_bytes <= limit_bytes * 0.9:
        return 1
    return max(1, math.ceil(total_jpeg_bytes / (limit_bytes * 0.9)))


def _write_mobile_pdf(service: JmcomicService, album_id: str) -> list[str]:
    album = service.get_client().get_album_detail(album_id)
    images = _collect_downloaded_images(service, album)
    if not images:
        raise RuntimeError(f"No downloaded images found for album {album_id}")

    output_dir = Path(PDF_OUTPUT_BASE)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_title = _safe_filename(album.title)
    limit_bytes = PDF_MAX_SIZE_MB * 1024 * 1024

    with tempfile.TemporaryDirectory(prefix=f"jmcomic_pdf_{album_id}_") as tmp:
        jpeg_paths = _resize_images_to_jpegs(images, Path(tmp))
        num_volumes = _estimate_volume_count(jpeg_paths, limit_bytes)

        if num_volumes == 1:
            output_path = output_dir / f"{safe_title}.pdf"
            _write_pdf_from_jpegs(jpeg_paths, output_path)
            output_paths = [str(output_path)]
        else:
            chunk_size = math.ceil(len(jpeg_paths) / num_volumes)
            output_paths: list[str] = []
            for volume_index, start in enumerate(range(0, len(jpeg_paths), chunk_size), 1):
                chunk = jpeg_paths[start : start + chunk_size]
                output_path = output_dir / f"{safe_title}_part{volume_index:02d}.pdf"
                _write_pdf_from_jpegs(chunk, output_path)

                actual_size = output_path.stat().st_size
                if actual_size > limit_bytes:
                    raise RuntimeError(
                        f"Volume {volume_index} exceeds size limit: "
                        f"{actual_size / 1024 / 1024:.1f} MB > {PDF_MAX_SIZE_MB} MB. "
                        "Try lowering PDF_MAX_SIDE/PDF_JPEG_QUALITY."
                    )
                output_paths.append(str(output_path))

    return output_paths


def patch_pdf_only_post_process() -> None:
    def pdf_only_post_process(self, album_id, process_type, params=None):
        if process_type != "img2pdf":
            self.logger.warning(
                "PDF-only mode: converting post_process(%s) for album %s to img2pdf",
                process_type,
                album_id,
            )
        try:
            output_paths = _write_mobile_pdf(self, album_id)
            message = "PDF-only mobile PDF generated successfully."
            if len(output_paths) > 1:
                message = (
                    f"Album split into {len(output_paths)} PDF volumes "
                    f"(each under {PDF_MAX_SIZE_MB} MB) for Feishu upload."
                )
            return {
                "status": "success",
                "process_type": "img2pdf",
                "album_id": album_id,
                "output_path": output_paths[0],
                "output_paths": output_paths,
                "is_directory": False,
                "message": message,
            }
        except Exception as exc:
            self.logger.exception("PDF-only mobile PDF generation failed")
            return {
                "status": "error",
                "process_type": "img2pdf",
                "album_id": album_id,
                "output_path": "",
                "output_paths": [],
                "is_directory": False,
                "message": f"PDF generation failed: {exc}",
            }

    JmcomicService.post_process = pdf_only_post_process


def main() -> None:
    patch_pdf_only_post_process()
    service = JmcomicService(OPTION_PATH)
    run_server("stdio", service, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
