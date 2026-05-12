"""Tests for provider error handling — no real API calls, just validation logic."""

import sys
import types

import pytest
from unittest.mock import MagicMock, patch
from src.providers.base import (
    BaseProvider,
    ProviderConfig,
    classify_error,
    compute_backoff,
    MAX_RETRY_WAIT,
)
from src.providers.ollama import OllamaProvider


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

    def test_retries_on_connection_refused(self):
        # Ollama failure mode: server starting up
        p = MockProvider(
            errors=[ConnectionError("Connection refused")],
            responses=["ok"],
        )
        result = p.chat_with_retry([{"role": "user", "content": "hi"}])
        assert result == "ok"
        assert p._call_count == 2

    def test_retries_on_model_loading(self):
        # Ollama failure mode: model still loading into VRAM
        p = MockProvider(
            errors=[RuntimeError("model is loading")],
            responses=["ok"],
        )
        result = p.chat_with_retry([{"role": "user", "content": "hi"}])
        assert result == "ok"

    def test_no_retry_on_oom(self):
        # Ollama failure mode: OOM — retrying same prompt won't help
        p = MockProvider(errors=[RuntimeError("CUDA out of memory")])
        with pytest.raises(RuntimeError, match="out of memory"):
            p.chat_with_retry([{"role": "user", "content": "hi"}])
        assert p._call_count == 1

    def test_no_retry_on_model_not_found(self):
        p = MockProvider(errors=[RuntimeError("Ollama model 'foo' is not installed")])
        with pytest.raises(RuntimeError, match="not installed"):
            p.chat_with_retry([{"role": "user", "content": "hi"}])
        assert p._call_count == 1

    def test_no_retry_on_context_overflow(self):
        # Surfaces early so caller can trim or downgrade model
        p = MockProvider(errors=[RuntimeError("context length exceeded")])
        with pytest.raises(RuntimeError, match="context length"):
            p.chat_with_retry([{"role": "user", "content": "hi"}])
        assert p._call_count == 1


class TestErrorClassifier:
    def test_classifies_retryable(self):
        assert classify_error(RuntimeError("Rate limit exceeded")) == "retryable"
        assert classify_error(RuntimeError("connection refused")) == "retryable"
        assert classify_error(RuntimeError("Server overloaded (529)")) == "retryable"
        assert classify_error(RuntimeError("model is loading into memory")) == "retryable"
        assert classify_error(RuntimeError("HTTP 503")) == "retryable"

    def test_classifies_non_retryable(self):
        assert classify_error(RuntimeError("CUDA out of memory")) == "non_retryable"
        assert classify_error(RuntimeError("invalid api key")) == "non_retryable"
        assert classify_error(RuntimeError("model not found")) == "non_retryable"
        assert classify_error(RuntimeError("context length exceeded")) == "non_retryable"

    def test_unknown_treated_as_non_retryable(self):
        # Unknown failures should fail fast to avoid hiding bugs in backoff loops
        assert classify_error(RuntimeError("totally novel error")) == "unknown"


class TestBackoff:
    def test_backoff_caps_at_max(self):
        # attempt=10 → 1024s without cap; should be capped
        for _ in range(20):
            wait = compute_backoff(10, base=1.0, jitter=True)
            assert wait <= MAX_RETRY_WAIT

    def test_backoff_grows_exponentially(self):
        # With jitter off, exact powers of 2
        assert compute_backoff(0, jitter=False) == 1.0
        assert compute_backoff(1, jitter=False) == 2.0
        assert compute_backoff(2, jitter=False) == 4.0
        assert compute_backoff(3, jitter=False) == 8.0

    def test_backoff_with_jitter_within_range(self):
        # Jitter scales the wait by [0.5, 1.0)
        for _ in range(20):
            wait = compute_backoff(2, base=1.0, jitter=True)
            assert 2.0 <= wait <= 4.0


def test_ollama_provider_falls_back_to_generate_when_chat_404(monkeypatch):
    class FakeHTTPError(Exception):
        def __init__(self, response):
            self.response = response

    class FakeResponse:
        def __init__(self, status_code=200, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise FakeHTTPError(self)

        def json(self):
            return self._payload

        def iter_lines(self):
            return iter(())

    calls = []

    def fake_post(url, json=None, **kwargs):
        calls.append((url, json))
        if url.endswith("/api/chat"):
            return FakeResponse(status_code=404)
        if url.endswith("/api/generate"):
            assert json["model"] == "llama3.1"
            assert "ASSISTANT:" in json["prompt"]
            return FakeResponse(payload={"response": "hello from generate"})
        raise AssertionError(f"unexpected url: {url}")

    fake_requests = types.SimpleNamespace(post=fake_post, HTTPError=FakeHTTPError)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    # Pre-set context_window so the test doesn't depend on /api/show probing
    provider = OllamaProvider(ProviderConfig(
        name="ollama", model="llama3.1", base_url="http://localhost:11434", context_window=8192
    ))
    result = provider.chat([{"role": "user", "content": "say hi"}], system="be concise")

    assert result == "hello from generate"
    assert [url for url, _payload in calls] == [
        "http://localhost:11434/api/chat",
        "http://localhost:11434/api/generate",
    ]


def test_ollama_provider_reports_missing_model_clearly(monkeypatch):
    class FakeHTTPError(Exception):
        def __init__(self, response):
            self.response = response

    class FakeResponse:
        def __init__(self, status_code=200, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise FakeHTTPError(self)

        def json(self):
            return self._payload

        def iter_lines(self):
            return iter(())

    def fake_post(url, json=None, **kwargs):
        if url.endswith("/api/chat"):
            return FakeResponse(status_code=404, payload={"error": "model 'llama3.1' not found"})
        raise AssertionError(f"unexpected post url: {url}")

    def fake_get(url, timeout):
        assert url == "http://localhost:11434/api/tags"
        return FakeResponse(payload={"models": [{"model": "qwen3:latest"}, {"model": "llama3.2:3b"}]})

    fake_requests = types.SimpleNamespace(post=fake_post, get=fake_get, HTTPError=FakeHTTPError)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    provider = OllamaProvider(ProviderConfig(name="ollama", model="llama3.1", base_url="http://localhost:11434"))

    with pytest.raises(RuntimeError, match="Ollama model 'llama3.1' is not installed"):
        provider.chat([{"role": "user", "content": "say hi"}])


def test_ollama_context_window_from_show_endpoint(monkeypatch):
    class FakeResponse:
        def __init__(self, payload=None):
            self.status_code = 200
            self._payload = payload or {}

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_post(url, json=None, **kwargs):
        if url.endswith("/api/show"):
            return FakeResponse(payload={
                "parameters": "stop \"<|eot_id|>\"\nnum_ctx          32768\ntemperature 0.7",
            })
        raise AssertionError(f"unexpected post url: {url}")

    fake_requests = types.SimpleNamespace(post=fake_post, HTTPError=Exception)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    provider = OllamaProvider(ProviderConfig(name="ollama", model="qwen2.5-coder:14b"))
    assert provider.get_context_window() == 32768


def test_ollama_context_window_falls_back_to_family(monkeypatch):
    class FakeResponse:
        def __init__(self, payload=None):
            self.status_code = 200
            self._payload = payload or {}

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_post(url, json=None, **kwargs):
        # Empty parameters block — forces family fallback
        return FakeResponse(payload={"parameters": ""})

    fake_requests = types.SimpleNamespace(post=fake_post, HTTPError=Exception)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    provider = OllamaProvider(ProviderConfig(name="ollama", model="llama3.1:8b"))
    assert provider.get_context_window() == 131072


def test_provider_config_carries_context_window():
    cfg = ProviderConfig(name="ollama", model="phi3", context_window=4096)
    provider = OllamaProvider(cfg)
    # Explicit config wins over auto-detection
    assert provider.get_context_window() == 4096


def test_ollama_chat_passes_json_mode_keep_alive_and_num_ctx(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "{}"}}

    def fake_post(url, json=None, **kwargs):
        captured["url"] = url
        captured["body"] = json
        return FakeResponse()

    fake_requests = types.SimpleNamespace(post=fake_post, HTTPError=Exception)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    provider = OllamaProvider(ProviderConfig(
        name="ollama",
        model="qwen2.5-coder:7b",
        context_window=32768,  # skip auto-detect
        keep_alive="1h",
    ))
    provider.chat([{"role": "user", "content": "ping"}], json_mode=True)

    assert captured["url"].endswith("/api/chat")
    body = captured["body"]
    assert body["format"] == "json"
    assert body["keep_alive"] == "1h"
    assert body["options"]["num_ctx"] == 32768
    assert body["stream"] is False


def test_ollama_chat_default_keep_alive_from_config():
    cfg = ProviderConfig(name="ollama", model="llama3.1:8b")
    # Default should be the 30m the dataclass declares
    assert cfg.keep_alive == "30m"


def test_ollama_provider_records_usage_metrics(monkeypatch):
    class FakeResponse:
        def __init__(self, payload=None):
            self.status_code = 200
            self._payload = payload or {}

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_post(url, json=None, **kwargs):
        if url.endswith("/api/chat"):
            return FakeResponse(payload={
                "message": {"content": "hello"},
                "total_duration": 12_000_000_000,
                "load_duration": 2_000_000_000,
                "prompt_eval_count": 123,
                "eval_count": 45,
                "eval_duration": 7_000_000_000,
            })
        raise AssertionError(f"unexpected post url: {url}")

    def fake_get(url, timeout):
        if url.endswith("/api/ps"):
            return FakeResponse(payload={
                "models": [{
                    "model": "qwen3:latest",
                    "size": 5_000_000_000,
                    "size_vram": 4_000_000_000,
                    "processor": "100% GPU",
                    "details": {
                        "family": "qwen3",
                        "parameter_size": "8B",
                        "quantization_level": "Q4_K_M",
                    },
                }]
            })
        raise AssertionError(f"unexpected get url: {url}")

    fake_requests = types.SimpleNamespace(post=fake_post, get=fake_get, HTTPError=Exception)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    provider = OllamaProvider(ProviderConfig(name="ollama", model="qwen3:latest", base_url="http://localhost:11434"))
    result = provider.chat([{"role": "user", "content": "say hi"}])

    assert result == "hello"
    usage = provider.get_last_usage()
    assert usage["model"] == "qwen3:latest"
    assert usage["prompt_eval_count"] == 123
    assert usage["eval_count"] == 45
    assert usage["size_vram_bytes"] == 4_000_000_000
    assert usage["processor"] == "100% GPU"
