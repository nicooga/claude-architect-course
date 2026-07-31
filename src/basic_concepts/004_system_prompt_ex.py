import functools
import json
from typing import List, Optional
from dotenv import load_dotenv
from anthropic import Anthropic
from anthropic.types import MessageParam

load_dotenv()

SYSTEM_PROMPT = """
You are a pragmatic software engineer that provides concise and practical solutions to specific problems.
You write code that speaks for itself rather than long winded comments.
"""

SYSTEM_PROMPT = "You are a Python engineer that wirte very concise code"

class MessageList(List):
    def add_user_message(self, text: str) -> MessageParam:
        message: MessageParam = {"role": "user", "content": text}
        self.append(message)
        return message

    def add_assistant_message(self, text: str) -> MessageParam:
        message: MessageParam = {"role": "assistant", "content": text}
        self.append(message)
        return message

    def print(self) -> None:
        print(json.dumps(self, indent=4))

def chat(messages: MessageList, system: Optional[str]) -> str:
    client = Anthropic()
    model = "claude-sonnet-4-5-20250929"
    params = { "model": model, "max_tokens": 1000, "messages": messages }
    if system: params["system"] = system
    response = client.messages.create(**params)
    return response.content[0].text

def main() -> None:
    sys_chat = functools.partial(chat, system=SYSTEM_PROMPT)
    messages = MessageList()

    print("Anthropic prompt ready")

    try:
        while True:
            print("?> ", end="")
            messages.add_user_message(input())
            answer = sys_chat(messages)
            messages.add_assistant_message(answer)
            print(answer)
            print()

    except KeyboardInterrupt:
        print("Exciting")


if __name__ == "__main__":
    main()