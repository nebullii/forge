"""Anthropic Claude provider."""

from typing import Generator

from .base import BaseProvider, ProviderConfig


# Claude model families share a 200k context window; new models extend it.
_CLAUDE_WINDOWS = {
    "claude-opus-4": 200000,
    "claude-sonnet-4": 200000,
    "claude-haiku-4": 200000,
    "claude-3-5": 200000,
    "claude-3-7": 200000,
    "claude-3": 200000,
}


class AnthropicProvider(BaseProvider):

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        import anthropic
        self.client = anthropic.Anthropic(api_key=config.api_key)

    def _detect_context_window(self) -> int:
        model = (self.config.model or "").lower()
        for prefix, window in _CLAUDE_WINDOWS.items():
            if model.startswith(prefix):
                return window
        return 200000

    def chat(self, messages: list[dict], system: str = "", **options) -> str:
        # Anthropic doesn't accept extra params we use elsewhere (json_mode,
        # keep_alive, ollama_options); silently ignore — the SDK enforces
        # strict kwargs and would reject them.
        kwargs = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        response = self.client.messages.create(**kwargs)
        if not response.content:
            raise RuntimeError("Anthropic returned an empty response (no content blocks)")
        return response.content[0].text

    def stream(self, messages: list[dict], system: str = "", **options) -> Generator[str, None, None]:
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
