from typing import Optional
from anthropic import Anthropic
from lib.ai_generation import MessageList

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"


class AnthropicChatAdapter:
    """Adapts the Anthropic SDK to the ChatPort interface."""

    def __init__(
        self,
        system: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 1000,
    ):
        self._client = Anthropic()
        self._system = system
        self._model = model
        self._max_tokens = max_tokens

    def send(self, messages: MessageList) -> str:
        params = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": messages,
        }
        if self._system:
            params["system"] = self._system
        response = self._client.messages.create(**params)
        return response.content[0].text
