import os
from pathlib import Path
from typing import Dict, List, Optional

from pypdf import PdfReader

from ..ports import OCRPort
from .types import PageList

DEFAULT_MIN_TEXT_CHARS = 20


class PDFLoader:
    """Walks a PDF page by page, preferring pypdf's text layer and falling
    back to OCR for image-only pages (ADR-011)."""

    def __init__(
        self,
        ocr: OCRPort,
        ocr_cache_root: str,
        min_text_chars: int = DEFAULT_MIN_TEXT_CHARS,
    ):
        self.ocr = ocr
        self.ocr_cache_root = ocr_cache_root
        self.min_text_chars = min_text_chars

    def load(self, pdf_path: str) -> PageList:
        book_stem = Path(pdf_path).stem
        raw_pages = [page.extract_text() or "" for page in PdfReader(pdf_path).pages]
        total = len(raw_pages)
        print(f"  {book_stem}: scanning {total} pages for a text layer...", flush=True)

        needs_ocr = [i for i, text in enumerate(raw_pages) if not self._is_usable(text)]
        if needs_ocr:
            print(
                f"  {book_stem}: {len(needs_ocr)}/{total} pages need OCR "
                "(may take a while on CPU)...",
                flush=True,
            )

        ocr_texts: Optional[Dict[int, str]] = None
        pages: List[str] = []
        for index, text in enumerate(raw_pages):
            if self._is_usable(text):
                pages.append(text)
                continue
            if ocr_texts is None:
                ocr_texts = self._transcribe(pdf_path, needs_ocr)
            pages.append(ocr_texts[index])

        return PageList(pages=pages, source=book_stem, ocr_pages=needs_ocr)

    def _is_usable(self, text: str) -> bool:
        non_whitespace = sum(1 for char in text if not char.isspace())
        return non_whitespace >= self.min_text_chars

    def _transcribe(self, pdf_path: str, page_indices: List[int]) -> Dict[int, str]:
        book_stem = Path(pdf_path).stem
        cache_dir = os.path.join(self.ocr_cache_root, book_stem)
        return self.ocr.transcribe(pdf_path, cache_dir=cache_dir, page_indices=page_indices)
