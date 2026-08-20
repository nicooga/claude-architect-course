from typing import Any, Dict

from lib.reminders import now_iso


class CurrentDateTimeTool:
    """Gives Claude precise time awareness (README gap #1). Implements
    ToolPort structurally — no inheritance needed."""

    name = "get_current_datetime"
    description = (
        "Returns the current date and time in ISO 8601 format (UTC). Use this "
        "whenever you need to know 'now' — for example, as the starting point "
        "for computing a relative date like 'a week from Thursday'."
    )
    input_schema: Dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    def execute(self, tool_input: Dict[str, Any]) -> str:
        return now_iso()
