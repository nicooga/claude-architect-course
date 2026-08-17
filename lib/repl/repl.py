from typing import Optional
from lib.ai_generation import MessageList
from .ports import ChatPort

# Importing readline is the whole mechanism behind line editing: CPython
# swaps in the GNU readline implementation of input() as an import side
# effect, which is what gives arrow-key history, cursor movement and
# word-delete. Nothing below references the module, so the import reads as
# unused — it isn't. Absent on Windows, where input() stays as it was.
try:
    import readline  # noqa: F401  (imported for its side effect)
except ImportError:
    pass


def run_repl(
    chat: ChatPort,
    messages: Optional[MessageList] = None,
) -> MessageList:
    """REPL over a ChatPort. Knows nothing about which client sits behind it."""

    messages = messages if messages is not None else MessageList()

    print("Ready")

    try:
        while True:
            # The prompt goes through input() rather than a preceding print()
            # so readline emits it itself and knows its width. Otherwise every
            # redraw — recalling a line from history, Ctrl+L — miscounts the
            # columns and leaves the prompt garbled.
            messages.add_user_message(input("?> "))

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
