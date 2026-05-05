"""Tests for capability-based model routing."""

import sys
import types

from src.providers.base import ProviderConfig
from src.router import ModelRouter


def _base_config():
    return {
        "providers": [
            {
                "name": "ollama",
                "base_url": "http://localhost:11434",
                "model": "llama3.1",
                "profiles": {
                    "fast_local": {
                        "model": "llama3.1",
                        "capabilities": ["cheap", "code", "local"],
                    },
                    "code_local": {
                        "model": "qwen2.5-coder:14b",
                        "capabilities": ["code", "local", "reasoning"],
                    },
                    "reason_local": {
                        "model": "qwen3:32b",
                        "capabilities": ["reasoning", "large_context", "local"],
                    },
                },
            },
            {
                "name": "openai",
                "api_key": "sk-test",
                "model": "gpt-4o",
                "capabilities": ["reasoning", "code"],
                "priority": 1,
            },
        ],
        "model_routing": {
            "planner": "ollama:reason_local",
            "builder": ["ollama:code_local", "openai"],
            "security": "ollama:reason_local",
        },
    }


def test_router_prefers_explicit_profile_then_fallbacks():
    router = ModelRouter(_base_config(), ProviderConfig(name="openai", model="gpt-4o"))
    chain = router.route_chain("builder")
    assert chain[0].provider_config.profile == "code_local"
    assert chain[1].provider_config.name == "openai"
    assert any(item.provider_config.profile == "fast_local" for item in chain)


def test_router_uses_capability_scoring_without_explicit_route():
    router = ModelRouter(_base_config(), ProviderConfig(name="openai", model="gpt-4o"))
    chain = router.route_chain("reviewer")
    assert chain[0].provider_config.profile == "reason_local"


def test_router_discovers_ollama_models(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "models": [
                    {
                        "name": "qwen2.5-coder:14b",
                        "model": "qwen2.5-coder:14b",
                        "size": 1,
                        "details": {
                            "family": "qwen2.5",
                            "parameter_size": "14B",
                            "quantization_level": "Q4_K_M",
                        },
                    }
                ]
            }

    def fake_get(url, timeout):
        assert url == "http://localhost:11434/api/tags"
        assert timeout == 5
        return FakeResponse()

    fake_requests = types.SimpleNamespace(get=fake_get)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    config = {
        "providers": [
            {"name": "ollama", "base_url": "http://localhost:11434", "model": "llama3.1", "discover": True}
        ]
    }
    router = ModelRouter(config, ProviderConfig(name="ollama", model="llama3.1", base_url="http://localhost:11434"))
    discovered = router.discover_ollama_models()
    assert discovered
    assert discovered[0].profile == "ollama:qwen2.5-coder:14b"
    assert "code" in discovered[0].capabilities
