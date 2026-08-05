from typing import List

from ..ingestion.types import PageList
from .types import Chunk

STRATEGY = "size"

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 200


def chunk_size_based(
    page_list: PageList,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> List[Chunk]:
    """Fixed-size sliding window per page (ADR-004) — never merges text
    across a page boundary, so `location` stays a trivial "page N"."""
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    stride = chunk_size - overlap
    chunks: List[Chunk] = []
    for page_number, page_text in enumerate(page_list.pages, start=1):
        start = 0
        page_len = len(page_text)
        while start < page_len:
            end = start + chunk_size
            chunks.append(
                Chunk(
                    text=page_text[start:end],
                    source=page_list.source,
                    location=f"page {page_number}",
                    strategy=STRATEGY,
                    chunk_id=f"{STRATEGY}:{page_list.source}:p{page_number}:{len(chunks)}",
                )
            )
            if end >= page_len:
                break
            start += stride
    return chunks
