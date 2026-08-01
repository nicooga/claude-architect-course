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

**Status: design complete, implementation not started.** See the roadmap
below.

## Architecture Decision Records

### ADR-001 — Ports/adapters applied selectively, not uniformly

**Context:** this unit could reach for a `Protocol` everywhere the way
`ChatPort`/`ToolPort` do, or nowhere, since several pieces here have
exactly one implementation.

**Decision:** introduce a port when *either* (a) there's a genuine,
non-hypothetical possibility of swapping the adapter, *or* (b) the
implementation wraps something expensive/external enough that tests will
want a fake in place of it. Reaching for the pattern everywhere regardless
is death by a thousand abstractions; skipping it everywhere loses the
decoupling and clear intent it buys where it's actually earned. Applied
per component:

| Component | Port? | Why |
| --- | --- | --- |
| Embeddings | **Yes** — `EmbeddingPort` | Loading a real `sentence-transformers` model is slow; isolated tests want a fake (ADR-002). |
| OCR | **Yes** — `OCRPort` | Not hypothetical — this exact swap happened mid-design: Claude vision was the original plan until cost-avoidance on the company API key changed the decision to local `doctr` (ADR-006). A `ClaudeVisionOCRAdapter` remains a plausible future implementation without touching `documents.py`. |
| Vector store | **Yes** — `VectorStorePort` | Also not hypothetical: there's a stated intent to try a production-grade vector store (e.g. chromadb, pgvector) here later. Case (a) applies even though the only adapter built in this unit is the hand-written in-memory `VectorStore` (ADR-003). |
| Lexical index (`BM25Index`) | No | Pure, fast, deterministic stdlib math, hand-written on purpose (ADR-008). Nothing expensive to fake, no stated intent to swap it. |
| Chunking strategies | No | Meant to run side by side for comparison (`build_index.py` branches explicitly across all three), not swapped transparently behind one call site — a different shape than "pick one adapter at composition time." |
| Fusion (RRF) | No | Pure function over already-computed rankings; nothing to fake, no second fusion strategy in scope. |

**Consequence:** `src/rag/ports.py` holds three protocols
(`EmbeddingPort`, `OCRPort`, `VectorStorePort`), kept local to this unit
rather than promoted to `lib/` — the same "promote only once a second unit
needs it" rule that moved `MessageList` from `basic_concepts` to
`lib/ai_generation` once `prompt_engineering` needed it too.

### ADR-002 — Local embeddings via `sentence-transformers`, behind `EmbeddingPort`

**Decision:** `sentence-transformers`, model `all-MiniLM-L6-v2` (small,
fast, standard baseline — a recommendation to confirm, not fixed).
Rejected `fastembed`. `SentenceTransformerEmbedder` implements
`EmbeddingPort` structurally — no inheritance, same duck-typing style as
every `ToolPort` implementation in `tool_usage/`.

**Consequences:** pulls in `torch`, a heavy dependency, but it's the
standard/well-documented choice; the port means a test-only fake embedder
can stand in without loading torch at all.

### ADR-003 — In-memory numpy vector store, hand-written cosine similarity, behind `VectorStorePort`

**Decision:** the first (and for now only) adapter is a hand-written
in-memory `VectorStore` doing cosine similarity over a numpy array —
matches this course's "build the mechanism yourself" style, and stays the
default for the teaching corpus. Per ADR-001, it sits behind
`VectorStorePort` (`search(query_embedding, top_k) -> list[SearchResult]`,
`save(index_dir)`, `load(index_dir)`) rather than being called directly,
because there's a genuine, stated intent to build a second adapter later
against a production-grade vector store (e.g. chromadb, pgvector) — the
same non-hypothetical-swap justification as `OCRPort` (ADR-006), just not
yet exercised.

**Consequence:** no persistence beyond what we build ourselves for the
in-memory adapter (see ADR-005); a future production-store adapter may
persist differently (e.g. delegate to the store's own storage) and would
implement `save`/`load` however fits that backend, or may not need them at
all if the backend is already durable — `VectorStorePort` only commits
callers to `search`.

### ADR-004 — Three chunking strategies, grouped in a `text_chunking/` package

**Decision:** size-based, structure-based, and semantic chunking as three
separate implementations — one file per strategy, shaped like
`src/tool_usage/tools/` (one file per tool), not the `basic_concepts`
numbered-script pattern.

Chunking is **page-scoped**: each chunker takes `pages: list[str]` and
never merges text across a page boundary, so citation (`location = "page
N"`) is trivial for all three.

**Consequence:** a unit that straddles a page break gets cut there —
acceptable for a teaching corpus.

### ADR-005 — One index per strategy, persisted to disk

**Decision:** `library/index/<strategy>/{embeddings.npy, bm25.json,
chunks.json, manifest.json}`.

**Rationale:** re-embedding a whole book on every REPL restart would be
wasteful; persisting per-strategy also lets the same question be re-asked
after rebuilding under a different strategy, to compare retrieval quality
directly.

### ADR-006 — Local OCR via `python-doctr`, not Claude vision — behind `OCRPort`

**Context:** the source books include one scan-only PDF. The original plan
was Claude vision transcription, but that would spend against a company
API key for something outside the course's budgeted scope.

**Decision:** `python-doctr[torch]` — reuses the `torch` dependency
already required by `sentence-transformers` (no new ML framework, just
extra model weights), runs fully offline, zero API cost.
`DoctrOCRAdapter` implements `OCRPort`
(`transcribe(pdf_path, cache_dir, max_pages) -> list[str]`);
`documents.py`'s `DocumentLoader` takes an `ocr: OCRPort` at construction
rather than importing a concrete OCR backend directly. Per ADR-001, this
is the one place in the unit where the port has already proven its worth:
swapping the adapter (e.g. back to a `ClaudeVisionOCRAdapter`, or to
Tesseract) is a one-line change in `build_index.py`'s wiring, with zero
changes to `documents.py`.

**Consequence:** CPU inference on a full book may be slow (minutes), but
it's a one-time, cached, free preprocessing step.

### ADR-007 — `pypdf` for text-layer PDF extraction, not PyMuPDF

**Decision:** `pypdf` — pure Python, permissively licensed — instead of
PyMuPDF, which is AGPL-licensed. `doctr` handles its own PDF→image
rasterization internally for the scanned-page case, so no separate
rasterization library is needed either.

### ADR-008 — BM25 implemented from scratch, not `rank_bm25`

**Decision:** hand-write BM25 (TF, IDF, length normalization) rather than
depend on `rank_bm25`. Consistent with the hand-written cosine similarity
(ADR-003); the formula is small enough to be a good teaching artifact in
its own right.

### ADR-009 — Hybrid fusion via Reciprocal Rank Fusion (RRF), not weighted score combination

**Decision:** combine BM25 and embedding search results by rank
(`1/(k+rank)`, standard `k=60`), not by raw score.

**Rationale:** BM25 scores are unbounded/corpus-dependent and cosine
similarity is bounded to `[-1, 1]` — combining raw scores needs fragile
per-query normalization; RRF sidesteps the scale mismatch entirely.

### ADR-010 — Environment risk: pin Python version before adding ML deps

**Context:** the project's `.venv` is currently on Python 3.14.1 with no
`.python-version` pin (`uv` picked the newest version satisfying
`requires-python = ">=3.12"`). `sentence-transformers` (torch) and
`python-doctr` (torch + opencv) are heavy ML dependencies whose wheels may
lag behind brand-new CPython releases.

**Decision:** when Stage 3 adds `sentence-transformers`, verify `uv add`
resolves cleanly first. If it doesn't, run `uv python pin 3.12` (adds a
`.python-version` file, still satisfies `>=3.12`) and `uv sync`.

## Staged roadmap

Each stage is independently buildable and verifiable before moving to the
next, mirroring how `tool_usage/README.md` sequences its five tools "in
order of increasing complexity."

- [ ] **Stage 1 — Size-based chunking.** `text_chunking/types.py` +
      `size_based.py`. No new dependencies. `Chunk` dataclass:
      `text`/`source`/`location`/`strategy`/`chunk_id`. Fixed-size sliding
      window per page with overlap (defaults to confirm: 1000 chars, 200
      overlap).

- [ ] **Stage 2 — Structure-based chunking.** `structure_based.py`. No new
      dependencies. Regex heading/paragraph heuristics, no parsing
      library. Compare boundaries against Stage 1 on a sample text.

- [ ] **Stage 3 — Embeddings + vector store + semantic chunking.**
      `uv add sentence-transformers numpy` (check ADR-010 first).
      `ports.py` (`EmbeddingPort` and `VectorStorePort` — ADR-001),
      `embedder.py` (`SentenceTransformerEmbedder`, implements
      `EmbeddingPort`), `vector_store.py` (`VectorStore`, hand-written
      cosine similarity, implements `VectorStorePort` per ADR-003), then
      `text_chunking/semantic.py` (regex sentence splitter +
      similarity-drop splitting, threshold default to confirm: 0.5).

- [ ] **Stage 4 — Document ingestion, text-only.** `uv add pypdf`.
      `documents.py` (`Document`, `DocumentLoader.load_documents()`, pypdf
      text-layer extraction + scanned-page detection — `DocumentLoader`
      already takes an `ocr: OCRPort` constructor param per ADR-006, even
      though this stage has no OCR adapter to pass yet) + `build_index.py`
      (CLI: load → chunk → embed → `VectorStore.save()` → `manifest.json`).
      Also add the `.gitignore` rule for `src/rag/library/` at this stage,
      once `library/raw/` first gets used (see "Local library" below).

- [ ] **Stage 5 — Local OCR for the scanned book.**
      `uv add "python-doctr[torch]"`. Add `OCRPort` to `ports.py`, then
      `ocr.py` (`DoctrOCRAdapter` implementing `OCRPort`, per-page disk
      cache under `library/ocr_cache/<book_stem>/`). Wire
      `DoctrOCRAdapter()` into `DocumentLoader`'s construction in
      `build_index.py` — `documents.py` itself needs no changes, per
      ADR-006.

- [ ] **Stage 6 — `search_documents` tool + REPL wiring (semantic-only).**
      `tools/search_documents.py` (`SearchDocumentsTool`, `ToolPort`
      shape, takes a `VectorStorePort` at construction — passed the
      in-memory `VectorStore` for now, per ADR-003), `tools/__init__.py`,
      `repl_smoke_test.py` (mirrors
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
form). Once Stage 4 lands, drop books into `src/rag/library/raw/` and
build the index locally:

```bash
uv run python -m src.rag.build_index --strategy size
```

`src/rag/library/` is (or will be, as of Stage 4) covered by a
`.gitignore` rule — nothing under it is meant to be tracked.

## Open defaults to confirm during implementation

None of these are settled requirements — they're starting points to
confirm or tune while building the corresponding stage:

- Embedding model: `all-MiniLM-L6-v2`.
- Chunk size/overlap: 1000 chars / 200 chars (size-based).
- Semantic chunking similarity threshold: 0.5.
- doctr's default model pair — lighter architectures are available if CPU
  OCR turns out too slow.
- BM25 `k1`/`b`: 1.5 / 0.75. RRF `k`: 60.
- Supported formats: PDF/.txt/.md only — no epub unless requested later.
