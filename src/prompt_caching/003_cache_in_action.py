"""Prompt caching, third experiment: a real conversation, priced.

`001_cache_basics.py` showed a cold write and a warm read; `002_cache_rules.py`
checked the rules that decide whether either happens. Neither answers the
question you actually have to answer for a real application: *what does this
buy me?*

So this file runs the shape most applications have — a multi-turn
conversation over one large document that never changes, with tool
definitions in front of it — and reports, per turn: the three token counters,
time-to-first-token, what the turn cost, and what the identical turn would
have cost with no breakpoint anywhere.

Every call is streamed, for one reason: the latency caching changes is
prefill, and prefill is over by the time the first token arrives. Total wall
clock is mostly generation, which a cache hit does not touch — measure only
that and the feature looks like it does nothing.

The counterfactual needs no second run: the counters already contain it.

    prompt tokens = input + cache_creation + cache_read

is what the model read this turn, cached or not, and it is exactly what an
uncached request for the same bytes would have billed at full input price.
`--replay-uncached` re-sends the recorded transcript with every breakpoint
removed and checks that arithmetic against the API. It is also the only way
to see the latency side, since that needs an uncached time-to-first-token to
compare against — and it is opt-in, because it doubles what the run spends.

Breakpoint placement here is the placement to copy (two of the four):

  1. the last system block — the static prefix. Tools render *before* system
     (tools -> system -> messages), so this one marker covers the tool
     definitions and the document together.
  2. the last block of the newest user turn — a rolling breakpoint over the
     growing history, moved forward every turn. The entry an earlier marker
     created outlives the marker, so moving it forward costs nothing.

Run it:

    uv run python -m src.prompt_caching.003_cache_in_action
    uv run python -m src.prompt_caching.003_cache_in_action --replay-uncached
    uv run python -m src.prompt_caching.003_cache_in_action --ttl 1h
"""

import argparse
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import anthropic
from anthropic import Anthropic
from anthropic.types import ContentBlock, Message, MessageParam, TextBlockParam, ToolParam
from pypdf import PdfReader

from lib.prompt_caching import (
    TTL,
    MAX_BREAKPOINTS,
    Prices,
    TokenUsage,
    cache_control,
    min_cacheable_tokens,
    prices_for,
    text_block,
)

MODEL = "claude-sonnet-4-5-20250929"

# Long enough for answers worth reading, short enough that output cost stays
# a rounding error next to the input side, which is what caching acts on.
MAX_TOKENS = 400

# The document. A book from the RAG unit's library if there is one — that is
# the realistic case, and the whole reason this stage sits after Stage 7's
# ingestion work — falling back to this repo's own ADRs so the script still
# runs on a fresh clone (`src/rag/library/` is gitignored).
LIBRARY_DIR = Path(__file__).parent.parent / "rag" / "library" / "raw"
ADR_DIR = Path(__file__).parent.parent / "rag" / "docs" / "adr"

# ~60k characters is roughly 15-20k tokens depending on the language: a
# document big enough that the savings are unmistakable, small enough that a
# full run with the uncached replay costs well under a dollar.
DEFAULT_DOC_CHARS = 60_000

# A page with less text than this has no usable text layer (it is a scan).
# Skipped rather than OCR'd: this script needs a long, real document, not a
# faithful transcription — src/rag/ingestion/ is where OCR belongs.
MIN_PAGE_CHARS = 200

# Front matter to step over by default when the document is a book: credits,
# a table of contents, and an index make for poor questions.
DEFAULT_SKIP_PAGES = 10

SYSTEM_INSTRUCTIONS = (
    "You are a study assistant. The complete text you need is included below "
    "and does not change during this conversation. Answer only from it, refer "
    "back to your earlier answers when the user asks you to, and keep every "
    "answer under 80 words. If the text does not settle a question, say so "
    "plainly."
)

# Deliberately document-agnostic, so the same transcript runs against a book
# or against the ADRs, and deliberately back-referential: turns 3-5 only make
# sense if the earlier turns are still in context. That is what makes the
# growing history worth caching rather than a detail.
TURNS: Tuple[str, ...] = (
    "In two sentences, what is this material about?",
    "List the three most important claims or decisions it makes, one line each.",
    "Of those three, which is the weakest, and why? Two sentences.",
    "Quote one sentence from the material, verbatim, that bears on that weakness.",
    "Would your answer change if only the first half of the material existed?",
)


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------


def load_book(pdf_path: Path, max_chars: int, skip_pages: int = 0) -> str:
    """Text-layer pages of `pdf_path`, up to `max_chars`.

    `skip_pages` drops front matter — a book's first pages are credits and a
    table of contents, which make for poor questions without making the
    measurement any different.
    """
    pages: List[str] = []
    total = 0
    for page in PdfReader(str(pdf_path)).pages[skip_pages:]:
        text = (page.extract_text() or "").strip()
        if len(text) < MIN_PAGE_CHARS:
            continue
        pages.append(text)
        total += len(text)
        if total >= max_chars:
            break
    return "\n\n".join(pages)[:max_chars]


def load_adrs(max_chars: int) -> str:
    """The RAG unit's ADRs, same corpus as the first two experiments."""
    paths = sorted(ADR_DIR.glob("*.md"))
    if not paths:
        raise FileNotFoundError(f"No ADR files found under {ADR_DIR}")
    return "\n\n".join(f"# {path.name}\n\n{path.read_text()}" for path in paths)[:max_chars]


def load_document(
    source: str, max_chars: int, skip_pages: int = 0
) -> Tuple[str, str, Optional[Path]]:
    """Returns (text, human-readable origin, the book it came from if any).

    `source` is "auto", "adrs", or a path to a PDF. "auto" prefers a book
    with a usable text layer and falls back to the ADRs, so the script
    behaves the same whether or not the local library exists.
    """
    if source == "adrs":
        return load_adrs(max_chars), f"ADRs from {ADR_DIR}", None

    candidates = [Path(source)] if source != "auto" else sorted(LIBRARY_DIR.glob("*.pdf"))
    for pdf_path in candidates:
        text = load_book(pdf_path, max_chars, skip_pages)
        # A scan-only book yields almost nothing here and is silently skipped
        # in "auto" mode; asked for by name, it is an error worth reporting.
        if len(text) >= max_chars // 2:
            return text, f"book {pdf_path.name}", pdf_path
        if source != "auto":
            raise SystemExit(
                f"{pdf_path} yielded only {len(text)} chars of text layer — it is "
                f"probably a scan. Use --document adrs, or ingest it via src/rag/."
            )

    return load_adrs(max_chars), f"ADRs from {ADR_DIR} (no usable book in {LIBRARY_DIR})", None


# --------------------------------------------------------------------------
# Request building
# --------------------------------------------------------------------------


def build_system(
    document: str, *, run_id: str, cached: bool, ttl: Optional[TTL]
) -> List[TextBlockParam]:
    """Instructions then document, with the breakpoint on the last block.

    One marker for the whole static prefix — tools included, since they
    render ahead of system.

    `run_id` goes into the first block, ahead of the breakpoint, so a fresh
    value makes the whole prefix hash differently and the run starts
    genuinely cold. Without it, a run started within the TTL of the previous
    one reads that run's entry on turn 1 and the numbers describe a warm
    start rather than the cold-then-warm arc this script is about. Same
    device as `002_cache_rules.py`, same reason.
    """
    return [
        text_block(f"[run {run_id}] {SYSTEM_INSTRUCTIONS}"),
        text_block(document, cached=cached, ttl=ttl),
    ]


def build_tools(*, other_books: Sequence[str]) -> List[ToolParam]:
    """One tool, present mainly to sit in front of the cached prefix.

    A realistic agent over a library has this tool; the questions below are
    all answerable from the document already in context, so it should never
    actually be called — `execute_tool` covers the case where it is, so a
    stray call cannot derail the measurement.

    No breakpoint of its own: a single small schema is a couple of hundred
    tokens, far below the model's minimum cacheable prefix, so a marker here
    would be a silent no-op. The system breakpoint already covers it. A
    tool-heavy agent is the case where a separate tool breakpoint earns its
    slot — see experiment 5 in `002_cache_rules.py` for what that buys.
    """
    listing = ", ".join(other_books) if other_books else "none indexed yet"
    return [
        {
            "name": "search_library",
            "description": (
                "Searches the user's *other* books — the ones not included in "
                "this conversation — and returns matching excerpts. The book "
                f"under discussion is already in context. Other titles: {listing}."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look for."}
                },
                "required": ["query"],
            },
        }
    ]


def execute_tool(name: str, tool_input: object) -> str:
    """Stub executor. Returning an honest empty result keeps a stray tool call
    from turning into an exception mid-measurement."""
    return f"No excerpts found (search_library is a stub in this experiment). Called {name} with {tool_input!r}."


# --------------------------------------------------------------------------
# Conversation
# --------------------------------------------------------------------------


@dataclass
class Turn:
    """One user question and everything the API appended in response.

    `appended` holds the raw assistant (and, if a tool ran, tool_result)
    messages, so `--replay-uncached` can rebuild a byte-identical transcript
    instead of a paraphrase of one.
    """

    question: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    seconds: float = 0.0
    # Time to the first content token of the turn's first response. This is
    # the number caching moves: a cache read replaces prefill over the whole
    # prefix, and prefill is what happens before the first token appears.
    # Total wall clock is dominated by generation, which caching does not
    # touch at all.
    ttft: float = 0.0
    first_prompt_tokens: int = 0
    answer: str = ""
    appended: List[MessageParam] = field(default_factory=list)


class Conversation:
    """The message list, plus the single rolling breakpoint over it.

    The breakpoint moves to the newest user turn every time, and the previous
    marker is dropped — the entry it created stays readable, so nothing is
    lost. Without this, a fixed marker would cache the first turn forever and
    every later turn would re-send the whole history at full price.
    """

    def __init__(self, *, cached: bool, ttl: Optional[TTL]) -> None:
        self.messages: List[MessageParam] = []
        self._cached = cached
        # Annotated, not inferred: pyright widens a Literal assigned to a bare
        # attribute to `str`, which then fails against the TTL alias.
        self._ttl: Optional[TTL] = ttl
        self._marked: Optional[TextBlockParam] = None

    def ask(self, question: str) -> None:
        block = text_block(question)
        if self._cached:
            if self._marked is not None:
                self._marked.pop("cache_control", None)
            block["cache_control"] = cache_control(self._ttl)
            self._marked = block
        self.messages.append({"role": "user", "content": [block]})

    def append(self, message: MessageParam) -> None:
        self.messages.append(message)


def run_turn(
    client: Anthropic,
    conversation: Conversation,
    *,
    question: str,
    system: List[TextBlockParam],
    tools: List[ToolParam],
) -> Turn:
    """Sends one user turn, following any tool loop it triggers.

    A turn can take more than one request, so its usage is a sum. The first
    request's prompt size is kept separately: that is the number the uncached
    replay can be compared against, since the replay stops before the tool
    loop would start.
    """
    turn = Turn(question=question)
    conversation.ask(question)

    while True:
        first_request = turn.usage.requests == 0
        response, elapsed, ttft = stream_once(
            client, system=system, messages=conversation.messages, tools=tools
        )
        turn.seconds += elapsed
        if first_request:
            turn.ttft = ttft

        usage = TokenUsage.from_usage(response.usage)
        if first_request:
            turn.first_prompt_tokens = usage.prompt_tokens
        turn.usage = turn.usage + usage

        assistant: MessageParam = {"role": "assistant", "content": response.content}
        conversation.append(assistant)
        turn.appended.append(assistant)

        if response.stop_reason != "tool_use":
            turn.answer = _text_of(response.content)
            return turn

        results: MessageParam = {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": execute_tool(block.name, block.input),
                }
                for block in response.content
                if block.type == "tool_use"
            ],
        }
        conversation.append(results)
        turn.appended.append(results)


def stream_once(
    client: Anthropic,
    *,
    system: List[TextBlockParam],
    messages: Sequence[MessageParam],
    tools: List[ToolParam],
) -> Tuple[Message, float, float]:
    """One streamed request. Returns (message, total seconds, seconds to first token).

    Streamed rather than plain `create()` purely to get time-to-first-token:
    prefill is the part of a request caching skips, and it all happens before
    the first token. Measured on total wall clock alone, a cache hit is nearly
    invisible — generation dominates, and generation is unaffected.
    """
    started = time.perf_counter()
    ttft = 0.0
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=messages,
        tools=tools,
    ) as stream:
        for event in stream:
            if not ttft and event.type in ("content_block_start", "content_block_delta"):
                ttft = time.perf_counter() - started
        message = stream.get_final_message()
    return message, time.perf_counter() - started, ttft


def _text_of(content: Sequence[ContentBlock]) -> str:
    return " ".join(block.text for block in content if block.type == "text").strip()


def measure_prefix(
    client: Anthropic, *, system: List[TextBlockParam], tools: List[ToolParam]
) -> Optional[int]:
    """Size of the static prefix, from the free counting endpoint.

    Returns None if that endpoint is unavailable rather than aborting the run:
    the check it feeds (is the prefix over the model's floor?) is a courtesy,
    and turn 1's `created` counter answers the same question for real — a
    prefix under the floor writes nothing.
    """
    try:
        return client.messages.count_tokens(
            model=MODEL,
            system=system,
            tools=tools,
            messages=[{"role": "user", "content": TURNS[0]}],
        ).input_tokens
    except anthropic.APIStatusError as error:
        print(f"  (count_tokens unavailable: {error.status_code} {error.message})")
        return None


# --------------------------------------------------------------------------
# Uncached replay
# --------------------------------------------------------------------------


@dataclass
class Replayed:
    """One uncached request standing in for one cached turn."""

    usage: TokenUsage
    seconds: float
    ttft: float


def replay_uncached(
    client: Anthropic,
    turns: Sequence[Turn],
    *,
    system: List[TextBlockParam],
    tools: List[ToolParam],
) -> List[Replayed]:
    """Re-sends the recorded transcript with no breakpoint anywhere.

    Turn N's request is the transcript up to and including question N — the
    same bytes the cached run sent, minus the markers. The reply is generated
    and thrown away; what is being read is `usage` and the clock. Its own
    output length will differ from the cached run's, so the token counts
    compare exactly and the totals only approximately.

    `system` must be the same blocks the cached run used, minus their
    breakpoint — including the run tag. The per-turn `match` column is there
    to catch it if it isn't.
    """
    history: List[MessageParam] = []
    measured: List[Replayed] = []

    for turn in turns:
        messages = history + [{"role": "user", "content": [text_block(turn.question)]}]
        response, elapsed, ttft = stream_once(
            client, system=system, messages=messages, tools=tools
        )
        measured.append(Replayed(TokenUsage.from_usage(response.usage), elapsed, ttft))
        # Advance with the *recorded* turn, not the reply just generated, so
        # every later request stays byte-identical to the cached run.
        history = messages + list(turn.appended)

    return measured


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

WIDTH = 104
ROW = "{turn:<6}{reqs:<6}{input:<8}{created:<9}{read:<8}{out:<7}{outcome:<10}{ttft:>7}{secs:>8}{cost:>11}{uncached:>11}{delta:>11}"


def print_header() -> None:
    print(
        ROW.format(
            turn="turn",
            reqs="reqs",
            input="input",
            created="created",
            read="read",
            out="out",
            outcome="outcome",
            ttft="ttft",
            secs="total",
            cost="cost",
            uncached="uncached",
            delta="saved",
        )
    )
    print("-" * WIDTH)


def print_row(
    label: str, usage: TokenUsage, ttft: float, seconds: float, prices: Prices
) -> None:
    saved = usage.savings_usd(prices)
    print(
        ROW.format(
            turn=label,
            reqs=usage.requests,
            input=usage.input_tokens,
            created=usage.cache_creation_tokens,
            read=usage.cache_read_tokens,
            out=usage.output_tokens,
            outcome=usage.outcome,
            ttft=f"{ttft:.2f}s",
            secs=f"{seconds:.1f}s",
            cost=f"${usage.cost_usd(prices):.4f}",
            uncached=f"${usage.uncached_cost_usd(prices):.4f}",
            delta=f"{'-' if saved < 0 else ''}${abs(saved):.4f}",
        )
    )


def report_turns(turns: Sequence[Turn], prices: Prices) -> TokenUsage:
    print_header()
    total = TokenUsage()
    elapsed = 0.0
    for index, turn in enumerate(turns, start=1):
        print_row(str(index), turn.usage, turn.ttft, turn.seconds, prices)
        total = total + turn.usage
        elapsed += turn.seconds
    print("-" * WIDTH)
    # The total row's ttft is a mean, not a sum: it is a per-request latency,
    # and summing it would say nothing.
    mean_ttft = sum(turn.ttft for turn in turns) / len(turns) if turns else 0.0
    print_row("all", total, mean_ttft, elapsed, prices)

    if total.created_1h:
        # Only interesting when --ttl 1h was used: the same tokens, written
        # at 2x base input instead of 1.25x.
        print(f"\n  write buckets: 5m={total.created_5m} tokens, 1h={total.created_1h} tokens")
    return total


def report_replay(
    turns: Sequence[Turn], measured: Sequence[Replayed], prices: Prices
) -> None:
    print(f"\n{'=' * WIDTH}\nuncached replay of the same transcript\n{'-' * WIDTH}")
    print(
        f"{'turn':<6}{'cached prompt':>15}{'replay prompt':>15}{'match':>8}"
        f"{'cached ttft':>14}{'replay ttft':>14}{'faster':>10}"
    )
    print("-" * WIDTH)

    total = TokenUsage()
    elapsed = 0.0
    mismatch = False
    for index, (turn, replayed) in enumerate(zip(turns, measured), start=1):
        # The replay has no breakpoints, so its `input_tokens` *is* the whole
        # prompt — and it should equal what the cached turn read plus wrote
        # plus paid full price for.
        agrees = replayed.usage.prompt_tokens == turn.first_prompt_tokens
        mismatch = mismatch or not agrees
        speedup = f"{replayed.ttft / turn.ttft:.1f}x" if turn.ttft else "n/a"
        print(
            f"{index:<6}{turn.first_prompt_tokens:>15}{replayed.usage.prompt_tokens:>15}"
            f"{'OK' if agrees else '!!':>8}{turn.ttft:>13.2f}s{replayed.ttft:>13.2f}s{speedup:>10}"
        )
        total = total + replayed.usage
        elapsed += replayed.seconds

    cached_total = sum((turn.usage for turn in turns), TokenUsage())
    print("-" * WIDTH)
    print(
        f"  cached run : ${cached_total.cost_usd(prices):.4f} over {cached_total.prompt_tokens} prompt tokens\n"
        f"  replay     : ${total.cost_usd(prices):.4f} over {total.prompt_tokens} prompt tokens"
    )
    if mismatch:
        print(
            "\n  !! A prompt-token count differs, which means the replay is not\n"
            "     byte-identical to the cached run — usually an assistant turn\n"
            "     that was not recorded verbatim. The cost comparison above is\n"
            "     only valid when every row says OK."
        )
    else:
        print(
            "\n  Every prompt-token count matches: input + created + read on a cached\n"
            "  turn is the same prompt the uncached request had to send in full. That\n"
            "  is why the counterfactual above needs no second run — this replay only\n"
            "  confirms it. The two dollar figures differ by a hair from the table's\n"
            "  because the replay generated its own, slightly different answers."
        )
        _report_latency_verdict(turns, measured)


def _report_latency_verdict(
    turns: Sequence[Turn], measured: Sequence[Replayed]
) -> None:
    """What the time-to-first-token column supports, and what it does not.

    Prefill is the work a cache read skips, so any latency win shows up here
    and nowhere else. Whether it is *visible* depends on prefix size: a
    ~20k-token prefill takes about a second either way, and run-to-run
    variance is of the same order. Rather than assert a speedup the numbers
    may not show, this reports the median over the warm turns and says which
    of the two situations the run is in.
    """
    # Turn 1 is excluded: cold either way, so it has no read to be faster than.
    warm = [
        replayed.ttft / turn.ttft
        for turn, replayed in list(zip(turns, measured))[1:]
        if turn.ttft
    ]
    if not warm:
        return
    median = sorted(warm)[len(warm) // 2]
    prefix = turns[-1].first_prompt_tokens
    print(
        f"\n  Latency: median {median:.1f}x faster to the first token on the warm turns\n"
        f"  (turn 1 excluded — it prefills either way)."
    )
    if median >= 1.3:
        print(
            "  That is the cache read replacing prefill over the whole prefix. Note\n"
            "  it never reaches the generation phase, which is most of the wall clock\n"
            "  in the `total` column and is unaffected by caching."
        )
    else:
        print(
            f"  Which is to say: inside the noise. Prefill over ~{prefix} tokens takes\n"
            "  about a second either way, and run-to-run variance is the same size, so\n"
            "  at this prefix length the cost saving is the real result and latency is\n"
            "  a rounding error. It scales with the prefix, though: at --doc-chars\n"
            "  160000 (~49k tokens) the same comparison measured 2.3x, 1.0s vs. 2.4s."
        )


def summarise(turns: Sequence[Turn], total: TokenUsage, prices: Prices) -> None:
    saved = total.savings_usd(prices)
    uncached = total.uncached_cost_usd(prices)
    share = (saved / uncached * 100) if uncached else 0.0
    print(
        f"\n  {len(turns)} turns, {total.requests} requests, {total.prompt_tokens} prompt tokens read by the model.\n"
        f"  Billed ${total.cost_usd(prices):.4f} instead of ${uncached:.4f} — {share:.0f}% less."
    )

    first = turns[0].usage
    if first.outcome == "write":
        print(
            "\n  Where it comes from: turn 1 is a loss on its own — it pays 1.25x to\n"
            "  write the document and reads nothing back — and every turn after it\n"
            "  reads that same prefix at 0.1x. Two calls is already break-even on the\n"
            "  5m window, so a conversation of any length is comfortably ahead."
        )
    else:
        # A read on turn 1 means the static prefix was still cached from an
        # earlier run — worth naming rather than quietly reporting a savings
        # figure that no cold start could reproduce.
        print(
            "\n  Note: turn 1 *read* rather than wrote, so this run inherited a cache\n"
            "  entry from an earlier one still inside its TTL and never paid the 1.25x\n"
            "  write. Real savings, but not what a cold start looks like: run without\n"
            "  --run-id (a fresh tag per run is the default) for that."
        )
    print(
        "\n  The document is nearly all of the savings; the history the turns add is\n"
        "  small by comparison. That is the general shape — cache the one big stable\n"
        "  thing first, and only then worry about the turns."
    )


# --------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Price a cached multi-turn conversation over a large document."
    )
    parser.add_argument(
        "--document",
        default="auto",
        help='"auto" (a book from src/rag/library/raw, else the ADRs), "adrs", or a path to a PDF',
    )
    parser.add_argument("--doc-chars", type=int, default=DEFAULT_DOC_CHARS, help="cap on document size")
    parser.add_argument(
        "--skip-pages",
        type=int,
        default=DEFAULT_SKIP_PAGES,
        help="pages of front matter to skip when the document is a book",
    )
    parser.add_argument("--turns", type=int, default=len(TURNS), help=f"how many of the {len(TURNS)} turns to run")
    parser.add_argument("--ttl", choices=("5m", "1h"), default="5m", help="cache window for every breakpoint")
    parser.add_argument(
        "--run-id",
        default=uuid.uuid4().hex[:8],
        help="tag mixed into the prefix ahead of the breakpoint; a fresh value per run "
        "(the default) guarantees a cold start, a fixed value deliberately reuses the "
        "previous run's entries",
    )
    parser.add_argument(
        "--replay-uncached",
        action="store_true",
        help="also re-send the recorded transcript with no breakpoints (doubles the spend)",
    )
    args = parser.parse_args()

    client = Anthropic()
    prices = prices_for(MODEL)
    ttl: Optional[TTL] = "1h" if args.ttl == "1h" else None

    document, origin, book = load_document(args.document, args.doc_chars, args.skip_pages)
    other_books = [
        path.name for path in sorted(LIBRARY_DIR.glob("*.pdf")) if path != book
    ]
    tools = build_tools(other_books=other_books)
    system = build_system(document, run_id=args.run_id, cached=True, ttl=ttl)

    floor = min_cacheable_tokens(MODEL)
    static_prefix = measure_prefix(client, system=system, tools=tools)

    print(
        f"model={MODEL}  ttl={args.ttl}  min_cacheable={floor}  "
        f"breakpoints=2/{MAX_BREAKPOINTS}  run_id={args.run_id}"
    )
    print(f"document: {len(document)} chars from {origin}")
    print(f"input ${prices.input_per_mtok:.2f}/MTok, output ${prices.output_per_mtok:.2f}/MTok (list price)")
    if static_prefix is None:
        print(
            "static prefix: unmeasured (count_tokens unavailable) — turn 1's "
            "`created` below is the real check\n"
        )
    else:
        print(f"static prefix (tools + system + document): ~{static_prefix} tokens\n")
        if static_prefix < floor:
            raise SystemExit(
                f"The static prefix is ~{static_prefix} tokens, under the {floor}-token "
                f"floor for {MODEL} — the breakpoint would be silently ignored. Raise --doc-chars."
            )

    conversation = Conversation(cached=True, ttl=ttl)
    turns: List[Turn] = []
    for question in TURNS[: args.turns]:
        turn = run_turn(client, conversation, question=question, system=system, tools=tools)
        turns.append(turn)
        print(f"[turn {len(turns)}] {question}\n  {turn.answer}\n")

    total = report_turns(turns, prices)
    summarise(turns, total, prices)

    if args.replay_uncached:
        # The same blocks, minus their breakpoint: the replay has to be
        # byte-identical to be a fair comparison, run tag included.
        plain_system = build_system(document, run_id=args.run_id, cached=False, ttl=None)
        measured = replay_uncached(client, turns, system=plain_system, tools=tools)
        report_replay(turns, measured, prices)


if __name__ == "__main__":
    main()
