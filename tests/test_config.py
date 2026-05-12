"""Tests for provider config resolution and local-first wizard."""

import sys
import types

import yaml

from src import config as config_module
from src.config import (
    build_local_first_config,
    detect_ollama_models,
    generate_default_config,
    get_provider_config,
    pick_local_model,
    pick_role_models,
)


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


def test_pick_local_model_prefers_coder_variant():
    installed = ["llama3.2:3b", "qwen2.5-coder:14b", "mistral:7b"]
    assert pick_local_model(installed) == "qwen2.5-coder:14b"


def test_pick_local_model_prefers_larger_qwen_coder():
    installed = ["qwen2.5-coder:7b", "qwen2.5-coder:32b", "qwen2.5-coder:14b"]
    assert pick_local_model(installed) == "qwen2.5-coder:32b"


def test_pick_local_model_falls_through_to_first():
    assert pick_local_model(["some-random-model:latest"]) == "some-random-model:latest"


def test_pick_local_model_empty_returns_none():
    assert pick_local_model([]) is None


def test_build_local_first_config_puts_ollama_first():
    yaml_text = build_local_first_config(["qwen2.5-coder:14b", "llama3.1:8b"])
    data = yaml.safe_load(yaml_text)
    providers = data["providers"]
    assert providers[0]["name"] == "ollama"
    assert providers[0]["model"] == "qwen2.5-coder:14b"
    assert providers[0]["priority"] > providers[1]["priority"]


def test_build_local_first_config_routes_builder_to_coder_model():
    yaml_text = build_local_first_config(["qwen2.5-coder:7b", "llama3.1:8b"])
    data = yaml.safe_load(yaml_text)
    coder_profile = data["providers"][0]["profiles"]["coder"]
    assert "coder" in coder_profile["model"].lower()


def test_pick_role_models_separates_reviewer_when_possible():
    roles = pick_role_models(["qwen2.5-coder:7b", "qwen3:latest", "llama3.2:3b"])
    # Builder should be the coder model; reviewer should be distinct
    assert "coder" in roles["coder"].lower()
    assert roles["reviewer"] != roles["coder"]
    # Primary is qwen3 (it's earlier in the preference list than llama3.2)
    assert roles["primary"] == "qwen3:latest"


def test_pick_role_models_collapses_when_only_one_installed():
    roles = pick_role_models(["llama3.1:8b"])
    assert roles["primary"] == roles["coder"] == roles["reviewer"] == "llama3.1:8b"


def test_pick_role_models_two_models_picks_reviewer():
    # primary=qwen3, coder=qwen3 (no coder-specific), reviewer=llama3
    roles = pick_role_models(["qwen3:latest", "llama3.2:3b"])
    assert roles["reviewer"] == "llama3.2:3b"


def test_build_local_first_config_emits_reviewer_profile():
    yaml_text = build_local_first_config(["qwen2.5-coder:7b", "qwen3:latest"])
    data = yaml.safe_load(yaml_text)
    profiles = data["providers"][0]["profiles"]
    assert "reviewer" in profiles
    assert data["model_routing"]["reviewer"] == "ollama:reviewer"
    # Builder and reviewer must point to different concrete models
    assert profiles["coder"]["model"] != profiles["reviewer"]["model"]


def test_detect_ollama_models_handles_unreachable(monkeypatch):
    def fail_get(*args, **kwargs):
        raise ConnectionError("no server")

    fake_requests = types.SimpleNamespace(get=fail_get)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    assert detect_ollama_models() == []


def test_detect_ollama_models_parses_tags(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "models": [
                    {"model": "qwen2.5-coder:14b"},
                    {"name": "llama3.1:8b"},
                ]
            }

    def fake_get(url, timeout):
        assert url.endswith("/api/tags")
        return FakeResponse()

    fake_requests = types.SimpleNamespace(get=fake_get)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    assert detect_ollama_models() == ["qwen2.5-coder:14b", "llama3.1:8b"]


def test_generate_default_config_local_when_detected(monkeypatch):
    monkeypatch.setattr(
        config_module, "detect_ollama_models",
        lambda **_: ["qwen2.5-coder:7b"],
    )
    yaml_text, installed = generate_default_config(detect=True)
    assert "local-first" in yaml_text
    assert installed == ["qwen2.5-coder:7b"]


def test_generate_default_config_cloud_when_no_local(monkeypatch):
    monkeypatch.setattr(config_module, "detect_ollama_models", lambda **_: [])
    yaml_text, installed = generate_default_config(detect=True)
    assert "local-first" not in yaml_text
    assert installed == []


def test_ensure_config_writes_local_first_on_first_run(tmp_path, monkeypatch, capsys):
    cfg_file = tmp_path / "config.yaml"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", cfg_file)
    monkeypatch.setattr(
        config_module, "detect_ollama_models",
        lambda **_: ["qwen2.5-coder:14b"],
    )

    config = config_module.ensure_config()

    assert cfg_file.exists()
    text = cfg_file.read_text()
    assert "local-first" in text
    assert config["providers"][0]["name"] == "ollama"


def test_ensure_config_writes_cloud_first_when_no_ollama(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", cfg_file)
    monkeypatch.setattr(config_module, "detect_ollama_models", lambda **_: [])

    config_module.ensure_config()

    assert cfg_file.exists()
    text = cfg_file.read_text()
    assert "local-first" not in text
    assert "anthropic" in text
