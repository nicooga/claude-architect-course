import logging
from typing import Any, Dict, List, Optional, cast
from anthropic import Anthropic
from anthropic.types import Message, TextBlock, ToolResultBlockParam, ToolUnionParam, ToolUseBlock
from lib.ai_generation import MessageList
from .ports import ToolPort

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# Logs go through the standard `logging` module rather than print() so they
# land on stderr, not stdout — the REPL owns stdout for its "?> " prompt and
# answers, and interleaving log lines into that stream would be confusing.
# Silent unless the app configures a handler (e.g. logging.basicConfig).
logger = logging.getLogger(__name__)


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
        self._tool_params: List[ToolUnionParam] = [_to_tool_param(tool) for tool in tools]

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
        call = _format_call(block.name, block.input)
        tool = self._tools.get(block.name)
        if tool is None:
            logger.warning("\n⏺ %s\n  ⎿ Error: no tool registered with that name\n", call)
            return {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": f"Error: no tool registered with name '{block.name}'",
                "is_error": True,
            }
        logger.info("\n⏺ %s", call)
        try:
            result = tool.execute(block.input)
        except Exception as e:
            logger.warning("  ⎿ Error: %s\n", e)
            return {"type": "tool_result", "tool_use_id": block.id, "content": f"Error: {e}", "is_error": True}
        logger.info("  ⎿ %s\n", _preview(result))
        return {"type": "tool_result", "tool_use_id": block.id, "content": result}


def _to_tool_param(tool: ToolPort) -> ToolUnionParam:
    """Anthropic-defined tools (bash, text editor, ...) are declared by
    `type`/`name` only — the model already knows their input shape, so no
    `input_schema` is sent. User-defined tools get the usual custom-tool
    shape. Distinguished structurally: an Anthropic-defined tool exposes a
    `type` attribute, a user-defined one doesn't."""
    tool_type = getattr(tool, "type", None)
    if tool_type is not None:
        return cast(ToolUnionParam, {"type": tool_type, "name": tool.name})
    return cast(
        ToolUnionParam,
        {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema},
    )


def _format_call(name: str, tool_input: Dict[str, Any]) -> str:
    """Renders a tool call as a Python-ish function signature, e.g.
    get_current_datetime(timezone="UTC") — the same shorthand coding agents
    like Claude Code and Codex use when narrating tool use."""
    args = ", ".join(f"{key}={value!r}" for key, value in tool_input.items())
    return f"{name}({args})"


def _preview(result: str, limit: int = 200) -> str:
    """Collapses a tool result to a single-line preview, truncating long
    output the way agent UIs show a snippet rather than the full payload."""
    flattened = str(result).replace("\n", " ")
    if len(flattened) <= limit:
        return flattened
    return f"{flattened[:limit]}… (+{len(flattened) - limit} chars)"


def _get_text(response: Message) -> str:
    """Extracts the first text block. Mirrors get_text() in
    src/prompt_engineering/evaluation_pipeline.py."""
    for block in response.content:
        if isinstance(block, TextBlock):
            return block.text
    block_types = [type(block).__name__ for block in response.content]
    raise TypeError(f"Expected a TextBlock in response.content, got {block_types}")
