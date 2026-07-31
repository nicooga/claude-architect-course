from typing import Any, Dict, Protocol


class ToolPort(Protocol):
    """What the Anthropic adapter needs to know about a tool.

    The adapter depends only on this shape — it knows nothing about how a
    given tool is implemented internally, only its name/description/schema
    and how to invoke it.
    """

    name: str
    description: str
    input_schema: Dict[str, Any]

    def execute(self, tool_input: Dict[str, Any]) -> str: ...
