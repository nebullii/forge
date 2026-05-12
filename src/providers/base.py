"""Base provider interface for LLM backends."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generator, Optional


# Conservative default; overridden per-provider/per-model.
DEFAULT_CONTEXT_WINDOW = 8192


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""
    name: str
    api_key: Optional[str] = None
    model: str = ""
    base_url: Optional[str] = None
    max_tokens: int = 8192
    context_window: Optional[int] = None  # None = auto-detect or provider default
    profile: str = ""
    capabilities: tuple[str, ...] = ()
    priority: int = 0
    metadata: dict = field(default_factory=dict)

    def __str__(self):
        profile = f"/{self.profile}" if self.profile else ""
        return f"{self.name}{profile} ({self.model})"


class BaseProvider(ABC):
    """Abstract base for all LLM providers."""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self._last_usage: dict = {}
        self._context_window: Optional[int] = config.context_window

    @abstractmethod
    def chat(self, messages: list[dict], system: str = "") -> str:
        """Send messages, return complete response text."""
        ...

    @abstractmethod
    def stream(self, messages: list[dict], system: str = "") -> Generator[str, None, None]:
        """Stream response tokens one at a time."""
        ...

    def get_context_window(self) -> int:
        """Return the model's context window size in tokens.

        Subclasses override _detect_context_window() to probe the model.
        Result is cached for the lifetime of the provider instance.
        """
        if self._context_window is None:
            try:
                self._context_window = self._detect_context_window()
            except Exception:
                self._context_window = DEFAULT_CONTEXT_WINDOW
        return self._context_window or DEFAULT_CONTEXT_WINDOW

    def _detect_context_window(self) -> int:
        """Override in subclasses to detect model context window."""
        return DEFAULT_CONTEXT_WINDOW

    def get_last_usage(self) -> dict:
        """Return the most recent provider usage metadata."""
        return dict(self._last_usage)

    def clear_last_usage(self) -> None:
        self._last_usage = {}

    def _set_last_usage(self, usage: Optional[dict]) -> None:
        self._last_usage = dict(usage or {})

    def chat_with_retry(self, messages: list[dict], system: str = "",
                        max_retries: int = 3) -> str:
        """Chat with exponential backoff retry on transient failures."""
        self.clear_last_usage()
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
