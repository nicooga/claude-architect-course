import functools
import json
import re
from typing import List, Optional, Self
from dotenv import load_dotenv
from anthropic import Anthropic
from anthropic.types import MessageCreateParams, MessageParam

load_dotenv()

SYSTEM_PROMPT = ""

class MessageList(List):
    def add_user_message(self, text: str) -> Self:
        message: MessageParam = {"role": "user", "content": text}
        self.append(message)
        return self

    def add_assistant_message(self, text: str) -> Self:
        message: MessageParam = {"role": "assistant", "content": text}
        self.append(message)
        return self

    def print(self) -> Self:
        print(json.dumps(self, indent=4))

def chat(
        messages: MessageList,
        system: Optional[str],
        temperature: float = 1.0
    ) -> str:
    client = Anthropic()
    model = "claude-sonnet-4-5-20250929"
    params: MessageCreateParams = {
        "model": model,
        "max_tokens": 1000,
        "messages": messages,
        "temperature": temperature
    }
    if system: params["system"] = system
    response = client.messages.create(**params)
    return response.content[0].text

def main() -> None:
    cold_chat = functools.partial(chat, system=SYSTEM_PROMPT, temperature=0.0)
    hot_chat = functools.partial(chat, system=SYSTEM_PROMPT, temperature=1.0)
    prompt = "Invent a brand-new superhero: give them a name and a one-sentence origin story."
    message_list = MessageList().add_user_message(prompt)

    print(f"Prompt=\"{prompt}\"")
    print("Temp=0.0. Output should be nearly deterministic")

    for _ in range(0, 3):
        print(cold_chat(message_list))
        print("=====")

    print("Temp=1.0. Output should be creative")

    for _ in range(0, 3):
        print(hot_chat(message_list))
        print("=====")


if __name__ == "__main__":
    main()