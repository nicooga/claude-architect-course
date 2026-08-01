from typing import Any, Dict, NoReturn


class WebSearchTool:
    """Anthropic-defined web search tool. Unlike the text editor tool, this
    one is server-executed too: Claude issues the search and reads the
    results entirely on Anthropic's side, so `execute` is never called —
    the adapter only ever sees the resulting server_tool_use /
    web_search_tool_result blocks, never a ToolUseBlock for this tool."""

    name = "web_search"
    type = "web_search_20250305"
    # Unused — Claude already knows this tool's input shape. Present only to
    # satisfy the ToolPort shape (see lib/anthropic_adapter/ports.py).
    description = ""
    input_schema: Dict[str, Any] = {}

    def execute(self, tool_input: Dict[str, Any]) -> NoReturn:
        raise NotImplementedError("web_search is executed server-side by Anthropic")
