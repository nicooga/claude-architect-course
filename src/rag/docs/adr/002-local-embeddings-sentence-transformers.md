# ADR-002: Local embeddings via sentence-transformers, behind EmbeddingPort

## Status

Accepted

## Context

Embeddings must be generated locally with OSS — no third-party embeddings
API (see the unit-level constraints in [`../../README.md`](../../README.md)).

## Decision

`sentence-transformers`, model `all-MiniLM-L6-v2` (small, fast, standard
baseline — a recommendation to confirm, not fixed). Rejected `fastembed`.
`SentenceTransformerEmbedder` implements `EmbeddingPort` structurally — no
inheritance, same duck-typing style as every `ToolPort` implementation in
`tool_usage/`.

## Consequences

Pulls in `torch`, a heavy dependency, but it's the standard/well-documented
choice; the port means a test-only fake embedder can stand in without
loading torch at all.
