"""Tests for CLI helpers."""

import sys
import types
from argparse import Namespace

from src.cli import (
    _apply_model_override,
    _merge_setup_provider,
    _provider_preflight,
    _select_ollama_model,
    cmd_eval,
)
from src.providers.base import ProviderConfig


def test_merge_setup_provider_replaces_provider_list_and_preserves_other_keys():
    existing = {
        "providers": [
            {"name": "anthropic", "api_key": "ant-key", "model": "claude-sonnet-4-20250514"},
            {"name": "openrouter", "api_key": "or-key", "model": "z-ai/glm-5"},
        ],
        "model_routing": {
            "planner": "ollama",
            "builder": "ollama",
        },
    }

    new_entry = {
        "name": "ollama",
        "base_url": "http://localhost:11434",
        "model": "llama3.1",
    }

    merged = _merge_setup_provider(existing, new_entry)

    assert merged["providers"] == [new_entry]
    assert merged["model_routing"] == existing["model_routing"]


def test_select_ollama_model_prefers_installed_default(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"model": "llama3.2:3b"}, {"model": "qwen3:latest"}]}

    def fake_get(url, timeout):
        assert url == "http://localhost:11434/api/tags"
        assert timeout == 5
        return FakeResponse()

    fake_requests = types.SimpleNamespace(get=fake_get)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    model, note = _select_ollama_model("llama3.2:3b")
    assert model == "llama3.2:3b"
    assert note == ""


def test_select_ollama_model_falls_back_to_first_local_model(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "models": [
                    {"model": "qwen3:latest"},
                    {"model": "glm-5:cloud", "remote_host": "https://ollama.com:443"},
                ]
            }

    def fake_get(url, timeout):
        return FakeResponse()

    fake_requests = types.SimpleNamespace(get=fake_get)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    model, note = _select_ollama_model("llama3.1")
    assert model == "qwen3:latest"
    assert "missing default 'llama3.1'" in note


def test_provider_preflight_delegates_to_ollama_connection_check(monkeypatch):
    def fake_test_provider_connection(provider, api_key, model):
        assert provider == "ollama"
        assert api_key == ""
        assert model == "qwen2.5:3b"
        return True, ""

    monkeypatch.setattr("src.cli._test_provider_connection", fake_test_provider_connection)

    ok, err = _provider_preflight(
        ProviderConfig(name="ollama", model="qwen2.5:3b", base_url="http://localhost:11434")
    )
    assert ok is True
    assert err == ""


def test_provider_preflight_skips_non_ollama():
    ok, err = _provider_preflight(ProviderConfig(name="openai", model="gpt-4o", api_key="sk-test"))
    assert ok is True
    assert err == ""


def test_apply_model_override_replaces_model_for_single_command():
    config = {
        "providers": [
            {"name": "ollama", "base_url": "http://localhost:11434", "model": "qwen2.5:3b"}
        ]
    }
    provider_config = ProviderConfig(name="ollama", model="qwen2.5:3b", base_url="http://localhost:11434")

    overridden, returned_config, scope = _apply_model_override(
        provider_config,
        config,
        "ollama",
        "qwen3:latest",
    )

    assert overridden.model == "qwen3:latest"
    assert returned_config is config
    assert scope == "ollama:qwen3:latest"


def test_cmd_eval_accepts_fixture_directory(capsys, tmp_path):
    (tmp_path / "planner-good.json").write_text(
        '{"decisions":{"stack":{"language":"Python","framework":"FastAPI","database":"sqlite3","frontend":"react","styling":"tailwind"},"architecture":"x","reasoning":"Complexity Level 2.","directory_structure":"/"},"tasks":[{"id":"task_01","name":"Setup","description":"Create skeleton","agent":"builder","specialization":"setup","files":["backend/main.py"]}]}'
    )
    args = Namespace(kind="planner", input=str(tmp_path))
    cmd_eval(args)
    output = capsys.readouterr().out
    assert "PASS planner-good.json" in output
