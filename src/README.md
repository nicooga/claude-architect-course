# Source

Exercises for the Claude Architect course, organized as one directory per
unit. Units are ordered — each builds on concepts from the ones before it —
and are meant to be read/run roughly in this order:

1. [`basic_concepts/`](#basic_concepts)
2. [`prompt_engineering/`](#prompt_engineering)
3. [`tool_usage/`](#tool_usage)

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

| File | Concept |
| --- | --- |
| `001_requests.py` | A single `messages.create` call and the request/response shape. |
| `002_looping.py` | Turning single calls into a multi-turn conversation loop (a REPL). |
| `003_system_prompt.py` | Steering behavior with a `system` prompt (a Socratic math tutor). |
| `004_system_prompt_ex.py` | A second system prompt example, with a mistake left in on purpose — two `SYSTEM_PROMPT` assignments, only the second takes effect. |
| `005_temperature.py` | Comparing `temperature=0.0` (near-deterministic) vs. `temperature=1.0` (creative) on the same prompt. |
| `006_streaming.py` | Streaming responses token-by-token with `messages.stream` instead of waiting for the full response. |
| `007_structured_data.py` | Constraining output format via assistant-message prefill + `stop_sequences`, rather than asking nicely in the prompt. |

## `prompt_engineering/`

Treats prompts as something you test and score, not just write. Builds a
small evaluation pipeline: generate a dataset of tasks, run a prompt against
each, and grade the results both mechanically and by another model call.

- `generate_dataset.py` — uses Claude to generate `dataset.data.json`, a set
  of tasks that each require a Python function, a JSON object, or a regex to
  solve.
- `evaluation_pipeline.py` — for each task: runs the prompt under test
  (`run_prompt`), checks the output actually parses for its target format
  (`grade_by_syntax`), and has a model grade it 1–10 on quality
  (`grade_by_model`, with retry-on-malformed-JSON). Writes
  `evaluation_results.data.json` with per-task scores and an average.
- `dataset.data.json` / `evaluation_results.data.json` — generated
  artifacts, checked in as a worked example rather than hand-written.

This is the first unit to depend on `lib/ai_generation` instead of a
local `MessageList`.

Run with:

```bash
uv run python -m src.prompt_engineering.generate_dataset
uv run python -m src.prompt_engineering.evaluation_pipeline
```

## `tool_usage/`

Teaches Claude to set reminders for future dates ("remind me a week from
Thursday") by closing three gaps with tools rather than prompting around
them: no precise time awareness, unreliable date arithmetic, and no way to
actually record a reminder. Then adds two of Anthropic's own built-in tools
to contrast client-executed vs. server-executed tool calling.

- `tools/current_datetime.py` — `get_current_datetime`: precise "now",
  client-executed.
- `tools/add_duration_to_datetime.py` — `add_duration_to_datetime`: date
  arithmetic offloaded from the model, client-executed.
- `tools/set_reminder.py` — `set_reminder`: the actual side effect,
  client-executed.
- `tools/text_editor.py` — Anthropic's built-in `str_replace_based_edit_tool`.
  Schema-less (Claude already knows its input shape); our job is just to
  execute `view`/`create`/`str_replace`/`insert`, confined to a configured
  working directory since the path is untrusted model output.
- `tools/web_search.py` — Anthropic's built-in `web_search`. Fully
  server-executed — Claude issues the search and reads results on
  Anthropic's side, so there's no `execute` to call at all; we just declare
  and register it.
- `repl_smoke_test.py` — an interactive REPL wired up with all five tools
  (via `lib.repl` + `lib.anthropic_adapter`) for manually exercising the
  chapter. See `tool_usage/README.md` for what to try at the prompt.

This unit is the first to depend on `lib.anthropic_adapter` (the
`ToolPort`/`ChatPort` structural interfaces) and `lib.repl` (the
client-agnostic REPL loop), rather than hand-rolling a chat loop per file.

See [`tool_usage/README.md`](tool_usage/README.md) for the full write-up and
manual test script.
