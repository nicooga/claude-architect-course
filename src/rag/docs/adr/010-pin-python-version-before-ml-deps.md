# ADR-010: Environment risk — pin Python version before adding ML deps

## Status

Accepted

## Context

The project's `.venv` is currently on Python 3.14.1 with no
`.python-version` pin (`uv` picked the newest version satisfying
`requires-python = ">=3.12"`). `sentence-transformers` (torch) and
`python-doctr` (torch + opencv) are heavy ML dependencies whose wheels may
lag behind brand-new CPython releases.

## Decision

Before adding whichever heavy ML dependency lands first — `python-doctr`
in the ingestion stage, or `sentence-transformers` in the later embeddings
stage (see [`../../README.md`](../../README.md#staged-roadmap) for current
stage numbers) — verify `uv add` resolves cleanly first. If it doesn't,
run `uv python pin 3.12` (adds a `.python-version` file, still satisfies
`>=3.12`) and `uv sync`.
