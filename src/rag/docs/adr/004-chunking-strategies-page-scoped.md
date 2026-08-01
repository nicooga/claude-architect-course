# ADR-004: Chunking strategies are page-scoped, with a seam-crossing exception for structure/semantic chunkers

## Status

Accepted (amended)

## Context

Three chunking strategies — size-based, structure-based, semantic — are
grouped in a `text_chunking/` package, one file per strategy, shaped like
`src/tool_usage/tools/` (one file per tool), not the `basic_concepts`
numbered-script pattern.

Page-level citation matters for this course: students need to open their
own copy of a book and verify a claim against a specific page. That means
every chunk needs to know which page(s) it came from.

The original decision made every chunker strictly page-scoped: each took
`pages: list[str]` and never merged text across a page boundary, so
`location = "page N"` was trivial for all three. On review, this is the
right call for size-based chunking but the wrong one for structure-based and
semantic chunking — both exist specifically to preserve real textual units
(paragraphs, semantically coherent spans), and forcing them to cut at a page
break defeats their purpose whenever a unit happens to straddle one.

Two alternatives to plain page-scoping were considered and rejected:

- **Flatten all pages into one continuous string before chunking**, with an
  offset → page index built in a separate pass. Rejected: this relocates
  the "which page is this character on" bookkeeping into a new
  preprocessing layer instead of removing it, since something still has to
  walk the pages to build that index.
- **Route OCR output back through a synthetic PDF and re-paginate it.**
  Rejected as part of
  [ADR-011](011-ingestion-unified-per-page-pipeline.md) — OCR already emits
  page-scoped text, so re-encoding it just to re-extract pages is pure
  overhead.

## Decision

- Chunkers take a `PageList`-like input (pages produced by
  [`ingestion/`](011-ingestion-unified-per-page-pipeline.md), never a
  flattened string).
- **Size-based chunking** stays strictly page-scoped: it never merges
  across a page boundary. This costs nothing extra — it already ignores
  paragraph/sentence structure and cuts every `chunk_size` characters
  regardless, so an additional cut at a page break adds no meaningful
  damage. What page-scoping buys here is citation: `location = "page N"` is
  trivial and always correct.
- **Structure-based and semantic chunking** may bridge a page seam when the
  unit they're built to preserve continues onto the next page. Both already
  have to decide "has this unit ended?" as their core job (paragraph
  boundaries, semantic similarity drops) — extending that decision to also
  examine the seam between page N and page N+1 is one more instance of a
  decision they already make locally, not a new subsystem or document-wide
  restructuring. When a chunk bridges a seam, `location` reports a range
  instead of a single page.

(See [`../../README.md`](../../README.md#staged-roadmap) for which build
stage each of these lands in — stage numbers aren't repeated here so this
record doesn't drift if the roadmap gets reordered, which is exactly what
happened once already: see [ADR-011](011-ingestion-unified-per-page-pipeline.md).)

## Consequences

- `Chunk.location` must support both a single-page form (`"page N"`) and a
  range form (`"pages N-M"`).
- Size-based chunking (already implemented) needs no change to its
  page-scoping behavior.
- Structure-based and semantic chunkers need a small, local extension at
  each page boundary (peek at the tail of page N and the head of page N+1)
  rather than any document-wide flattening or index reconstruction.
- A unit that straddles a page break in size-based chunking still gets cut
  there — acceptable for a teaching corpus, and consistent with that
  strategy's whole approach.
