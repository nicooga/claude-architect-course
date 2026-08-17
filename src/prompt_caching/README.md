# Prompt Caching

## Goal

Cover the three required prompt-caching lessons — what the feature is, the
rules that govern it, and caching in action with measured results — as three
scripts that answer the question the API can answer for itself. Every claim
in this unit is printed from `response.usage` rather than asserted in prose,
because the failure mode of prompt caching is not an error: a breakpoint that
does not apply is a silent no-op, and "my cache never hits" is a bug you can
only see in the counters.

It sits right after [`tool_usage/`](../tool_usage) because the two most
natural things to cache — a tool-heavy prefix and a long document — both
already exist in this repo: the tool definitions from Stage 3 and the books
from [`rag/`](../rag).

## The one idea

The request prefix is hashed, in render order:

```
tools -> system -> messages
```

A `cache_control: {"type": "ephemeral"}` breakpoint means *everything up to
here can be reused by a later request whose prefix is byte-identical*.
Everything after it is free to vary. That single sentence generates the whole
feature — every rule below is a consequence of it, and every bug is a byte
that changed where you did not expect it to.

## Scripts

Run each as a module from the project root, with `ANTHROPIC_API_KEY` set
(e.g. `source .envrc`).

### `001_cache_basics.py` — cold write, warm read

```bash
uv run python -m src.prompt_caching.001_cache_basics
```

Three calls over the same long system prompt (this repo's own ADRs): one with
no breakpoint as the baseline, then a cold call that writes the cache, then a
warm call that reads it while asking a *different* question. Prints the three
counters for each.

What to look for:

| Call | `cache_creation` | `cache_read` |
| --- | --- | --- |
| no breakpoint | 0 | 0 |
| cold | > 0 | 0 |
| warm | 0 | > 0 |

### `002_cache_rules.py` — the rules, one experiment each

```bash
uv run python -m src.prompt_caching.002_cache_rules
uv run python -m src.prompt_caching.002_cache_rules --only ttl --ttl-wait 90 --expire
```

Five experiments, each of which classifies its own calls from the counters
and checks the verdict against the rule, so a line reading `!!` instead of
`OK ` means the rule (or this repo's understanding of it) is wrong:

1. **prefix** — vary what follows the breakpoint and the entry is reused;
   change one word before it and you get a second entry, not an overwrite.
2. **minimum** — under the model's floor (1024 tokens on Sonnet 4.5) a
   breakpoint is ignored, with no error. Both counters at 0 is the signature.
3. **cap** — four breakpoints per request, shared across tools + system +
   messages. A fifth is a 400, and so is four plus top-level
   `cache_control`, because auto-caching needs a slot of its own.
4. **ttl** — 5m and 1h are separate buckets, priced differently and reported
   separately; a read refreshes the window for free, but only while the
   entry is still alive. The timing parts need real waiting, so they are
   opt-in (`--ttl-wait`, `--expire`).
5. **order** — a breakpoint on the last system block covers the tools too,
   so a one-sentence tool edit throws away a document-sized entry; the
   reverse does not hold, because invalidation is tiered.

Each experiment tags its prefix with a per-run id, so runs are independent
and start genuinely cold. `--run-id fixed` opts back into sharing entries
across runs.

### `003_cache_in_action.py` — what it actually buys

```bash
uv run python -m src.prompt_caching.003_cache_in_action
uv run python -m src.prompt_caching.003_cache_in_action --replay-uncached
```

A five-turn conversation over one large document that never changes (a book
from `src/rag/library/raw/` if there is one, else the ADRs), with tool
definitions in front of it — the shape most applications have. Reports per
turn: the counters, time-to-first-token, what the turn cost, and what the
same turn would have cost with no breakpoint anywhere.

The counterfactual needs no second run, because the counters contain it:

```
prompt tokens = input + cache_creation + cache_read
```

is what the model read this turn either way, and it is exactly what an
uncached request for the same bytes would have billed at full input price.
`--replay-uncached` re-sends the recorded transcript with every breakpoint
removed and checks that arithmetic against the API — the `match` column has
to be `OK` on every row for the comparison to mean anything — and it is what
supplies the uncached time-to-first-token. It is opt-in because it doubles
what the run spends.

The first three turns of a cold run over a ~19k-token document (Sonnet 4.5,
list price):

```
turn  reqs  input   created  read    out    outcome      ttft   total       cost   uncached      saved
--------------------------------------------------------------------------------------------------------
1     1     3       18618    0       69     write       1.19s    3.0s    $0.0709    $0.0569   -$0.0140
2     1     3       87       18618   103    extend      0.90s    3.4s    $0.0075    $0.0577    $0.0502
3     1     3       122      18705   118    extend      0.98s    4.2s    $0.0078    $0.0583    $0.0504
```

Three things in that table are the lesson:

- **Turn 1 is a loss.** It pays 1.25x to write the document and reads
  nothing back. Caching is only ever an investment; a one-shot prompt should
  not carry a breakpoint at all.
- **`input=3`.** The uncached remainder after the last matching breakpoint —
  not the prompt size. Read `input_tokens` as the total and a cached agent
  looks like it is sending nothing.
- **`extend`, not `read`.** Every later turn reads the prefix it matched
  *and* writes the slightly longer one that now includes the previous
  question and answer. That is the rolling breakpoint working.

Totals from cold starts over that same document: **$0.0862 vs. $0.1728 (50%
less) over three turns**, and **$0.0996 vs. $0.2882 (65% less) over five** —
the write is amortised further with every turn. Almost all of it is the
document; the history the turns add contributes very little.

A run started within the TTL of a previous one reads that run's entry on turn
1, skips the write entirely, and reports something like 87% — real savings,
but not what a cold start looks like. `003` names that case in its own output
rather than quietly printing the better number.

**Latency is the part worth being careful about.** Caching skips prefill, and
prefill is over before the first token arrives; generation is untouched. So
total wall clock barely moves and time-to-first-token is where to look — but
even TTFT only separates once the prefix is big. At ~19k tokens the measured
median was 1.1x, inside the run-to-run noise. At `--doc-chars 160000`
(~49k tokens) the same comparison measured **2.3x — 1.0s cached vs. 2.4s
uncached**. Below that, the cost saving is the whole story.

Useful flags: `--document adrs|<path.pdf>`, `--doc-chars`, `--skip-pages`,
`--turns`, `--ttl 1h`, `--run-id`.

## Placement, as used in `003`

Two of the four breakpoints, which is the placement to copy:

1. **The last system block** — the static prefix. Because tools render
   before system, this one marker covers the tool definitions *and* the
   document.
2. **The last block of the newest user turn** — a rolling breakpoint over
   the growing history, moved forward every turn. Moving it costs nothing:
   the entry an earlier marker created outlives the marker, so the previous
   turn's prefix is still readable after its marker is gone.

Two breakpoints are deliberately left spare — for a per-session or per-user
prefix, which is the next thing a real application needs.

There is no breakpoint on the tool definition here: one small schema is a
couple of hundred tokens, far below the 1024-token floor, so a marker there
would be a silent no-op. A tool-heavy agent is the case where a separate
tool breakpoint earns its slot, and experiment 5 in `002` shows what it buys
— tools survive a system-prompt change, because invalidation is tiered.

## What lives in `lib/prompt_caching/`

Extracted so later stages can turn caching on without re-deriving any of it.
`001` and `002` stay self-contained on purpose — the mechanics are their
lesson — and `003` is the first file here to import them.

- `cache_control.py` — `text_block()`, `with_cache_control()`, `cache_last()`
  for hanging a breakpoint on a block or a tool definition, plus
  `min_cacheable_tokens(model)`. The floor is a per-model table rather than a
  constant because it is **not** monotonic across generations: 512 tokens on
  Opus 5, 1024 on Sonnet 4.5, 4096 on Opus 4.6 and Haiku 4.5. It raises on an
  unknown model instead of guessing, since guessing low is invisible.
- `usage.py` — `TokenUsage` (the counters, addable across requests and turns,
  with `prompt_tokens` and `outcome` derived rather than assumed), the
  multipliers (`1.25x` 5m write, `2x` 1h write, `0.1x` read), the break-even
  call counts that follow from them, and `cost_usd` / `uncached_cost_usd` /
  `savings_usd` against a per-model price table.

Prices are list prices as published in February 2026, and the table is easy
to leave stale: treat any dollar figure these scripts print as a way to
compare two runs of the same script, not as a quote.

## Gotchas worth carrying forward

- **`input_tokens` is the uncached remainder, not the prompt.** Total prompt
  size is the sum of the three counters.
- **Caches are model-scoped.** Changing the model discards every entry, so
  `MODEL` and the floor constant have to move together.
- **A short prefix fails silently.** Check it with `count_tokens` (free), or
  read turn 1's `created` — 0 means the marker did nothing.
- **Never rebuild the tool list per request.** Tools render first, so an
  unsorted `dict` or a per-user tool set invalidates everything behind it.
  Same for anything volatile in the system prompt: `datetime.now()`, a
  request id, a session id.
- **A cache entry can outlive the run that wrote it.** A rerun inside the TTL
  reads the previous run's entries and reports savings a cold start could not
  reproduce — which is why both `002` and `003` mix a per-run id into the
  prefix ahead of every breakpoint.
- **`count_tokens` can fail while `messages.create` is fine.** It did during
  this unit's development (500s for an hour), which is why `003` treats the
  prefix measurement as optional and falls back to the counters.
