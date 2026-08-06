# ADR-005: One index per strategy, persisted to disk

## Status

Accepted

## Decision

`library/index/<strategy>/{embeddings.npy, bm25.json, chunks.json,
manifest.json}`. One index per strategy, not one per book — `build_index.py`
chunks every book under `library/raw/` and embeds all of their chunks
together before saving, so a strategy's index spans the whole library and a
single search can surface results from any book. `chunks.json` (via each
`Chunk.source`) is what tells them apart at retrieval time, not a separate
directory per book.

## Rationale

Re-embedding a whole book on every REPL restart would be wasteful;
persisting per-strategy also lets the same question be re-asked after
rebuilding under a different strategy, to compare retrieval quality
directly. Merging books into one index (rather than one per book) matches
how retrieval is actually used: a question doesn't name which book to
search, so `search_documents` (Stage 5) needs one search over the whole
library per strategy, not a per-book fan-out.
