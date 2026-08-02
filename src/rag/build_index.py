from pathlib import Path

from .ingestion import DoctrOCRAdapter, PDFLoader

LIBRARY_DIR = Path(__file__).parent / "library"
RAW_DIR = LIBRARY_DIR / "raw"
OCR_CACHE_DIR = LIBRARY_DIR / "ocr_cache"


def summarize(loader: PDFLoader, pdf_path: Path) -> None:
    print(f"Processing {pdf_path.name}...", flush=True)
    page_list = loader.load(str(pdf_path))
    total_chars = sum(len(page) for page in page_list.pages)
    print(
        f"{page_list.source}: {len(page_list.pages)} pages, "
        f"{len(page_list.ocr_pages)} via OCR, {total_chars} chars"
    )


def main() -> None:
    pdf_paths = sorted(RAW_DIR.glob("*.pdf"))
    if not pdf_paths:
        print(f"No PDFs found in {RAW_DIR}. Drop a book there and rerun.")
        return

    loader = PDFLoader(ocr=DoctrOCRAdapter(), ocr_cache_root=str(OCR_CACHE_DIR))
    for pdf_path in pdf_paths:
        summarize(loader, pdf_path)


if __name__ == "__main__":
    main()
