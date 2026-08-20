# MCP Server

## Goal

Take the reminders project from [`tool_usage/`](../tool_usage) and publish it
over the Model Context Protocol, so the capabilities stop being Python objects
handed to an adapter inside one process and become something any client can
discover and call. Same three gaps, same domain logic — `lib/reminders` is
imported by both sides — but a different delivery.

Building the server before the client ([Stage 6](../mcp_client)) is
deliberate: a server can be driven end to end by clients that already exist,
so a failure is a failure in the server rather than in a half-written client.

## The one idea

MCP has three primitives, and what separates them is not what they can do but
**who is allowed to reach for them**:

| Primitive | Controlled by | Who initiates |
| --- | --- | --- |
| Tool | the model | Claude, mid-turn, from the tool list |
| Resource | the application | the client, deciding what context to attach |
| Prompt | the user | a person, invoking it by name |

That split is the whole reason a client cannot expose all three the same way.
Tools need no user interface at all — they ride in the `tools` request
parameter and Claude picks. Resources and prompts have no other entry point
than the keyboard, which is why Claude Code renders one as an `@` mention and
the other as `/mcp__<server>__<prompt>`, and why a REPL that sends every line
verbatim as one user message (like [`lib/repl`](../../lib/repl)) has nowhere
to put them.

## What the server exposes

One of each primitive, over the reminders domain, in
[`server.py`](server.py).

### Tools — model-controlled

| Tool | Comes from |
| --- | --- |
| `get_current_datetime` | Stage 3, gap #1: no precise clock |
| `add_duration_to_datetime` | Stage 3, gap #2: unreliable date arithmetic |
| `set_reminder` | Stage 3, gap #3: no way to record anything |
| `list_reminders` | new — the read side |
| `delete_reminder` | new — and the failure demo |

All three Stage 3 tools cross over, not just the interesting two: the gaps
travel together, and dropping `add_duration_to_datetime` puts the model back
to computing "a week from Thursday" in its head, which is the unreliability
Stage 3 exists to remove.

The schemas are **not** hand-written here. Stage 3 spells out an
`input_schema` dict per tool; the SDK derives the same thing from the type
annotations and the description from the docstring:

```python
@mcp.tool()
def set_reminder(message: str, datetime: str) -> str:
    """Records a reminder for a future datetime. ..."""
```

```json
{"properties": {"message": {"title": "Message", "type": "string"},
                "datetime": {"title": "Datetime", "type": "string"}},
 "required": ["message", "datetime"], "type": "object"}
```

That correspondence is what Stage 6 rests on: the model receives the same
tool definition either way and cannot tell where the tool lives.

### Resource — application-controlled

`reminders://all` renders the reminder list as JSON. It reads exactly the
state the tools write, which is the point: the same data reached through a
primitive with a different controller. Set a reminder with the tool, then
read the resource and watch it change — but note that *you* attached it,
whereas Claude chose to call the tool.

### Prompt — user-controlled

`review_reminders(timeframe)` returns two messages, and the second one is the
**assistant's**:

```
[user]      Review my reminders for this week. For each one tell me whether…
[assistant] I'll start by calling list_reminders to see everything that is
            scheduled, then get_current_datetime so I can tell past from…
```

A server-authored turn on Claude's side of the conversation is what separates
an MCP prompt from a canned string or a local skill. It also fixes the shape
of the client-side seam: a `str -> str` preprocessor cannot express this, so
a REPL that wants prompts needs a line expander returning a *list* of
messages.

## The two error channels

A tool that fails is not a protocol that failed, and MCP keeps them apart. A
tool error is a **successful** JSON-RPC response carrying `isError: true` —
the model sees it and can recover. A JSON-RPC error means the call never
reached a tool at all, and the model never sees anything.

`delete_reminder` shows the first: a real id succeeds, an unknown one raises,
and the SDK wraps any non-`MCPError` exception out of a tool into
`isError: true`.

Measured against this server, the split is not where you would guess:

| Call | Channel |
| --- | --- |
| `delete_reminder` with an unknown id | result, `isError: true` |
| `tools/call` with an unknown tool name | result, `isError: true` |
| `tools/call` missing a required argument | result, `isError: true` |
| `prompts/get` with an unknown prompt name | JSON-RPC error |
| `resources/read` on an unregistered URI | JSON-RPC error |

`tools/call` is effectively a one-channel surface: even protocol-level
mistakes come back as tool errors, because anything reaching the model is
something the model might recover from. The other two primitives, which no
model chose to invoke, raise properly. Stage 6's adapter therefore maps
`isError` onto its own `is_error` tool result and lets `MCPError` propagate.

## State

Reminders live in a JSON file, not in memory. Every stdio client spawns its
own copy of the server, so process-local state would mean the Inspector
showing an empty list immediately after Claude Code set a reminder — and the
resource demo showing nothing at all.

Default path `~/.claude-architect-course/reminders.json`, overridable with
`MCP_REMINDERS_PATH`. Absolute on purpose: each client launches the server
from whatever directory it happens to be in, and a relative path would
scatter one file per launch directory. A missing file is an empty list, not
an error.

## Running it

`lib.reminders` resolves under all of these without any `sys.path` help,
because the project is installed editable into `.venv` — the server does not
have to be run as `python -m`, which matters because these launchers load the
file by path.

```bash
# MCP Inspector
uv run mcp dev src/mcp_server/server.py

# stdio, for a client to spawn
uv run mcp run src/mcp_server/server.py

# streamable HTTP on 127.0.0.1:8000/mcp
uv run mcp run src/mcp_server/server.py --transport streamable-http
```

`tools/list` is identical across both transports, with no code change — the
precondition for Stage 6's transport comparison.

## Manual test script

### In the Inspector (`uv run mcp dev src/mcp_server/server.py`)

- **Tools** — `tools/list` shows five, with generated schemas. Call
  `get_current_datetime`, feed its result to `add_duration_to_datetime` with
  `weeks: 1`, feed *that* to `set_reminder`. This is the Stage 3 chain, done
  by hand.
- **Resources** — read `reminders://all` and confirm the reminder you just
  set is in it.
- **Prompts** — `prompts/get` `review_reminders` with `timeframe: this week`,
  and check that two messages come back with `user` and `assistant` roles.
- **Errors** — call `delete_reminder` with a garbage id. The response is a
  *result* with `isError: true`, not a protocol error. Then delete a real id
  and confirm `list_reminders` shrinks.

### In Claude Code

Register the **venv interpreter directly**, not `uv run`:

```bash
claude mcp add reminders -- "$PWD/.venv/bin/python" "$PWD/src/mcp_server/server.py"
```

Then `/mcp` to confirm it connected. The resource appears as an `@` mention
and the prompt as `/mcp__reminders__review_reminders`. Ask it
`Set a reminder for my doctor's appointment. It's a week from Thursday.` and
watch the same three-tool chain happen over the protocol.

`uv run mcp run ...` is the right thing to type by hand and the wrong thing to
register, because a client relaunches the server on every connect and every
reconnect. Before `uv run` execs anything it re-resolves the lockfile and
verifies all 129 requirements are present, which means stat-walking a 5.4 GB
tree — this project pulls in torch, the nvidia CUDA runtime and triton via
`python-doctr[torch]` and `sentence-transformers`, none of which this server
imports. Warm, that check costs milliseconds. Cold, on a filesystem where
metadata is expensive (WSL2, network mounts), it has taken over 30s here and
blown Claude Code's 30s connect timeout:

```
Connection failed after 31586ms (CONNECT_TIMEOUT): Request timed out
Successfully connected (transport: stdio) in 15331ms      # same server, warmer
Successfully connected (transport: stdio) in 5386ms       # warmer still
```

The venv interpreter skips the check entirely and starts in under a second,
cold or warm. `MCP_TIMEOUT` (milliseconds) raises the client's patience if you
ever do need the `uv run` form, but it treats the symptom.

Claude Code's own log for the server is the place to confirm any of this:
`~/.cache/claude-cli-nodejs/<slugified-project-path>/mcp-logs-reminders/`.

This is what covers resources and prompts for the exam topic: `lib/repl`
never has to grow an input syntax, because clients that render all three
already exist.
