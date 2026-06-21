"""Validated filesystem manifest and delivery planning for JMComic albums."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
}


@dataclass(frozen=True)
class ChapterSpec:
    chapter_id: str
    index: int
    title: str
    expected_images: int
    directory: Path
    expected_filenames: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "directory", Path(self.directory))


@dataclass
class ChapterScan:
    spec: ChapterSpec
    image_paths: list[Path] = field(default_factory=list)
    empty_paths: list[Path] = field(default_factory=list)
    corrupt_paths: list[Path] = field(default_factory=list)
    unexpected_paths: list[Path] = field(default_factory=list)
    ambiguous_directory: bool = False

    @property
    def missing_images(self) -> int:
        return max(self.spec.expected_images - len(self.image_paths), 0)

    @property
    def is_complete(self) -> bool:
        return (
            len(self.image_paths) == self.spec.expected_images
            and not self.empty_paths
            and not self.corrupt_paths
            and not self.unexpected_paths
            and not self.ambiguous_directory
        )


@dataclass
class AlbumManifest:
    album_id: str
    title: str
    chapters: list[ChapterScan]

    @property
    def expected_images(self) -> int:
        return sum(chapter.spec.expected_images for chapter in self.chapters)

    @property
    def valid_images(self) -> int:
        return sum(len(chapter.image_paths) for chapter in self.chapters)

    @property
    def empty_images(self) -> int:
        return sum(len(chapter.empty_paths) for chapter in self.chapters)

    @property
    def corrupt_images(self) -> int:
        return sum(len(chapter.corrupt_paths) for chapter in self.chapters)

    @property
    def unexpected_images(self) -> int:
        return sum(len(chapter.unexpected_paths) for chapter in self.chapters)

    @property
    def missing_images(self) -> int:
        return sum(chapter.missing_images for chapter in self.chapters)

    @property
    def completed_chapters(self) -> int:
        return sum(chapter.is_complete for chapter in self.chapters)

    @property
    def status(self) -> str:
        if self.chapters and self.completed_chapters == len(self.chapters):
            return "complete"
        return "partial"

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "album_id": self.album_id,
            "title": self.title,
            "status": self.status,
            "expected_images": self.expected_images,
            "valid_images": self.valid_images,
            "missing_images": self.missing_images,
            "empty_images": self.empty_images,
            "corrupt_images": self.corrupt_images,
            "unexpected_images": self.unexpected_images,
            "completed_chapters": self.completed_chapters,
            "chapters": [
                {
                    "chapter_id": chapter.spec.chapter_id,
                    "index": chapter.spec.index,
                    "title": chapter.spec.title,
                    "directory": str(chapter.spec.directory),
                    "expected_images": chapter.spec.expected_images,
                    "expected_filenames": list(chapter.spec.expected_filenames),
                    "valid_images": len(chapter.image_paths),
                    "missing_images": chapter.missing_images,
                    "empty_images": len(chapter.empty_paths),
                    "corrupt_images": len(chapter.corrupt_paths),
                    "unexpected_images": len(chapter.unexpected_paths),
                    "ambiguous_directory": chapter.ambiguous_directory,
                    "complete": chapter.is_complete,
                    "image_paths": [str(path) for path in chapter.image_paths],
                    "empty_paths": [str(path) for path in chapter.empty_paths],
                    "corrupt_paths": [str(path) for path in chapter.corrupt_paths],
                    "unexpected_paths": [str(path) for path in chapter.unexpected_paths],
                }
                for chapter in self.chapters
            ],
        }

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)


@dataclass(frozen=True)
class ChapterPayload:
    chapter_id: str
    index: int
    title: str
    image_paths: tuple[str, ...]
    total_bytes: int
    page_count: int


@dataclass(frozen=True)
class VolumePlan:
    chapters: tuple[ChapterPayload, ...]
    total_bytes: int
    page_count: int
    output_name: str


@dataclass(frozen=True)
class RetrySnapshot:
    attempt: int
    valid_images: int
    completed_chapters: int


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    delay_seconds: int
    reason: str


def _natural_key(path: Path) -> tuple:
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", path.as_posix())
    )


def _scan_chapter(
    spec: ChapterSpec,
    excluded_dirs: Sequence[Path] = (),
    ambiguous_directory: bool = False,
) -> ChapterScan:
    scan = ChapterScan(spec=spec, ambiguous_directory=ambiguous_directory)
    if not spec.directory.is_dir():
        return scan

    candidates = sorted(
        (
            path
            for path in spec.directory.rglob("*")
            if path.is_file()
            and path.suffix.casefold() in IMAGE_EXTENSIONS
            and not any(path.resolve().is_relative_to(directory) for directory in excluded_dirs)
        ),
        key=lambda path: _natural_key(path.relative_to(spec.directory)),
    )
    expected_names = set(spec.expected_filenames)
    for path in candidates:
        if expected_names and path.name not in expected_names:
            scan.unexpected_paths.append(path)
            continue
        if path.stat().st_size == 0:
            scan.empty_paths.append(path)
            continue
        try:
            with Image.open(path) as image:
                image.verify()
        except (OSError, SyntaxError, ValueError):
            scan.corrupt_paths.append(path)
            continue
        scan.image_paths.append(path)
    return scan


def build_manifest(
    album_id: str,
    title: str,
    chapter_specs: Iterable[ChapterSpec],
    manifest_path: Path | None = None,
) -> AlbumManifest:
    """Scan canonical chapter directories in API order and optionally persist JSON."""
    specs = list(chapter_specs)
    resolved_dirs = [spec.directory.resolve() for spec in specs]
    directory_counts = {
        directory: resolved_dirs.count(directory) for directory in set(resolved_dirs)
    }
    scans = []
    for index, spec in enumerate(specs):
        current = resolved_dirs[index]
        excluded = [
            directory
            for other_index, directory in enumerate(resolved_dirs)
            if other_index != index
            and directory != current
            and directory.is_relative_to(current)
        ]
        scans.append(
            _scan_chapter(
                spec,
                excluded,
                ambiguous_directory=directory_counts[current] > 1,
            )
        )

    manifest = AlbumManifest(
        album_id=str(album_id),
        title=title,
        chapters=scans,
    )
    if manifest_path is not None:
        manifest.save(manifest_path)
    return manifest


def load_chapter_specs(manifest_path: Path) -> list[ChapterSpec]:
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    specs: list[ChapterSpec] = []
    for chapter in data["chapters"]:
        expected_filenames = chapter.get("expected_filenames")
        if expected_filenames is None and chapter.get("complete"):
            expected_filenames = [Path(path).name for path in chapter["image_paths"]]
        specs.append(
            ChapterSpec(
                chapter_id=str(chapter["chapter_id"]),
                index=int(chapter["index"]),
                title=str(chapter["title"]),
                expected_images=int(chapter["expected_images"]),
                directory=Path(chapter["directory"]),
                expected_filenames=tuple(expected_filenames or ()),
            )
        )
    return specs


def _volume_name(title: str, chapters: Sequence[ChapterPayload]) -> str:
    first = chapters[0].index
    last = chapters[-1].index
    span = f"{first:03d}" if first == last else f"{first:03d}-{last:03d}"
    return f"{title}_第{span}話.pdf"


def plan_volumes(
    title: str,
    chapters: Sequence[ChapterPayload],
    limit_bytes: int,
) -> list[VolumePlan]:
    """Pack complete chapters without splitting a chapter across volume plans."""
    if limit_bytes <= 0:
        raise ValueError("limit_bytes must be positive")

    volumes: list[VolumePlan] = []
    pending: list[ChapterPayload] = []
    pending_bytes = 0

    def flush() -> None:
        nonlocal pending, pending_bytes
        if not pending:
            return
        volumes.append(
            VolumePlan(
                chapters=tuple(pending),
                total_bytes=pending_bytes,
                page_count=sum(chapter.page_count for chapter in pending),
                output_name=_volume_name(title, pending),
            )
        )
        pending = []
        pending_bytes = 0

    for chapter in chapters:
        if chapter.total_bytes > limit_bytes:
            raise ValueError(
                f"chapter {chapter.chapter_id} exceeds the volume limit: "
                f"{chapter.total_bytes} > {limit_bytes}"
            )
        if pending and pending_bytes + chapter.total_bytes > limit_bytes:
            flush()
        pending.append(chapter)
        pending_bytes += chapter.total_bytes
    flush()
    return volumes


def write_pdf(
    image_paths: Sequence[str | Path], output_path: Path, dpi: int = 150
) -> None:
    """Write images to PDF without holding the resulting PDF bytes in memory."""
    import img2pdf

    if not image_paths:
        raise ValueError("cannot create a PDF without images")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with temporary.open("wb") as output:
            img2pdf.convert(
                *(str(path) for path in image_paths),
                outputstream=output,
                layout_fun=img2pdf.get_fixed_dpi_layout_fun((dpi, dpi)),
            )
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_pdf_pages(output_path: Path, expected_pages: int) -> int:
    """Raise unless a PDF exists, is readable, and has the exact page count."""
    from pypdf import PdfReader

    output_path = Path(output_path)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"PDF output is missing or empty: {output_path}")
    try:
        actual_pages = len(PdfReader(str(output_path)).pages)
    except Exception as exc:
        raise RuntimeError(f"PDF output is unreadable: {output_path}: {exc}") from exc
    if actual_pages != expected_pages:
        raise RuntimeError(
            f"PDF page count mismatch for {output_path}: "
            f"expected {expected_pages}, got {actual_pages}"
        )
    return actual_pages


def decide_retry(snapshots: Sequence[RetrySnapshot]) -> RetryDecision:
    if not snapshots:
        return RetryDecision(True, 15, "initial-attempt")
    if snapshots[-1].attempt >= 5:
        return RetryDecision(False, 0, "max-attempts")
    if len(snapshots) >= 3:
        recent = snapshots[-3:]
        states = {(item.valid_images, item.completed_chapters) for item in recent}
        if len(states) == 1:
            return RetryDecision(False, 0, "no-progress")
    delay = (15, 30, 60)[min(snapshots[-1].attempt - 1, 2)]
    return RetryDecision(True, delay, "progress-or-repairable")
