"""OpenAI-compatible provider (covers OpenAI, Together AI, Groq)."""

from typing import Generator

from .base import BaseProvider, ProviderConfig

BASE_URLS = {
    "together": "https://api.together.xyz/v1",
    "groq": "https://api.groq.com/openai/v1",
}


# Public context windows for common OpenAI / Together / Groq models.
_OPENAI_WINDOWS = {
    "gpt-4o": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16385,
    "o1": 128000,
    "o3": 200000,
    # Together-hosted llama variants
    "meta-llama/meta-llama-3.1-405b": 131072,
    "meta-llama/meta-llama-3.1-70b": 131072,
    "meta-llama/meta-llama-3.1-8b": 131072,
    # Groq-hosted
    "llama-3.1-70b": 131072,
    "mixtral-8x7b": 32768,
}


class OpenAIProvider(BaseProvider):

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        from openai import OpenAI
        base_url = config.base_url or BASE_URLS.get(config.name.lower())
        kwargs = {"api_key": config.api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)

    def _detect_context_window(self) -> int:
        model = (self.config.model or "").lower()
        for prefix in sorted(_OPENAI_WINDOWS, key=len, reverse=True):
            if model.startswith(prefix):
                return _OPENAI_WINDOWS[prefix]
        return 128000  # modern default

    def chat(self, messages: list[dict], system: str = "", **options) -> str:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        kwargs: dict = {
            "model": self.config.model,
            "messages": msgs,
            "max_tokens": self.config.max_tokens,
        }
        if options.get("json_mode"):
            kwargs["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(**kwargs)
        if not response.choices:
            raise RuntimeError("OpenAI returned an empty response (no choices)")
        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError("OpenAI returned a null message content")
        return content

    def stream(self, messages: list[dict], system: str = "", **options) -> Generator[str, None, None]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        kwargs: dict = {
            "model": self.config.model,
            "messages": msgs,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }
        if options.get("json_mode"):
            kwargs["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(**kwargs)
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
