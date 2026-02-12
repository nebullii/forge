"""Base provider interface for LLM backends."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generator, Optional


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""
    name: str
    api_key: Optional[str] = None
    model: str = ""
    base_url: Optional[str] = None
    max_tokens: int = 8192

    def __str__(self):
        return f"{self.name} ({self.model})"


class BaseProvider(ABC):
    """Abstract base for all LLM providers."""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    def chat(self, messages: list[dict], system: str = "") -> str:
        """Send messages, return complete response text."""
        ...

    @abstractmethod
    def stream(self, messages: list[dict], system: str = "") -> Generator[str, None, None]:
        """Stream response tokens one at a time."""
        ...

    def chat_with_retry(self, messages: list[dict], system: str = "",
                        max_retries: int = 3) -> str:
        """Chat with exponential backoff retry on transient failures."""
        for attempt in range(max_retries):
            try:
                return self.chat(messages, system)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                err_str = str(e).lower()
                if "rate" in err_str or "timeout" in err_str or "529" in err_str or "overloaded" in err_str:
                    wait = 2 ** attempt
                    time.sleep(wait)
                else:
                    raise
