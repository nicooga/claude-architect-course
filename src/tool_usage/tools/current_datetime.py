from typing import Any, Dict

from lib.reminders import now_iso


class CurrentDateTimeTool:
    """Gives Claude precise time awareness (README gap #1). Implements
    ToolPort structurally — no inheritance needed."""

    name = "get_current_datetime"
    description = (
        "Returns the current date and time in ISO 8601 format at the given "
        "UTC offset. Required, with no default — call get_user_utc_offset "
        "first if you don't already know the user's offset from earlier in "
        "the conversation. 'today'/'tomorrow' depend on the local calendar "
        "day, which UTC and a user's offset can disagree about at any given "
        "moment. Use this whenever you need to know 'now' — for example, as "
        "the starting point for computing a relative date like 'a week from "
        "Thursday'."
    )
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "utc_offset_hours": {
                "type": "number",
                "description": "The user's UTC offset in hours, e.g. -3 for Argentina.",
            }
        },
        "required": ["utc_offset_hours"],
    }

    async def execute(self, tool_input: Dict[str, Any]) -> str:
        return now_iso(utc_offset_hours=tool_input["utc_offset_hours"])
