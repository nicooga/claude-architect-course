import json
import os
from typing import List, Optional

import numpy as np

from .ports import SearchResult
from .text_chunking.types import Chunk


class VectorStore:
    """Implements VectorStorePort: in-memory numpy array, hand-written
    cosine similarity (ADR-003). `build()` populates it from chunks +
    their embeddings (produced by an EmbeddingPort elsewhere — this class
    never embeds anything itself); `save`/`load` persist that state to
    `library/index/<strategy>/` (ADR-005).
    """

    def __init__(self) -> None:
        self._chunks: List[Chunk] = []
        self._embeddings: Optional[np.ndarray] = None  # (n, dim), L2-normalized

    def build(self, chunks: List[Chunk], embeddings: List[np.ndarray]) -> None:
        self._chunks = list(chunks)
        matrix = np.stack(embeddings).astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        self._embeddings = matrix / norms

    def search(self, query_embedding: np.ndarray, top_k: int) -> List[SearchResult]:
        if self._embeddings is None or not self._chunks:
            return []
        query = query_embedding / np.linalg.norm(query_embedding)
        scores = self._embeddings @ query
        top_indices = np.argsort(-scores)[:top_k]
        return [
            SearchResult(chunk=self._chunks[i], score=float(scores[i]))
            for i in top_indices
        ]

    def save(self, index_dir: str) -> None:
        if self._embeddings is None:
            raise ValueError("nothing to save — call build() first")
        os.makedirs(index_dir, exist_ok=True)
        np.save(os.path.join(index_dir, "embeddings.npy"), self._embeddings)
        chunks_payload = [chunk.__dict__ for chunk in self._chunks]
        with open(os.path.join(index_dir, "chunks.json"), "w", encoding="utf-8") as f:
            json.dump(chunks_payload, f, ensure_ascii=False, indent=2)

    def load(self, index_dir: str) -> None:
        self._embeddings = np.load(os.path.join(index_dir, "embeddings.npy"))
        with open(os.path.join(index_dir, "chunks.json"), "r", encoding="utf-8") as f:
            chunks_payload = json.load(f)
        self._chunks = [Chunk(**payload) for payload in chunks_payload]
