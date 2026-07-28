import json
from typing import List, Optional
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

def chat_stream(messages: MessageList, system: Optional[str] = None) -> Stream:
    client = Anthropic()
    model = "claude-sonnet-4-5-20250929"
    params = { "model": model, "max_tokens": 1000, "messages": messages }
    if system: params["system"] = system
    return client.messages.stream(**params)

def main() -> None:
    messages = MessageList()

    print("Anthropic prompt ready")

    try:
        while True:
            print("?> ", end="")

            messages.add_user_message(input())

            with chat_stream(messages) as stream:
                for text in stream.text_stream:
                    print(text, end="")

                # final_message = stream.get_final_message()

            print()

    except KeyboardInterrupt:
        print("Exciting")


if __name__ == "__main__":
    main()