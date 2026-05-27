"""Tests for build policy loading, validation, and default file creation."""

import yaml

from src.policy import BuildPolicy, load_build_policy, write_default_policy


class TestBuildPolicy:
    def test_defaults_when_missing(self, tmp_path):
        policy = load_build_policy(tmp_path)
        assert policy.mode == "balanced"
        assert policy.approval_mode == "off"
        assert policy.auto_export_openapi is True

    def test_loads_known_fields(self, tmp_path):
        forge_path = tmp_path / ".forge"
        forge_path.mkdir()
        (forge_path / "policy.yaml").write_text(yaml.dump({
            "approval_mode": "interactive",
            "approval_gates": ["plan", "review"],
            "allowed_frameworks": ["rails", "django"],
            "allowed_agents": ["builder", "reviewer"],
        }))
        policy = load_build_policy(forge_path)
        assert policy.approval_mode == "interactive"
        assert policy.should_gate("plan") is True

    def test_validates_frameworks_and_agents(self):
        policy = BuildPolicy(
            allowed_frameworks=["django"],
            allowed_agents=["builder"],
        )
        errors = policy.validate_plan(
            {"framework": "Rails", "frontend": "React"},
            ["builder", "security"],
        )
        assert any("framework='Rails'" in err for err in errors)
        assert any("frontend='React'" in err for err in errors)
        assert any("agent 'security'" in err for err in errors)

    def test_write_default_policy(self, tmp_path):
        path = tmp_path / "policy.yaml"
        write_default_policy(path)
        content = path.read_text()
        assert "approval_gates" in content
        assert "support_tier" in content
        assert "allowed_providers" in content
        assert "fail_on_warning_categories" in content
        assert "auto_export_openapi: true" in content

    def test_validate_provider(self):
        policy = BuildPolicy(allowed_providers=["ollama", "openai"])
        assert policy.validate_provider("ollama") == []
        errors = policy.validate_provider("anthropic")
        assert errors
        assert "Allowed providers" in errors[0]
