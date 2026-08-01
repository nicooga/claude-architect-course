# ADR-003: In-memory numpy vector store, hand-written cosine similarity, behind VectorStorePort

## Status

Accepted

## Context

A vector store is needed to search embedded chunks. This course favors
building the mechanism yourself over reaching for a library, and there's a
stated intent to try a production-grade vector store (chromadb, pgvector)
later.

## Decision

The first (and for now only) adapter is a hand-written in-memory
`VectorStore` doing cosine similarity over a numpy array — matches this
course's "build the mechanism yourself" style, and stays the default for the
teaching corpus. Per [ADR-001](001-ports-and-adapters-applied-selectively.md),
it sits behind `VectorStorePort` (`search(query_embedding, top_k) ->
list[SearchResult]`, `save(index_dir)`, `load(index_dir)`) rather than being
called directly, because there's a genuine, stated intent to build a second
adapter later against a production-grade vector store — the same
non-hypothetical-swap justification as `OCRPort`
([ADR-006](006-local-ocr-doctr.md)), just not yet exercised.

## Consequences

No persistence beyond what we build ourselves for the in-memory adapter (see
[ADR-005](005-one-index-per-strategy-persisted.md)); a future
production-store adapter may persist differently (e.g. delegate to the
store's own storage) and would implement `save`/`load` however fits that
backend, or may not need them at all if the backend is already durable —
`VectorStorePort` only commits callers to `search`.
