# ADR-003: In-memory numpy vector store, hand-written cosine similarity, behind VectorStorePort

## Status

Accepted

## Context

A vector store is needed to search embedded chunks. This course favors
building the mechanism yourself over reaching for a library, and there's a
stated intent to try a production-grade vector store (chromadb, pgvector)
later.

A query vector is only meaningful against an index built by the same
embedding model. A mismatch surfaces as plausible-looking cosine scores
over an incompatible space, so it has to be caught structurally rather
than by inspecting results.

## Decision

The first (and for now only) adapter is a hand-written in-memory
`VectorStore` doing cosine similarity over a numpy array — matches this
course's "build the mechanism yourself" style, and stays the default for the
teaching corpus. Per [ADR-001](001-ports-and-adapters-applied-selectively.md),
it sits behind `VectorStorePort` rather than being called directly, because
there's a genuine, stated intent to build a second adapter later against a
production-grade vector store — the same non-hypothetical-swap justification
as `OCRPort` ([ADR-006](006-local-ocr-doctr.md)), just not yet exercised.

The port is `search(query: str, top_k) -> list[SearchResult]`, plus
`save(index_dir)` / `load(index_dir)`. Taking the query as text keeps
embedding inside the adapter, which the port exists to hide, and it is a
contract every candidate backend can meet: a pgvector or faiss adapter
embeds in the adapter, chroma embeds natively.

`VectorStore` takes an `EmbeddingPort` at construction and embeds on both
sides of the index: `add(chunks)` embeds and appends, `search(query)`
embeds the query. Holding the embedder also lets the store enforce model
identity — `save` stamps the model name and dimension into `model.json`
alongside the vectors, and `load` accepts an index only if that name
matches the store's own embedder. `EmbeddingPort` exposes a `name`
property for this.

`add` takes a list, because the embedder's efficient unit is the batch. It
appends: a chunk's vector is a pure function of its own text, so existing
rows stay valid as the index grows, and the vectors on disk are exactly
those a single-shot build would produce. Changing the model is a rebuild.

`VectorStore.search_vector(query_embedding, top_k)` serves callers that
already hold a vector: MMR / diversity reranking against already-selected
vectors, near-duplicate detection between chunks, HyDE-style query
expansion. `VectorStorePort` declares `search` alone, so this stays an
adapter-level affordance for code that has a vector in hand.

## Consequences

No persistence beyond what we build ourselves for the in-memory adapter (see
[ADR-005](005-one-index-per-strategy-persisted.md)); a future
production-store adapter may persist differently (e.g. delegate to the
store's own storage) and would implement `save`/`load` however fits that
backend, or may not need them at all if the backend is already durable —
`VectorStorePort` only commits callers to `search`.

An index directory is only loadable by a store constructed with the model
that wrote it; `library/` is local, gitignored, and reproducible from
`build_index.py`, so a mismatch is a rebuild rather than a migration.

`HybridRetriever` ([ADR-009](009-hybrid-fusion-rrf.md)) composes over this
store as one of two retrievers, owning the lexical index
([ADR-008](008-bm25-from-scratch.md)) and the fusion between them. Both
retrievers take the query as text, so it passes the query straight through
to each.
