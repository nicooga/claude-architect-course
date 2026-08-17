# Claude Architect Course

Hands-on exercises working toward the **Claude Architect Certification
Exam**. Each topic is covered by a small exploratory code session inside
[`src/`](src/README.md), supported by reusable code inside [`lib/`](lib) so
later units import shared building blocks instead of copy-pasting them
forward.

- Runtime: Python 3.12+, managed with `uv`.
- Run anything as a module from the project root:
  `uv run python -m src.basic_concepts.001_requests`
- `just typecheck` runs pyright with the same config Pylance uses.
- Requires `ANTHROPIC_API_KEY` in the environment (e.g. `source .envrc`).

## Exam coverage

Required/recommended content and where it lives in this repo.

### Course: Building with the Claude API

| Required topic | Stage | Status |
| --- | --- | --- |
| Accessing Claude with the API | [Stage 1](#stage-1--accessing-claude-with-the-api-done) | Done |
| Tool Use with Claude | [Stage 3](#stage-3--tool-use-with-claude-done) | Done |
| Features of Claude: Prompt Caching | [Stage 4](#stage-4--prompt-caching-done) | Done |
| Features of Claude: Rules of Prompt Caching | [Stage 4](#stage-4--prompt-caching-done) | Done |
| Features of Claude: Prompt Caching in Action | [Stage 4](#stage-4--prompt-caching-done) | Done |
| Model Context Protocol | [Stage 5](#stage-5--model-context-protocol-todo) | To do |

### Course: Introduction to Agent Skills

| Required topic | Stage | Status |
| --- | --- | --- |
| Agent Skills (authoring, structure, progressive disclosure, invocation) | [Stage 6](#stage-6--agent-skills-todo) | To do |

### Extra (not required for the exam)

| Topic | Stage | Status |
| --- | --- | --- |
| Prompt engineering + evaluation pipeline | [Stage 2](#stage-2--prompt-engineering-and-evaluation-done) | Done |
| RAG (chunking, embeddings, vector search, hybrid retrieval) | [Stage 7](#stage-7--rag-optional-exploration-in-progress) | In progress |

## Stages

Ordered so each stage can lean on the one before it. Stages 1-4 are done;
5-6 are the remaining required work; 7 is personal exploration and can be
picked up or dropped at any point.

### Stage 1 - Accessing Claude with the API (done)

[`src/basic_concepts/`](src/basic_concepts/README.md)

The building blocks of the Messages API, one concept per script and no
shared library code yet, so the mechanics stay visible end to end: single
requests, multi-turn loops, system prompts, temperature, streaming, and
structured output via prefill + `stop_sequences`.

- [x] `001_requests.py` - a single `messages.create` call, request/response shape
- [x] `002_looping.py` - multi-turn conversation loop
- [x] `003_system_prompt.py` / `004_system_prompt_ex.py` - steering with `system`
- [x] `005_temperature.py` - determinism vs. creativity
- [x] `006_streaming.py` - `messages.stream`
- [x] `007_structured_data.py` - assistant prefill + `stop_sequences`

### Stage 2 - Prompt engineering and evaluation (done)

[`src/prompt_engineering/`](src/prompt_engineering/README.md)

Treats prompts as something you test and score. Generates a task dataset
with Claude, runs the prompt under test against each task, then grades
mechanically (does the output parse?) and by model. First unit to depend on
`lib/ai_generation`.

- [x] `generate_dataset.py`
- [x] `evaluation_pipeline.py` (syntax grading + model grading + averages)

### Stage 3 - Tool Use with Claude (done)

[`src/tool_usage/`](src/tool_usage/README.md)

Closes three model limitations with tools instead of prompting around them
(no precise time awareness, unreliable date arithmetic, no way to record a
reminder), then contrasts client-executed with server-executed tools. First
unit to depend on `lib/anthropic_adapter` (`ToolPort`/`ChatPort`) and
`lib/repl`.

- [x] `get_current_datetime`, `add_duration_to_datetime`, `set_reminder` - client-executed custom tools
- [x] `str_replace_based_edit_tool` - built-in, schema-less, client-executed
- [x] `web_search` - built-in, fully server-executed
- [x] `repl_smoke_test.py` - all five tools wired into an interactive REPL

### Stage 4 - Prompt caching (done)

[`src/prompt_caching/`](src/prompt_caching/README.md)

Covers all three required lessons: what prompt caching is, the rules that
govern it, and caching in action with measured results. Best placed right
after tool use, because a tool-heavy system prompt plus a long RAG-style
document are the two most natural things to cache, and both already exist
in this repo. First unit to depend on `lib/prompt_caching`.

- [x] `001_cache_basics.py` - add a `cache_control: {"type": "ephemeral"}`
      breakpoint to a long system prompt; print
      `cache_creation_input_tokens` vs. `cache_read_input_tokens` from
      `response.usage` on a cold then warm call.
- [x] `002_cache_rules.py` - demonstrate the rules empirically: prefix-only
      matching (a change before the breakpoint busts the cache, a change
      after it does not), minimum cacheable prefix length, the 4-breakpoint
      cap, TTL/refresh behavior, and the ordering
      (tools -> system -> messages) that determines what the prefix is.
      Each call classifies its own outcome from the usage counters and
      checks it against the rule, so the script is self-verifying; the
      timing parts are opt-in (`--ttl-wait`, `--expire`) because they need
      real waiting.
- [x] `003_cache_in_action.py` - a five-turn conversation over a large cached
      document (a book from `src/rag/library/` when there is one, the ADRs
      otherwise), with tool definitions in front of it. Two breakpoints: the
      last system block for the static prefix (which covers the tools, since
      they render first) and a rolling one on the newest user turn.
      Reports per-turn counters, time-to-first-token, cost, and the cost the
      same turn would have had uncached - derived from the counters
      themselves (`input + created + read` is what an uncached request would
      have billed), with `--replay-uncached` re-sending the recorded
      transcript to check that arithmetic against the API and to supply an
      uncached time-to-first-token to compare against.
- [x] Extract the reusable bits into `lib/prompt_caching/` -
      `cache_control.py` (block/tool breakpoint helpers, the per-model
      minimum-prefix table) and `usage.py` (`TokenUsage`, the write/read
      multipliers, and cost vs. uncached-cost math against a price table).
      `001`/`002` stay self-contained on purpose; `003` imports them.
- [x] `README.md` for the unit, in the style of the other unit READMEs.

### Stage 5 - Model Context Protocol (todo)

`src/mcp/` (to create)

Ties directly back to Stage 3: MCP is the standardized transport for the
same tool-use loop, with the tools living outside the process.

Planned steps:

- [ ] `server/` - a small MCP server exposing a couple of the Stage 3 tools
      (e.g. `get_current_datetime`, `set_reminder`) over stdio, so the
      before/after against the local implementations is direct.
- [ ] `001_mcp_client.py` - an MCP client that connects to the server,
      lists tools/resources/prompts, and calls one, showing the protocol
      primitives explicitly.
- [ ] `002_mcp_repl.py` - bridge the MCP tool list into `lib/repl` via an
      adapter that satisfies the existing `ToolPort`, proving the REPL does
      not care whether a tool is local or remote.
- [ ] `lib/mcp_adapter/` - the MCP-to-`ToolPort` adapter, mirroring how
      `lib/anthropic_adapter` is structured.
- [ ] Note the connection-mode differences (stdio vs. remote/HTTP, and
      Anthropic's server-side MCP connector) in the unit README.
- [ ] `README.md` for the unit.

`lib/repl` gaps against the course's reference CLI (`cli_project`, which
builds its input layer on `prompt_toolkit`). The first two are prerequisites
for this stage; the rest are polish:

- [x] Line editing and history. `lib/repl/repl.py` imports `readline` for its
      side effect - CPython only routes `input()` through GNU readline once
      that module has been imported - and passes the prompt to `input("?> ")`
      rather than printing it first, so readline emits the prompt itself and
      knows its width when it redraws. `lib/repl/stubbed_chat_smoke_test.py`
      drives the REPL against an echo `ChatPort`: run it plain for an
      interactive REPL that costs no tokens, or with `--check` for a
      pty-driven assertion that the up arrow still recalls the previous line.
- [ ] A hook for the two MCP input syntaxes. `run_repl` sends every line
      verbatim as one user message, so there is nowhere for `@resource`
      mentions (read the resource, inject its content as context) or
      `/prompt arg` commands (fetch the server-authored `PromptMessage`s and
      splice them into the history, bypassing the user-turn wrapper) to live.
      An optional line-preprocessor argument on `run_repl` covers both. This
      is an abstraction gap, not a UX one - it exists independently of any
      completion UI.
- [ ] (optional) Tab completion over the server's primitives: `/` opens a
      menu of prompts with their descriptions, `@` opens a menu of resource
      ids, the argument position after `/prompt ` completes resource ids, and
      ghost text hints the prompt's first argument name. Costs a
      `prompt_toolkit` dependency plus a rewrite of the input layer, and
      `001_mcp_client.py` printing the server's inventory already covers
      discoverability. Two things to fix rather than copy if we do build it:
      the reference's completer treats its resource list as `list[str]` in
      the `@` branch but as dicts in the argument-position branch, so
      `/summarize dep<TAB>` silently yields nothing; and its space keybinding
      decides whether an argument is expected by sniffing for `doc`/`file`/`id`
      in the typed value, when MCP's `Prompt.arguments` states it outright.
- [ ] (optional) Ctrl+C cancels an in-flight request instead of exiting the
      loop, and styled prompt / completion-menu colors.

### Stage 6 - Agent Skills (todo)

`src/agent_skills/` (to create)

Covers the "Introduction to Agent Skills" course. Comes after MCP because
skills are the layer above tools: instructions and assets the model loads
on demand, often invoking tools/MCP servers underneath.

Planned steps:

- [ ] `skills/<name>/SKILL.md` - author one real skill with valid YAML
      frontmatter (`name`, `description`), showing what makes a description
      trigger reliably.
- [ ] Progressive disclosure - split the skill into `SKILL.md` plus
      `references/` and a `scripts/` helper, demonstrating that only the
      frontmatter is always in context and the body/resources load on
      demand.
- [ ] `001_skill_invocation.py` - load the skill through the API (skills
      as a container/tool-backed capability) and show it being selected and
      applied to a task.
- [ ] Contrast the delivery surfaces (Claude Code plugin skills vs. API
      skills vs. Claude.app) and note which parts of the authoring format
      are shared.
- [ ] `README.md` for the unit, including the authoring checklist.

### Stage 7 - RAG (optional exploration, in progress)

[`src/rag/`](src/rag/README.md)

Not required for the exam - built out of curiosity, and useful as a corpus
for Stage 4's caching experiments. Has its own ADR log and staged roadmap.

- [x] Ingestion pipeline (pypdf text layer + local doctr OCR)
- [x] Size-based chunking
- [x] Structure-based chunking
- [x] Embeddings + in-memory vector store + semantic chunking
- [x] `search_documents` tool + REPL wiring (semantic-only)
- [ ] Lexical indexing (BM25) + hybrid fusion (RRF)

## Layout

```
lib/                     reusable code imported by units
  ai_generation/         MessageList + chat helpers
  anthropic_adapter/     ChatPort/ToolPort structural interfaces
  prompt_caching/        cache_control block builders + usage/cost reporting
  repl/                  client-agnostic REPL loop
src/                     one directory per unit (see src/README.md)
```
