import json
import os
from typing import List, Optional

import numpy as np

from .ports import EmbeddingPort, SearchResult
from .text_chunking.types import Chunk

MODEL_FILE = "model.json"


class VectorStore:
    """Implements VectorStorePort: in-memory numpy array, hand-written
    cosine similarity (ADR-003).

    The store owns an `EmbeddingPort` and embeds on both sides of the
    index: `add(chunks)` embeds them, `search(query)` embeds the query.
    `save`/`load` stamp and check the model name, so an index is only ever
    queried through the model that built it (ADR-003). State is persisted
    to `library/index/<strategy>/` (ADR-005).
    """

    def __init__(self, embedder: EmbeddingPort) -> None:
        self._embedder = embedder
        self._chunks: List[Chunk] = []
        self._embeddings: Optional[np.ndarray] = None  # (n, dim), L2-normalized

    def add(self, chunks: List[Chunk]) -> None:
        """Embed and append. Takes a list because the embedder's efficient
        unit is the batch: one model invocation covers every new chunk. A
        chunk's vector is a pure function of its own text, so appending
        leaves existing rows valid and yields exactly the matrix a
        single-shot build would.
        """
        if not chunks:
            return
        matrix = np.stack(self._embedder.embed([chunk.text for chunk in chunks]))
        matrix = matrix.astype(np.float32)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)

        if self._embeddings is None:
            self._embeddings = matrix
        else:
            if matrix.shape[1] != self._embeddings.shape[1]:
                raise ValueError(
                    f"embedding dim {matrix.shape[1]} does not match "
                    f"indexed dim {self._embeddings.shape[1]}"
                )
            self._embeddings = np.vstack([self._embeddings, matrix])
        self._chunks.extend(chunks)

    def search(self, query: str, top_k: int) -> List[SearchResult]:
        return self.search_vector(self._embedder.embed([query])[0], top_k)

    def search_vector(self, query_embedding: np.ndarray, top_k: int) -> List[SearchResult]:
        """Serves callers that already hold a vector: MMR/diversity
        reranking against already-selected vectors, near-duplicate
        detection between chunks, HyDE-style expansion where the vector
        comes from a synthesized document. `VectorStorePort` declares
        `search` alone, so this is an adapter-level affordance (ADR-003).
        """
        if self._embeddings is None or not self._chunks:
            return []
        query_vector = query_embedding / np.linalg.norm(query_embedding)
        scores = self._embeddings @ query_vector
        top_indices = np.argsort(-scores)[:top_k]
        return [
            SearchResult(chunk=self._chunks[i], score=float(scores[i]))
            for i in top_indices
        ]

    def save(self, index_dir: str) -> None:
        if self._embeddings is None:
            raise ValueError("nothing to save — call add() first")
        os.makedirs(index_dir, exist_ok=True)
        np.save(os.path.join(index_dir, "embeddings.npy"), self._embeddings)
        chunks_payload = [chunk.__dict__ for chunk in self._chunks]
        with open(os.path.join(index_dir, "chunks.json"), "w", encoding="utf-8") as f:
            json.dump(chunks_payload, f, ensure_ascii=False, indent=2)
        with open(os.path.join(index_dir, MODEL_FILE), "w", encoding="utf-8") as f:
            json.dump(
                {"model": self._embedder.name, "dim": int(self._embeddings.shape[1])},
                f,
                indent=2,
            )

    def load(self, index_dir: str) -> None:
        model_path = os.path.join(index_dir, MODEL_FILE)
        if not os.path.exists(model_path):
            raise ValueError(
                f"{model_path} is missing — this index predates model stamping; "
                "rebuild it with build_index.py"
            )
        with open(model_path, "r", encoding="utf-8") as f:
            model_meta = json.load(f)
        if model_meta["model"] != self._embedder.name:
            raise ValueError(
                f"index at {index_dir} was built with {model_meta['model']!r}, "
                f"but this store embeds with {self._embedder.name!r} — "
                "scores would be meaningless; rebuild the index or construct "
                "the store with the matching embedder"
            )

        self._embeddings = np.load(os.path.join(index_dir, "embeddings.npy"))
        with open(os.path.join(index_dir, "chunks.json"), "r", encoding="utf-8") as f:
            chunks_payload = json.load(f)
        self._chunks = [Chunk(**payload) for payload in chunks_payload]
