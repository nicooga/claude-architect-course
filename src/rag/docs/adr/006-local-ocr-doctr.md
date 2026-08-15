# ADR-006: Local OCR via python-doctr, not Claude vision — behind OCRPort

## Status

Accepted

## Context

The source books include one scan-only PDF. The original plan was Claude
vision transcription, but that would spend against a company API key for
something outside the course's budgeted scope.

## Decision

`python-doctr[torch]` — runs fully offline, zero API cost; the same
`torch` install is reused once the embeddings stage adds
`sentence-transformers`, so this is the only new ML framework the unit
brings in. `DoctrOCRAdapter` implements `OCRPort`
(`transcribe(pdf_path, cache_dir, page_indices) -> dict[int, str]`); the
ingestion loader ([ADR-011](011-ingestion-unified-per-page-pipeline.md))
takes an `ocr: OCRPort` at construction rather than importing a concrete
OCR backend directly. Per
[ADR-001](001-ports-and-adapters-applied-selectively.md), this is the one
place in the unit where the port had already proven its worth before it
was even built: swapping the adapter (e.g. back to a
`ClaudeVisionOCRAdapter`, or to Tesseract) is a one-line change in
`build_index.py`'s wiring, with zero changes to the loader itself.

`transcribe()` takes the specific pages that need OCR, not a page count
from 0 — a mixed document may only need it for a handful of image-only
pages out of hundreds, and the model is the expensive part, so nothing
gets OCR'd unless it's actually missing a text layer. Those requested
pages are still processed in small batches (8) rather than one call each,
since doctr's model runs far more efficiently batched than invoked
per-page — the batching just applies to what was asked for, not the
whole document. The ingestion loader calls it lazily, once per `load()`,
only the first time a page is found to need OCR, passing every image-only
page index it found in one call; it memoizes the returned mapping for the
rest of that call and looks up each image-only page in it as the
per-page loop ([ADR-011](011-ingestion-unified-per-page-pipeline.md))
reaches it. Each batch is written to disk under
`library/ocr_cache/<book_stem>/` as soon as it completes, so an
interrupted run resumes from the last cached page instead of starting
over, and a run after full success skips the model entirely.

A page image wider than it is tall is a double-page spread (a book scanned
two physical pages at a time, not one page per image) — `DoctrOCRAdapter`
splits it into left/right halves and OCRs each separately, joined with a
blank line, rather than feeding doctr the full spread. doctr's own reading
order doesn't reliably separate a wide spread's two halves: observed
interleaving their lines mid-sentence (a fragment from the left half
directly followed by an unrelated one from the right half, no punctuation
between them for downstream sentence splitting to catch). Splitting first
sidesteps that instead of trying to fix reading order after the fact. This
check is purely `width > height` on the page image, no per-book metadata —
confirmed against both books in this project: all 218 pages of the
scan-only book are uniformly landscape (a double-page-spread scan), the
other book's pages are all portrait, so the check needs no book-level
override to avoid misfiring on it.

## Consequences

CPU inference on a full book may be slow (minutes to just over an hour for
a ~200-page scan-only book at this batch size), but it's a one-time,
cached, free preprocessing step. Splitting a spread doubles the images fed
to doctr per requested page, which is part of that cost.
