# Source

Exercises for the Claude Architect course, organized as one directory per
unit. Units are ordered — each builds on concepts from the ones before it —
and are meant to be read/run roughly in this order:

1. [`basic_concepts/`](basic_concepts/README.md)
2. [`prompt_engineering/`](prompt_engineering/README.md)
3. [`tool_usage/`](tool_usage/README.md)
4. `prompt_caching/` (in progress)
5. `mcp/` (planned)
6. `agent_skills/` (planned)
7. [`rag/`](rag/README.md) (optional exploration)

See the [root README](../README.md) for how these units map to the Claude
Architect Certification Exam content and for the plan behind the planned
units.

Shared, reusable code (the `MessageList` helper, the Anthropic chat adapter,
the generic REPL loop) lives outside `src/`, in [`lib/`](../lib), and is
imported by later units instead of being copy-pasted forward.

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

## `rag/`

Builds a RAG pipeline — chunking, local embeddings, vector search, and
hybrid lexical+semantic retrieval — exposed to the agent as a tool, reusing
`lib.repl` and `lib.anthropic_adapter` exactly as `tool_usage/` does.
Embeddings are generated locally (no third-party API), and the unit avoids
spending against the course's Anthropic API key wherever a local
alternative exists (e.g. OCR for a scan-only source book).

See [`rag/README.md`](rag/README.md) for the full ADR log and staged
roadmap — implementation is in progress.
