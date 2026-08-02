import os
from typing import Dict, List

CACHE_FILENAME = "page_{index:04d}.txt"

# Pages per doctr call. Chunking (rather than one call for all requested
# pages) trades a little batching efficiency for visible progress on long
# books, and lets each batch's results be cached before the next one starts.
BATCH_SIZE = 8


class DoctrOCRAdapter:
    """Implements `OCRPort` via python-doctr (ADR-006).

    Only ever runs doctr over the pages it's asked for — a mixed document
    may need OCR for a handful of pages out of hundreds, and the model is
    the expensive part, not the request. Those pages are processed in
    batches rather than one call, so results can be cached incrementally.
    Each batch is written to disk under `cache_dir` as soon as it
    completes, so an interrupted run resumes from the last cached page
    instead of starting over, and a rerun after full success skips the
    model entirely.
    """

    def transcribe(
        self, pdf_path: str, cache_dir: str, page_indices: List[int]
    ) -> Dict[int, str]:
        cached = self._read_cache(cache_dir, page_indices)
        missing = [i for i in page_indices if i not in cached]
        if not missing:
            print(f"    OCR: {len(page_indices)} pages already cached, skipping doctr", flush=True)
            return cached
        if cached:
            print(
                f"    OCR: resuming — {len(cached)}/{len(page_indices)} pages already cached",
                flush=True,
            )

        from doctr.io import DocumentFile
        from doctr.models import ocr_predictor

        print("    OCR: loading doctr model (downloads weights on first run)...", flush=True)
        model = ocr_predictor(pretrained=True)
        doc_pages = DocumentFile.from_pdf(pdf_path)

        for start in range(0, len(missing), BATCH_SIZE):
            batch_indices = missing[start : start + BATCH_SIZE]
            result = model([doc_pages[i] for i in batch_indices])
            batch_texts = {
                index: page.render() for index, page in zip(batch_indices, result.pages)
            }
            cached.update(batch_texts)
            self._write_cache(cache_dir, batch_texts)
            print(f"    OCR: {len(cached)}/{len(page_indices)} pages done", flush=True)

        return cached

    def _read_cache(self, cache_dir: str, page_indices: List[int]) -> Dict[int, str]:
        texts: Dict[int, str] = {}
        for i in page_indices:
            path = os.path.join(cache_dir, CACHE_FILENAME.format(index=i))
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    texts[i] = f.read()
        return texts

    def _write_cache(self, cache_dir: str, texts: Dict[int, str]) -> None:
        os.makedirs(cache_dir, exist_ok=True)
        for index, text in texts.items():
            path = os.path.join(cache_dir, CACHE_FILENAME.format(index=index))
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
