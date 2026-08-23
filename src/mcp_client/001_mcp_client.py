"""MCP client, first experiment: the raw protocol, no `lib/` code involved.

Stage 5 built a server exposing one of each MCP primitive over the reminders
domain. This file is the client side of that, driving the SDK directly
against a stdio-spawned copy of `src/mcp_server/server.py` — no `ToolPort`,
no `ChatPort`, no REPL, and no call to the Anthropic API anywhere in here.
The point is to see the protocol's own shape before any of it gets wrapped:
`lib/mcp_adapter/` (a later step) is what turns MCP tools into `ToolPort`s
Claude can actually call.

One call of each primitive:

    tools/call      set_reminder            model-controlled
    resources/read  reminders://all         application-controlled
    prompts/get     review_reminders        user-controlled

plus two deliberate failures, because `src/mcp_server/server.py`'s
`delete_reminder` sets up an asymmetry worth seeing: `tools/call` is a
one-channel surface (an unknown tool, a bad argument, and a raised exception
all come back as a *successful* JSON-RPC response with `isError: true`), but
`resources/read` and `prompts/get` raise a real `MCPError` for an unknown
URI/name. Both show up below, side by side.

Run it:

    uv run python -m src.mcp_client.001_mcp_client
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, MCPError, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import PromptMessage, TextContent, TextResourceContents

SERVER_PATH = Path(__file__).parent.parent / "mcp_server" / "server.py"

REMINDER_DATETIME = "2026-08-30T09:00:00Z"


def banner(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'-' * 72}")


def content_text(blocks: list) -> str:
    """Flattens a list of content blocks into the str a ToolPort.execute
    would return. Only TextContent is handled — the reminders server never
    returns anything else, and that flattening is `lib/mcp_adapter`'s job,
    not this script's."""
    parts = [block.text for block in blocks if isinstance(block, TextContent)]
    return "\n".join(parts)


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            banner("initialize")
            init = await session.initialize()
            print(f"server:   {init.server_info.name} {init.server_info.version}")
            print(f"protocol: {init.protocol_version}")
            print(f"instructions: {init.instructions}")

            banner("tools/list")
            tools = (await session.list_tools()).tools
            for tool in tools:
                print(f"- {tool.name}: {tool.description}")

            banner("resources/list")
            resources = (await session.list_resources()).resources
            for resource in resources:
                print(f"- {resource.uri} ({resource.mime_type}): {resource.description}")

            banner("prompts/list")
            prompts = (await session.list_prompts()).prompts
            for prompt in prompts:
                args = ", ".join(arg.name for arg in prompt.arguments or [])
                print(f"- {prompt.name}({args}): {prompt.description}")

            # --- tools/call: model-controlled -------------------------------
            banner("tools/call: set_reminder (success)")
            result = await session.call_tool(
                "set_reminder",
                {"message": "Ship the MCP client", "datetime": REMINDER_DATETIME},
            )
            print(f"is_error: {result.is_error}")
            print(content_text(result.content))

            # --- resources/read: application-controlled ---------------------
            banner("resources/read: reminders://all")
            read = await session.read_resource("reminders://all")
            for contents in read.contents:
                if isinstance(contents, TextResourceContents):
                    print(contents.text)

            # --- prompts/get: user-controlled --------------------------------
            banner("prompts/get: review_reminders (roles visible)")
            prompt_result = await session.get_prompt("review_reminders", {"timeframe": "this week"})
            message: PromptMessage
            for message in prompt_result.messages:
                text = message.content.text if isinstance(message.content, TextContent) else message.content
                print(f"[{message.role}] {text}")

            # --- error channel 1: isError, a normal JSON-RPC response -------
            banner("tools/call: delete_reminder with a bad id (isError channel)")
            failed_call = await session.call_tool("delete_reminder", {"reminder_id": "does-not-exist"})
            print(f"is_error: {failed_call.is_error}")
            print(content_text(failed_call.content))

            # --- error channel 2: a real JSON-RPC/MCPError -------------------
            banner("resources/read: an unregistered URI (protocol error channel)")
            try:
                await session.read_resource("reminders://bogus")
            except MCPError as error:
                print(f"MCPError: code={error.code} message={error.message!r}")

            print(
                "\nSame server, two different tools/call-adjacent failures: "
                "the bad tool call above returned normally with isError=True; "
                "the bad resource read raised. `lib/mcp_adapter` (next step) "
                "keeps mapping isError onto ToolPort's own error result and "
                "lets MCPError propagate, because only the first is something "
                "Claude can act on mid-turn."
            )


if __name__ == "__main__":
    asyncio.run(main())
