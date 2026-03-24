"""Token budget management for agent prompts.

Prevents context overflow by truncating the largest sections when the total
prompt exceeds a configurable token budget.  Uses a simple char-based estimate
(4 chars ≈ 1 token) — good enough for budget enforcement without requiring
a tokenizer dependency.
"""

from __future__ import annotations

CHARS_PER_TOKEN = 4

# Default max tokens for the *prompt* sent to an agent (not the response).
# Most models accept 128k+ context, but sending huge prompts wastes money
# and degrades output quality.  32k is a practical sweet spot.
DEFAULT_MAX_PROMPT_TOKENS = 32_000


def estimate_tokens(text: str) -> int:
    """Rough token count estimate."""
    return len(text) // CHARS_PER_TOKEN


def truncate_to_budget(
    sections: dict[str, str],
    max_tokens: int = DEFAULT_MAX_PROMPT_TOKENS,
    protected: set[str] | None = None,
) -> dict[str, str]:
    """Truncate prompt sections to fit within a token budget.

    Args:
        sections: Ordered dict of {section_name: text}. Order matters —
                  later sections are truncated first.
        max_tokens: Maximum total tokens across all sections.
        protected: Section names that should never be truncated (e.g., "spec").

    Returns:
        New dict with the same keys, large sections truncated with a
        "[truncated]" marker.  Protected sections are never cut.
    """
    protected = protected or set()
    total = sum(estimate_tokens(v) for v in sections.values())

    if total <= max_tokens:
        return dict(sections)

    overflow = total - max_tokens
    result = dict(sections)

    # Truncate largest unprotected sections first
    trimmable = [
        (k, estimate_tokens(v))
        for k, v in sections.items()
        if k not in protected
    ]
    trimmable.sort(key=lambda x: x[1], reverse=True)

    for key, size in trimmable:
        if overflow <= 0:
            break
        cut = min(overflow, size - 100)  # keep at least 100 tokens
        if cut <= 0:
            continue
        char_cut = cut * CHARS_PER_TOKEN
        text = result[key]
        result[key] = text[: len(text) - char_cut] + "\n\n[truncated — full content too large]"
        overflow -= cut

    return result


def budget_prompt(
    spec: str,
    rules: str,
    decisions_str: str = "",
    contracts: str = "",
    backend_code: str = "",
    pm_prompts: str = "",
    max_tokens: int = DEFAULT_MAX_PROMPT_TOKENS,
) -> dict[str, str]:
    """Apply token budget to a typical agent prompt.

    Returns a dict of section texts, truncated to fit.  ``spec`` and ``rules``
    are protected and never truncated.
    """
    sections = {}
    if spec:
        sections["spec"] = spec
    if rules:
        sections["rules"] = rules
    if decisions_str:
        sections["decisions"] = decisions_str
    if pm_prompts:
        sections["pm_prompts"] = pm_prompts
    if contracts:
        sections["contracts"] = contracts
    if backend_code:
        sections["backend_code"] = backend_code

    return truncate_to_budget(
        sections,
        max_tokens=max_tokens,
        protected={"spec", "rules"},
    )
