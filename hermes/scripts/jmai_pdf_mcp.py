#!/usr/bin/env python3
"""Run jmcomic-ai with validated, PDF-only mobile delivery."""

from __future__ import annotations

import contextvars
import contextlib
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from jmcomic import DirRule, Feature, JmOption
from jmcomic_ai.core import JmcomicService
from jmcomic_ai.mcp.server import run_server

try:
    from .jmcomic_pipeline import (
        ChapterPayload,
        ChapterSpec,
        build_manifest,
        load_chapter_specs,
        plan_volumes,
        validate_pdf_pages,
        write_pdf,
    )
except ImportError:
    from jmcomic_pipeline import (  # type: ignore
        ChapterPayload,
        ChapterSpec,
        build_manifest,
        load_chapter_specs,
        plan_volumes,
        validate_pdf_pages,
        write_pdf,
    )


PDF_OUTPUT_BASE = os.environ.get("JMCOMIC_PDF_BASE_DIR", "/tmp/monitor_charts/jmcomic")
STATE_BASE = os.environ.get("JMCOMIC_STATE_BASE_DIR", "/root/.hermes/state/jmcomic")
OPTION_PATH = os.environ.get("JM_OPTION_PATH", "/root/.jmcomic/option.yml")
PDF_MAX_SIDE = int(os.environ.get("JMCOMIC_PDF_MAX_SIDE", "1800"))
PDF_JPEG_QUALITY = int(os.environ.get("JMCOMIC_PDF_JPEG_QUALITY", "72"))
# Production observations show uploads become unreliable near 20 MB.
PDF_MAX_SIZE_MB = int(os.environ.get("JMCOMIC_PDF_MAX_SIZE_MB", "18"))
PDF_PLAN_RATIO = float(os.environ.get("JMCOMIC_PDF_PLAN_RATIO", "0.90"))
UNIQUE_DIRECTORY_RULE = "Bd / JM{Aid}-{Pid}"

_ORIGINAL_OPTION_DOWNLOAD_ALBUM = JmOption.download_album
_ORIGINAL_SERVICE_DOWNLOAD_ALBUM = JmcomicService.download_album
_ACTIVE_FEATURE: contextvars.ContextVar["ValidatedMobilePdfFeature | None"] = (
    contextvars.ContextVar("jmcomic_validated_pdf_feature", default=None)
)
_PATCHED = False


def route_library_logs_to_stderr() -> None:
    """Keep third-party logs away from the MCP JSON-RPC stdout stream."""
    for handler in logging.getLogger("jmcomic").handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setStream(sys.stderr)


def _safe_filename(value: str) -> str:
    value = re.sub(r'[\x00/\\:*?"<>|]+', "_", value).strip().rstrip(".")
    return value or "album"


def ensure_unique_directory_rule(option: JmOption) -> None:
    current = option.dir_rule
    if current.rule_dsl == UNIQUE_DIRECTORY_RULE:
        return
    option.dir_rule = DirRule(
        UNIQUE_DIRECTORY_RULE,
        base_dir=current.base_dir,
        normalize_zh=current.normalize_zh,
    )


def _album_title(album: Any) -> str:
    return str(getattr(album, "name", None) or getattr(album, "title", None) or "album")


def _album_id(album: Any) -> str:
    return str(getattr(album, "album_id", None) or getattr(album, "id", None) or "unknown")


def _chapter_specs(service: JmcomicService, album: Any) -> list[ChapterSpec]:
    specs: list[ChapterSpec] = []
    client = None
    for index, photo in enumerate(album, 1):
        if hasattr(photo, "page_arr") and photo.page_arr is None:
            client = client or service.get_client()
            photo = client.get_photo_detail(photo.photo_id)
        specs.append(
            ChapterSpec(
                chapter_id=str(getattr(photo, "photo_id", index)),
                index=index,
                title=str(getattr(photo, "name", f"chapter-{index}")),
                expected_images=len(photo),
                directory=Path(service.option.decide_image_save_dir(photo)),
                expected_filenames=tuple(
                    Path(name).name for name in (getattr(photo, "page_arr", None) or ())
                ),
            )
        )
    return specs


def _base_result(album: Any) -> dict[str, Any]:
    return {
        "status": "error",
        "process_type": "img2pdf",
        "album_id": _album_id(album),
        "title": _album_title(album),
        "output_path": "",
        "output_paths": [],
        "is_directory": False,
    }


def _pad_min_dimension(image, minimum: int = 8):
    from PIL import Image

    width, height = image.size
    if width >= minimum and height >= minimum:
        return image
    canvas = Image.new(
        "RGB",
        (max(width, minimum), max(height, minimum)),
        color="white",
    )
    canvas.paste(image, ((canvas.width - width) // 2, (canvas.height - height) // 2))
    return canvas


def _resize_chapters(manifest, temporary_dir: Path) -> list[ChapterPayload]:
    from PIL import Image

    payloads: list[ChapterPayload] = []
    for chapter in manifest.chapters:
        chapter_dir = temporary_dir / f"{chapter.spec.index:04d}"
        chapter_dir.mkdir(parents=True, exist_ok=True)
        jpeg_paths: list[str] = []
        total_bytes = 0
        for page_index, source in enumerate(chapter.image_paths, 1):
            destination = chapter_dir / f"{page_index:05d}.jpg"
            with Image.open(source) as image:
                image = image.convert("RGB")
                image.thumbnail((PDF_MAX_SIDE, PDF_MAX_SIDE), Image.Resampling.LANCZOS)
                image = _pad_min_dimension(image)
                image.save(
                    destination,
                    "JPEG",
                    quality=PDF_JPEG_QUALITY,
                    optimize=True,
                )
            jpeg_paths.append(str(destination))
            total_bytes += destination.stat().st_size
        payloads.append(
            ChapterPayload(
                chapter_id=chapter.spec.chapter_id,
                index=chapter.spec.index,
                title=chapter.spec.title,
                image_paths=tuple(jpeg_paths),
                total_bytes=total_bytes,
                page_count=len(jpeg_paths),
            )
        )
    return payloads


def process_album(service: JmcomicService, album: Any, downloader: Any = None) -> dict[str, Any]:
    """Validate disk state and create size-safe PDFs only for a complete album."""
    result = _base_result(album)
    album_id = result["album_id"]
    manifest_path = Path(STATE_BASE) / album_id / "manifest.json"
    chapter_ids = [str(getattr(photo, "photo_id", "")) for photo in album]
    chapter_specs = None
    if manifest_path.is_file():
        try:
            cached_specs = load_chapter_specs(manifest_path)
            if [spec.chapter_id for spec in cached_specs] == chapter_ids:
                chapter_specs = cached_specs
        except (KeyError, OSError, TypeError, ValueError):
            service.logger.warning("Ignoring unusable JMComic manifest cache: %s", manifest_path)
    metadata_source = "manifest-cache" if chapter_specs is not None else "api"
    if chapter_specs is None:
        chapter_specs = _chapter_specs(service, album)
    manifest = build_manifest(
        album_id=album_id,
        title=result["title"],
        chapter_specs=chapter_specs,
        manifest_path=manifest_path,
    )
    result.update(
        {
            "manifest_path": str(manifest_path),
            "expected_images": manifest.expected_images,
            "valid_images": manifest.valid_images,
            "missing_images": manifest.missing_images,
            "empty_images": manifest.empty_images,
            "corrupt_images": manifest.corrupt_images,
            "unexpected_images": manifest.unexpected_images,
            "ambiguous_chapters": sum(
                chapter.ambiguous_directory for chapter in manifest.chapters
            ),
            "completed_chapters": manifest.completed_chapters,
            "chapter_count": len(manifest.chapters),
            "metadata_source": metadata_source,
        }
    )
    if manifest.status != "complete":
        result.update(
            {
                "status": "partial",
                "message": (
                    "Download is incomplete; no PDF was generated. "
                    f"Valid {manifest.valid_images}/{manifest.expected_images}, "
                    f"missing {manifest.missing_images}, corrupt {manifest.corrupt_images}, "
                    f"empty {manifest.empty_images}, unexpected {manifest.unexpected_images}."
                ),
                "missing_chapter_ids": [
                    chapter.spec.chapter_id
                    for chapter in manifest.chapters
                    if not chapter.is_complete
                ],
            }
        )
        return result

    output_dir = Path(PDF_OUTPUT_BASE)
    output_dir.mkdir(parents=True, exist_ok=True)
    hard_limit = PDF_MAX_SIZE_MB * 1024 * 1024
    planning_limit = int(hard_limit * PDF_PLAN_RATIO)
    created: list[Path] = []
    try:
        with tempfile.TemporaryDirectory(prefix=f"jmcomic_pdf_{album_id}_") as temporary:
            payloads = _resize_chapters(manifest, Path(temporary))
            plans = plan_volumes(_safe_filename(result["title"]), payloads, planning_limit)
            for plan in plans:
                output_path = output_dir / plan.output_name
                image_paths = [path for chapter in plan.chapters for path in chapter.image_paths]
                write_pdf(image_paths, output_path)
                validate_pdf_pages(output_path, plan.page_count)
                if output_path.stat().st_size > hard_limit:
                    raise RuntimeError(
                        f"PDF exceeds {PDF_MAX_SIZE_MB} MB after encoding: {output_path}"
                    )
                created.append(output_path)

        total_pdf_pages = sum(
            validate_pdf_pages(path, plan.page_count)
            for path, plan in zip(created, plans, strict=True)
        )
        if total_pdf_pages != manifest.valid_images:
            raise RuntimeError(
                f"album PDF page count mismatch: expected {manifest.valid_images}, "
                f"got {total_pdf_pages}"
            )
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise

    output_paths = [str(path) for path in created]
    result.update(
        {
            "status": "success",
            "output_path": output_paths[0],
            "output_paths": output_paths,
            "pdf_pages": total_pdf_pages,
            "message": (
                f"Validated {manifest.valid_images}/{manifest.expected_images} images and "
                f"generated {len(output_paths)} PDF volume(s), each under "
                f"{PDF_MAX_SIZE_MB} MB."
            ),
        }
    )
    return result


class ValidatedMobilePdfFeature(Feature):
    def __init__(self, service: JmcomicService):
        self.service = service
        self.result: dict[str, Any] | None = None

    def should_invoke(self, feature_from: str, when: str) -> bool:
        return feature_from == "download_album" and when == "after_album"

    def invoke(self, option: JmOption, feature_from: str, when: str, **kwargs) -> None:
        if not self.should_invoke(feature_from, when):
            return
        album = kwargs["album"]
        try:
            self.result = process_album(self.service, album, kwargs.get("downloader"))
        except Exception as exc:
            self.service.logger.exception("Validated mobile PDF generation failed")
            self.result = _base_result(album)
            self.result["message"] = f"PDF generation failed: {exc}"


def _merge_feature(existing: Any, feature: ValidatedMobilePdfFeature) -> Any:
    if existing is None:
        return feature
    if isinstance(existing, list):
        return [*existing, feature]
    return [existing, feature]


def patch_validated_pdf_pipeline() -> None:
    global _PATCHED
    if _PATCHED:
        return

    def option_download_album(self, album_id, *args, **kwargs):
        feature = _ACTIVE_FEATURE.get()
        if feature is not None:
            kwargs["extra"] = _merge_feature(kwargs.get("extra"), feature)
        return _ORIGINAL_OPTION_DOWNLOAD_ALBUM(self, album_id, *args, **kwargs)

    async def service_download_album(self, album_id, ctx=None):
        feature = ValidatedMobilePdfFeature(self)
        token = _ACTIVE_FEATURE.set(feature)
        try:
            upstream = await _ORIGINAL_SERVICE_DOWNLOAD_ALBUM(self, album_id, ctx)
        finally:
            _ACTIVE_FEATURE.reset(token)

        result = dict(upstream)
        if result.get("status") != "success":
            return result
        if feature.result is None:
            result.update(
                {
                    "status": "error",
                    "process_type": "img2pdf",
                    "output_path": "",
                    "output_paths": [],
                    "message": "Validated PDF feature did not run; success is not trusted.",
                }
            )
            return result
        result.update(feature.result)
        return result

    def pdf_only_post_process(self, album_id, process_type, params=None):
        if process_type != "img2pdf":
            self.logger.warning(
                "PDF-only mode: converting post_process(%s) for album %s to img2pdf",
                process_type,
                album_id,
            )
        try:
            album = self.get_client().get_album_detail(album_id)
            return process_album(self, album)
        except Exception as exc:
            self.logger.exception("Validated PDF recovery failed")
            result = {
                "status": "error",
                "process_type": "img2pdf",
                "album_id": str(album_id),
                "output_path": "",
                "output_paths": [],
                "is_directory": False,
                "message": f"PDF generation failed: {exc}",
            }
            return result

    JmOption.download_album = option_download_album
    JmcomicService.download_album = service_download_album
    JmcomicService.post_process = pdf_only_post_process
    _PATCHED = True


# Compatibility for existing smoke scripts and deployment notes.
patch_pdf_only_post_process = patch_validated_pdf_pipeline


def main() -> None:
    patch_validated_pdf_pipeline()
    route_library_logs_to_stderr()
    with contextlib.redirect_stdout(sys.stderr):
        service = JmcomicService(OPTION_PATH)
    ensure_unique_directory_rule(service.option)
    run_server("stdio", service, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
