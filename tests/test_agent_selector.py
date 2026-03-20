"""Tests for AgentSelector."""

import pytest

from src.agent_selector import AgentSelector, ALL_AGENTS


@pytest.fixture
def selector():
    return AgentSelector()


def _decisions(framework="fastapi", frontend="react", language="python"):
    return {
        "stack": {
            "language": language,
            "framework": framework,
            "database": "postgresql",
            "frontend": frontend,
        }
    }


class TestSuggest:
    def test_frontend_in_stack_included(self, selector):
        assert "frontend" in selector.suggest(_decisions(frontend="react"))

    def test_frontend_none_excluded(self, selector):
        assert "frontend" not in selector.suggest(_decisions(frontend="none"))

    def test_frontend_empty_excluded(self, selector):
        assert "frontend" not in selector.suggest(_decisions(frontend=""))

    def test_cli_framework_excludes_frontend(self, selector):
        assert "frontend" not in selector.suggest(_decisions(framework="click", frontend="none"))

    def test_cli_framework_excludes_deploy(self, selector):
        assert "deploy" not in selector.suggest(_decisions(framework="typer", frontend="none"))

    def test_always_includes_backend(self, selector):
        assert "backend" in selector.suggest(_decisions())

    def test_always_includes_ci(self, selector):
        assert "ci" in selector.suggest(_decisions())

    def test_always_includes_security(self, selector):
        assert "security" in selector.suggest(_decisions())

    def test_reviewer_is_last(self, selector):
        agents = selector.suggest(_decisions(frontend="react"))
        assert agents[-1] == "reviewer"

    def test_web_app_includes_deploy(self, selector):
        assert "deploy" in selector.suggest(_decisions(framework="fastapi", frontend="react"))


class TestParseFlag:
    def test_all_returns_every_agent(self, selector):
        assert set(selector.parse_flag("all")) == set(ALL_AGENTS)

    def test_auto_returns_empty_sentinel(self, selector):
        assert selector.parse_flag("auto") == []

    def test_explicit_list(self, selector):
        assert selector.parse_flag("backend,ci") == ["backend", "ci"]

    def test_strips_whitespace(self, selector):
        assert selector.parse_flag(" backend , ci , deploy ") == ["backend", "ci", "deploy"]

    def test_case_insensitive(self, selector):
        assert selector.parse_flag("Backend,CI") == ["backend", "ci"]

    def test_unknown_agent_raises(self, selector):
        with pytest.raises(ValueError, match="Unknown agent"):
            selector.parse_flag("backend,unicorn")


class TestFormatSuggestion:
    def test_output_contains_agent_names(self, selector):
        decisions = _decisions(frontend="react")
        agents = selector.suggest(decisions)
        output = selector.format_suggestion(agents, decisions)
        for name in agents:
            assert name in output

    def test_output_contains_stack_info(self, selector):
        decisions = _decisions(framework="fastapi", frontend="react")
        agents = selector.suggest(decisions)
        output = selector.format_suggestion(agents, decisions)
        assert "fastapi" in output.lower()
