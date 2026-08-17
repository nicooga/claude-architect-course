"""Reading `response.usage` when prompt caching is on, and pricing it.

Three counters describe the input side of a cached request, and the trap is
that they are disjoint rather than nested:

    prompt tokens = input_tokens + cache_creation_input_tokens + cache_read_input_tokens

`input_tokens` is only the uncached remainder — the tokens after the last
breakpoint that matched. An agent that ran for an hour and reports
`input_tokens: 4000` did not send 4000 tokens; the rest came from the cache.
Every derived number here (what a call did, what it cost, what it would have
cost uncached) is computed from those counters, never assumed.
"""

from dataclasses import dataclass
from typing import Dict, Literal

from anthropic.types import Usage

# What a call did with the cache, derived from the counters. "extend" is the
# multi-turn case: read a shorter prefix and wrote a longer one in the same
# request, which is what a rolling breakpoint over a growing conversation
# looks like once it is warm.
Outcome = Literal["write", "read", "extend", "uncached"]

# Multipliers on the model's base *input* price. A write costs more than
# plain input because the entry is stored; a read is the whole point.
CACHE_WRITE_5M = 1.25
CACHE_WRITE_1H = 2.0
CACHE_READ = 0.1

# Break-even, straight from those multipliers: with the 5m window a second
# request already pays for the write (1.25 + 0.1 < 2 uncached sends); with
# the 1h window it takes a third (2 + 0.2 < 3). Below these counts caching
# is a loss, which is why one-shot prompts should not carry a breakpoint.
BREAK_EVEN_CALLS_5M = 2
BREAK_EVEN_CALLS_1H = 3


@dataclass(frozen=True)
class Prices:
    """Published list price per million tokens, for one model."""

    input_per_mtok: float
    output_per_mtok: float


# Per-model list prices in USD per million tokens, as published in
# February 2026. Cheap to state, cheap to get wrong: treat a number printed
# by this module as an estimate for comparing two runs of the same script,
# not as a quote. Keys are matched as ID prefixes, longest first, so dated
# snapshots ("claude-sonnet-4-5-20250929") resolve to their family.
PRICES: Dict[str, Prices] = {
    "claude-opus-5": Prices(5.00, 25.00),
    "claude-opus-4-8": Prices(5.00, 25.00),
    "claude-sonnet-5": Prices(3.00, 15.00),
    "claude-sonnet-4-6": Prices(3.00, 15.00),
    "claude-sonnet-4-5": Prices(3.00, 15.00),
    "claude-haiku-4-5": Prices(1.00, 5.00),
}


def prices_for(model: str) -> Prices:
    """List prices for `model`. Raises rather than guessing."""
    for prefix in sorted(PRICES, key=len, reverse=True):
        if model.startswith(prefix):
            return PRICES[prefix]
    raise KeyError(
        f"No prices known for {model!r}. Add them to PRICES from the pricing "
        f"page — a wrong multiplier makes every cost figure here fiction."
    )


@dataclass(frozen=True)
class TokenUsage:
    """The counters from one request, or the sum of several.

    Flat and additive so a turn that took two requests (a tool-use loop) and
    a whole conversation can be described by the same type.
    """

    input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    # The write, split by which window it landed in. The two are priced
    # differently, so the split is what makes a 1h experiment auditable.
    created_5m: int = 0
    created_1h: int = 0
    requests: int = 0

    @classmethod
    def from_usage(cls, usage: Usage) -> "TokenUsage":
        creation = usage.cache_creation
        return cls(
            input_tokens=usage.input_tokens,
            cache_creation_tokens=usage.cache_creation_input_tokens or 0,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
            output_tokens=usage.output_tokens,
            created_5m=creation.ephemeral_5m_input_tokens if creation else 0,
            created_1h=creation.ephemeral_1h_input_tokens if creation else 0,
            requests=1,
        )

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            created_5m=self.created_5m + other.created_5m,
            created_1h=self.created_1h + other.created_1h,
            requests=self.requests + other.requests,
        )

    @property
    def prompt_tokens(self) -> int:
        """Everything the model read: cached and uncached alike.

        This is the number an uncached run of the same request would have
        billed at full input price, which makes it the honest baseline for
        any "what did caching save?" claim.
        """
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens

    @property
    def outcome(self) -> Outcome:
        if self.cache_creation_tokens and self.cache_read_tokens:
            return "extend"
        if self.cache_creation_tokens:
            return "write"
        if self.cache_read_tokens:
            return "read"
        return "uncached"

    def cost_usd(self, prices: Prices) -> float:
        """What this usage was billed, at list price.

        The write is priced from the per-window split rather than from
        `cache_creation_tokens`, because 5m and 2x-priced 1h writes can both
        appear in one request.
        """
        per_input_token = prices.input_per_mtok / 1_000_000
        return (
            self.input_tokens * per_input_token
            + self.created_5m * per_input_token * CACHE_WRITE_5M
            + self.created_1h * per_input_token * CACHE_WRITE_1H
            + self.cache_read_tokens * per_input_token * CACHE_READ
            + self.output_tokens * prices.output_per_mtok / 1_000_000
        )

    def uncached_cost_usd(self, prices: Prices) -> float:
        """The counterfactual: the same bytes with no breakpoint anywhere.

        Output is unaffected by caching, so it carries over unchanged and
        only the input side is re-priced.
        """
        return (
            self.prompt_tokens * prices.input_per_mtok / 1_000_000
            + self.output_tokens * prices.output_per_mtok / 1_000_000
        )

    def savings_usd(self, prices: Prices) -> float:
        """Positive when caching paid off, negative when it cost more.

        Negative is a real outcome, not a bug: a prefix written once and never
        read again is billed at 1.25x for nothing.
        """
        return self.uncached_cost_usd(prices) - self.cost_usd(prices)


def format_tokens(usage: TokenUsage) -> str:
    """One-line counter dump, aligned for stacking under each other."""
    return (
        f"input={usage.input_tokens:<7} created={usage.cache_creation_tokens:<7} "
        f"read={usage.cache_read_tokens:<7} out={usage.output_tokens:<6} "
        f"prompt={usage.prompt_tokens:<7} {usage.outcome}"
    )
