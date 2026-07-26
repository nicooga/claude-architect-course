import json
from typing import List
from dataclasses import dataclass, field
from dotenv import load_dotenv
from anthropic import Anthropic
from anthropic.types import MessageParam

load_dotenv()

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

def chat(messages: MessageList) -> str:
    client = Anthropic()
    model = "claude-sonnet-4-5-20250929"
    response = client.messages.create(model=model, max_tokens=1000, messages=messages)
    return response.content[0].text

def main() -> None:
    messages = MessageList()

    print("Anthropic prompt ready")

    try:
        while True:
            print("?> ", end="")
            messages.add_user_message(input())
            answer = chat(messages)
            messages.add_assistant_message(answer)
            print(answer)
            print()

    except KeyboardInterrupt:
        print("Exciting")


if __name__ == "__main__":
    main()