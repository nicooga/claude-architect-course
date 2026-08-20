from typing import Any, Dict

from lib.reminders import add_duration


class AddDurationToDateTimeTool:
    """Reliable date arithmetic, offloaded from the model (README gap #2).
    Implements ToolPort structurally — no inheritance needed."""

    name = "add_duration_to_datetime"
    description = (
        "Adds a duration to an ISO 8601 datetime and returns the resulting "
        "ISO 8601 datetime. Use this instead of computing dates yourself — "
        "pass the starting datetime (e.g. from get_current_datetime) and "
        "the offset expressed in weeks/days/hours/minutes."
    )
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "datetime": {
                "type": "string",
                "description": "Starting datetime in ISO 8601 format.",
            },
            "weeks": {"type": "number", "default": 0},
            "days": {"type": "number", "default": 0},
            "hours": {"type": "number", "default": 0},
            "minutes": {"type": "number", "default": 0},
        },
        "required": ["datetime"],
    }

    def execute(self, tool_input: Dict[str, Any]) -> str:
        # `or 0` because an explicit null for an omitted offset is a shape
        # the model does produce, and timedelta will not take None.
        return add_duration(
            tool_input["datetime"],
            weeks=tool_input.get("weeks", 0) or 0,
            days=tool_input.get("days", 0) or 0,
            hours=tool_input.get("hours", 0) or 0,
            minutes=tool_input.get("minutes", 0) or 0,
        )
