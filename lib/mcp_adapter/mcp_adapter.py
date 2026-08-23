from typing import Any, Dict, List
from mcp import ClientSession
from mcp.types import ContentBlock, TextContent, Tool
from lib.anthropic_adapter import ToolPort


def content_text(blocks: List[ContentBlock]) -> str:
    """Flattens CallToolResult.content into the str ToolPort.execute
    returns. Only TextContent is handled — same scope as the local copy of
    this helper in src/mcp_client/001_mcp_client.py, which stays
    self-contained on purpose rather than importing this one."""
    parts = [block.text for block in blocks if isinstance(block, TextContent)]
    return "\n".join(parts)


class MCPTool:
    """Adapts one MCP tool to the ToolPort interface.

    No setup/teardown of its own — the caller opens and owns the
    ClientSession (stdio_client + ClientSession async context managers) and
    this class just calls through it, the same division of responsibility
    ToolPort already has with a local tool owning its own store.
    """

    def __init__(self, session: ClientSession, tool: Tool) -> None:
        self._session = session
        self.name = tool.name
        self.description = tool.description or ""
        self.input_schema: Dict[str, Any] = tool.input_schema

    async def execute(self, tool_input: Dict[str, Any]) -> str:
        result = await self._session.call_tool(self.name, tool_input)
        text = content_text(result.content)
        if result.is_error:
            # ToolPort.execute returns a str on success only — an MCP-side
            # isError: true has to travel the same channel a local tool's
            # exception already does, so AnthropicChatAdapter._run_tool's
            # existing except-Exception builds the same is_error tool
            # result it builds for a raised KeyError/ValueError.
            raise RuntimeError(text)
        return text


async def mcp_tools(session: ClientSession) -> List[ToolPort]:
    """Lists the tools a session's server exposes and wraps each as a
    ToolPort, ready to hand straight to AnthropicChatAdapter(tools=...)."""
    tools = (await session.list_tools()).tools
    return [MCPTool(session, tool) for tool in tools]
