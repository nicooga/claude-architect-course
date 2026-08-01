# ADR-008: BM25 implemented from scratch, not rank_bm25

## Status

Accepted

## Decision

Hand-write BM25 (TF, IDF, length normalization) rather than depend on
`rank_bm25`. Consistent with the hand-written cosine similarity
([ADR-003](003-in-memory-vector-store.md)); the formula is small enough to
be a good teaching artifact in its own right.
