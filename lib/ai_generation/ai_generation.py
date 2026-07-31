import json
from typing import List
from anthropic import Anthropic
from anthropic.types import ContentBlock, MessageParam, ToolResultBlockParam


class MessageList(List):
    def add_user_message(self, text: str) -> MessageParam:
        message: MessageParam = {"role": "user", "content": text}
        self.append(message)
        return message

    def add_assistant_message(self, text: str) -> MessageParam:
        message: MessageParam = {"role": "assistant", "content": text}
        self.append(message)
        return message

    def add_assistant_blocks(self, content: List[ContentBlock]) -> MessageParam:
        """Appends a raw assistant response (text + tool_use blocks) as-is."""
        message: MessageParam = {"role": "assistant", "content": content}
        self.append(message)
        return message

    def add_tool_results(self, results: List[ToolResultBlockParam]) -> MessageParam:
        """Appends one or more tool_result blocks as a single user turn."""
        message: MessageParam = {"role": "user", "content": results}
        self.append(message)
        return message

    def print(self) -> None:
        print(json.dumps(self, indent=4))
