# ADR-011: Ingestion as a single per-page pipeline, not parallel Scan/PDF branches

## Status

Accepted

## Context

A PDF page is not guaranteed to be fully digitized — a given page can
contain plain text, an image, or a mixture of both. That means a source
document can't be cleanly classified as "text PDF" vs. "scan" at the
whole-file level; classification has to happen per page.

An earlier sketch modeled ingestion as two parallel branches converging on
a page list: `Scan → OCR → PDF → PDFPaginator → PageList` alongside
`PDF → PDFPaginator → PageList`. This was rejected on review:

- `OCRPort.transcribe()` ([ADR-006](006-local-ocr-doctr.md)) already returns
  `list[str]` — page-scoped text. Routing that back through a synthetic
  "PDF" and a second paginator means manufacturing a fake PDF with an
  injected text layer just to re-extract what OCR already produced in
  paginated form.
- A whole-document Scan/PDF fork contradicted the per-page granularity the
  design already needed ("pypdf text-layer extraction + scanned-page
  detection"), which is a per-page decision, not a per-document one.

This also changed the build sequence: every chunking strategy
([ADR-004](004-chunking-strategies-page-scoped.md)) consumes the `PageList`
this pipeline produces, so ingestion has to be built *before* any chunker,
not after — it can no longer be a mid-roadmap stage.

## Decision

`src/rag/ingestion/` (new subpackage, sibling to `text_chunking/`, same
one-file-per-concern shape) implements a single pipeline that walks a PDF
page by page:

1. Try `pypdf` text-layer extraction for the page.
2. If the page yields no usable text (image-only), fall back to
   `OCRPort.transcribe` ([ADR-006](006-local-ocr-doctr.md)) for just that
   page.
3. Append the resulting text to the running page list.

There is no document-level Scan/PDF fork — a fully-scanned book is simply
the case where every page takes the OCR branch. Output is a `PageList`
(`pages: list[str]`, `source: str`, with room for provenance metadata such
as whether OCR was used), replacing the separate `pages`/`source`
parameters chunkers took previously
([ADR-004](004-chunking-strategies-page-scoped.md)).

The pypdf-based per-page extraction step is not a port — per
[ADR-001](001-ports-and-adapters-applied-selectively.md)'s test, there's no
stated intent to swap it and it wraps nothing expensive. OCR remains behind
`OCRPort` exactly as ADR-006 already decided; ingestion is simply its
caller, invoked per page instead of per document.

`DoctrOCRAdapter` ([ADR-006](006-local-ocr-doctr.md)) is built alongside
the rest of ingestion and wired into the loader's construction
(`ocr: OCRPort` constructor param) in this same stage — see
[`../../README.md`](../../README.md#staged-roadmap). The loader depends
only on `OCRPort`, not the concrete adapter, so a different implementation
(e.g. a future `ClaudeVisionOCRAdapter`) stays a one-line change in
`build_index.py`'s wiring, with zero changes to the loader itself.

## Consequences

- Mixed-content PDFs (mostly native text with a stray scanned page) are
  handled for free, with no special-casing beyond the per-page loop.
- The loader's `ocr: OCRPort` constructor param keeps the concrete OCR
  backend swappable without touching the loader itself, matching
  ADR-006's original promise.
- Chunker signatures (`chunk_size_based`, and structure/semantic to follow)
  take a `PageList` instead of raw `pages: list[str]` + `source: str`.
  **`text_chunking/size_based.py`'s current signature predates this
  decision** and needs a follow-up update — not done as part of this doc
  change, tracked as a note on its roadmap entry.
- The roadmap had to be reordered: ingestion moved from a mid-sequence
  stage to the first stage, since it produces the input type every other
  stage now depends on.
