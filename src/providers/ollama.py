"""Ollama local model provider."""

import json
from typing import Generator

from .base import BaseProvider, ProviderConfig


class OllamaProvider(BaseProvider):

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = (config.base_url or "http://localhost:11434").rstrip("/")

    def chat(self, messages: list[dict], system: str = "") -> str:
        import requests
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={"model": self.config.model, "messages": msgs, "stream": False},
            timeout=300,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    def stream(self, messages: list[dict], system: str = "") -> Generator[str, None, None]:
        import requests
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={"model": self.config.model, "messages": msgs, "stream": True},
            stream=True,
            timeout=300,
        )
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                if "message" in data:
                    yield data["message"].get("content", "")
