import json
from typing import List
from dataclasses import dataclass, field
from dotenv import load_dotenv
from anthropic import Anthropic
from anthropic.types import MessageParam

load_dotenv()

class MessageList(List):
    def add_user_message(self, text: str) -> None:
        return self.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str) -> None:
        return self.append({"role": "assistant", "content": text})

    def print(self) -> None:
        print(json.dumps(self, indent=4))

def chat(messages: MessageList) -> str:
    client = Anthropic()
    model = "claude-sonnet-4-5-20250929"
    response = client.messages.create(model=model, max_tokens=1000, messages=messages)
    return response.content[0].text

def main() -> None:
    messages = MessageList()
    messages.add_user_message("Define quantum computing. Answer in one sentence.")
    messages.add_assistant_message(chat(messages))
    messages.add_user_message("Write another answer")
    messages.add_assistant_message(chat(messages))
    messages.print()


if __name__ == "__main__":
    main()