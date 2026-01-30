"""AI provider adapters - unified interface for any AI."""

import json
from abc import ABC, abstractmethod
from typing import Generator
from .config import Provider


class AIAdapter(ABC):
    """Base class for AI providers."""

    @abstractmethod
    def chat(self, messages: list[dict], system: str = None) -> str:
        """Send messages and get response."""
        pass

    @abstractmethod
    def stream(self, messages: list[dict], system: str = None) -> Generator[str, None, None]:
        """Stream response tokens."""
        pass


class AnthropicAdapter(AIAdapter):
    """Anthropic Claude adapter."""

    def __init__(self, api_key: str, model: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def chat(self, messages: list[dict], system: str = None) -> str:
        kwargs = {"model": self.model, "max_tokens": 8192, "messages": messages}
        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)
        return response.content[0].text

    def stream(self, messages: list[dict], system: str = None) -> Generator[str, None, None]:
        kwargs = {"model": self.model, "max_tokens": 8192, "messages": messages}
        if system:
            kwargs["system"] = system

        with self.client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text


class OpenAIAdapter(AIAdapter):
    """OpenAI GPT adapter."""

    def __init__(self, api_key: str, model: str, base_url: str = None):
        from openai import OpenAI
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model

    def chat(self, messages: list[dict], system: str = None) -> str:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=msgs,
            max_tokens=8192,
        )
        return response.choices[0].message.content

    def stream(self, messages: list[dict], system: str = None) -> Generator[str, None, None]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)

        stream = self.client.chat.completions.create(
            model=self.model,
            messages=msgs,
            max_tokens=8192,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class GoogleAdapter(AIAdapter):
    """Google Gemini adapter."""

    def __init__(self, api_key: str, model: str):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)

    def chat(self, messages: list[dict], system: str = None) -> str:
        # Convert to Gemini format
        history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [msg["content"]]})

        chat = self.model.start_chat(history=history)
        prompt = messages[-1]["content"]
        if system:
            prompt = f"{system}\n\n{prompt}"

        response = chat.send_message(prompt)
        return response.text

    def stream(self, messages: list[dict], system: str = None) -> Generator[str, None, None]:
        history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [msg["content"]]})

        chat = self.model.start_chat(history=history)
        prompt = messages[-1]["content"]
        if system:
            prompt = f"{system}\n\n{prompt}"

        response = chat.send_message(prompt, stream=True)
        for chunk in response:
            yield chunk.text


class OllamaAdapter(AIAdapter):
    """Ollama (local) adapter."""

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages: list[dict], system: str = None) -> str:
        import requests

        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)

        response = requests.post(
            f"{self.base_url}/api/chat",
            json={"model": self.model, "messages": msgs, "stream": False},
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    def stream(self, messages: list[dict], system: str = None) -> Generator[str, None, None]:
        import requests

        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)

        response = requests.post(
            f"{self.base_url}/api/chat",
            json={"model": self.model, "messages": msgs, "stream": True},
            stream=True,
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                if "message" in data:
                    yield data["message"].get("content", "")


class GroqAdapter(OpenAIAdapter):
    """Groq adapter (OpenAI-compatible)."""

    def __init__(self, api_key: str, model: str):
        super().__init__(api_key, model, base_url="https://api.groq.com/openai/v1")


def create_adapter(provider: Provider) -> AIAdapter:
    """Factory function to create the appropriate adapter."""
    name = provider.name.lower()

    if name == "anthropic":
        return AnthropicAdapter(provider.api_key, provider.model)
    elif name == "openai":
        return OpenAIAdapter(provider.api_key, provider.model, provider.base_url)
    elif name == "google":
        return GoogleAdapter(provider.api_key, provider.model)
    elif name == "ollama":
        return OllamaAdapter(provider.base_url, provider.model)
    elif name == "groq":
        return GroqAdapter(provider.api_key, provider.model)
    else:
        # Try OpenAI-compatible as fallback
        return OpenAIAdapter(provider.api_key, provider.model, provider.base_url)
