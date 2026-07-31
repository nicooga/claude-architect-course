from typing import Optional
from lib.ai_generation import MessageList
from .ports import ChatPort


def run_repl(
    chat: ChatPort,
    messages: Optional[MessageList] = None,
) -> MessageList:
    """REPL over a ChatPort. Knows nothing about which client sits behind it."""

    messages = messages if messages is not None else MessageList()

    print("Ready")

    try:
        while True:
            print("?> ", end="")
            messages.add_user_message(input())

            try:
                answer = chat.send(messages)
            except Exception as e:
                print(f"Error: {e}")
                print()
                continue

            messages.add_assistant_message(answer)
            print(answer)
            print()

    except (KeyboardInterrupt, EOFError):
        print("Exciting")

    return messages
