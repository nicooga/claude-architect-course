from typing import Any, Dict, List, Optional

from lib.reminders import InMemoryReminderStore, Reminder, ReminderStore


class SetReminderTool:
    """The actual side effect: recording a reminder in the system (README
    gap #3). Implements ToolPort structurally — no inheritance needed.

    The store is injected so the same tool can be backed by process-local
    state here and by the JSON file the Stage 5 MCP server shares across
    client processes.
    """

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

    def __init__(self, store: Optional[ReminderStore] = None) -> None:
        self.store: ReminderStore = store if store is not None else InMemoryReminderStore()

    @property
    def reminders(self) -> List[Reminder]:
        return self.store.list()

    def execute(self, tool_input: Dict[str, Any]) -> str:
        reminder = self.store.add(
            message=tool_input["message"], datetime=tool_input["datetime"]
        )
        return f"Reminder set for {reminder.datetime}: {reminder.message}"
