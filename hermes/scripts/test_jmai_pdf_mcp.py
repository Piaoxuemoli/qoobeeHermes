#!/usr/bin/env python3
"""Compatibility launcher for the validated JMComic pipeline test suite."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromNames(
        ["tests.test_jmcomic_pipeline", "tests.test_jmai_pdf_mcp"]
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
