"""MCP client, third experiment: two axes the first two files didn't touch.

001/002 answered "does it matter whether a tool lives locally or on an MCP
server" (no, to the model). This file walks two further axes in the same
spirit, against the same Stage 5 reminders server:

Part A — does the *transport* the server runs over matter? Spawn the server
once over stdio and once over streamable HTTP and diff `tools/list` between
them. It shouldn't differ at all — same server code either way — which is
the stronger claim `src/mcp_server/README.md` already makes ("`tools/list`
is identical across both transports, with no code change").

Part B — does it matter *who executes the tool*? Everything so far —
001's raw `session.call_tool`, 002's `MCPTool.execute` — has been us calling
the server ourselves. Anthropic's server-side MCP connector (the
`mcp_servers` request parameter) is the other option: Claude's own backend
opens the MCP session and calls the tool, and the reply comes back as
`mcp_tool_use` / `mcp_tool_result` content blocks with no `ToolUseBlock`
anywhere for us to run — the exact shape of Stage 3's `web_search`
(`src/tool_usage/tools/web_search.py`), just for a tool we wrote ourselves
instead of one Anthropic hosts. This is the one place the model's-eye view
actually changes: not the tool list, but who's on the other end of the call.

The connector's `url` must be a real `https://` address — it has no way to
reach a process on this machine directly, so Part B tunnels the streamable
HTTP server out through `ngrok` first. That tunnel is course-environment
plumbing to let Anthropic's infrastructure reach a server that only exists
on this laptop; it isn't part of the MCP connector concept itself, which is
why it's opened only for the few seconds Part B needs it, around an
otherwise unauthenticated local server.

Run it:

    uv run python -m src.mcp_client.003_mcp_transports
"""

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List

from anthropic import AsyncAnthropic
from anthropic.types.beta import BetaMCPToolResultBlock, BetaMCPToolUseBlock, BetaTextBlock
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool

SERVER_PATH = Path(__file__).parent.parent / "mcp_server" / "server.py"

HTTP_HOST = "127.0.0.1"
HTTP_PORT = 8000
HTTP_URL = f"http://{HTTP_HOST}:{HTTP_PORT}/mcp"

NGROK_API = "http://127.0.0.1:4040/api/tunnels"

# Same string lib/anthropic_adapter/anthropic_adapter.py's DEFAULT_MODEL
# uses — kept as a local literal rather than imported, the same
# self-containment call 001/002 already made.
MODEL = "claude-sonnet-4-5-20250929"

REMINDERS_PROMPT = "List all my reminders."


def banner(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'-' * 72}")


def content_text(blocks: list) -> str:
    """Flattens CallToolResult.content the same way 001/lib.mcp_adapter do —
    redefined locally rather than imported, same self-containment policy."""
    from mcp.types import TextContent

    parts = [block.text for block in blocks if isinstance(block, TextContent)]
    return "\n".join(parts)


# --- Part A: same server, two transports -----------------------------------


@asynccontextmanager
async def stdio_session() -> AsyncIterator[ClientSession]:
    """Spawns the reminders server over stdio — the 001/002 pattern."""
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _wait_for_port(host: str, port: int, proc: "asyncio.subprocess.Process", timeout: float = 10.0) -> None:
    """Polls a raw TCP connect until the server is accepting connections.
    Checks proc.returncode each attempt so a subprocess that crashed on
    startup fails immediately instead of waiting out the full timeout."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if proc.returncode is not None:
            stderr = b""
            if proc.stderr is not None:
                stderr = await proc.stderr.read()
            raise RuntimeError(
                f"reminders server (streamable-http) exited with code {proc.returncode} "
                f"before opening {host}:{port}: {stderr.decode(errors='replace')}"
            )
        try:
            _, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            if loop.time() >= deadline:
                raise TimeoutError(f"reminders server did not open {host}:{port} within {timeout}s")
            await asyncio.sleep(0.1)


@asynccontextmanager
async def http_server(*, allow_any_host: bool = False) -> AsyncIterator[None]:
    """Spawns `sys.executable src/mcp_server/server.py streamable-http` as a
    subprocess (not `uv run mcp run ...` — see src/mcp_server/README.md on
    that command's slow cold start in this environment), waits for it to
    accept connections, and terminates it on the way out — including on an
    exception raised inside the `with` block.

    `allow_any_host` opts the server into `MCP_ALLOW_ANY_HOST=1` (see
    server.py's `__main__`): binding host="127.0.0.1" auto-enables
    DNS-rebinding protection, which rejects a request whose Host header
    isn't a localhost variant — exactly what a request forwarded through the
    Part B ngrok tunnel looks like. Part A talks to the server directly over
    127.0.0.1 and leaves the protection on."""
    env = dict(os.environ)
    if allow_any_host:
        env["MCP_ALLOW_ANY_HOST"] = "1"
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(SERVER_PATH),
        "streamable-http",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        await _wait_for_port(HTTP_HOST, HTTP_PORT, proc)
        yield
    finally:
        proc.terminate()
        await proc.wait()


@asynccontextmanager
async def http_session() -> AsyncIterator[ClientSession]:
    async with streamable_http_client(HTTP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def tool_dict(tool: Tool) -> Dict[str, Any]:
    """Tool as a plain dict for printing and for the equality assertion."""
    return tool.model_dump(mode="json")


async def compare_transports() -> None:
    banner("tools/list: stdio")
    async with stdio_session() as session:
        stdio_tools: List[Tool] = (await session.list_tools()).tools
    for tool in stdio_tools:
        print(f"- {tool.name}: {tool.description}")

    banner("tools/list: streamable HTTP")
    async with http_server():
        async with http_session() as session:
            http_tools: List[Tool] = (await session.list_tools()).tools
    for tool in http_tools:
        print(f"- {tool.name}: {tool.description}")

    # Unlike 002's local-vs-MCP comparison — genuinely different schema
    # sources (a hand-written dict vs. a Pydantic-derived one) — both lists
    # here come from the identical server code, just reached over a
    # different transport. Nothing legitimately differs, so the honest claim
    # is full equality, not just the name/required-args/type reduction 002
    # settles for.
    stdio_dicts = [tool_dict(t) for t in stdio_tools]
    http_dicts = [tool_dict(t) for t in http_tools]
    assert stdio_dicts == http_dicts, "tools/list diverged between stdio and streamable HTTP"
    print("\nidentical tools/list on both transports — the transport is invisible here")


# --- Part B: Anthropic's server-side MCP connector ---------------------------


@asynccontextmanager
async def ngrok_tunnel(port: int) -> AsyncIterator[str]:
    """Spawns `ngrok http <port>` and yields the public https:// URL it
    reports, read from ngrok's own local inspection API — the connector
    needs a real https:// endpoint and has no way to reach a process on this
    machine directly. Torn down in `finally`, including on exception."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ngrok",
            "http",
            str(port),
            "--log",
            "stdout",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "ngrok not found on PATH. Install it, or run `ngrok config check` "
            "if it's already installed but not authenticated."
        )
    try:
        url = await _poll_ngrok_api(proc, timeout=15.0)
        yield url
    finally:
        proc.terminate()
        await proc.wait()


async def _poll_ngrok_api(proc: "asyncio.subprocess.Process", timeout: float) -> str:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if proc.returncode is not None:
            raise RuntimeError(f"ngrok exited with code {proc.returncode} before reporting a tunnel")
        try:
            with urllib.request.urlopen(NGROK_API, timeout=1.0) as response:
                payload = json.loads(response.read())
            for tunnel in payload.get("tunnels", []):
                public_url = tunnel.get("public_url", "")
                if public_url.startswith("https://"):
                    return public_url
        except (urllib.error.URLError, ConnectionError, TimeoutError, json.JSONDecodeError):
            pass
        if loop.time() >= deadline:
            raise RuntimeError(
                f"ngrok did not report an https:// tunnel within {timeout}s — "
                "is it authenticated? (`ngrok config check`)"
            )
        await asyncio.sleep(0.2)


async def connector_call(public_url: str) -> None:
    banner("Anthropic server-side MCP connector (mcp_servers)")
    client = AsyncAnthropic()
    response = await client.beta.messages.create(
        model=MODEL,
        max_tokens=1000,
        betas=["mcp-client-2025-11-20"],
        mcp_servers=[{"type": "url", "url": f"{public_url}/mcp", "name": "reminders"}],
        tools=[{"type": "mcp_toolset", "mcp_server_name": "reminders"}],
        messages=[{"role": "user", "content": REMINDERS_PROMPT}],
    )

    mcp_uses = [b for b in response.content if isinstance(b, BetaMCPToolUseBlock)]
    mcp_results = [b for b in response.content if isinstance(b, BetaMCPToolResultBlock)]
    assert mcp_uses, f"expected at least one mcp_tool_use block, got: {[b.type for b in response.content]}"

    for use in mcp_uses:
        print(f"mcp_tool_use:    server={use.server_name} name={use.name} input={use.input}")
    for result in mcp_results:
        print(f"mcp_tool_result: is_error={result.is_error} content={result.content!r}")

    text = next((b.text for b in response.content if isinstance(b, BetaTextBlock)), "")
    print(f"\nfinal text: {text}")

    print(
        "\nno ToolUseBlock, no local session.call_tool anywhere above — the "
        "whole call/result cycle happened inside Anthropic's infrastructure "
        "within this one messages.create() call, the server-executed twin "
        "of 001's session.call_tool and 002's local ToolPort.execute — the "
        "same shape as Stage 3's web_search, just for a tool we wrote."
    )


async def main() -> None:
    await compare_transports()

    async with http_server(allow_any_host=True):
        async with ngrok_tunnel(HTTP_PORT) as public_url:
            print(f"\nngrok tunnel: {public_url} -> http://{HTTP_HOST}:{HTTP_PORT}")
            await connector_call(public_url)


if __name__ == "__main__":
    asyncio.run(main())
