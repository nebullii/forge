"""Tests for PlannerAgent._parse_plan()."""

import warnings
import pytest
import yaml

from src.agents.planner import PlannerAgent


def _make_planner():
    """Instantiate PlannerAgent without a real provider."""
    return PlannerAgent.__new__(PlannerAgent)


def _yaml(d: dict) -> str:
    return yaml.dump(d, default_flow_style=False)


VALID_PLAN = {
    "decisions": {
        "stack": {
            "language": "Python",
            "framework": "FastAPI",
            "database": "SQLite",
            "frontend": "none",
            "styling":  "none",
        },
        "architecture": "REST API served by FastAPI.",
        "reasoning":    "API-only spec requires no frontend.",
    },
    "tasks": [
        {
            "id":          "task_01",
            "name":        "Setup",
            "description": "Initialise project structure",
            "agent":       "coder",
        },
        {
            "id":          "task_02",
            "name":        "Models",
            "description": "Create database models",
            "agent":       "backend",
        },
    ],
}


class TestParsePlan:
    def setup_method(self):
        self.planner = _make_planner()

    def test_valid_yaml_parses(self):
        result = self.planner._parse_plan(_yaml(VALID_PLAN))
        assert len(result["tasks"]) == 2
        assert result["tasks"][0]["id"] == "task_01"
        assert result["decisions"]["stack"]["language"] == "Python"

    def test_strips_yaml_fences(self):
        fenced = f"```yaml\n{_yaml(VALID_PLAN)}```"
        result = self.planner._parse_plan(fenced)
        assert result["tasks"][0]["name"] == "Setup"

    def test_strips_plain_fences(self):
        fenced = f"```\n{_yaml(VALID_PLAN)}```"
        result = self.planner._parse_plan(fenced)
        assert len(result["tasks"]) == 2

    def test_raises_on_empty_task_list(self):
        plan = {**VALID_PLAN, "tasks": []}
        with pytest.raises(ValueError, match="empty task list"):
            self.planner._parse_plan(_yaml(plan))

    def test_raises_when_tasks_key_missing(self):
        plan = {"decisions": VALID_PLAN["decisions"]}
        with pytest.raises(ValueError, match="valid plan with tasks"):
            self.planner._parse_plan(_yaml(plan))

    def test_raises_on_missing_required_field(self):
        plan = {
            **VALID_PLAN,
            "tasks": [{"id": "task_01", "name": "No desc"}],
        }
        with pytest.raises(ValueError, match="missing required field"):
            self.planner._parse_plan(_yaml(plan))

    def test_unknown_agent_normalizes_to_coder(self):
        plan = {
            **VALID_PLAN,
            "tasks": [
                {
                    "id":          "task_01",
                    "name":        "X",
                    "description": "Y",
                    "agent":       "unicorn_agent",
                }
            ],
        }
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = self.planner._parse_plan(_yaml(plan))

        assert result["tasks"][0]["agent"] == "coder"
        assert any("unicorn_agent" in str(w.message) for w in caught)

    def test_valid_agents_set_is_defined(self):
        assert "backend"  in PlannerAgent._VALID_AGENTS
        assert "frontend" in PlannerAgent._VALID_AGENTS
        assert "coder"    in PlannerAgent._VALID_AGENTS
