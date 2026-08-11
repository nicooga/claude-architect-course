from typing import List, Optional

import numpy as np

DEFAULT_MODEL = "all-MiniLM-L6-v2"


class SentenceTransformerEmbedder:
    """Implements EmbeddingPort via sentence-transformers (ADR-002).

    The model is loaded lazily on first `embed()` call, not in `__init__`
    — same reasoning as `DoctrOCRAdapter` deferring its doctr import: a
    fake/test embedder can stand in without ever pulling in torch.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model: Optional[object] = None

    @property
    def name(self) -> str:
        return self._model_name

    def embed(self, texts: List[str]) -> List[np.ndarray]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            print(f"    Embedding: loading {self._model_name}...", flush=True)
            self._model = SentenceTransformer(self._model_name)

        embeddings = self._model.encode(texts, show_progress_bar=False)  # type: ignore[attr-defined]
        return [np.asarray(embedding) for embedding in embeddings]
