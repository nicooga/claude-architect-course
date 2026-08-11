import argparse
import textwrap
from pathlib import Path

from .embedder import SentenceTransformerEmbedder
from .vector_store import VectorStore

INDEX_DIR = Path(__file__).parent / "library" / "index"


def search(strategy_name: str, query: str, top_k: int, preview_chars: int) -> None:
    index_dir = INDEX_DIR / strategy_name
    if not index_dir.exists():
        print(f"No index at {index_dir}. Build it with: uv run python -m src.rag.build_index --strategy {strategy_name}")
        return

    store = VectorStore(SentenceTransformerEmbedder())
    store.load(str(index_dir))

    results = store.search(query, top_k)
    if not results:
        print("No results.")
        return

    for rank, result in enumerate(results, start=1):
        chunk = result.chunk
        print(f"[{rank}] {result.score:.4f}  {chunk.source}  {chunk.location}  ({chunk.chunk_id})")
        preview = " ".join(chunk.text.split())[:preview_chars]
        print(textwrap.indent(textwrap.fill(preview, width=88), "    "))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Query a persisted RAG index.")
    parser.add_argument("query")
    parser.add_argument("--strategy", default="semantic")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--preview-chars", type=int, default=400)
    args = parser.parse_args()
    search(args.strategy, args.query, args.top_k, args.preview_chars)


if __name__ == "__main__":
    main()
