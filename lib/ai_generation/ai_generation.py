import json
from typing import List
from anthropic import Anthropic
from anthropic.types import MessageParam


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
