import json
from typing import List
from dotenv import load_dotenv
from anthropic import Anthropic, Stream
from anthropic.types import MessageParam

load_dotenv()

SYSTEM_PROMPT = None

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

def chat(
        messages: MessageList,
        system: str = None,
        stop_sequences: List[str] = None
    ) -> Stream:
    client = Anthropic()
    model = "claude-sonnet-4-5-20250929"
    params = { "model": model, "max_tokens": 1000, "messages": messages }
    if system: params["system"] = system
    if stop_sequences: params["stop_sequences"] = stop_sequences
    response = client.messages.create(**params)
    return response.content[0].text

def main() -> None:
    messages = MessageList()

    messages.add_user_message("Generate three different AWS CLI commands. Each should be very short")
    messages.add_assistant_message("[\"")
    answer = chat(messages, stop_sequences=["\"]"])
    print(f'["{answer}"]')


if __name__ == "__main__":
    main()