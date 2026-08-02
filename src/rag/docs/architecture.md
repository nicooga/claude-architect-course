# RAG Architecture

Diagrams grounding the design recorded in [`adr/`](adr/). The ADRs are the
source of truth for *why*; this file is a visual index of *how the pieces
fit together*, kept in sync with them but not a duplicate of their prose.
See [`../README.md`](../README.md#staged-roadmap) for which numbered stage
builds which piece.

## Pipeline: source book to search result

```mermaid
flowchart TD
    subgraph ING["ingestion/ (ADR-011)"]
        A[Source PDF] --> B{Per page}
        B -->|native text layer| C[pypdf extraction]
        B -->|image-only page| D["OCRPort.transcribe()<br/>DoctrOCRAdapter, ADR-006"]
        C --> E[PageList]
        D --> E
    end

    subgraph CHK["text_chunking/ (ADR-004)"]
        E --> F["chunk_size_based()<br/>page-scoped, never bridges a seam"]
        E --> G["chunk_structure_based()<br/>may bridge a page seam"]
        E --> H["chunk_semantic()<br/>may bridge a page seam"]
        F --> I[Chunk list]
        G --> I
        H --> I
    end

    subgraph IDX["build_index.py (ADR-005)"]
        I --> J["EmbeddingPort<br/>SentenceTransformerEmbedder, ADR-002"]
        I --> K["BM25Index (ADR-008)"]
        J --> L["VectorStorePort<br/>VectorStore, ADR-003"]
        L --> M["library/index/&lt;strategy&gt;/embeddings.npy"]
        K --> N["library/index/&lt;strategy&gt;/bm25.json"]
    end

    subgraph RET["retrieval.py + tools/search_documents.py"]
        O[Query] --> J
        O --> K
        L --> P["HybridRetriever<br/>reciprocal_rank_fusion(), ADR-009"]
        K --> P
        P --> Q[SearchResult list]
        Q --> R["SearchDocumentsTool (ToolPort)"]
    end

    R --> S["Claude, via lib.repl / lib.anthropic_adapter"]
```

## Core types and ports

```mermaid
classDiagram
    class PageList {
        +list~str~ pages
        +str source
        +list~int~ ocr_pages
    }
    class Chunk {
        +str text
        +str source
        +str location
        +str strategy
        +str chunk_id
    }
    class SearchResult {
        +Chunk chunk
        +float score
    }
    class EmbeddingPort {
        <<protocol>>
        +embed(texts) list~ndarray~
    }
    class OCRPort {
        <<protocol>>
        +transcribe(pdf_path, cache_dir, page_indices) dict~int, str~
    }
    class VectorStorePort {
        <<protocol>>
        +search(query_embedding, top_k) list~SearchResult~
        +save(index_dir)
        +load(index_dir)
    }
    class SentenceTransformerEmbedder
    class DoctrOCRAdapter
    class VectorStore
    class BM25Index
    class HybridRetriever

    EmbeddingPort <|.. SentenceTransformerEmbedder
    OCRPort <|.. DoctrOCRAdapter
    VectorStorePort <|.. VectorStore
    HybridRetriever --> VectorStorePort
    HybridRetriever --> BM25Index
    PageList --> Chunk : chunked into
    Chunk --> SearchResult : wrapped in
```

## Notes

- `location` on `Chunk` is either a single page (`"page N"`) or, for
  structure-based/semantic chunks that bridge a page seam, a range
  (`"pages N-M"`) — see [ADR-004](adr/004-chunking-strategies-page-scoped.md).
- The ingestion pipeline has no Scan/PDF fork: a fully-scanned book is just
  the case where every page takes the OCR branch — see
  [ADR-011](adr/011-ingestion-unified-per-page-pipeline.md).
