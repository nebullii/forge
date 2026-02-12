"""Anthropic Claude provider."""

from typing import Generator

from .base import BaseProvider, ProviderConfig


class AnthropicProvider(BaseProvider):

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        import anthropic
        self.client = anthropic.Anthropic(api_key=config.api_key)

    def chat(self, messages: list[dict], system: str = "") -> str:
        kwargs = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        response = self.client.messages.create(**kwargs)
        return response.content[0].text

    def stream(self, messages: list[dict], system: str = "") -> Generator[str, None, None]:
        kwargs = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        with self.client.messages.stream(**kwargs) as s:
            for text in s.text_stream:
                yield text
