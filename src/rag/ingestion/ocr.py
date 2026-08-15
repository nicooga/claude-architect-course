import os
from typing import Dict, List, Tuple

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

    A page image wider than it is tall is treated as a double-page spread
    (a book scanned two physical pages at a time) and split into left/right
    halves before OCR, each transcribed separately and joined with a blank
    line: doctr's reading-order heuristic doesn't reliably separate the two
    halves of a wide spread, and was observed interleaving their lines
    (a sentence from the left half immediately followed by an unrelated one
    from the right half, with no punctuation between them for downstream
    sentence splitting to catch). Splitting first sidesteps that rather
    than trying to fix reading order after the fact. Known blind spot: a
    genuinely landscape single page (e.g. a full-page foldout chart) would
    be mis-split by this same width>height check — not a concern for the
    two books this pipeline has been run against so far.
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
            feed_images, spans = self._prepare_images(doc_pages, batch_indices)
            result = model(feed_images)
            batch_texts = {
                index: "\n\n".join(result.pages[i].render() for i in range(*span))
                for index, span in zip(batch_indices, spans)
            }
            cached.update(batch_texts)
            self._write_cache(cache_dir, batch_texts)
            print(f"    OCR: {len(cached)}/{len(page_indices)} pages done", flush=True)

        return cached

    def _prepare_images(self, doc_pages, page_indices: List[int]) -> Tuple[List, List[Tuple[int, int]]]:
        """Builds the flat list of images to feed doctr for one batch, splitting
        any double-page spread into left/right halves first. `spans[i]` is the
        `(start, end)` range in the returned image list — as a `range()`-ready
        pair — that page_indices[i]'s text was rendered from: length 2 for a
        split spread, 1 otherwise."""
        images = []
        spans = []
        for index in page_indices:
            image = doc_pages[index]
            height, width = image.shape[:2]
            start = len(images)
            if width > height:
                midpoint = width // 2
                images.append(image[:, :midpoint])
                images.append(image[:, midpoint:])
            else:
                images.append(image)
            spans.append((start, len(images)))
        return images, spans

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
