from lib.repl import run_repl
from lib.anthropic_adapter import AnthropicChatAdapter


def main() -> None:
    chat = AnthropicChatAdapter(system="You are a helpful assistant.")
    run_repl(chat)


if __name__ == "__main__":
    main()
