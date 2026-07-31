from lib.repl import run_repl
from lib.anthropic_adapter import AnthropicChatAdapter
from src.tool_usage.tools import CurrentDateTimeTool


def main() -> None:
    chat = AnthropicChatAdapter(
        system="You are a helpful assistant.",
        tools=[CurrentDateTimeTool()],
    )
    run_repl(chat)


if __name__ == "__main__":
    main()
