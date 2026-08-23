"""The Stage 3 reminders project, re-exposed over MCP.

Same three gaps, same domain logic (`lib/reminders`), different delivery:
instead of `ToolPort` classes handed to `AnthropicChatAdapter` inside one
process, the capabilities are published over a protocol and any client can
pick them up. Two things become possible that were not before — a read side
worth exposing (`list_reminders` and the `reminders://all` resource), and
server-authored conversation (the `review_reminders` prompt).

One of each primitive is deliberate, because the three differ in who is
allowed to reach for them:

    tools      model-controlled        Claude decides, mid-turn
    resources  application-controlled  the client decides what to attach
    prompts    user-controlled         a person invokes them by name

Run it:

    uv run mcp dev src/mcp_server/server.py                        # Inspector
    uv run mcp run src/mcp_server/server.py                        # stdio
    uv run mcp run src/mcp_server/server.py --transport streamable-http

The server object is module-level and named `mcp` because that is one of the
names `mcp run`/`mcp dev` look for. `lib.reminders` imports cleanly under all
of them: the project is installed editable into `.venv`, so resolution does
not depend on the cwd the client happens to launch us from.
"""

import json
import os
import sys
from typing import Any, Dict, List

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.prompts.base import AssistantMessage, Message, UserMessage
from mcp.server.transport_security import TransportSecuritySettings

from lib.reminders import JsonFileReminderStore, add_duration, now_iso

# File-backed on purpose. Every stdio client spawns its own server process,
# so in-memory state would mean the Inspector showing an empty list right
# after Claude Code set a reminder — and the resource demo showing nothing.
store = JsonFileReminderStore()

mcp = MCPServer(
    name="reminders",
    instructions=(
        "Set and review reminders. Never compute a date yourself: call "
        "get_current_datetime for 'now', then add_duration_to_datetime for "
        "any relative offset, and only then set_reminder."
    ),
)


# --- Tools: model-controlled ------------------------------------------------
#
# No `input_schema` here, unlike the Stage 3 tools in
# src/tool_usage/tools/. The SDK derives it from the type annotations and
# the description from the docstring, which is what Stage 6 diffs against
# the hand-written dicts — the claim being that the model cannot tell the
# difference.


@mcp.tool()
def get_current_datetime(utc_offset_hours: float) -> str:
    """Returns the current date and time in ISO 8601 format at the given UTC
    offset. Required, with no default: this server has no way to know the
    caller's timezone on its own, and 'today'/'tomorrow' depend on the local
    calendar day, which UTC and a user's offset can disagree about at any
    given moment. Use this whenever you need to know 'now' - for example, as
    the starting point for computing a relative date like 'a week from
    Thursday'."""
    return now_iso(utc_offset_hours=utc_offset_hours)


@mcp.tool()
def add_duration_to_datetime(
    datetime: str,
    weeks: float = 0,
    days: float = 0,
    hours: float = 0,
    minutes: float = 0,
) -> str:
    """Adds a duration to an ISO 8601 datetime and returns the resulting ISO
    8601 datetime. Use this instead of computing dates yourself — pass the
    starting datetime (e.g. from get_current_datetime) and the offset
    expressed in weeks/days/hours/minutes."""
    return add_duration(datetime, weeks=weeks, days=days, hours=hours, minutes=minutes)


@mcp.tool()
def set_reminder(message: str, datetime: str) -> str:
    """Records a reminder for a future datetime. Use this once you have a
    concrete ISO 8601 datetime for when the reminder should fire — compute it
    first with get_current_datetime and add_duration_to_datetime if the user
    gave a relative time."""
    reminder = store.add(message=message, datetime=datetime)
    return f"Reminder {reminder.id} set for {reminder.datetime}: {reminder.message}"


@mcp.tool()
def list_reminders() -> str:
    """Returns every reminder currently recorded, with its id, message and
    scheduled datetime. Use this before answering any question about what is
    already scheduled, and to find the id of a reminder to delete."""
    reminders = store.list()
    if not reminders:
        return "No reminders are currently set."
    return "\n".join(f"{r.id}  {r.datetime}  {r.message}" for r in reminders)


@mcp.tool()
def delete_reminder(reminder_id: str) -> str:
    """Deletes the reminder with the given id. Call list_reminders first if
    you do not already know the id."""
    # The tool error channel. This raise comes back as a *successful*
    # JSON-RPC response carrying isError: true, because the SDK catches any
    # non-MCPError exception out of a tool and wraps it that way — the model
    # sees the failure and can recover from it, which is the entire point of
    # the separate channel.
    #
    # tools/call is in fact a one-channel surface: measured against this
    # server, an unknown tool name and a schema-violating argument also come
    # back as isError: true, not as protocol errors. What does raise a real
    # JSON-RPC error is the other two primitives — prompts/get with an
    # unknown name, resources/read with an unregistered URI — and that
    # asymmetry is the thing worth seeing. Stage 6's ToolPort adapter maps
    # isError onto its own `is_error` tool result and lets MCPError
    # propagate, because only the first is something Claude can act on.
    try:
        removed = store.delete(reminder_id)
    except KeyError:
        raise ValueError(
            f"No reminder with id {reminder_id!r}. Call list_reminders to see valid ids."
        )
    return f"Deleted reminder {removed.id}: {removed.message}"


# --- Resource: application-controlled ---------------------------------------


@mcp.resource(
    "reminders://all",
    name="All reminders",
    description="The full reminder list as JSON, as the tools currently see it.",
    mime_type="application/json",
)
def all_reminders() -> str:
    """The same state the tools read and write, reached through a different
    primitive. Set a reminder with the tool, then read this: the client
    attaches it as context on its own initiative (Claude Code renders it as
    an `@` mention), rather than Claude deciding to call it mid-turn."""
    payload: List[Dict[str, Any]] = [reminder.as_dict() for reminder in store.list()]
    return json.dumps(payload, indent=2)


# --- Prompt: user-controlled ------------------------------------------------


@mcp.prompt()
def review_reminders(timeframe: str) -> List[Message]:
    """Walk through the reminders falling in a given timeframe (e.g. 'this
    week', 'the next 3 days') and suggest what to reschedule or drop."""
    # Two messages, and the second one is the assistant's. That is the whole
    # difference between an MCP prompt and a local skill or a canned string:
    # the server writes turns on both sides of the conversation, so it can
    # put a commitment in Claude's mouth before Claude has said anything.
    # A `str -> str` client-side preprocessor cannot express this, which is
    # why lib/repl would need a line expander returning message lists.
    return [
        UserMessage(
            f"Review my reminders for {timeframe}. For each one tell me whether "
            "it still makes sense, and flag anything already in the past."
        ),
        AssistantMessage(
            "I'll start by calling list_reminders to see everything that is "
            "scheduled, then get_current_datetime so I can tell past from "
            "future, and I'll go through them one by one."
        ),
    ]


if __name__ == "__main__":
    # `mcp run --transport ...` imports this module and calls mcp.run() with
    # the transport itself, so this branch only matters when the file is run
    # directly. Same server object either way.
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"

    run_kwargs: Dict[str, Any] = {}
    if transport == "streamable-http" and os.environ.get("MCP_ALLOW_ANY_HOST"):
        # Binding host="127.0.0.1" (the default) auto-enables DNS-rebinding
        # protection: the SDK only accepts Host/Origin headers naming
        # localhost. Right for every normal launch here — Inspector, Claude
        # Code, a same-machine client — but it also rejects a request
        # forwarded through a reverse proxy/tunnel that preserves the
        # original public Host header (Stage 6's ngrok tunnel, for one).
        # Opt-in only, and only for this transport, so every other caller
        # keeps the protection on by default.
        run_kwargs["transport_security"] = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    mcp.run(transport, **run_kwargs)  # type: ignore[arg-type]
