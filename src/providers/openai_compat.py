"""OpenAI-compatible provider (covers OpenAI, Together AI, Groq)."""

from typing import Generator

from .base import BaseProvider, ProviderConfig

BASE_URLS = {
    "together": "https://api.together.xyz/v1",
    "groq": "https://api.groq.com/openai/v1",
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

    def chat(self, messages: list[dict], system: str = "") -> str:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=msgs,
            max_tokens=self.config.max_tokens,
        )
        return response.choices[0].message.content

    def stream(self, messages: list[dict], system: str = "") -> Generator[str, None, None]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=msgs,
            max_tokens=self.config.max_tokens,
            stream=True,
        )
        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
