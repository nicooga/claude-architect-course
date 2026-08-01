# ADR-009: Hybrid fusion via Reciprocal Rank Fusion (RRF), not weighted score combination

## Status

Accepted

## Decision

Combine BM25 and embedding search results by rank (`1/(k+rank)`, standard
`k=60`), not by raw score.

## Rationale

BM25 scores are unbounded/corpus-dependent and cosine similarity is bounded
to `[-1, 1]` — combining raw scores needs fragile per-query normalization;
RRF sidesteps the scale mismatch entirely.
