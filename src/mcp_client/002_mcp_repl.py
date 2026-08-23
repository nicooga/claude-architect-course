"""MCP client, second experiment: the REPL with its tool list built from a
server instead of from local imports.

001_mcp_client.py drove the raw protocol by hand. This file drives the same
Stage 5 reminders server through lib/mcp_adapter's ToolPort wrapper and
lib/repl's run_repl — the Stage 3 REPL, unmodified, now talking to a remote
tool set instead of local `src/tool_usage/tools` classes. Not both at once:
that would just duplicate the same five reminder tools under two names and
give the model two ways to do the same thing.

The claim the whole stage rests on — Claude cannot tell where a tool lives —
gets checked before the REPL even starts, by diffing the `tools` request
parameter AnthropicChatAdapter would actually send for a local set_reminder
against the MCP-backed one. They are *not* byte-identical JSON: the MCP
schema is auto-derived from type hints/docstring (fastmcp/Pydantic), so it
carries a `title` per property and a top-level one, drops per-property
`description`, and wraps the docstring across lines instead of one hand-
written sentence. What does match, and is what's asserted below, is the
part Claude actually acts on: the tool name, the required argument names,
and each property's JSON type. The `title`/formatting noise is metadata
Claude ignores either way.

Run it:

    uv run python -m src.mcp_client.002_mcp_repl
"""

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from lib.anthropic_adapter import AnthropicChatAdapter, ToolPort
from lib.mcp_adapter import mcp_tools
from lib.repl import run_repl
from src.tool_usage.tools import SetReminderTool

SERVER_PATH = Path(__file__).parent.parent / "mcp_server" / "server.py"

SYSTEM_PROMPT = (
    "You are a helpful assistant that manages the user's reminders. Use "
    "get_current_datetime and add_duration_to_datetime to compute a concrete "
    "ISO 8601 datetime before calling set_reminder, and list_reminders / "
    "delete_reminder to review or clean up what's already recorded."
)


@asynccontextmanager
async def reminders_session() -> AsyncIterator[ClientSession]:
    """Spawns the Stage 5 reminders server as a subprocess over stdio and
    hands back an initialized ClientSession. Everything downstream of this —
    mcp_tools(), AnthropicChatAdapter, run_repl — only ever sees the
    resulting ToolPort list. The REPL in particular has no idea an MCP
    session, let alone a subprocess, is behind its tools; that's the same
    ChatPort/ToolPort seam Stage 3 built."""
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def to_tool_param(tool: ToolPort) -> Dict[str, Any]:
    """The {name, description, input_schema} shape AnthropicChatAdapter
    sends to the API for a custom tool. Rebuilt here rather than imported —
    it's `lib.anthropic_adapter.anthropic_adapter._to_tool_param`, a private
    detail of that module."""
    return {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}


def banner(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'-' * 72}")


async def main() -> None:
    # stderr, not stdout — see src/tool_usage/repl_smoke_test.py.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")

    async with reminders_session() as session:
        tools = await mcp_tools(session)
        by_name = {tool.name: tool for tool in tools}

        banner("tools request parameter: local vs. MCP-backed set_reminder")
        local_param = to_tool_param(SetReminderTool())
        remote_param = to_tool_param(by_name["set_reminder"])
        print(json.dumps(local_param, indent=2))
        print("--- vs. ---")
        print(json.dumps(remote_param, indent=2))

        local_schema, remote_schema = local_param["input_schema"], remote_param["input_schema"]
        local_types = {k: v["type"] for k, v in local_schema["properties"].items()}
        remote_types = {k: v["type"] for k, v in remote_schema["properties"].items()}
        assert local_param["name"] == remote_param["name"], "tool name diverged"
        assert set(local_schema["required"]) == set(remote_schema["required"]), "required args diverged"
        assert local_types == remote_types, "property types diverged"
        print(
            "same name, same required args, same property types — the only "
            "differences (auto-derived `title` metadata, description "
            "formatting) are things Claude never acts on"
        )

        chat = AnthropicChatAdapter(system=SYSTEM_PROMPT, tools=tools)
        await run_repl(chat)


if __name__ == "__main__":
    asyncio.run(main())
