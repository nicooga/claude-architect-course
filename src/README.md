# Source

Exercises for the Claude Architect course, organized as one directory per
unit. Units are ordered — each builds on concepts from the ones before it —
and are meant to be read/run roughly in this order:

1. [`basic_concepts/`](basic_concepts/README.md)
2. [`prompt_engineering/`](prompt_engineering/README.md)
3. [`tool_usage/`](tool_usage/README.md)
4. [`prompt_caching/`](prompt_caching/README.md)
5. [`mcp_server/`](mcp_server/README.md)
6. `mcp_client/` (planned)
7. `agent_skills/` (planned)
8. [`rag/`](rag/README.md) (optional exploration)

See the [root README](../README.md) for how these units map to the Claude
Architect Certification Exam content and for the plan behind the planned
units.

Shared, reusable code (the `MessageList` helper, the Anthropic chat adapter,
the generic REPL loop, the prompt-caching block builders and usage/cost
reporting, the reminder store and date helpers) lives outside `src/`, in
[`lib/`](../lib), and is imported by later units instead of being copy-pasted
forward.

Run any module from the project root with `uv`, e.g.:

```bash
uv run python -m src.basic_concepts.001_requests
```

## `basic_concepts/`

The building blocks of the Messages API, each script isolating one concept.
No shared library code yet — every file defines its own minimal
`MessageList` so the mechanics are visible end to end.

See [`basic_concepts/README.md`](basic_concepts/README.md) for the
file-by-file breakdown.

## `prompt_engineering/`

Treats prompts as something you test and score, not just write. Builds a
small evaluation pipeline: generate a dataset of tasks, run a prompt
against each, and grade the results both mechanically and by another model
call. This is the first unit to depend on `lib/ai_generation` instead of a
local `MessageList`.

See [`prompt_engineering/README.md`](prompt_engineering/README.md) for the
full write-up.

## `tool_usage/`

Teaches Claude to set reminders for future dates ("remind me a week from
Thursday") by closing three gaps with tools rather than prompting around
them: no precise time awareness, unreliable date arithmetic, and no way to
actually record a reminder. Then adds two of Anthropic's own built-in tools
to contrast client-executed vs. server-executed tool calling. This unit is
the first to depend on `lib.anthropic_adapter` (the `ToolPort`/`ChatPort`
structural interfaces) and `lib.repl` (the client-agnostic REPL loop),
rather than hand-rolling a chat loop per file.

See [`tool_usage/README.md`](tool_usage/README.md) for the full write-up
and manual test script.

## `prompt_caching/`

Covers the feature the way its failure mode demands: every claim is printed
from `response.usage`, because a breakpoint that does not apply raises no
error. One script for the mechanics (cold write, warm read), one that checks
each rule empirically and classifies its own results (prefix matching, the
minimum prefix, the four-breakpoint cap, TTL and refresh, render order), and
one that prices a real multi-turn conversation over a large cached document —
per-turn counters, time-to-first-token, and cost against the uncached
counterfactual. First unit to depend on `lib.prompt_caching`.

See [`prompt_caching/README.md`](prompt_caching/README.md) for the write-up,
the placement pattern, and the measured results.

## `mcp_server/`

Publishes the `tool_usage/` reminders project over the Model Context Protocol,
so the same capabilities stop being Python objects passed to an adapter and
become something any client can discover. One of each primitive, chosen to
make the split visible: five tools (model-controlled), the
`reminders://all` resource (application-controlled) reading exactly the state
the tools write, and a `review_reminders` prompt (user-controlled) that
returns a server-authored assistant turn alongside the user one. Driven from
the MCP Inspector and Claude Code rather than from a client of ours, which is
what keeps resources and prompts out of `lib/repl`'s input layer. The domain
logic is shared with Stage 3 through `lib.reminders`, and the tool schemas are
derived from annotations instead of hand-written.

See [`mcp_server/README.md`](mcp_server/README.md) for the primitive/control
table, the two error channels, and the manual test script.

## `rag/`

Builds a RAG pipeline — chunking, local embeddings, vector search, and
hybrid lexical+semantic retrieval — exposed to the agent as a tool, reusing
`lib.repl` and `lib.anthropic_adapter` exactly as `tool_usage/` does.
Embeddings are generated locally (no third-party API), and the unit avoids
spending against the course's Anthropic API key wherever a local
alternative exists (e.g. OCR for a scan-only source book).

See [`rag/README.md`](rag/README.md) for the full ADR log and staged
roadmap — implementation is in progress.
