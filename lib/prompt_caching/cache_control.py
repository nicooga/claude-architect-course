"""Building blocks for requests that use prompt caching.

Two things every caching call site needs and nobody wants to re-derive:

  * a way to hang a `cache_control` breakpoint on a content block or a tool
    definition, given that `system="..."` as a plain string has nowhere to
    put one;
  * the model's minimum cacheable prefix, because a breakpoint on a shorter
    prefix is a silent no-op rather than an error.
"""

from typing import Any, Dict, List, Literal, Optional, Sequence, TypeVar, cast

from anthropic.types import CacheControlEphemeralParam, TextBlockParam

TTL = Literal["5m", "1h"]

# The two windows the API offers. 5m is the default and costs 1.25x base
# input to write; 1h costs 2x. See lib/prompt_caching/usage.py for the math.
EPHEMERAL_5M: CacheControlEphemeralParam = {"type": "ephemeral"}
EPHEMERAL_1H: CacheControlEphemeralParam = {"type": "ephemeral", "ttl": "1h"}

# Minimum cacheable prefix, per model. Below this a breakpoint is ignored:
# no error, no warning, both usage counters simply stay at 0.
#
# The floor is *not* monotonic across generations, which is why this is a
# table and not a constant — 512 on the newest models, 4096 on Opus 4.6/4.5
# and Haiku 4.5. Keys are matched as ID prefixes, longest first, so dated
# snapshots ("claude-sonnet-4-5-20250929") resolve to their family.
MIN_CACHEABLE_TOKENS: Dict[str, int] = {
    "claude-opus-5": 512,
    "claude-fable-5": 512,
    "claude-mythos-5": 512,
    "claude-opus-4-8": 1024,
    "claude-sonnet-5": 1024,
    "claude-sonnet-4-6": 1024,
    "claude-sonnet-4-5": 1024,
    "claude-sonnet-4": 1024,
    "claude-opus-4-1": 1024,
    "claude-opus-4-0": 1024,
    "claude-opus-4-7": 2048,
    "claude-opus-4-6": 4096,
    "claude-opus-4-5": 4096,
    "claude-haiku-4-5": 4096,
}

# Caching is a prefix match over the *rendered* request, and this is the
# order it renders in. Kept here as documentation with a name, since every
# question about "what does this breakpoint actually cover?" is answered by
# it: a breakpoint on the last system block covers the tools too.
PREFIX_ORDER = ("tools", "system", "messages")

# A breakpoint looks back at most this many content blocks for an existing
# entry. A single turn that appends more blocks than this (an agentic turn
# with many tool_use/tool_result pairs) can push the previous entry out of
# range, and the next request misses silently.
LOOKBACK_BLOCKS = 20

# Breakpoints per request, shared across tools + system + messages — not
# four each. Top-level `cache_control` consumes one of them.
MAX_BREAKPOINTS = 4


def min_cacheable_tokens(model: str) -> int:
    """The minimum cacheable prefix for `model`.

    Raises rather than guessing a default: silently assuming the wrong floor
    is how a caching bug becomes invisible, since a too-short prefix simply
    never caches.
    """
    for prefix in sorted(MIN_CACHEABLE_TOKENS, key=len, reverse=True):
        if model.startswith(prefix):
            return MIN_CACHEABLE_TOKENS[prefix]
    raise KeyError(
        f"No minimum cacheable prefix known for {model!r}. Look it up in the "
        f"prompt caching docs and add it to MIN_CACHEABLE_TOKENS — the floor "
        f"is per-model and not monotonic across generations."
    )


def cache_control(ttl: Optional[TTL] = None) -> CacheControlEphemeralParam:
    """The breakpoint marker itself. `None` means the default 5-minute window."""
    return EPHEMERAL_1H if ttl == "1h" else EPHEMERAL_5M


def text_block(
    text: str, *, cached: bool = False, ttl: Optional[TTL] = None
) -> TextBlockParam:
    """One text block, optionally carrying a breakpoint.

    `cache_control` is set per content block, so anything cacheable has to be
    built as a list of blocks rather than passed as a plain string.
    """
    block: TextBlockParam = {"type": "text", "text": text}
    if cached:
        block["cache_control"] = cache_control(ttl)
    return block


# Any TypedDict that accepts a `cache_control` key: text/image/document
# blocks, tool_result blocks, and tool definitions. Typed loosely on purpose
# — the SDK spells these as a dozen unrelated TypedDicts, and narrowing them
# here would buy nothing that the call site doesn't already know.
Param = TypeVar("Param", bound=Dict[str, Any])


def with_cache_control(param: Param, *, ttl: Optional[TTL] = None) -> Param:
    """Copy of `param` carrying a breakpoint.

    Copies rather than mutating: the same tool definition or block is often
    reused across requests, and a breakpoint that leaks into a request that
    was meant to be uncached quietly ruins a measurement.
    """
    return cast(Param, {**param, "cache_control": cache_control(ttl)})


def cache_last(
    blocks: Sequence[Param], *, ttl: Optional[TTL] = None
) -> List[Param]:
    """Copy of `blocks` with a breakpoint on the last one, and only there.

    The common placement for a static prefix (instructions + document) and
    for the rolling breakpoint in a multi-turn conversation: the prefix is
    cumulative, so marking the last block covers everything before it with
    one of the four breakpoints. Any marker already present on an earlier
    block is stripped, which is what makes this safe to call per turn — the
    entry an earlier marker created outlives the marker, so moving the
    breakpoint forward loses nothing.
    """
    if not blocks:
        raise ValueError("cache_last() needs at least one block to mark")
    stripped = [
        cast(Param, {key: value for key, value in block.items() if key != "cache_control"})
        for block in blocks
    ]
    stripped[-1] = with_cache_control(stripped[-1], ttl=ttl)
    return stripped
