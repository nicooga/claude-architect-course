# ADR-005: One index per strategy, persisted to disk

## Status

Accepted

## Decision

`library/index/<strategy>/{embeddings.npy, bm25.json, chunks.json,
manifest.json}`.

## Rationale

Re-embedding a whole book on every REPL restart would be wasteful;
persisting per-strategy also lets the same question be re-asked after
rebuilding under a different strategy, to compare retrieval quality
directly.
