from typing import Any, Dict

from ..ports import VectorStorePort

DEFAULT_TOP_K = 5
MAX_TOP_K = 20


class SearchDocumentsTool:
    """Exposes retrieval to the agent. Implements ToolPort structurally,
    the same way `src/tool_usage/tools/` does — no inheritance.

    Takes a `VectorStorePort` at construction (ADR-003), so the tool never
    learns which backend answers the query, nor which embedding model sits
    behind it. Stage 6 swaps in a `HybridRetriever` here without touching
    this file, as long as it keeps the `search(query, top_k)` shape.
    """

    name = "search_documents"
    description = (
        "Searches the user's personal library of books for passages "
        "relevant to a query, and returns the best-matching excerpts with "
        "their source book and page location. Use this whenever the "
        "question concerns the content of those books — quote and cite the "
        "returned excerpts rather than answering from memory. The search is "
        "semantic, not keyword-based: phrase the query as the idea you are "
        "looking for, in the language the books are written in."
    )
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "What to look for, phrased as a topic or a statement "
                    "rather than as keywords."
                ),
            },
            "top_k": {
                "type": "integer",
                "description": (
                    f"How many excerpts to return (default {DEFAULT_TOP_K}, "
                    f"max {MAX_TOP_K})."
                ),
            },
        },
        "required": ["query"],
    }

    def __init__(self, store: VectorStorePort) -> None:
        self._store = store

    async def execute(self, tool_input: Dict[str, Any]) -> str:
        query = tool_input["query"]
        top_k = min(int(tool_input.get("top_k") or DEFAULT_TOP_K), MAX_TOP_K)

        results = self._store.search(query, top_k)
        if not results:
            return f"No passages found for {query!r}."

        # Plain delimited text rather than JSON: the payload is prose, and
        # the model reads it more reliably with the metadata labeled inline
        # than wrapped in escaped JSON strings.
        blocks = []
        for rank, result in enumerate(results, start=1):
            chunk = result.chunk
            blocks.append(
                f"[{rank}] source: {chunk.source} | location: {chunk.location} | "
                f"score: {result.score:.3f}\n{chunk.text.strip()}"
            )
        return "\n\n---\n\n".join(blocks)
