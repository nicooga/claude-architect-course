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

**Status: implementation in progress — no stage is fully complete yet.**
`text_chunking/size_based.py`'s chunking algorithm was written before the
roadmap was reordered (see [ADR-011](docs/adr/011-ingestion-unified-per-page-pipeline.md));
it still needs a small signature update once Stage 1 lands. See the roadmap
below.

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

- [ ] **Stage 1 — Ingestion pipeline, text-only.** `uv add pypdf`.
      `ingestion/types.py` (`PageList`: `pages: list[str]`, `source: str`),
      `ingestion/documents.py` (walks a PDF page by page, `pypdf`
      text-layer extraction per page; takes an `ocr: OCRPort` constructor
      param per [ADR-006](docs/adr/006-local-ocr-doctr.md)/[ADR-011](docs/adr/011-ingestion-unified-per-page-pipeline.md)
      even though no adapter exists yet — an image-only page hitting the
      OCR branch at this stage should fail loudly, not silently drop
      content) + `build_index.py` (CLI: load → chunk → embed →
      `VectorStore.save()` → `manifest.json`). Also add the `.gitignore`
      rule for `src/rag/library/` at this stage, once `library/raw/` first
      gets used (see "Local library" below).

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
      `ports.py` (`EmbeddingPort` and `VectorStorePort` —
      [ADR-001](docs/adr/001-ports-and-adapters-applied-selectively.md)),
      `embedder.py` (`SentenceTransformerEmbedder`, implements
      `EmbeddingPort`), `vector_store.py` (`VectorStore`, hand-written
      cosine similarity, implements `VectorStorePort` per
      [ADR-003](docs/adr/003-in-memory-vector-store.md)), then
      `text_chunking/semantic.py` (regex sentence splitter +
      similarity-drop splitting, threshold default to confirm: 0.5; may
      also bridge a page seam per ADR-004, same as Stage 3).

- [ ] **Stage 5 — Local OCR for the scanned book.**
      `uv add "python-doctr[torch]"`. Add `OCRPort` to `ports.py`, then
      `ingestion/ocr.py` (`DoctrOCRAdapter` implementing `OCRPort`,
      per-page disk cache under `library/ocr_cache/<book_stem>/`). Wire
      `DoctrOCRAdapter()` into the `ingestion/documents.py` loader's
      construction in `build_index.py` — the loader itself needs no
      changes, per [ADR-006](docs/adr/006-local-ocr-doctr.md)/[ADR-011](docs/adr/011-ingestion-unified-per-page-pipeline.md);
      it was already calling the OCR branch, just without a real adapter
      behind it until now.

- [ ] **Stage 6 — `search_documents` tool + REPL wiring (semantic-only).**
      `tools/search_documents.py` (`SearchDocumentsTool`, `ToolPort`
      shape, takes a `VectorStorePort` at construction — passed the
      in-memory `VectorStore` for now, per
      [ADR-003](docs/adr/003-in-memory-vector-store.md)),
      `tools/__init__.py`, `repl_smoke_test.py` (mirrors
      `src/tool_usage/repl_smoke_test.py`). Add a "Testing the REPL"
      section to this README once this stage lands.

- [ ] **Stage 7 — Lexical indexing (BM25) + hybrid fusion.** No new
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
uv run python -m src.rag.build_index --strategy size
```

`src/rag/library/` is (or will be, as of Stage 1) covered by a
`.gitignore` rule — nothing under it is meant to be tracked.

## Open defaults to confirm during implementation

None of these are settled requirements — they're starting points to
confirm or tune while building the corresponding stage:

- Embedding model: `all-MiniLM-L6-v2`.
- Chunk size/overlap: 1000 chars / 200 chars (size-based).
- Semantic chunking similarity threshold: 0.5.
- What counts as "usable text" from a pypdf page extraction (e.g. a
  minimum non-whitespace character count) before the ingestion pipeline
  treats a page as image-only and falls back to OCR.
- doctr's default model pair — lighter architectures are available if CPU
  OCR turns out too slow.
- BM25 `k1`/`b`: 1.5 / 0.75. RRF `k`: 60.
- Supported formats: PDF/.txt/.md only — no epub unless requested later.

## More docs

- [`docs/architecture.md`](docs/architecture.md) — Mermaid diagrams of the
  full pipeline and core types.
- [`docs/adr/`](docs/adr/) — one file per architecture decision record.
