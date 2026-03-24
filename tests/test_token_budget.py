"""Tests for token budget management."""

import pytest
from src.collaboration.token_budget import (
    estimate_tokens,
    truncate_to_budget,
    budget_prompt,
    CHARS_PER_TOKEN,
)


class TestEstimateTokens:
    def test_empty(self):
        assert estimate_tokens("") == 0

    def test_short(self):
        assert estimate_tokens("hello world") == len("hello world") // CHARS_PER_TOKEN

    def test_proportional(self):
        text = "a" * 4000
        assert estimate_tokens(text) == 1000


class TestTruncateToBudget:
    def test_within_budget_unchanged(self):
        sections = {"a": "short", "b": "also short"}
        result = truncate_to_budget(sections, max_tokens=10000)
        assert result == sections

    def test_large_section_truncated(self):
        big = "x" * 40000  # 10000 tokens
        sections = {"spec": "important", "code": big}
        result = truncate_to_budget(sections, max_tokens=5000)
        assert len(result["code"]) < len(big)
        assert "[truncated" in result["code"]

    def test_protected_not_truncated(self):
        big = "x" * 40000
        sections = {"spec": big, "code": "small"}
        result = truncate_to_budget(sections, max_tokens=5000, protected={"spec"})
        assert result["spec"] == big  # protected, not cut
        assert result["code"] == "small"  # already small

    def test_largest_cut_first(self):
        sections = {
            "a": "x" * 400,   # 100 tokens
            "b": "y" * 4000,  # 1000 tokens
            "c": "z" * 40000, # 10000 tokens
        }
        result = truncate_to_budget(sections, max_tokens=5000)
        # "c" should be cut the most
        assert len(result["c"]) < len(sections["c"])
        assert "[truncated" in result["c"]

    def test_all_keys_preserved(self):
        sections = {"a": "x" * 40000, "b": "y" * 40000}
        result = truncate_to_budget(sections, max_tokens=1000)
        assert set(result.keys()) == {"a", "b"}


class TestBudgetPrompt:
    def test_small_prompt_unchanged(self):
        result = budget_prompt(spec="my spec", rules="my rules")
        assert result["spec"] == "my spec"
        assert result["rules"] == "my rules"

    def test_large_backend_code_truncated(self):
        result = budget_prompt(
            spec="spec",
            rules="rules",
            backend_code="x" * 200000,
            max_tokens=10000,
        )
        assert "[truncated" in result["backend_code"]
        assert result["spec"] == "spec"  # protected
        assert result["rules"] == "rules"  # protected

    def test_spec_and_rules_protected(self):
        result = budget_prompt(
            spec="x" * 200000,
            rules="y" * 200000,
            max_tokens=1000,
        )
        # Even though they're huge, they're protected
        assert result["spec"] == "x" * 200000
        assert result["rules"] == "y" * 200000

    def test_empty_sections_excluded(self):
        result = budget_prompt(spec="spec", rules="rules", contracts="", backend_code="")
        assert "contracts" not in result
        assert "backend_code" not in result
