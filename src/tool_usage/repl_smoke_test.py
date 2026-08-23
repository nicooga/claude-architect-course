import asyncio
import logging
import sys
import tempfile

from lib.repl import run_repl
from lib.anthropic_adapter import AnthropicChatAdapter
from src.tool_usage.tools import (
    AddDurationToDateTimeTool,
    CurrentDateTimeTool,
    GetUserUTCOffsetTool,
    SetReminderTool,
    TextEditorTool,
    WebSearchTool,
)


async def main() -> None:
    # stderr, not stdout, so tool-call logs don't interleave with the REPL's
    # "?> " prompt and answers on stdout. Bare message only — the ⏺/⎿ markers
    # in the log lines themselves carry the framing, same as an agent CLI.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")

    # Scratch directory for the text editor tool — a fresh temp dir per run
    # so the smoke test never touches real project files.
    workdir = tempfile.mkdtemp(prefix="tool_usage_text_editor_")
    print(f"Text editor working directory: {workdir}")

    chat = AnthropicChatAdapter(
        system=(
            "You are a helpful assistant. When using the text editor tool, "
            f"your working directory is {workdir} — read and write files there."
        ),
        tools=[
            GetUserUTCOffsetTool(),
            CurrentDateTimeTool(),
            AddDurationToDateTimeTool(),
            SetReminderTool(),
            TextEditorTool(root_dir=workdir),
            WebSearchTool(),
        ],
    )
    await run_repl(chat)


if __name__ == "__main__":
    asyncio.run(main())
