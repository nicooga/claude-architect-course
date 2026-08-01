# ADR-001: Ports/adapters applied selectively, not uniformly

## Status

Accepted

## Context

This unit could reach for a `Protocol` everywhere the way `ChatPort`/`ToolPort`
do, or nowhere, since several pieces here have exactly one implementation.

## Decision

Introduce a port when *either* (a) there's a genuine, non-hypothetical
possibility of swapping the adapter, *or* (b) the implementation wraps
something expensive/external enough that tests will want a fake in place of
it. Reaching for the pattern everywhere regardless is death by a thousand
abstractions; skipping it everywhere loses the decoupling and clear intent it
buys where it's actually earned.

Applied per component:

| Component | Port? | Why |
| --- | --- | --- |
| Embeddings | **Yes** — `EmbeddingPort` | Loading a real `sentence-transformers` model is slow; isolated tests want a fake ([ADR-002](002-local-embeddings-sentence-transformers.md)). |
| OCR | **Yes** — `OCRPort` | Not hypothetical — this exact swap happened mid-design: Claude vision was the original plan until cost-avoidance on the company API key changed the decision to local `doctr` ([ADR-006](006-local-ocr-doctr.md)). A `ClaudeVisionOCRAdapter` remains a plausible future implementation without touching the ingestion loader. |
| Vector store | **Yes** — `VectorStorePort` | Also not hypothetical: there's a stated intent to try a production-grade vector store (e.g. chromadb, pgvector) here later. Case (a) applies even though the only adapter built in this unit is the hand-written in-memory `VectorStore` ([ADR-003](003-in-memory-vector-store.md)). |
| Lexical index (`BM25Index`) | No | Pure, fast, deterministic stdlib math, hand-written on purpose ([ADR-008](008-bm25-from-scratch.md)). Nothing expensive to fake, no stated intent to swap it. |
| Chunking strategies | No | Meant to run side by side for comparison (`build_index.py` branches explicitly across all three), not swapped transparently behind one call site — a different shape than "pick one adapter at composition time." |
| Fusion (RRF) | No | Pure function over already-computed rankings; nothing to fake, no second fusion strategy in scope. |
| PDF pagination (ingestion) | No | Single deterministic `pypdf` implementation, no stated intent to swap ([ADR-011](011-ingestion-unified-per-page-pipeline.md)). |

## Consequences

`src/rag/ports.py` holds the cross-cutting protocols (`EmbeddingPort`,
`OCRPort`, `VectorStorePort`), kept local to this unit rather than promoted
to `lib/` — the same "promote only once a second unit needs it" rule that
moved `MessageList` from `basic_concepts` to `lib/ai_generation` once
`prompt_engineering` needed it too.
