"""Prompt caching, second experiment: the rules, checked one at a time.

`001_cache_basics.py` showed the happy path — a cold write, then a warm read.
This file goes after the rules that decide *whether* that happens. One
experiment per rule, each printing `response.usage`, so every verdict comes
from the API rather than from prose:

  1. prefix  - only what precedes the breakpoint must stay byte-identical
  2. minimum - a prefix below the model's floor is silently not cached
  3. cap     - at most 4 breakpoints per request; a 5th is a 400
  4. ttl     - 5m vs. 1h are separate buckets, and a read refreshes for free
  5. order   - the prefix is tools -> system -> messages, in that order

Two conventions make the results repeatable:

  * Every experiment tags its *first* system block with a per-run id. That id
    sits before every breakpoint, so each run starts genuinely cold and no
    experiment can read another one's entries. It costs one cache write per
    experiment per run — the price of a result that does not depend on when
    the script last ran. `--run-id fixed` opts back into sharing entries
    across runs, which is itself a way to watch the TTL expire.
  * The reply is never the point here, so every call asks for one short answer
    with a small `max_tokens`. What is being measured is the token accounting.

Run everything (fast experiments only):

    uv run python -m src.prompt_caching.002_cache_rules

Add the slow TTL parts:

    uv run python -m src.prompt_caching.002_cache_rules --only ttl --ttl-wait 90 --expire
"""

import argparse
import time
import uuid
from pathlib import Path
from typing import List, Literal, Optional, Sequence, Tuple, Union

import anthropic
from anthropic import Anthropic, omit
from anthropic.types import MessageParam, TextBlockParam, ToolParam, Usage

MODEL = "claude-sonnet-4-5-20250929"

# Paired with MODEL, and deliberately not a shared constant: the floor is
# per-model and is *not* monotonic across generations — 512 tokens on Opus 5
# and Fable 5, 1024 on Sonnet 4.5 / 4.6 / Sonnet 5 / Opus 4.8, 2048 on Opus
# 4.7, 4096 on Opus 4.6 / 4.5 and Haiku 4.5. Change MODEL and this must
# change with it. Caches are also model-scoped, so switching models discards
# every entry the other scripts in this unit wrote.
MIN_CACHEABLE_TOKENS = 1024

ADR_DIR = Path(__file__).parent.parent / "rag" / "docs" / "adr"

# Small enough to keep the slow/expensive experiments cheap, comfortably over
# MIN_CACHEABLE_TOKENS for this model. Verified at runtime, not trusted.
SHORT_DOC_CHARS = 6000

# The default cache window. Not configurable via the API — the only other
# option is ttl="1h" — so it is a constant here rather than a parameter.
TTL_5M_SECONDS = 300

MAX_TOKENS = 16
ANSWER_STYLE = "Answer in at most five words."

# Three questions so an experiment can vary what comes *after* the breakpoint
# without varying anything before it.
QUESTION_A = f"Which ADR covers chunking? {ANSWER_STYLE}"
QUESTION_B = f"Which ADR covers embeddings? {ANSWER_STYLE}"
QUESTION_C = f"Which ADR covers OCR? {ANSWER_STYLE}"

# What a call did with the cache, derived from the usage counters rather than
# assumed. "extend" is the multi-turn case: read a shorter prefix and wrote a
# longer one in the same request.
Outcome = Literal["write", "read", "extend", "uncached", "error"]
Expected = Union[Outcome, Tuple[Outcome, ...]]


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------


def load_document() -> str:
    """Concatenates the RAG unit's ADRs into one long, stable document.

    Same source as `001_cache_basics.py`: already in the repo, long enough to
    cache, and real prose. This file and 001 stay self-contained on purpose —
    the mechanics are the lesson, so they are spelled out rather than
    imported. `lib/prompt_caching/` is where the reusable versions of the
    block builders and the usage/cost reporting live, and
    `003_cache_in_action.py` is the first file here to use them.
    """
    paths = sorted(ADR_DIR.glob("*.md"))
    if not paths:
        raise FileNotFoundError(f"No ADR files found under {ADR_DIR}")
    return "\n\n".join(f"# {path.name}\n\n{path.read_text()}" for path in paths)


def split_evenly(text: str, parts: int) -> List[str]:
    """Splits text into `parts` roughly equal chunks, one per breakpoint.

    Only the *first* chunk has to clear MIN_CACHEABLE_TOKENS: prefixes are
    cumulative, so every later breakpoint sits on a strictly longer prefix
    and clears the floor automatically.
    """
    size = len(text) // parts + 1
    return [text[i : i + size] for i in range(0, len(text), size)][:parts]


# --------------------------------------------------------------------------
# Request building
# --------------------------------------------------------------------------


def text_block(text: str, *, cached: bool = False, ttl: Optional[Literal["5m", "1h"]] = None) -> TextBlockParam:
    """One system block, optionally carrying a breakpoint.

    `cache_control` is per content block, which is why the system prompt is
    built as a list here rather than passed as a plain string.
    """
    block: TextBlockParam = {"type": "text", "text": text}
    if cached:
        block["cache_control"] = {"type": "ephemeral", "ttl": ttl} if ttl else {"type": "ephemeral"}
    return block


def tag(run_id: str, experiment: str) -> str:
    """The per-run, per-experiment marker that keeps cache entries separate.

    Goes into the first system block — ahead of every breakpoint — so two
    experiments with otherwise identical prefixes hash differently, and a
    re-run does not read the previous run's entries.
    """
    return f"[run {run_id} / experiment {experiment}]"


def adr_catalogue(chars_per_adr: int = 600) -> str:
    """An opening slice of each ADR, used as a long tool description.

    Experiment 5 needs a breakpoint *on a tool*, and the minimum-prefix rule
    applies to the tools prefix just as it does to system: a bare schema is
    ~100 tokens and would never cache. A catalogue of what the tool can look
    up is a realistic way for a real tool definition to get long enough —
    tool-heavy agents clear the floor on tool definitions alone.
    """
    paths = sorted(ADR_DIR.glob("*.md"))
    entries = [f"- {path.stem}: {path.read_text()[:chars_per_adr].strip()}" for path in paths]
    return "\n".join(entries)


def lookup_tool(catalogue: str, *, cached: bool = False, note: str = "") -> ToolParam:
    """A custom tool whose definition is long enough to be worth caching.

    `note` exists only so an experiment can change one detail of the tool and
    watch what that invalidates. The model is never actually expected to call
    this tool — `MAX_TOKENS` is far too small — it is here to occupy the
    front of the prefix.
    """
    tool: ToolParam = {
        "name": "lookup_adr",
        "description": (
            "Look up an architecture decision record by number." + (f" {note}" if note else "") + "\n\n"
            "Records available to this tool:\n" + catalogue
        ),
        "input_schema": {
            "type": "object",
            "properties": {"number": {"type": "string", "description": "ADR number, e.g. 004"}},
            "required": ["number"],
        },
    }
    if cached:
        tool["cache_control"] = {"type": "ephemeral"}
    return tool


# --------------------------------------------------------------------------
# Measurement
# --------------------------------------------------------------------------


def count_tokens(
    client: Anthropic,
    system: List[TextBlockParam],
    question: str,
    tools: Optional[List[ToolParam]] = None,
) -> int:
    """Prefix size, measured on the free counting endpoint.

    Cheaper than inferring it from a paid call, and it never touches the
    cache — so calling it first cannot disturb an experiment.
    """
    messages: List[MessageParam] = [{"role": "user", "content": question}]
    return client.messages.count_tokens(
        model=MODEL,
        system=system,
        messages=messages,
        tools=tools if tools is not None else omit,
    ).input_tokens


def classify(usage: Usage) -> Outcome:
    created = usage.cache_creation_input_tokens or 0
    read = usage.cache_read_input_tokens or 0
    if created and read:
        return "extend"
    if created:
        return "write"
    if read:
        return "read"
    return "uncached"


def report(label: str, usage: Usage, expected: Expected) -> Outcome:
    """Prints the three counters and checks them against what the rule predicts.

    `input_tokens` is only the tokens *after* the last breakpoint, so the full
    prompt size is the sum of all three — which is why a warm call shows a
    tiny `input_tokens` next to a large read.
    """
    wanted = (expected,) if isinstance(expected, str) else expected
    actual = classify(usage)
    mark = "OK " if actual in wanted else "!! "
    created = usage.cache_creation_input_tokens or 0
    read = usage.cache_read_input_tokens or 0

    print(f"  {mark}{label}")
    print(f"       input={usage.input_tokens:<6} created={created:<6} read={read:<6} -> {actual}")
    if created and usage.cache_creation is not None:
        # Which TTL bucket the write landed in. The two are billed
        # differently: 1.25x base input for 5m, 2x for 1h.
        print(
            f"       buckets: 5m={usage.cache_creation.ephemeral_5m_input_tokens} "
            f"1h={usage.cache_creation.ephemeral_1h_input_tokens}"
        )
    if actual not in wanted:
        print(f"       expected {' or '.join(wanted)} — see the notes for this experiment")
    return actual


def send(
    client: Anthropic,
    label: str,
    *,
    system: List[TextBlockParam],
    question: str,
    expect: Expected,
    tools: Optional[List[ToolParam]] = None,
    top_level_cache: bool = False,
) -> Outcome:
    """One measured call. Returns what it did with the cache.

    `BadRequestError` is caught rather than raised because two of the rules
    below are only observable as a 400 — the rejection *is* the result.
    """
    messages: List[MessageParam] = [{"role": "user", "content": question}]
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            tools=tools if tools is not None else omit,
            cache_control={"type": "ephemeral"} if top_level_cache else omit,
        )
    except anthropic.BadRequestError as error:
        wanted = (expect,) if isinstance(expect, str) else expect
        mark = "OK " if "error" in wanted else "!! "
        print(f"  {mark}{label}")
        print(f"       400 {error.message}")
        return "error"
    return report(label, response.usage, expect)


def banner(title: str, note: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'-' * 72}\n{note}")


# --------------------------------------------------------------------------
# Rule 1 — the prefix, and only the prefix
# --------------------------------------------------------------------------


def experiment_prefix(client: Anthropic, document: str, run_id: str) -> None:
    banner(
        "1. prefix-only matching",
        "A breakpoint caches everything before it. Vary what comes after and\n"
        "the entry is reused; change one word before it and the hash differs,\n"
        "so nothing after that point can match either.",
    )

    def system_for(instruction_suffix: str) -> List[TextBlockParam]:
        # The tag and the instructions are the first block; the document is
        # the second and carries the breakpoint. So the breakpoint's prefix
        # is instructions + document, and editing the instructions edits the
        # prefix even though the document is untouched.
        instructions = f"{tag(run_id, 'prefix')} You answer questions about the ADRs below. {instruction_suffix}"
        return [text_block(instructions), text_block(document, cached=True)]

    original = system_for("Cite the ADR number.")
    edited = system_for("Cite the ADR number please.")

    send(client, "cold: first sight of this prefix", system=original, question=QUESTION_A, expect="write")
    send(client, "same prefix, different question (change AFTER)", system=original, question=QUESTION_B, expect="read")
    send(client, "one word added to block 1 (change BEFORE)", system=edited, question=QUESTION_B, expect="write")
    send(client, "back to the original prefix, third question", system=original, question=QUESTION_C, expect="read")

    print(
        "\n  Rule: the breakpoint's prefix must be byte-identical; everything\n"
        "  after it is free to vary. The edited run did not overwrite the\n"
        "  original entry — it created a second one, which is why call 4 still\n"
        "  reads. Two prompt variants means two cache entries, each paying its\n"
        "  own write."
    )


# --------------------------------------------------------------------------
# Rule 2 — the minimum cacheable prefix
# --------------------------------------------------------------------------


def experiment_minimum(client: Anthropic, document: str, run_id: str) -> None:
    banner(
        "2. minimum cacheable prefix",
        f"Below {MIN_CACHEABLE_TOKENS} tokens ({MODEL}) a breakpoint is ignored.\n"
        "There is no error and no warning: both counters simply stay at 0,\n"
        "which is exactly what a 'cache that never hits' looks like.",
    )

    def system_for(slice_chars: int, label: str) -> List[TextBlockParam]:
        header = f"{tag(run_id, f'minimum-{label}')} You answer questions about the ADR excerpt below."
        return [text_block(header), text_block(document[:slice_chars], cached=True)]

    # ~2000 chars is well under the floor for this model; SHORT_DOC_CHARS is
    # well over. Both are measured rather than assumed.
    too_short = system_for(2000, "short")
    long_enough = system_for(SHORT_DOC_CHARS, "long")

    short_tokens = count_tokens(client, too_short, QUESTION_A)
    long_tokens = count_tokens(client, long_enough, QUESTION_A)
    print(f"\n  measured: short prefix ~{short_tokens} tokens, long prefix ~{long_tokens} tokens")
    if short_tokens >= MIN_CACHEABLE_TOKENS or long_tokens < MIN_CACHEABLE_TOKENS:
        raise SystemExit(
            f"This experiment needs one prefix under and one over {MIN_CACHEABLE_TOKENS} "
            f"tokens; got {short_tokens} and {long_tokens}. Adjust the slice sizes."
        )

    send(client, "under the floor, marked: call 1", system=too_short, question=QUESTION_A, expect="uncached")
    send(client, "under the floor, marked: call 2", system=too_short, question=QUESTION_A, expect="uncached")
    send(client, "over the floor, marked: call 1", system=long_enough, question=QUESTION_A, expect="write")
    send(client, "over the floor, marked: call 2", system=long_enough, question=QUESTION_B, expect="read")

    print(
        "\n  Rule: a marker on a short prefix is a silent no-op, so 'created and\n"
        "  read are both 0' is the signature to look for — not an exception.\n"
        "  Check the prefix length with count_tokens before blaming the code."
    )


# --------------------------------------------------------------------------
# Rule 3 — four breakpoints, and no more
# --------------------------------------------------------------------------


def experiment_cap(client: Anthropic, document: str, run_id: str) -> None:
    banner(
        "3. the four-breakpoint cap",
        "Four breakpoints are allowed. A fifth is rejected, and so is four\n"
        "plus top-level automatic caching, because auto-caching needs a free\n"
        "slot to place its own marker in.",
    )

    header = text_block(f"{tag(run_id, 'cap')} You answer questions about the ADRs below.")

    def system_with(parts: int) -> List[TextBlockParam]:
        return [header] + [text_block(chunk, cached=True) for chunk in split_evenly(document, parts)]

    four = system_with(4)
    five = system_with(5)

    # Only the first breakpoint needs to clear the floor: the prefix at each
    # later breakpoint includes every earlier chunk, so it is strictly longer.
    first_prefix = count_tokens(client, four[:2], QUESTION_A)
    print(f"\n  measured: prefix at breakpoint 1 ~{first_prefix} tokens")
    if first_prefix < MIN_CACHEABLE_TOKENS:
        raise SystemExit(
            f"Breakpoint 1 sits on ~{first_prefix} tokens, under the "
            f"{MIN_CACHEABLE_TOKENS} floor — use fewer chunks or a longer document."
        )

    send(client, "4 breakpoints: call 1", system=four, question=QUESTION_A, expect="write")
    send(client, "4 breakpoints: call 2", system=four, question=QUESTION_B, expect=("read", "extend"))
    send(client, "5 breakpoints", system=five, question=QUESTION_A, expect="error")
    send(
        client,
        "4 breakpoints + top-level cache_control",
        system=four,
        question=QUESTION_A,
        expect="error",
        top_level_cache=True,
    )

    print(
        "\n  Rule: 4 per request, shared across tools + system + messages — not\n"
        "  4 each. Top-level cache_control is a convenience that consumes one\n"
        "  of the four, so it composes with three explicit breakpoints, not\n"
        "  four. Spend them on stability boundaries: tools+system, a\n"
        "  per-session prefix, and the last turn or two."
    )


# --------------------------------------------------------------------------
# Rule 4 — TTL, buckets, and the free refresh
# --------------------------------------------------------------------------


def experiment_ttl(client: Anthropic, document: str, run_id: str, *, wait_seconds: int, expire: bool) -> None:
    banner(
        "4. TTL and refresh",
        "5m and 1h are separate buckets, priced differently (1.25x vs. 2x base\n"
        "input to write) and reported separately in usage.cache_creation.\n"
        "Reading an entry refreshes its window for free — but the clock runs\n"
        "from the start of the request that touched it, so generation time\n"
        "counts against the TTL.",
    )

    excerpt = document[:SHORT_DOC_CHARS]

    def system_for(label: str, ttl: Optional[Literal["5m", "1h"]]) -> List[TextBlockParam]:
        header = f"{tag(run_id, f'ttl-{label}')} You answer questions about the ADR excerpt below."
        return [text_block(header), text_block(excerpt, cached=True, ttl=ttl)]

    one_hour = system_for("1h", "1h")
    send(client, 'ttl="1h": cold write lands in the 1h bucket', system=one_hour, question=QUESTION_A, expect="write")
    send(client, 'ttl="1h": read', system=one_hour, question=QUESTION_B, expect="read")

    if wait_seconds <= 0 and not expire:
        print(
            "\n  (skipped the timing parts — they need real waiting.\n"
            "   --ttl-wait 90 shows the free refresh; --expire shows a 5m entry\n"
            "   lapse while the 1h entry above survives the same silence.)"
        )
        return
    if wait_seconds >= TTL_5M_SECONDS:
        raise SystemExit(
            f"--ttl-wait must be under the {TTL_5M_SECONDS}s window, otherwise the entry "
            f"lapses between reads and the refresh is never exercised. Use --expire for that."
        )

    # Showing the refresh takes more than one read: two reads 90s apart both
    # land inside the original 5-minute window, so they would only prove the
    # entry survived 3 minutes. What has to be true is that *cumulative*
    # elapsed time exceeds the TTL while every individual gap stays under it —
    # then a warm read at the end can only be explained by the window having
    # been pushed out along the way. Hence enough gaps to clear the window
    # with a margin, whatever gap size was asked for.
    five_min = system_for("5m", None)

    if wait_seconds > 0:
        gaps = max(2, -(-(TTL_5M_SECONDS + 30) // wait_seconds))
        print(f"\n  {gaps} reads {wait_seconds}s apart = {gaps * wait_seconds}s total, vs. a {TTL_5M_SECONDS}s TTL")
        send(client, "default ttl: cold write (5m bucket)", system=five_min, question=QUESTION_A, expect="write")
        for attempt in range(1, gaps + 1):
            elapsed = wait_seconds * attempt
            print(f"\n  sleeping {wait_seconds}s ...")
            time.sleep(wait_seconds)
            marker = "" if elapsed <= TTL_5M_SECONDS else "  <- past the original window"
            send(client, f"read at {elapsed}s{marker}", system=five_min, question=QUESTION_B, expect="read")

        print(
            f"\n  Rule: the last read is {gaps * wait_seconds}s after the write, well past the\n"
            f"  {TTL_5M_SECONDS}s TTL, and still warm — each read pushed the window out again\n"
            f"  at no cost. The clock starts at request *start*, though, so a slow\n"
            f"  streamed response eats into the gap."
        )

    if not expire:
        return

    if wait_seconds <= 0:
        # The refresh loop above is what normally writes this entry; with
        # --expire on its own it has not run, so write it here.
        send(client, "default ttl: cold write (5m bucket)", system=five_min, question=QUESTION_A, expect="write")

    # This is the whole case for the 1h TTL: the same silence, applied to two
    # entries that differ only in their window. Refreshing is free but only
    # reaches entries that are still alive, so nothing about the 5m entry's
    # earlier reads helps it here.
    lapse = TTL_5M_SECONDS + 30
    print(f"\n  sleeping {lapse}s — longer than the 5m window, shorter than the 1h one ...")
    time.sleep(lapse)
    send(client, f"5m entry after {lapse}s of silence", system=five_min, question=QUESTION_A, expect="write")
    send(client, f"1h entry after the same {lapse}s", system=one_hour, question=QUESTION_C, expect="read")

    print(
        "\n  Rule: the 5m entry lapsed and had to be paid for again, while the 1h\n"
        "  entry written at the top of this experiment read straight through the\n"
        "  same gap. That is what the longer window buys — surviving idle time,\n"
        "  not serving more traffic. It is worth its 2x write (vs. 1.25x) only\n"
        "  when reuse gaps land between 5 minutes and an hour: under 5 minutes\n"
        "  the free refresh already covers you, and over an hour both windows\n"
        "  lapse and the cheaper write wins."
    )


# --------------------------------------------------------------------------
# Rule 5 — the prefix is tools -> system -> messages
# --------------------------------------------------------------------------


def experiment_order(client: Anthropic, document: str, run_id: str) -> None:
    banner(
        "5. render order: tools -> system -> messages",
        "Tools are rendered before system, so a breakpoint on the last system\n"
        "block covers the tool definitions too — and editing a tool busts it.\n"
        "The reverse does not hold: a breakpoint on a tool survives a system\n"
        "change, because invalidation is tiered rather than all-or-nothing.",
    )

    catalogue = adr_catalogue()
    plain_tool = lookup_tool(catalogue)
    edited_tool = lookup_tool(catalogue, note="Prefer the newest record.")

    header = text_block(f"{tag(run_id, 'order-a')} You answer questions about the ADRs below.")
    system = [header, text_block(document, cached=True)]

    print("\n  (a) breakpoint on the last system block, tools present")
    send(client, "cold write", system=system, question=QUESTION_A, expect="write", tools=[plain_tool])
    send(client, "identical tools, new question", system=system, question=QUESTION_B, expect="read", tools=[plain_tool])
    send(
        client,
        "one sentence added to the TOOL, system untouched",
        system=system,
        question=QUESTION_B,
        expect="write",
        tools=[edited_tool],
    )

    # Now move the breakpoint onto the tool itself. The tools prefix has to
    # clear the floor on its own, which is what adr_catalogue() is for.
    cached_tool = lookup_tool(catalogue, cached=True)
    system_a = [text_block(f"{tag(run_id, 'order-b')} You are terse. Answer about the ADRs.")]
    system_b = [text_block(f"{tag(run_id, 'order-b')} You are terse and formal. Answer about the ADRs.")]

    tool_prefix = count_tokens(client, [], QUESTION_A, tools=[cached_tool])
    print(f"\n  (b) breakpoint on the tool definition (~{tool_prefix} tokens of tools)")
    if tool_prefix < MIN_CACHEABLE_TOKENS:
        raise SystemExit(
            f"The tools prefix is ~{tool_prefix} tokens, under the "
            f"{MIN_CACHEABLE_TOKENS} floor — raise chars_per_adr in adr_catalogue()."
        )

    send(client, "cold write (tools only; system is full price)", system=system_a, question=QUESTION_A, expect="write", tools=[cached_tool])
    send(client, "SYSTEM changed, tools untouched", system=system_b, question=QUESTION_A, expect="read", tools=[cached_tool])
    send(
        client,
        "TOOL changed",
        system=system_b,
        question=QUESTION_A,
        expect="write",
        tools=[lookup_tool(catalogue, cached=True, note="Prefer the newest record.")],
    )

    print(
        "\n  Rule: order decides what a breakpoint covers. In (a) the tool sat\n"
        "  inside the cached prefix, so a one-sentence tool edit threw away a\n"
        "  document-sized entry. In (b) the same system edit cost nothing,\n"
        "  because a system change invalidates system + messages but not\n"
        "  tools. Practical consequence: never rebuild the tool list per\n"
        "  request (sort it, freeze it), and keep volatile text out of system."
    )


# --------------------------------------------------------------------------


EXPERIMENTS = ("prefix", "minimum", "cap", "ttl", "order")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the rules of prompt caching empirically.")
    parser.add_argument("--only", choices=EXPERIMENTS + ("all",), default="all", help="run a single experiment")
    parser.add_argument(
        "--run-id",
        default=uuid.uuid4().hex[:8],
        help="tag mixed into every prefix; a fresh value per run keeps runs independent, "
        "a fixed value deliberately shares entries across runs",
    )
    parser.add_argument(
        "--ttl-wait",
        type=int,
        default=0,
        help="seconds between reads in the TTL experiment; must be under the 300s window, "
        "and enough reads are done to push cumulative elapsed time past it (0 skips the timing parts)",
    )
    parser.add_argument(
        "--expire",
        action="store_true",
        help="in the TTL experiment, also wait out the 5-minute window to watch an entry lapse",
    )
    args = parser.parse_args()

    client = Anthropic()
    document = load_document()
    selected: Sequence[str] = EXPERIMENTS if args.only == "all" else (args.only,)

    print(f"model={MODEL}  min_cacheable={MIN_CACHEABLE_TOKENS}  run_id={args.run_id}")
    print(f"document: {len(document)} chars from {ADR_DIR}")

    if "prefix" in selected:
        experiment_prefix(client, document, args.run_id)
    if "minimum" in selected:
        experiment_minimum(client, document, args.run_id)
    if "cap" in selected:
        experiment_cap(client, document, args.run_id)
    if "ttl" in selected:
        experiment_ttl(client, document, args.run_id, wait_seconds=args.ttl_wait, expire=args.expire)
    if "order" in selected:
        experiment_order(client, document, args.run_id)


if __name__ == "__main__":
    main()
