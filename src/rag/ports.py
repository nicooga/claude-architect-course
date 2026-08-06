from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Protocol

import numpy as np

if TYPE_CHECKING:
    # Deferred (rather than a top-level import) to avoid a circular import:
    # text_chunking/semantic.py imports EmbeddingPort from this module, so
    # this module can't import from text_chunking at runtime.
    from .text_chunking.types import Chunk


@dataclass
class SearchResult:
    chunk: Chunk
    score: float


class OCRPort(Protocol):
    """What the ingestion pipeline needs from an OCR backend.

    Takes the specific pages that need OCR rather than a page count from 0
    — a mixed document may only need OCR for a handful of image-only pages,
    and there's no reason to run the (expensive) model over pages that
    already have a usable text layer. Batching what *is* requested is still
    far more efficient than invoking the model once per page (see ADR-006).
    """

    def transcribe(
        self, pdf_path: str, cache_dir: str, page_indices: List[int]
    ) -> Dict[int, str]: ...


class EmbeddingPort(Protocol):
    """What chunking/indexing/retrieval need from an embedding backend."""

    def embed(self, texts: List[str]) -> List[np.ndarray]: ...


class VectorStorePort(Protocol):
    """What retrieval needs from a vector store (ADR-003). Only `search` is
    committed to here — persistence is whatever fits a given backend (see
    ADR-003's consequences), but the in-memory adapter implements save/load
    too since it has no other durability."""

    def search(self, query_embedding: np.ndarray, top_k: int) -> List[SearchResult]: ...

    def save(self, index_dir: str) -> None: ...

    def load(self, index_dir: str) -> None: ...
