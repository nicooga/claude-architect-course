import argparse
import json
import logging
import sys
from pathlib import Path

from lib.anthropic_adapter import AnthropicChatAdapter
from lib.repl import run_repl

from .embedder import SentenceTransformerEmbedder
from .tools import SearchDocumentsTool
from .vector_store import VectorStore

INDEX_DIR = Path(__file__).parent / "library" / "index"

SYSTEM_PROMPT = (
    "You are a research assistant over the user's personal library of "
    "books. Answer questions about their content only from passages "
    "returned by the search_documents tool — search first, then answer. "
    "Cite every claim with the source book and location shown on the "
    "excerpt you used. If the search returns nothing relevant, say so "
    "plainly instead of answering from your own knowledge.\n\n"
    "Indexed books: {sources}"
)


def _load_store(strategy_name: str) -> VectorStore:
    index_dir = INDEX_DIR / strategy_name
    if not index_dir.exists():
        raise SystemExit(
            f"No index at {index_dir}. Build it with: "
            f"uv run python -m src.rag.build_index --strategy {strategy_name}"
        )
    store = VectorStore(SentenceTransformerEmbedder())
    store.load(str(index_dir))
    return store


def _sources(strategy_name: str) -> str:
    manifest_path = INDEX_DIR / strategy_name / "manifest.json"
    if not manifest_path.exists():
        return "unknown (index has no manifest.json — rebuild it)"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    return ", ".join(manifest.get("sources", [])) or "none"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="REPL over the RAG index, with search_documents wired in."
    )
    parser.add_argument("--strategy", default="semantic")
    args = parser.parse_args()

    # stderr, not stdout, so tool-call logs don't interleave with the REPL's
    # "?> " prompt and answers on stdout — same as tool_usage's smoke test.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")

    store = _load_store(args.strategy)
    print(f"Index: {args.strategy}")

    chat = AnthropicChatAdapter(
        system=SYSTEM_PROMPT.format(sources=_sources(args.strategy)),
        max_tokens=2000,
        tools=[SearchDocumentsTool(store)],
    )
    run_repl(chat)


if __name__ == "__main__":
    main()
