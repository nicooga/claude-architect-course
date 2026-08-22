from typing import Protocol
from lib.ai_generation import MessageList


class ChatPort(Protocol):
    """What the agent loop needs from a chat client. Nothing else.

    System prompt, model, and any other client detail are the adapter's
    concern, bound at construction time.
    """

    async def send(self, messages: MessageList) -> str: ...
