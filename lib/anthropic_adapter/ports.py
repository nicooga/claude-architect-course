from typing import Any, Dict, Protocol


class ToolPort(Protocol):
    """What the Anthropic adapter needs to know about a tool.

    The adapter depends only on this shape — it knows nothing about how a
    given tool is implemented internally, only its name/description/schema
    and how to invoke it.

    Anthropic-defined tools (bash, text editor, ...) are schema-less: Claude
    already knows their input shape server-side. A tool signals this by
    exposing a `type` attribute (e.g. "text_editor_20250728") instead of
    `description`/`input_schema` — the adapter sends `{type, name}` only for
    those, and falls back to the custom-tool shape otherwise.
    """

    name: str
    description: str
    input_schema: Dict[str, Any]

    async def execute(self, tool_input: Dict[str, Any]) -> str: ...
