"""Tests for prompt budget helper."""

from src.budget import PromptBudget, estimate_tokens, is_small_context, CHARS_PER_TOKEN


class FakeProvider:
    def __init__(self, window):
        self._window = window

    def get_context_window(self):
        return self._window


def test_estimate_tokens_proportional_to_chars():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 400) == 100  # 400 chars / 4 = 100 tokens


def test_budget_consume_and_remaining():
    budget = PromptBudget(context_window=8000, reserved_output=2000, safety_margin=0)
    # Available: 6000 tokens = 24000 chars
    assert budget.remaining == 6000
    budget.consume("x" * 4000)  # 1000 tokens
    assert budget.remaining == 5000


def test_budget_fits_and_trim():
    budget = PromptBudget(context_window=4000, reserved_output=1000, safety_margin=0)
    # Available: 3000 tokens = 12000 chars
    short = "x" * 1000
    long = "x" * 20000
    assert budget.fits(short)
    assert not budget.fits(long)

    trimmed = budget.trim(long)
    assert estimate_tokens(trimmed) <= budget.remaining
    assert "truncated" in trimmed


def test_budget_for_model_uses_provider_window():
    budget = PromptBudget.for_model(FakeProvider(window=32768), reserved_output=2048)
    assert budget.context_window == 32768


def test_is_small_context():
    assert is_small_context(4096)
    assert is_small_context(8192)
    assert not is_small_context(32768)
    assert not is_small_context(131072)
