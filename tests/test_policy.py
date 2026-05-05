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
            "allowed_agents": ["backend", "frontend"],
            "allow_adk": False,
        }))
        policy = load_build_policy(forge_path)
        assert policy.approval_mode == "interactive"
        assert policy.should_gate("plan") is True
        assert policy.allow_adk is False

    def test_validates_frameworks_agents_and_adk(self):
        policy = BuildPolicy(
            allowed_frameworks=["django"],
            allowed_agents=["backend", "frontend"],
            allow_adk=False,
        )
        errors = policy.validate_plan(
            {"framework": "Rails", "frontend": "React"},
            ["backend", "deploy"],
            use_adk=True,
        )
        assert any("ADK" in err for err in errors)
        assert any("framework='Rails'" in err for err in errors)
        assert any("frontend='React'" in err for err in errors)
        assert any("agent 'deploy'" in err for err in errors)

    def test_write_default_policy(self, tmp_path):
        path = tmp_path / "policy.yaml"
        write_default_policy(path)
        content = path.read_text()
        assert "approval_gates" in content
        assert "auto_export_openapi: true" in content
