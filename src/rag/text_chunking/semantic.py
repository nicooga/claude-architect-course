import re
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from ..ingestion.types import PageList
from ..ports import EmbeddingPort
from .types import Chunk

STRATEGY = "semantic"

DEFAULT_SIMILARITY_THRESHOLD = 0.5
DEFAULT_MAX_CHUNK_SIZE = 1000

_LINE_HYPHEN_BREAK = re.compile(r"-\n(?=[a-záéíóúñü])")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ0-9\"'¿¡])")


@dataclass
class _Sentence:
    text: str
    page: int


def _dehyphenate(text: str) -> str:
    return _LINE_HYPHEN_BREAK.sub("", text)


def _page_sentences(page_text: str, page_number: int) -> List[_Sentence]:
    normalized = " ".join(_dehyphenate(page_text).split())
    return [
        _Sentence(sentence.strip(), page_number)
        for sentence in _SENTENCE_BOUNDARY.split(normalized)
        if sentence.strip()
    ]


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denominator) if denominator else 0.0


def chunk_semantic(
    page_list: PageList,
    embedder: EmbeddingPort,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
) -> List[Chunk]:
    """Packs sentences together while consecutive sentences stay
    semantically similar, splitting wherever similarity drops below
    `similarity_threshold` or `max_chunk_size` would be exceeded — same
    dual-condition, sentence-boundary-only cut as `chunk_structure_based`,
    just driven by embeddings instead of headings. Per ADR-004, a run of
    similar sentences may bridge a page seam when nothing forces a break
    there; `location` then reports a page range instead of a single page.
    """
    sentences: List[_Sentence] = []
    for page_number, page_text in enumerate(page_list.pages, start=1):
        sentences.extend(_page_sentences(page_text, page_number))

    if not sentences:
        return []

    embeddings = embedder.embed([sentence.text for sentence in sentences])

    chunks: List[Chunk] = []
    parts: List[str] = []
    length = 0
    first_page: Optional[int] = None
    last_page: Optional[int] = None

    def flush() -> None:
        nonlocal parts, length, first_page, last_page
        if not parts:
            return
        location = (
            f"page {first_page}"
            if first_page == last_page
            else f"pages {first_page}-{last_page}"
        )
        chunks.append(
            Chunk(
                text=" ".join(parts),
                source=page_list.source,
                location=location,
                strategy=STRATEGY,
                chunk_id=f"{STRATEGY}:{page_list.source}:p{first_page}:{len(chunks)}",
            )
        )
        parts, length, first_page, last_page = [], 0, None, None

    def add(piece: str, page: int) -> None:
        nonlocal length, first_page, last_page
        parts.append(piece)
        length += len(piece) + (1 if len(parts) > 1 else 0)
        first_page = page if first_page is None else first_page
        last_page = page

    add(sentences[0].text, sentences[0].page)
    for i in range(1, len(sentences)):
        sentence = sentences[i]
        similarity = _cosine_similarity(embeddings[i - 1], embeddings[i])
        exceeds_size = length + len(sentence.text) + 1 > max_chunk_size
        if similarity < similarity_threshold or exceeds_size:
            flush()
        add(sentence.text, sentence.page)

    flush()
    return chunks
