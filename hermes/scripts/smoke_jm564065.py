#!/usr/bin/env python3
"""Smoke test: download JM564065 and generate PDF(s) via the PDF-only wrapper.

Run on the server where jmcomic-ai and img2pdf are installed:
    PYTHONPATH=/root/.hermes/scripts python3 smoke_jm564065.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# Add wrapper location to path if run standalone.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# Import wrapper first so it patches JmcomicService.post_process.
import jmai_pdf_mcp as jmai

from jmcomic_ai.core import JmcomicService

ALBUM_ID = os.environ.get("SMOKE_ALBUM_ID", "564065")
OPTION_PATH = os.environ.get("JM_OPTION_PATH", "/root/.jmcomic/option.yml")


def main() -> int:
    print(f"=== JMComic PDF smoke test for album {ALBUM_ID} ===")
    jmai.patch_pdf_only_post_process()
    service = JmcomicService(OPTION_PATH)

    print("[1/3] Downloading album...")
    start = time.time()
    download_result = asyncio.run(service.download_album(ALBUM_ID))
    print(f"Download result: {download_result}")
    print(f"Download took {time.time() - start:.1f}s")

    print("[2/3] Generating PDF via patched post_process...")
    start = time.time()
    result = service.post_process(
        ALBUM_ID,
        "img2pdf",
        params={
            "level": "album",
            "filename_rule": "Atitle",
            "dir_rule": {
                "rule": "Bd/{Atitle}.pdf",
                "base_dir": "/tmp/monitor_charts/jmcomic",
            },
        },
    )
    print(f"post_process result: {result}")
    print(f"PDF generation took {time.time() - start:.1f}s")

    if result.get("status") != "success":
        print("ERROR: PDF generation failed")
        return 1

    output_paths = result.get("output_paths", [result.get("output_path")])
    print("[3/3] Verifying generated files...")
    limit_bytes = jmai.PDF_MAX_SIZE_MB * 1024 * 1024
    total_size = 0
    all_ok = True
    for path in output_paths:
        p = Path(path)
        if not p.exists():
            print(f"ERROR: missing file {path}")
            all_ok = False
            continue
        size = p.stat().st_size
        total_size += size
        status = "OK" if size <= limit_bytes else "TOO LARGE"
        print(f"  {path}: {size / 1024 / 1024:.2f} MB ({status})")
        if size > limit_bytes:
            all_ok = False

    print(f"Total size: {total_size / 1024 / 1024:.2f} MB across {len(output_paths)} file(s)")
    print("=== PASS ===" if all_ok else "=== FAIL ===")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
