"""Token budget helpers for context-window-aware prompting.

Local models often have small windows (4k–32k). This module gives agents a
single place to ask: "given my model's context window, how many tokens do I
have left for project context after the system prompt, spec, and reserved
output?" Trim project files to fit instead of relying on silent truncation.
"""

from __future__ import annotations

from dataclasses import dataclass


# Conservative chars-per-token estimate. Real tokenizers vary 2.5–4.5 chars/tok
# across English code; 4 is a safe middle ground for budgeting decisions.
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Cheap token estimate without pulling in tiktoken."""
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class PromptBudget:
    """Tracks how many tokens are still available for a prompt.

    Use with the model's full context window:

        budget = PromptBudget.for_model(provider, reserved_output=2048)
        budget.consume(system_prompt)
        budget.consume(spec)
        if not budget.fits(extra_context):
            extra_context = budget.trim(extra_context)
    """

    context_window: int
    reserved_output: int = 2048
    safety_margin: int = 256
    used: int = 0

    @classmethod
    def for_model(cls, provider, reserved_output: int = 2048) -> "PromptBudget":
        try:
            window = provider.get_context_window()
        except Exception:
            from .providers.base import DEFAULT_CONTEXT_WINDOW
            window = DEFAULT_CONTEXT_WINDOW
        return cls(context_window=window, reserved_output=reserved_output)

    @property
    def remaining(self) -> int:
        budget = self.context_window - self.reserved_output - self.safety_margin
        return max(0, budget - self.used)

    def consume(self, text: str) -> None:
        self.used += estimate_tokens(text)

    def fits(self, text: str) -> bool:
        return estimate_tokens(text) <= self.remaining

    def trim(self, text: str, suffix: str = "\n\n[... truncated to fit context ...]") -> str:
        """Truncate *text* so it (plus suffix) fits in the remaining budget."""
        budget = self.remaining
        if budget <= 0:
            return ""
        if estimate_tokens(text) <= budget:
            return text
        suffix_tokens = estimate_tokens(suffix)
        keep_tokens = max(0, budget - suffix_tokens)
        keep_chars = keep_tokens * CHARS_PER_TOKEN
        return text[:keep_chars] + suffix


def is_small_context(window: int) -> bool:
    """True for models that can't comfortably hold a full Forge planner prompt."""
    return window < 16000
