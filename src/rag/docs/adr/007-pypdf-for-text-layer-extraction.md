# ADR-007: pypdf for text-layer PDF extraction, not PyMuPDF

## Status

Accepted

## Decision

`pypdf` — pure Python, permissively licensed — instead of PyMuPDF, which is
AGPL-licensed. `doctr` handles its own PDF→image rasterization internally
for the scanned-page case, so no separate rasterization library is needed
either.
