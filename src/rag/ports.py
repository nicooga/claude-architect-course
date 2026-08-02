from typing import Dict, List, Protocol


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
