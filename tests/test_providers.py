"""Tests for provider error handling — no real API calls, just validation logic."""

import pytest
from unittest.mock import MagicMock, patch
from src.providers.base import BaseProvider, ProviderConfig


class MockProvider(BaseProvider):
    """Test provider that returns canned responses or raises."""

    def __init__(self, responses=None, errors=None):
        super().__init__(ProviderConfig(name="mock", model="test"))
        self._responses = list(responses or [])
        self._errors = list(errors or [])
        self._call_count = 0

    def chat(self, messages, system=""):
        self._call_count += 1
        if self._errors:
            raise self._errors.pop(0)
        if self._responses:
            return self._responses.pop(0)
        return ""

    def stream(self, messages, system=""):
        yield from self.chat(messages, system).split()


class TestRetryLogic:
    def test_no_retry_on_success(self):
        p = MockProvider(responses=["ok"])
        result = p.chat_with_retry([{"role": "user", "content": "hi"}])
        assert result == "ok"
        assert p._call_count == 1

    def test_retries_on_rate_limit(self):
        p = MockProvider(
            errors=[RuntimeError("rate limit exceeded")],
            responses=["ok"],
        )
        result = p.chat_with_retry([{"role": "user", "content": "hi"}])
        assert result == "ok"
        assert p._call_count == 2

    def test_retries_on_timeout(self):
        p = MockProvider(
            errors=[RuntimeError("request timeout")],
            responses=["ok"],
        )
        result = p.chat_with_retry([{"role": "user", "content": "hi"}])
        assert result == "ok"

    def test_retries_on_overloaded(self):
        p = MockProvider(
            errors=[RuntimeError("server overloaded")],
            responses=["ok"],
        )
        result = p.chat_with_retry([{"role": "user", "content": "hi"}])
        assert result == "ok"

    def test_no_retry_on_non_transient(self):
        p = MockProvider(errors=[RuntimeError("invalid api key")])
        with pytest.raises(RuntimeError, match="invalid api key"):
            p.chat_with_retry([{"role": "user", "content": "hi"}])
        assert p._call_count == 1

    def test_raises_after_max_retries(self):
        p = MockProvider(errors=[
            RuntimeError("rate limit"),
            RuntimeError("rate limit"),
            RuntimeError("rate limit"),
        ])
        with pytest.raises(RuntimeError, match="rate limit"):
            p.chat_with_retry([{"role": "user", "content": "hi"}], max_retries=3)
        assert p._call_count == 3
