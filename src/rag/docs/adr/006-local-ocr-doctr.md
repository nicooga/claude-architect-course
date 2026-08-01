# ADR-006: Local OCR via python-doctr, not Claude vision — behind OCRPort

## Status

Accepted

## Context

The source books include one scan-only PDF. The original plan was Claude
vision transcription, but that would spend against a company API key for
something outside the course's budgeted scope.

## Decision

`python-doctr[torch]` — reuses the `torch` dependency already required by
`sentence-transformers` (no new ML framework, just extra model weights),
runs fully offline, zero API cost. `DoctrOCRAdapter` implements `OCRPort`
(`transcribe(pdf_path, cache_dir, max_pages) -> list[str]`); the ingestion
loader ([ADR-011](011-ingestion-unified-per-page-pipeline.md)) takes an
`ocr: OCRPort` at construction rather than importing a concrete OCR backend
directly. Per [ADR-001](001-ports-and-adapters-applied-selectively.md), this
is the one place in the unit where the port had already proven its worth
before it was even built: swapping the adapter (e.g. back to a
`ClaudeVisionOCRAdapter`, or to Tesseract) is a one-line change in
`build_index.py`'s wiring, with zero changes to the loader itself.

## Consequences

CPU inference on a full book may be slow (minutes), but it's a one-time,
cached, free preprocessing step.
