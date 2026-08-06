# RAG

## Goal

Build a RAG pipeline unit — chunking, local embeddings, vector search, and
hybrid lexical+semantic retrieval — exposed to the agent as a `ToolPort`
tool, reusing `lib/repl` (`run_repl`) and `lib/anthropic_adapter`
(`ChatPort`/`ToolPort`, `AnthropicChatAdapter`) exactly as
[`tool_usage/`](../tool_usage) does. No changes are needed to `lib/`.

Two constraints shaped every design decision below:

1. **Embeddings must be generated locally with OSS** — no third-party
   embeddings API.
2. **Nothing in this unit should spend against the company-provided
   Anthropic API key unnecessarily.** RAG isn't part of the course's
   original budget/program, so anything that can run locally and free
   should — including OCR for the one source book that's scan-only.

This document is the design record for the unit: the architecture
decisions made and why, and a staged roadmap for building it. It's meant to
be readable on its own — a future session can pick up implementation
directly from here without needing the conversation that produced it.

**Status: Stages 1–4 (ingestion, size-based chunking, structure-based
chunking, embeddings + vector store + semantic chunking) complete; Stage 5
onward not yet started.**

## Architecture Decision Records

Design decisions and their rationale live as individual records in
[`docs/adr/`](docs/adr/), not inline here, so this README doesn't drift out
of sync with them. See [`docs/architecture.md`](docs/architecture.md) for a
diagram of how the pieces described below fit together.

| ADR | Decision |
| --- | --- |
| [001](docs/adr/001-ports-and-adapters-applied-selectively.md) | Ports/adapters applied selectively, not uniformly |
| [002](docs/adr/002-local-embeddings-sentence-transformers.md) | Local embeddings via `sentence-transformers`, behind `EmbeddingPort` |
| [003](docs/adr/003-in-memory-vector-store.md) | In-memory numpy vector store, behind `VectorStorePort` |
| [004](docs/adr/004-chunking-strategies-page-scoped.md) | Chunking strategies are page-scoped, with a seam-crossing exception for structure/semantic chunkers |
| [005](docs/adr/005-one-index-per-strategy-persisted.md) | One index per strategy, persisted to disk |
| [006](docs/adr/006-local-ocr-doctr.md) | Local OCR via `python-doctr`, not Claude vision — behind `OCRPort` |
| [007](docs/adr/007-pypdf-for-text-layer-extraction.md) | `pypdf` for text-layer PDF extraction, not PyMuPDF |
| [008](docs/adr/008-bm25-from-scratch.md) | BM25 implemented from scratch, not `rank_bm25` |
| [009](docs/adr/009-hybrid-fusion-rrf.md) | Hybrid fusion via Reciprocal Rank Fusion (RRF) |
| [010](docs/adr/010-pin-python-version-before-ml-deps.md) | Environment risk: pin Python version before adding ML deps |
| [011](docs/adr/011-ingestion-unified-per-page-pipeline.md) | Ingestion as a single per-page pipeline, not parallel Scan/PDF branches |

## Staged roadmap

Each stage is independently buildable and verifiable before moving to the
next, mirroring how `tool_usage/README.md` sequences its five tools "in
order of increasing complexity." Ingestion comes first — every chunker
consumes the `PageList` it produces, so it can no longer be a mid-sequence
stage (see [ADR-011](docs/adr/011-ingestion-unified-per-page-pipeline.md)
for how this reordering happened).

- [x] **Stage 1 — Ingestion pipeline (text + OCR).** `uv add pypdf
      "python-doctr[torch]"` (checking
      [ADR-010](docs/adr/010-pin-python-version-before-ml-deps.md) first).
      `ports.py` (`OCRPort` —
      [ADR-001](docs/adr/001-ports-and-adapters-applied-selectively.md);
      later stages append `EmbeddingPort`/`VectorStorePort` to this same
      file), `ingestion/types.py` (`PageList`: `pages: list[str]`, `source:
      str`), `ingestion/documents.py` (walks a PDF page by page, `pypdf`
      text-layer extraction per page, falling back per page to an
      `ocr: OCRPort` constructor param per
      [ADR-006](docs/adr/006-local-ocr-doctr.md)/[ADR-011](docs/adr/011-ingestion-unified-per-page-pipeline.md)),
      `ingestion/ocr.py` (`DoctrOCRAdapter` implementing `OCRPort`,
      per-book disk cache under `library/ocr_cache/<book_stem>/`) +
      `build_index.py` (CLI: for now, scans `library/raw/*.pdf` and prints
      an ingestion summary per book — the chunk → embed → save →
      `manifest.json` steps get added incrementally as Stages 2 and 4
      land). Also add the `.gitignore` rule for `src/rag/library/` at this
      stage, once `library/raw/` first gets used (see "Local library"
      below).

- [x] **Stage 2 — Size-based chunking.** `text_chunking/types.py` +
      `size_based.py`. No new dependencies. `Chunk` dataclass:
      `text`/`source`/`location`/`strategy`/`chunk_id`. Fixed-size sliding
      window per page with overlap (1000 chars, 200 overlap — confirmed).
      `chunk_size_based` takes the `PageList` Stage 1 produces directly.
      `build_index.py` gained a `--strategy` flag (`size` for now) and now
      prints a chunk count/avg-length summary per book alongside the
      ingestion summary.

- [x] **Stage 3 — Structure-based chunking.** `structure_based.py`. No new
      dependencies. Regex heading/paragraph heuristics, no parsing
      library: a line is a heading if it's short, doesn't end mid-sentence,
      and is either a numbered heading (`Capítulo 3`) or fully uppercase;
      everything else is grouped into blank-line-separated paragraph
      blocks (or, absent blank lines — the normal case for PDF text — one
      block per heading-to-heading run) and packed into chunks up to
      `max_chunk_size` (1000, mirrors Stage 2's default for
      comparability), cutting only at a sentence boundary. A heading
      always starts a new chunk. Per
      [ADR-004](docs/adr/004-chunking-strategies-page-scoped.md), a
      paragraph/sentence run bridges a page seam whenever nothing (heading
      or size budget) forces a break there — `location` then reports a
      range (`"pages N-M"`) instead of a single page.

- [x] **Stage 4 — Embeddings + vector store + semantic chunking.**
      `uv add sentence-transformers numpy` resolved cleanly against the
      existing `python-doctr[torch]` dependency, so no `.python-version`
      pin was needed ([ADR-010](docs/adr/010-pin-python-version-before-ml-deps.md)).
      `ports.py` gained `EmbeddingPort`, `VectorStorePort`, and the
      `SearchResult` dataclass they share
      ([ADR-001](docs/adr/001-ports-and-adapters-applied-selectively.md)).
      `embedder.py` (`SentenceTransformerEmbedder`, lazy-loads the model on
      first `embed()` call, same reasoning as `DoctrOCRAdapter` deferring
      its import). `vector_store.py` (`VectorStore`, hand-written cosine
      similarity over a stacked, L2-normalized numpy array, implements
      `VectorStorePort` per [ADR-003](docs/adr/003-in-memory-vector-store.md);
      `save`/`load` round-trip `embeddings.npy` + `chunks.json`).
      `text_chunking/semantic.py` (regex sentence splitter, page-scoped
      like Stage 3's paragraph splitter, then packs sentences together
      while adjacent-sentence cosine similarity stays at/above
      `similarity_threshold` (confirmed: 0.5) and the running chunk stays
      under `max_chunk_size` (1000, same default as Stages 2–3); may
      bridge a page seam per ADR-004, same as Stage 3). `build_index.py`
      now does the full chunk → embed → save → `manifest.json` sequence
      for whichever `--strategy` is selected (`size`/`structure`/`semantic`),
      merging every book under `library/raw/` into one index per strategy
      under `library/index/<strategy>/` (ADR-005) instead of only printing
      a chunk-count summary.

- [ ] **Stage 5 — `search_documents` tool + REPL wiring (semantic-only).**
      `tools/search_documents.py` (`SearchDocumentsTool`, `ToolPort`
      shape, takes a `VectorStorePort` at construction — passed the
      in-memory `VectorStore` for now, per
      [ADR-003](docs/adr/003-in-memory-vector-store.md)),
      `tools/__init__.py`, `repl_smoke_test.py` (mirrors
      `src/tool_usage/repl_smoke_test.py`). Add a "Testing the REPL"
      section to this README once this stage lands.

- [ ] **Stage 6 — Lexical indexing (BM25) + hybrid fusion.** No new
      dependency (stdlib only). `lexical_index.py` (`BM25Index`, `k1=1.5`,
      `b=0.75` defaults), `retrieval.py` (`reciprocal_rank_fusion()`,
      `HybridRetriever`). Update `build_index.py` to also save
      `bm25.json`; update `search_documents.py`/`repl_smoke_test.py` to
      use `HybridRetriever` (itself built from a `VectorStorePort` +
      `BM25Index`) instead of the vector store directly. Compare hybrid
      vs. pure-semantic retrieval as the payoff of this stage.

## Conventions to follow

Mirror `src/tool_usage/` throughout: one file per tool/strategy, a barrel
`__init__.py`, a `repl_smoke_test.py` entry point. `ToolPort`
(`lib/anthropic_adapter/ports.py`) and `ChatPort`/`run_repl`
(`lib/repl/`) need no changes at any stage.

## Local library

Source books are the user's own material and must never be committed, and
neither should the derived index (it reproduces book text in chunked
form). Once Stage 1 lands, drop books into `src/rag/library/raw/` and
build the index locally:

```bash
uv run python -m src.rag.build_index
```

This scans `library/raw/*.pdf`, prints an ingestion summary per book (page
count, OCR fallback pages, characters extracted), chunks every book with
`--strategy` (`size`, `structure`, or `semantic`) and prints a chunk
count/avg-length summary, then embeds every chunk across the whole library
and saves one index — `library/index/<strategy>/{embeddings.npy,
chunks.json, manifest.json}` — for that strategy (ADR-005).

`src/rag/library/` is covered by a `.gitignore` rule — nothing under it is
meant to be tracked.

## Testing ingestion, chunking, embeddings, and the vector store (Stages 1–4)

There's no test framework wired up yet (no `pytest` in `pyproject.toml`) —
verification for these stages is manual, the same way `tool_usage`'s
"Testing the REPL" section is.

**End-to-end, against your own books.** This is the primary smoke test for
both stages at once: it exercises `PDFLoader` (text-layer extraction + OCR
fallback + OCR cache) and `chunk_size_based` together, against whatever
you've dropped in `library/raw/`.

```bash
uv run python -m src.rag.build_index --strategy size
```

Look for, per book:

- A pages/OCR/chars line from ingestion — OCR page count should be 0 for a
  book with a text layer, and equal to the page count for a scan-only book
  (rerun once so the OCR cache under `library/ocr_cache/<book_stem>/` makes
  the second run fast — the first run downloads doctr's weights and runs
  the model).
- A `[size] N chunks, M chars avg` line — `M` should sit close to
  `DEFAULT_CHUNK_SIZE` (1000) for any book with pages longer than a
  chunk, since only each page's last chunk is typically short.

**Isolated, without a real PDF.** To check `chunk_size_based`'s boundary
behavior directly — chunk size, overlap, `chunk_id` format — without
waiting on a PDF or OCR:

```bash
uv run python -c "
from src.rag.ingestion.types import PageList
from src.rag.text_chunking import chunk_size_based

page_list = PageList(pages=['a' * 2500, 'short page'], source='demo')
chunks = chunk_size_based(page_list, chunk_size=1000, overlap=200)
for c in chunks:
    print(c.chunk_id, c.location, len(c.text))
"
```

Expect 3 chunks from the first page (0–1000, 800–1800, 1600–2500 — each
new window starts `chunk_size - overlap` characters after the last) and 1
short chunk from the second, all tagged `location="page 1"` /
`location="page 2"` respectively — chunks never cross a page boundary
(ADR-004).

**End-to-end, `structure` strategy — compare against `size`.** Same
command, `--strategy structure`:

```bash
uv run python -m src.rag.build_index --strategy structure
```

Against the two books used to build this stage: the text-layer book
(Pedrosa et al.) produced 279 structure chunks vs. 365 size chunks over
the same pages, with sentence-clean boundaries and page ranges on chunks
whose paragraph bridges a page seam (`pages N-M`) — the payoff this stage
is meant to demonstrate. The scan-only, OCR'd book (Romero) shows a real
limitation instead: its running header/chapter-title lines are repeated,
all-caps text on *every* page, which `_is_heading` can't distinguish from
a real heading (no cross-page repetition check — see the docstring in
`structure_based.py`), so it forces a chunk break on nearly every page and
pulls the average chunk size well under 1000. Worth reproducing once
against your own books rather than trusting these numbers as they age.

**Isolated, without a real PDF.** To check heading detection, sentence
packing, and seam bridging directly:

```bash
uv run python -c "
from src.rag.ingestion.types import PageList
from src.rag.text_chunking import chunk_structure_based

page_list = PageList(
    pages=[
        'INTRODUCTION\nThis is the first sentence. The next one runs long '
        'enough that it does not finish before the page does, it just',
        'continues right where it left off. A new sentence starts here.',
    ],
    source='demo',
)
chunks = chunk_structure_based(page_list, max_chunk_size=500)
for c in chunks:
    print(c.chunk_id, c.location, repr(c.text))
"
```

Expect a single chunk, `location="pages 1-2"`: the heading merges into the
same chunk as the body that follows it, and the sentence split across the
page boundary rejoins into one sentence in the output text instead of
being cut at the seam.

**End-to-end, `semantic` strategy — compare against `size`/`structure`.**
Same command, `--strategy semantic` (slower than the other two: it embeds
every sentence in the library, not just every saved chunk):

```bash
uv run python -m src.rag.build_index --strategy semantic
```

Against the two books used to build this stage: 3563 semantic chunks for
Romero and 906 for Pedrosa et al., both at ~280 chars average — well under
the 1000-char `max_chunk_size` budget, meaning the 0.5 similarity threshold
is the binding constraint almost everywhere rather than the size cap.
Adjacent sentences in real prose apparently drop below 0.5 cosine
similarity often enough that most chunks end up single- or few-sentence.
Worth tuning `similarity_threshold` lower if fewer, larger chunks are
wanted — left at 0.5 here since retrieval quality (see below), not chunk
size, is this stage's actual payoff.

**Verifying the saved index round-trips and retrieves.** Load a
strategy's saved index back and run a real query through it — this is the
actual payoff of Stage 4, and the first point in the pipeline where a
question can be answered by content instead of just inspected as text:

```bash
uv run python -c "
from src.rag.vector_store import VectorStore
from src.rag.embedder import SentenceTransformerEmbedder

store = VectorStore()
store.load('src/rag/library/index/semantic')

embedder = SentenceTransformerEmbedder()
query_embedding = embedder.embed(['crisis economica en Argentina'])[0]

for result in store.search(query_embedding, top_k=3):
    print(round(result.score, 3), result.chunk.location, result.chunk.text[:120])
"
```

Run once per strategy directory (`size`, `structure`, `semantic`) to
compare which one surfaces the most on-topic passage for the same query.
Against this project's two books, `semantic` and `size` both returned
genuinely on-topic passages (crisis-era economic history) for this query,
at similar top scores (~0.74–0.79 cosine).

**Isolated, without a real PDF or a real embedder.** To check
similarity-drop splitting and seam bridging directly, without waiting on
`sentence-transformers` to load a real model:

```bash
uv run python -c "
import numpy as np
from src.rag.ingestion.types import PageList
from src.rag.text_chunking import chunk_semantic

class FakeEmbedder:
    def embed(self, texts):
        # one-hot on each sentence's first word, so shared-topic sentences
        # come out identical and topic switches come out orthogonal
        vecs = []
        for t in texts:
            v = np.zeros(4)
            v[hash(t.split()[0].lower()) % 4] = 1.0
            vecs.append(v)
        return vecs

page_list = PageList(
    pages=[
        'Cats are mammals. Cats have fur.',
        'Cats purr when happy. Rockets need fuel.',
    ],
    source='demo',
)
chunks = chunk_semantic(page_list, FakeEmbedder())
for c in chunks:
    print(c.chunk_id, c.location, repr(c.text))
"
```

Expect two chunks: the three "Cats..." sentences merge into one,
`location="pages 1-2"` (the run bridges the page seam, same as
structure-based), and "Rockets need fuel." splits off into its own chunk
since it drops below the similarity threshold against the sentence before
it.

## Open defaults to confirm during implementation

None of these are settled requirements — they're starting points to
confirm or tune while building the corresponding stage:

- Embedding model: `all-MiniLM-L6-v2` (confirmed — loads and embeds both
  books' chunks/sentences without issue; retrieval quality checked in
  "Testing ingestion, chunking, embeddings, and the vector store" above).
- Semantic chunking similarity threshold: 0.5 (confirmed as the value in
  use, but see the finding below — it's the binding constraint on chunk
  size almost everywhere for real prose, well before `max_chunk_size` is
  reached, so it's worth revisiting if larger semantic chunks are wanted).
- Structure-based/semantic chunking `max_chunk_size`: 1000, chosen to
  mirror Stage 2's default so all three strategies' chunk counts are
  directly comparable (confirmed against the two books in this project —
  see "Testing ingestion, chunking, embeddings, and the vector store"
  above).
- Structure-based heading detection has no cross-page repetition check —
  a scanned book's repeated running header/footer lines match the
  all-caps heading heuristic on every page. Fixing this (e.g. dropping
  lines that repeat verbatim across most pages, at the ingestion layer)
  is out of scope for Stage 3; flagged here in case it's worth doing
  before Stage 4 builds on top of these chunks.
- Same root cause, different symptom: a run of consecutive heading-like
  lines with no body text between them (a title page — author, title,
  subtitle, edition, each its own short all-caps line) comes out as
  several separate near-empty chunks instead of one. This is the ceiling
  of inferring structure from plain text with regexes rather than from a
  format that actually carries structure (HTML/XML); not worth chasing
  for this experiment, so left as-is.
- Semantic chunking's similarity check only compares each sentence to the
  one immediately before it, not to a running chunk centroid — cheap (one
  cosine per sentence, no recomputation as a chunk grows) and matches this
  experiment's from-scratch style, at the cost of being more sensitive to
  a single locally-dissimilar sentence than a centroid comparison would
  be. Against the two books here it produces small chunks (~280 chars
  avg) well under `max_chunk_size` — see "Testing ingestion, chunking,
  embeddings, and the vector store" above — not worth chasing a
  centroid-based variant for this experiment.
- What counts as "usable text" from a pypdf page extraction before the
  ingestion pipeline treats a page as image-only and falls back to OCR:
  fewer than 20 non-whitespace characters (`PDFLoader`'s `min_text_chars`,
  tunable at construction).
- doctr's default model pair — lighter architectures are available if CPU
  OCR turns out too slow.
- BM25 `k1`/`b`: 1.5 / 0.75. RRF `k`: 60.
- Supported formats: PDF/.txt/.md only — no epub unless requested later.

## More docs

- [`docs/architecture.md`](docs/architecture.md) — Mermaid diagrams of the
  full pipeline and core types.
- [`docs/adr/`](docs/adr/) — one file per architecture decision record.
