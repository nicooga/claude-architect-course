from typing import Any, Dict, List, Optional
from anthropic import Anthropic
from anthropic.types import Message, TextBlock, ToolParam, ToolResultBlockParam, ToolUseBlock
from lib.ai_generation import MessageList
from .ports import ToolPort

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"


class AnthropicChatAdapter:
    """Adapts the Anthropic SDK to the ChatPort interface.

    Knows nothing about how a given tool is implemented — only the ToolPort
    shape (name/description/input_schema/execute). Runs the full tool-use
    loop internally so ChatPort/send() keeps returning a plain str and
    lib/repl/repl.py never has to change.
    """

    def __init__(
        self,
        system: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 1000,
        tools: Optional[List[ToolPort]] = None,
    ):
        self._client = Anthropic()
        self._system = system
        self._model = model
        self._max_tokens = max_tokens

        tools = tools or []
        self._tools: Dict[str, ToolPort] = {tool.name: tool for tool in tools}
        self._tool_params: List[ToolParam] = [
            {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}
            for tool in tools
        ]

    def send(self, messages: MessageList) -> str:
        params: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": messages,
        }
        if self._system:
            params["system"] = self._system
        if self._tool_params:
            params["tools"] = self._tool_params

        response = self._client.messages.create(**params)

        while response.stop_reason == "tool_use":
            messages.add_assistant_blocks(response.content)

            tool_results: List[ToolResultBlockParam] = [
                self._run_tool(block)
                for block in response.content
                if isinstance(block, ToolUseBlock)
            ]
            messages.add_tool_results(tool_results)

            # params["messages"] is the same MessageList object we just
            # mutated above, so the next call picks it up automatically.
            response = self._client.messages.create(**params)

        return _get_text(response)

    def _run_tool(self, block: ToolUseBlock) -> ToolResultBlockParam:
        tool = self._tools.get(block.name)
        if tool is None:
            return {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": f"Error: no tool registered with name '{block.name}'",
                "is_error": True,
            }
        try:
            result = tool.execute(block.input)
        except Exception as e:
            return {"type": "tool_result", "tool_use_id": block.id, "content": f"Error: {e}", "is_error": True}
        return {"type": "tool_result", "tool_use_id": block.id, "content": result}


def _get_text(response: Message) -> str:
    """Extracts the first text block. Mirrors get_text() in
    src/prompt_engineering/evaluation_pipeline.py."""
    for block in response.content:
        if isinstance(block, TextBlock):
            return block.text
    block_types = [type(block).__name__ for block in response.content]
    raise TypeError(f"Expected a TextBlock in response.content, got {block_types}")
