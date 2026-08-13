"""Prompt caching, first experiment: cold write vs. warm read.

The whole feature rests on one idea — the request prefix
(tools -> system -> messages) is hashed, and a `cache_control` breakpoint
says "everything up to here can be reused by a later request whose prefix
is byte-identical". So the experiment is:

  1. Build a long, stable system prompt (this unit's own ADR files, so the
     text is real and costs nothing to obtain).
  2. Mark its last block with `cache_control: {"type": "ephemeral"}`.
  3. Send the same prefix twice with different questions after it, and read
     `response.usage` both times.

Cold call:  cache_creation_input_tokens > 0, cache_read_input_tokens == 0
Warm call:  cache_creation_input_tokens == 0, cache_read_input_tokens > 0

A third call sends the same prompt with no breakpoint at all, as the
baseline the other two are compared against: every token at full price.
"""

from pathlib import Path
from typing import List

from anthropic import Anthropic
from anthropic.types import MessageParam, TextBlockParam

MODEL = "claude-sonnet-4-5-20250929"

# Sonnet 4.5 will not create a cache entry for a prefix shorter than this.
# There is no error when the prefix is too short — the request just behaves
# as if no breakpoint were there, which is exactly the kind of silent
# non-effect worth knowing about before debugging a "cache that never hits".
MIN_CACHEABLE_TOKENS = 1024

ADR_DIR = Path(__file__).parent.parent / "rag" / "docs" / "adr"

QUESTIONS = [
    "Which ADR decides how chunking strategies relate to page boundaries, and what does it decide?",
    "Why was BM25 implemented from scratch instead of using a library?",
]


def load_document() -> str:
    """Concatenates the RAG unit's ADRs into one long document.

    Any large, stable text would do — ADRs are convenient because they are
    already in the repo, are genuinely long enough to cache, and are real
    prose rather than filler, so the model's answers are checkable.
    """
    paths = sorted(ADR_DIR.glob("*.md"))
    if not paths:
        raise FileNotFoundError(f"No ADR files found under {ADR_DIR}")
    return "\n\n".join(f"# {path.name}\n\n{path.read_text()}" for path in paths)


def build_system(document: str, cached: bool) -> List[TextBlockParam]:
    """System prompt as a list of blocks rather than a plain string, because
    `cache_control` is set per content block — a `system="..."` string has
    nowhere to hang the breakpoint.

    The breakpoint goes on the *last* block: it caches everything before it,
    so instructions + document are covered by one marker.
    """
    instructions: TextBlockParam = {
        "type": "text",
        "text": (
            "You answer questions about the architecture decision records below. "
            "Cite the ADR number you relied on. Answer in at most three sentences."
        ),
    }
    doc_block: TextBlockParam = {"type": "text", "text": document}
    if cached:
        doc_block["cache_control"] = {"type": "ephemeral"}
    return [instructions, doc_block]


def count_tokens(client: Anthropic, system: List[TextBlockParam], question: str) -> int:
    """Token counting is a separate, free endpoint — used here to check the
    prefix clears MIN_CACHEABLE_TOKENS before spending anything on it."""
    messages: List[MessageParam] = [{"role": "user", "content": question}]
    return client.messages.count_tokens(model=MODEL, system=system, messages=messages).input_tokens


def ask(client: Anthropic, label: str, system: List[TextBlockParam], question: str) -> None:
    messages: List[MessageParam] = [{"role": "user", "content": question}]
    response = client.messages.create(
        model=MODEL, max_tokens=300, system=system, messages=messages
    )
    usage = response.usage
    # `input_tokens` is only the *uncached remainder*, not the total. The
    # full prompt size is the sum of the three counters below, which is why
    # a warm call shows a tiny `input_tokens` next to a large cache read.
    print(f"\n[{label}]")
    print(f"  question              : {question}")
    print(f"  input_tokens          : {usage.input_tokens}")
    print(f"  cache_creation_tokens : {usage.cache_creation_input_tokens}")
    print(f"  cache_read_tokens     : {usage.cache_read_input_tokens}")
    print(f"  output_tokens         : {usage.output_tokens}")


def main() -> None:
    client = Anthropic()
    document = load_document()

    cached_system = build_system(document, cached=True)
    plain_system = build_system(document, cached=False)

    prefix_tokens = count_tokens(client, cached_system, QUESTIONS[0])
    print(f"Document: {len(document)} chars, prefix ~{prefix_tokens} tokens")
    if prefix_tokens < MIN_CACHEABLE_TOKENS:
        raise SystemExit(
            f"Prefix is {prefix_tokens} tokens, below the {MIN_CACHEABLE_TOKENS}-token "
            f"minimum for {MODEL} — the breakpoint would be silently ignored."
        )

    # Baseline first: same prompt, no breakpoint. Nothing is written to the
    # cache, so it does not disturb the cold/warm pair that follows.
    ask(client, "no cache_control (baseline)", plain_system, QUESTIONS[0])

    # Cold: the breakpoint's prefix has never been seen, so it is written.
    ask(client, "cold — writes the cache", cached_system, QUESTIONS[0])

    # Warm: identical prefix, different question *after* the breakpoint.
    # The question varies, the cached part does not — which is the whole
    # point: only what precedes the breakpoint has to stay byte-identical.
    ask(client, "warm — reads the cache", cached_system, QUESTIONS[1])


if __name__ == "__main__":
    main()
