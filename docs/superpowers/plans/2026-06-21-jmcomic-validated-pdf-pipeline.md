# JMComic Validated PDF Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make JMComic downloads resumable and ensure PDF delivery is complete, chapter-ordered, size-safe, and never reported successful when pages are missing.

**Architecture:** Replace the wrapper's metadata-reconstruction post-process with a custom jmcomic `Feature` attached to the original `download_album` lifecycle. The feature builds a persistent manifest from the same album object, validates every chapter against disk, produces chapter-boundary PDF volumes, validates output page counts, and exposes structured `success`/`partial`/`error` results. A recovery post-process path reuses the same pipeline.

**Tech Stack:** Python 3.11+, jmcomic 2.7 Feature API, Pillow, img2pdf, pikepdf, standard-library unittest.

---

### Task 1: Manifest and recursive discovery

**Files:**
- Create: `hermes/scripts/jmcomic_pipeline.py`
- Create: `tests/test_jmcomic_pipeline.py`

- [ ] Write failing tests proving nested `.webp` files are recursively discovered, corrupt/empty files are reported, non-numeric chapter names are retained, and chapter order prefers API metadata.
- [ ] Run `python -m unittest tests.test_jmcomic_pipeline -v`; expect failures because the pipeline module does not exist.
- [ ] Implement `ChapterSpec`, `ChapterScan`, `AlbumManifest`, recursive image discovery, validation, and JSON manifest persistence.
- [ ] Run the tests; expect all Task 1 tests to pass.

### Task 2: Exact completeness semantics

**Files:**
- Modify: `hermes/scripts/jmcomic_pipeline.py`
- Modify: `tests/test_jmcomic_pipeline.py`

- [ ] Write failing tests proving one missing page yields `partial`, exact counts yield `complete`, and no percentage tolerance is accepted.
- [ ] Run the focused tests and confirm the expected assertion failures.
- [ ] Implement per-chapter and album-level exact completeness evaluation with explicit missing/corrupt counts.
- [ ] Run the full test file and confirm it passes.

### Task 3: Chapter-aware mobile PDF volumes

**Files:**
- Modify: `hermes/scripts/jmcomic_pipeline.py`
- Modify: `tests/test_jmcomic_pipeline.py`

- [ ] Write failing tests for chapter-boundary volume planning, 18 MB limits, deterministic names, and exact PDF page-count validation.
- [ ] Confirm the tests fail because volume planning and validation are absent.
- [ ] Implement streaming chapter conversion, size-aware volume flushes only at chapter boundaries, and pikepdf page validation.
- [ ] Run the complete tests and confirm they pass.

### Task 4: Downloader Feature and MCP integration

**Files:**
- Modify: `hermes/scripts/jmai_pdf_mcp.py`
- Modify: `tests/test_jmai_pdf_mcp.py`

- [ ] Write failing tests proving `ValidatedMobilePdfFeature` receives the original album/downloader, returns `partial` without output on incomplete scans, and `post_process(zip)` never emits ZIP.
- [ ] Confirm failures against the current wrapper.
- [ ] Patch `JmcomicService.download_album` to call jmcomic's public `download_album(..., extra=feature)` API and return manifest/output fields; make `post_process` reuse the pipeline.
- [ ] Run wrapper and pipeline tests.

### Task 5: Retry and progress policy

**Files:**
- Modify: `hermes/scripts/jmcomic_pipeline.py`
- Modify: `tests/test_jmcomic_pipeline.py`
- Modify: `hermes/SOUL.md`

- [ ] Write failing tests for retry decisions: continue on progress, stop after two no-progress snapshots, and cap attempts at five.
- [ ] Implement pure retry-decision helpers and persist attempt snapshots in the manifest.
- [ ] Update SOUL with 15/30/60 second backoff, chapter-level repair, exact checkpoints, and no ZIP fallback.
- [ ] Run all tests.

### Task 6: Documentation and deployment verification

**Files:**
- Modify: `docs/integration-handoff.md`
- Modify: `docs/manga-download-sop-review.md`

- [ ] Document Feature lifecycle integration, manifest schema, recursive formats, exact success semantics, 18 MB chapter-boundary volumes, and recovery behavior.
- [ ] Run `python -m compileall hermes/scripts` and `python -m unittest discover -s tests -v`.
- [ ] Deploy scripts/SOUL to `/root/.hermes`, restart gateway, and run `hermes mcp test jmcomic`.
- [ ] Validate against the existing large album: discovered page count equals manifest count, PDF page total equals valid image total, and every output is below the configured limit.
