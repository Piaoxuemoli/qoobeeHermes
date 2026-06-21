#!/usr/bin/env python3
"""Hard-link unambiguous legacy JMComic chapters into unique directories."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from jmcomic import DirRule
from jmcomic_ai.core import JmcomicService

from jmai_pdf_mcp import OPTION_PATH, UNIQUE_DIRECTORY_RULE


def migrate(album_id: str, manifest_path: Path, apply: bool) -> dict:
    service = JmcomicService(OPTION_PATH)
    album = service.get_client().get_album_detail(album_id)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chapters = {str(item["chapter_id"]): item for item in manifest["chapters"]}
    directory_counts = Counter(item["directory"] for item in manifest["chapters"])
    target_rule = DirRule(
        UNIQUE_DIRECTORY_RULE,
        base_dir=service.option.dir_rule.base_dir,
        normalize_zh=service.option.dir_rule.normalize_zh,
    )

    summary = {
        "album_id": str(album_id),
        "eligible_chapters": 0,
        "linked_images": 0,
        "repair_chapter_ids": [],
        "dry_run": not apply,
    }
    for photo in album:
        chapter_id = str(photo.photo_id)
        chapter = chapters.get(chapter_id)
        eligible = (
            chapter is not None
            and chapter["complete"]
            and directory_counts[chapter["directory"]] == 1
        )
        if not eligible:
            summary["repair_chapter_ids"].append(chapter_id)
            continue

        summary["eligible_chapters"] += 1
        destination_dir = Path(target_rule.decide_image_save_dir(album, photo))
        if apply:
            destination_dir.mkdir(parents=True, exist_ok=True)
        for source_value in chapter["image_paths"]:
            source = Path(source_value)
            destination = destination_dir / source.name
            if apply:
                if destination.exists():
                    if destination.stat().st_size != source.stat().st_size:
                        raise RuntimeError(f"destination conflicts with source: {destination}")
                else:
                    os.link(source, destination)
            summary["linked_images"] += 1
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("album_id")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.album_id, args.manifest, args.apply), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
