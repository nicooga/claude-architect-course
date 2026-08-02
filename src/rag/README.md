# RAG

## Goal

Build a RAG pipeline unit — chunking, local embeddings, vector search, and
hybrid lexical+semantic retrieval — exposed to the agent as a `ToolPort`
tool, reusing `lib/repl` (`run_repl`) and `lib/anthropic_adapter`
(`ChatPort`/`ToolPort`, `AnthropicChatAdapter`) exactly as
[`tool_usage/`](../tool_usage) does. No changes are needed to `lib/`.

Two constraints shaped every design decision below:

1. **Embeddings must be generated locally with OSS** — no third-party
   embeddings API.
2. **Nothing in this unit should spend against the company-provided
   Anthropic API key unnecessarily.** RAG isn't part of the course's
   original budget/program, so anything that can run locally and free
   should — including OCR for the one source book that's scan-only.

This document is the design record for the unit: the architecture
decisions made and why, and a staged roadmap for building it. It's meant to
be readable on its own — a future session can pick up implementation
directly from here without needing the conversation that produced it.

**Status: Stage 1 (ingestion) complete; Stage 2 onward not yet started.**
`text_chunking/size_based.py`'s chunking algorithm was written before the
roadmap was reordered (see [ADR-011](docs/adr/011-ingestion-unified-per-page-pipeline.md));
it still needs a small signature update to accept the `PageList` Stage 1
now produces before Stage 2 can be marked done. See the roadmap below.

## Architecture Decision Records

Design decisions and their rationale live as individual records in
[`docs/adr/`](docs/adr/), not inline here, so this README doesn't drift out
of sync with them. See [`docs/architecture.md`](docs/architecture.md) for a
diagram of how the pieces described below fit together.

| ADR | Decision |
| --- | --- |
| [001](docs/adr/001-ports-and-adapters-applied-selectively.md) | Ports/adapters applied selectively, not uniformly |
| [002](docs/adr/002-local-embeddings-sentence-transformers.md) | Local embeddings via `sentence-transformers`, behind `EmbeddingPort` |
| [003](docs/adr/003-in-memory-vector-store.md) | In-memory numpy vector store, behind `VectorStorePort` |
| [004](docs/adr/004-chunking-strategies-page-scoped.md) | Chunking strategies are page-scoped, with a seam-crossing exception for structure/semantic chunkers |
| [005](docs/adr/005-one-index-per-strategy-persisted.md) | One index per strategy, persisted to disk |
| [006](docs/adr/006-local-ocr-doctr.md) | Local OCR via `python-doctr`, not Claude vision — behind `OCRPort` |
| [007](docs/adr/007-pypdf-for-text-layer-extraction.md) | `pypdf` for text-layer PDF extraction, not PyMuPDF |
| [008](docs/adr/008-bm25-from-scratch.md) | BM25 implemented from scratch, not `rank_bm25` |
| [009](docs/adr/009-hybrid-fusion-rrf.md) | Hybrid fusion via Reciprocal Rank Fusion (RRF) |
| [010](docs/adr/010-pin-python-version-before-ml-deps.md) | Environment risk: pin Python version before adding ML deps |
| [011](docs/adr/011-ingestion-unified-per-page-pipeline.md) | Ingestion as a single per-page pipeline, not parallel Scan/PDF branches |

## Staged roadmap

Each stage is independently buildable and verifiable before moving to the
next, mirroring how `tool_usage/README.md` sequences its five tools "in
order of increasing complexity." Ingestion comes first — every chunker
consumes the `PageList` it produces, so it can no longer be a mid-sequence
stage (see [ADR-011](docs/adr/011-ingestion-unified-per-page-pipeline.md)
for how this reordering happened).

- [x] **Stage 1 — Ingestion pipeline (text + OCR).** `uv add pypdf
      "python-doctr[torch]"` (checking
      [ADR-010](docs/adr/010-pin-python-version-before-ml-deps.md) first).
      `ports.py` (`OCRPort` —
      [ADR-001](docs/adr/001-ports-and-adapters-applied-selectively.md);
      later stages append `EmbeddingPort`/`VectorStorePort` to this same
      file), `ingestion/types.py` (`PageList`: `pages: list[str]`, `source:
      str`), `ingestion/documents.py` (walks a PDF page by page, `pypdf`
      text-layer extraction per page, falling back per page to an
      `ocr: OCRPort` constructor param per
      [ADR-006](docs/adr/006-local-ocr-doctr.md)/[ADR-011](docs/adr/011-ingestion-unified-per-page-pipeline.md)),
      `ingestion/ocr.py` (`DoctrOCRAdapter` implementing `OCRPort`,
      per-book disk cache under `library/ocr_cache/<book_stem>/`) +
      `build_index.py` (CLI: for now, scans `library/raw/*.pdf` and prints
      an ingestion summary per book — the chunk → embed → save →
      `manifest.json` steps get added incrementally as Stages 2 and 4
      land). Also add the `.gitignore` rule for `src/rag/library/` at this
      stage, once `library/raw/` first gets used (see "Local library"
      below).

- [ ] **Stage 2 — Size-based chunking.** `text_chunking/types.py` +
      `size_based.py`. No new dependencies. `Chunk` dataclass:
      `text`/`source`/`location`/`strategy`/`chunk_id`. Fixed-size sliding
      window per page with overlap (defaults to confirm: 1000 chars, 200
      overlap). **Note:** the chunking algorithm here was already written
      before the roadmap was reordered, against a `pages: list[str],
      source: str` signature; it needs a small update to accept the
      `PageList` Stage 1 produces before this stage can be marked done.

- [ ] **Stage 3 — Structure-based chunking.** `structure_based.py`. No new
      dependencies. Regex heading/paragraph heuristics, no parsing
      library. Compare boundaries against Stage 2 on a sample text. Per
      [ADR-004](docs/adr/004-chunking-strategies-page-scoped.md), may
      bridge a page seam when a paragraph continues onto the next page —
      report `location` as a range (`"pages N-M"`) when it does.

- [ ] **Stage 4 — Embeddings + vector store + semantic chunking.**
      `uv add sentence-transformers numpy` (check
      [ADR-010](docs/adr/010-pin-python-version-before-ml-deps.md) first).
      `ports.py` gains `EmbeddingPort` and `VectorStorePort`
      ([ADR-001](docs/adr/001-ports-and-adapters-applied-selectively.md)),
      `embedder.py` (`SentenceTransformerEmbedder`, implements
      `EmbeddingPort`), `vector_store.py` (`VectorStore`, hand-written
      cosine similarity, implements `VectorStorePort` per
      [ADR-003](docs/adr/003-in-memory-vector-store.md)), then
      `text_chunking/semantic.py` (regex sentence splitter +
      similarity-drop splitting, threshold default to confirm: 0.5; may
      also bridge a page seam per ADR-004, same as Stage 3).

- [ ] **Stage 5 — `search_documents` tool + REPL wiring (semantic-only).**
      `tools/search_documents.py` (`SearchDocumentsTool`, `ToolPort`
      shape, takes a `VectorStorePort` at construction — passed the
      in-memory `VectorStore` for now, per
      [ADR-003](docs/adr/003-in-memory-vector-store.md)),
      `tools/__init__.py`, `repl_smoke_test.py` (mirrors
      `src/tool_usage/repl_smoke_test.py`). Add a "Testing the REPL"
      section to this README once this stage lands.

- [ ] **Stage 6 — Lexical indexing (BM25) + hybrid fusion.** No new
      dependency (stdlib only). `lexical_index.py` (`BM25Index`, `k1=1.5`,
      `b=0.75` defaults), `retrieval.py` (`reciprocal_rank_fusion()`,
      `HybridRetriever`). Update `build_index.py` to also save
      `bm25.json`; update `search_documents.py`/`repl_smoke_test.py` to
      use `HybridRetriever` (itself built from a `VectorStorePort` +
      `BM25Index`) instead of the vector store directly. Compare hybrid
      vs. pure-semantic retrieval as the payoff of this stage.

## Conventions to follow

Mirror `src/tool_usage/` throughout: one file per tool/strategy, a barrel
`__init__.py`, a `repl_smoke_test.py` entry point. `ToolPort`
(`lib/anthropic_adapter/ports.py`) and `ChatPort`/`run_repl`
(`lib/repl/`) need no changes at any stage.

## Local library

Source books are the user's own material and must never be committed, and
neither should the derived index (it reproduces book text in chunked
form). Once Stage 1 lands, drop books into `src/rag/library/raw/` and
build the index locally:

```bash
uv run python -m src.rag.build_index
```

As of Stage 1, this scans `library/raw/*.pdf` and prints an ingestion
summary per book (page count, OCR fallback pages, characters extracted).
The `--strategy` flag joins this command once chunking lands (Stage 2+).

`src/rag/library/` is covered by a `.gitignore` rule — nothing under it is
meant to be tracked.

## Open defaults to confirm during implementation

None of these are settled requirements — they're starting points to
confirm or tune while building the corresponding stage:

- Embedding model: `all-MiniLM-L6-v2`.
- Chunk size/overlap: 1000 chars / 200 chars (size-based).
- Semantic chunking similarity threshold: 0.5.
- What counts as "usable text" from a pypdf page extraction before the
  ingestion pipeline treats a page as image-only and falls back to OCR:
  fewer than 20 non-whitespace characters (`PDFLoader`'s `min_text_chars`,
  tunable at construction).
- doctr's default model pair — lighter architectures are available if CPU
  OCR turns out too slow.
- BM25 `k1`/`b`: 1.5 / 0.75. RRF `k`: 60.
- Supported formats: PDF/.txt/.md only — no epub unless requested later.

## More docs

- [`docs/architecture.md`](docs/architecture.md) — Mermaid diagrams of the
  full pipeline and core types.
- [`docs/adr/`](docs/adr/) — one file per architecture decision record.
