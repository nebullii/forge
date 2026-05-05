"""Tests for provider config resolution."""

from src.config import get_provider_config


def test_get_provider_config_supports_profile_reference():
    config = {
        "providers": [
            {
                "name": "ollama",
                "base_url": "http://localhost:11434",
                "model": "llama3.1",
                "profiles": {
                    "code_local": {
                        "model": "qwen2.5-coder:14b",
                        "capabilities": ["code", "local"],
                    }
                },
            }
        ]
    }

    resolved = get_provider_config(config, "ollama:code_local")
    assert resolved.name == "ollama"
    assert resolved.profile == "code_local"
    assert resolved.model == "qwen2.5-coder:14b"
    assert "code" in resolved.capabilities
