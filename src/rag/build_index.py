import argparse
import json
from functools import partial
from pathlib import Path
from typing import List

from .embedder import SentenceTransformerEmbedder
from .ingestion import DoctrOCRAdapter, PDFLoader
from .text_chunking import Chunk, chunk_semantic, chunk_size_based, chunk_structure_based
from .vector_store import VectorStore

LIBRARY_DIR = Path(__file__).parent / "library"
RAW_DIR = LIBRARY_DIR / "raw"
OCR_CACHE_DIR = LIBRARY_DIR / "ocr_cache"
INDEX_DIR = LIBRARY_DIR / "index"

STRATEGIES = {
    "size": chunk_size_based,
    "structure": chunk_structure_based,
    "semantic": chunk_semantic,
}


def _chunk_book(loader: PDFLoader, pdf_path: Path, chunker, strategy_name: str) -> List[Chunk]:
    print(f"Processing {pdf_path.name}...", flush=True)
    page_list = loader.load(str(pdf_path))
    total_chars = sum(len(page) for page in page_list.pages)
    print(
        f"{page_list.source}: {len(page_list.pages)} pages, "
        f"{len(page_list.ocr_pages)} via OCR, {total_chars} chars"
    )

    chunks = chunker(page_list)
    avg_chars = total_chars / len(chunks) if chunks else 0
    print(f"  [{strategy_name}] {len(chunks)} chunks, {avg_chars:.0f} chars avg")
    return chunks


def build_index(strategy_name: str) -> None:
    pdf_paths = sorted(RAW_DIR.glob("*.pdf"))
    if not pdf_paths:
        print(f"No PDFs found in {RAW_DIR}. Drop a book there and rerun.")
        return

    loader = PDFLoader(ocr=DoctrOCRAdapter(), ocr_cache_root=str(OCR_CACHE_DIR))
    embedder = SentenceTransformerEmbedder()
    chunker = STRATEGIES[strategy_name]
    if strategy_name == "semantic":
        # chunk_semantic needs an embedder to compare sentences; the other
        # two strategies don't take one, so it's bound here rather than
        # threaded through a uniform signature all chunkers must share.
        chunker = partial(chunker, embedder=embedder)

    all_chunks: List[Chunk] = []
    for pdf_path in pdf_paths:
        all_chunks.extend(_chunk_book(loader, pdf_path, chunker, strategy_name))

    if not all_chunks:
        print("No chunks produced, nothing to index.")
        return

    print(f"Embedding {len(all_chunks)} chunks...", flush=True)
    embeddings = embedder.embed([chunk.text for chunk in all_chunks])

    store = VectorStore()
    store.build(all_chunks, embeddings)

    import ipdb; ipdb.set_trace()

    index_dir = INDEX_DIR / strategy_name
    store.save(str(index_dir))
    sources = sorted({chunk.source for chunk in all_chunks})
    with open(index_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(
            {"strategy": strategy_name, "chunk_count": len(all_chunks), "sources": sources},
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"Saved index to {index_dir} ({len(all_chunks)} chunks, {len(sources)} sources)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=sorted(STRATEGIES), default="semantic")
    args = parser.parse_args()
    build_index(args.strategy)


if __name__ == "__main__":
    main()
