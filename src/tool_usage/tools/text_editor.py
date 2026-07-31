from pathlib import Path
from typing import Any, Dict, List, Optional


class TextEditorTool:
    """Anthropic-defined text editor tool (view/create/str_replace/insert).
    Schema-less and client-executed: Claude knows the input shape natively,
    we just run the file operations. Confines every operation to `root_dir`
    since `path` is untrusted model output."""

    name = "str_replace_based_edit_tool"
    type = "text_editor_20250728"
    # Unused — Claude already knows this tool's input shape. Present only to
    # satisfy the ToolPort shape (see lib/anthropic_adapter/ports.py).
    description = ""
    input_schema: Dict[str, Any] = {}

    def __init__(self, root_dir: str) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, tool_input: Dict[str, Any]) -> str:
        command = tool_input["command"]
        path = self._resolve(tool_input["path"])

        if command == "view":
            return self._view(path, tool_input.get("view_range"))
        if command == "create":
            return self._create(path, tool_input["file_text"])
        if command == "str_replace":
            return self._str_replace(path, tool_input["old_str"], tool_input["new_str"])
        if command == "insert":
            return self._insert(path, tool_input["insert_line"], tool_input["insert_text"])
        raise ValueError(f"Unknown command: {command!r}")

    def _resolve(self, path: str) -> Path:
        resolved = Path(path).resolve()
        if resolved != self.root_dir and self.root_dir not in resolved.parents:
            raise ValueError(f"Path escapes working directory {self.root_dir}: {path}")
        return resolved

    def _view(self, path: Path, view_range: Optional[List[int]]) -> str:
        if path.is_dir():
            entries = sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir())
            return "\n".join(entries) or "(empty directory)"

        lines = path.read_text().splitlines()
        start = 1
        if view_range:
            start, end = view_range
            lines = lines[start - 1 : len(lines) if end == -1 else end]
        return "\n".join(f"{i}\t{line}" for i, line in enumerate(lines, start=start))

    def _create(self, path: Path, file_text: str) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file_text)
        return f"Created {path}"

    def _str_replace(self, path: Path, old_str: str, new_str: str) -> str:
        text = path.read_text()
        count = text.count(old_str)
        if count == 0:
            raise ValueError(f"old_str not found in {path}")
        if count > 1:
            raise ValueError(f"old_str is not unique in {path} ({count} matches)")
        path.write_text(text.replace(old_str, new_str, 1))
        return f"Replaced 1 occurrence in {path}"

    def _insert(self, path: Path, insert_line: int, insert_text: str) -> str:
        lines = path.read_text().splitlines()
        lines[insert_line:insert_line] = insert_text.splitlines()
        path.write_text("\n".join(lines) + "\n")
        return f"Inserted text after line {insert_line} in {path}"
