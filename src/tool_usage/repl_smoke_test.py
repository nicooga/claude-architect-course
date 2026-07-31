import logging
import sys

from lib.repl import run_repl
from lib.anthropic_adapter import AnthropicChatAdapter
from src.tool_usage.tools import AddDurationToDateTimeTool, CurrentDateTimeTool, SetReminderTool


def main() -> None:
    # stderr, not stdout, so tool-call logs don't interleave with the REPL's
    # "?> " prompt and answers on stdout. Bare message only — the ⏺/⎿ markers
    # in the log lines themselves carry the framing, same as an agent CLI.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")

    chat = AnthropicChatAdapter(
        system="You are a helpful assistant.",
        tools=[CurrentDateTimeTool(), AddDurationToDateTimeTool(), SetReminderTool()],
    )
    run_repl(chat)


if __name__ == "__main__":
    main()
