from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class Reminder:
    message: str
    datetime: str


class SetReminderTool:
    """The actual side effect: recording a reminder in the system (README
    gap #3). Implements ToolPort structurally — no inheritance needed."""

    name = "set_reminder"
    description = (
        "Records a reminder for a future datetime. Use this once you have "
        "a concrete ISO 8601 datetime for when the reminder should fire — "
        "compute it first with get_current_datetime and "
        "add_duration_to_datetime if the user gave a relative time."
    )
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "What to remind the user about.",
            },
            "datetime": {
                "type": "string",
                "description": "When to remind the user, in ISO 8601 format.",
            },
        },
        "required": ["message", "datetime"],
    }

    def __init__(self) -> None:
        self.reminders: List[Reminder] = []

    def execute(self, tool_input: Dict[str, Any]) -> str:
        reminder = Reminder(message=tool_input["message"], datetime=tool_input["datetime"])
        self.reminders.append(reminder)
        return f"Reminder set for {reminder.datetime}: {reminder.message}"
