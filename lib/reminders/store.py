"""Where reminders live, in two interchangeable shapes.

Stage 3 only ever wrote reminders, so a list on the tool instance was
enough. Stage 5 has to read them back — through `list_reminders`, and
through the `reminders://all` resource — and it has to do so across
processes: every stdio client spawns its own copy of the server, so a
reminder set from Claude Code is invisible to the Inspector unless it
lands on disk. Hence two stores with the same shape, chosen by the caller.

Structural typing throughout, matching `lib/anthropic_adapter/ports.py`:
nothing inherits from anything, and `ReminderStore` exists so the injection
sites can name the shape.
"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Protocol
from uuid import uuid4

# Cwd is not ours to assume: Claude Code, the MCP Inspector and a bare
# `mcp run` each launch the server from wherever they happen to be, so a
# relative default would scatter one JSON file per launch directory.
DEFAULT_STORE_PATH = Path.home() / ".claude-architect-course" / "reminders.json"
STORE_PATH_ENV_VAR = "MCP_REMINDERS_PATH"


@dataclass
class Reminder:
    id: str
    message: str
    datetime: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ReminderStore(Protocol):
    """What both stores expose. `delete` raises KeyError for an unknown id."""

    def add(self, message: str, datetime: str) -> Reminder: ...
    def list(self) -> List[Reminder]: ...
    def delete(self, reminder_id: str) -> Reminder: ...


def _new_id() -> str:
    # Short enough that a person can retype it into a tool call by hand,
    # which is exactly what exercising the delete path in the Inspector
    # asks for.
    return uuid4().hex[:8]


class InMemoryReminderStore:
    """Per-process, lost on exit. What Stage 3 has always done."""

    def __init__(self) -> None:
        self._reminders: List[Reminder] = []

    def add(self, message: str, datetime: str) -> Reminder:
        reminder = Reminder(id=_new_id(), message=message, datetime=datetime)
        self._reminders.append(reminder)
        return reminder

    def list(self) -> List[Reminder]:
        return list(self._reminders)

    def delete(self, reminder_id: str) -> Reminder:
        for index, reminder in enumerate(self._reminders):
            if reminder.id == reminder_id:
                return self._reminders.pop(index)
        raise KeyError(reminder_id)


class JsonFileReminderStore:
    """A JSON array on disk, re-read and rewritten on every call.

    No caching and no file locking: the whole point is that a second
    process sees the first one's writes, and the file holds a handful of
    short records.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _default_path()

    def add(self, message: str, datetime: str) -> Reminder:
        reminder = Reminder(id=_new_id(), message=message, datetime=datetime)
        reminders = self.list()
        reminders.append(reminder)
        self._write(reminders)
        return reminder

    def list(self) -> List[Reminder]:
        # A store that has never been written to is empty, not broken.
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
        return [Reminder(**item) for item in raw]

    def delete(self, reminder_id: str) -> Reminder:
        reminders = self.list()
        for index, reminder in enumerate(reminders):
            if reminder.id == reminder_id:
                removed = reminders.pop(index)
                self._write(reminders)
                return removed
        raise KeyError(reminder_id)

    def _write(self, reminders: List[Reminder]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [reminder.as_dict() for reminder in reminders]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _default_path() -> Path:
    override = os.environ.get(STORE_PATH_ENV_VAR)
    return Path(override).expanduser() if override else DEFAULT_STORE_PATH
