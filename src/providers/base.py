"""Base provider interface for LLM backends."""

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generator, Optional


# Conservative default; overridden per-provider/per-model.
DEFAULT_CONTEXT_WINDOW = 8192

# Maximum wait between retries (seconds). Caps exponential backoff.
MAX_RETRY_WAIT = 30.0


# Substrings that mark a failure as non-retryable. Surfacing these immediately
# saves the user a 30-second backoff loop on bugs the retry can't fix:
#   - bad auth, bad model name, OOM (won't change on retry).
NON_RETRYABLE_PATTERNS = (
    "out of memory",
    "cuda out of memory",
    "cannot allocate",
    "model not found",
    "not installed",
    "invalid api key",
    "invalid_api_key",
    "unauthorized",
    "authentication",
    "context length",
    "context_length_exceeded",
    "maximum context",
    "no such file",
)

# Substrings that mark a failure as transient. Backoff + retry is appropriate:
#   - rate limits, timeouts, server overload, Ollama model loading.
RETRYABLE_PATTERNS = (
    "rate",
    "timeout",
    "529",
    "503",
    "502",
    "overloaded",
    "connection refused",
    "connection reset",
    "connection aborted",
    "max retries exceeded",
    "model is loading",
    "loading model",
    "temporarily unavailable",
    "server disconnected",
    "remote end closed",
)


def classify_error(exc: Exception) -> str:
    """Return 'retryable', 'non_retryable', or 'unknown' for an exception."""
    err = str(exc).lower()
    for pat in NON_RETRYABLE_PATTERNS:
        if pat in err:
            return "non_retryable"
    for pat in RETRYABLE_PATTERNS:
        if pat in err:
            return "retryable"
    return "unknown"


def compute_backoff(attempt: int, base: float = 1.0, jitter: bool = True) -> float:
    """Exponential backoff with jitter, capped at MAX_RETRY_WAIT.

    attempt is 0-indexed: attempt=0 → ~1s, attempt=1 → ~2s, attempt=2 → ~4s.
    """
    wait = min(base * (2 ** attempt), MAX_RETRY_WAIT)
    if jitter:
        wait = wait * (0.5 + random.random() * 0.5)
    return wait


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""
    name: str
    api_key: Optional[str] = None
    model: str = ""
    base_url: Optional[str] = None
    max_tokens: int = 8192
    context_window: Optional[int] = None  # None = auto-detect or provider default
    # Ollama-specific knob: how long to keep the model loaded after a request.
    # Default "30m" amortizes the 5-15s load cost across an entire build.
    # Set to "0" to unload immediately, or "-1" / "indefinite" to pin in memory.
    keep_alive: str = "30m"
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
    def chat(self, messages: list[dict], system: str = "", **options) -> str:
        """Send messages, return complete response text.

        Recognised options (providers may ignore those they don't support):
          - json_mode (bool): request structured JSON output.
        """
        ...

    @abstractmethod
    def stream(self, messages: list[dict], system: str = "", **options) -> Generator[str, None, None]:
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

    def stream_with_retry(self, messages: list[dict], system: str = "",
                          max_retries: int = 3, **options) -> Generator[str, None, None]:
        """Stream with classified retry on transient failures.

        Retries only the connection setup (no resume mid-stream). Once a chunk
        is yielded, downstream consumers see partial output if the stream is
        cut — agents should accumulate and revalidate the full response.
        """
        self.clear_last_usage()
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                yield from self.stream(messages, system, **options)
                return
            except Exception as e:
                last_exc = e
                kind = classify_error(e)
                if kind != "retryable" or attempt == max_retries - 1:
                    raise
                time.sleep(compute_backoff(attempt))
        if last_exc:
            raise last_exc

    def chat_with_retry(self, messages: list[dict], system: str = "",
                        max_retries: int = 3, **options) -> str:
        """Chat with classified retry on transient failures.

        Classifier behaviour:
          - retryable (rate limit, timeout, connection refused, model loading):
            exponential backoff with jitter, capped at MAX_RETRY_WAIT.
          - non_retryable (bad auth, OOM, model-not-found, context-overflow):
            raise immediately; retrying won't help.
          - unknown: treated as non-retryable to fail fast on bugs; if you
            need a behaviour change, add the pattern to RETRYABLE_PATTERNS.

        Extra ``options`` (e.g. ``json_mode=True``) pass through to ``chat()``.
        """
        self.clear_last_usage()
        for attempt in range(max_retries):
            try:
                return self.chat(messages, system, **options)
            except Exception as e:
                kind = classify_error(e)
                if kind != "retryable" or attempt == max_retries - 1:
                    raise
                time.sleep(compute_backoff(attempt))
        # Unreachable — loop either returns or raises
        raise RuntimeError("chat_with_retry exhausted retries without raising")
