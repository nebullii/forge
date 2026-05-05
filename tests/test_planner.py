"""Tests for planner task normalization into the four-layer workflow."""

from src.agents.planner import PlannerAgent
from src.providers.base import BaseProvider, ProviderConfig


class _UnusedProvider(BaseProvider):
    def __init__(self):
        super().__init__(ProviderConfig(name="mock", model="mock-1"))

    def chat(self, messages, system=""):
        return ""

    def stream(self, messages, system=""):
        yield ""


def test_parse_plan_normalizes_legacy_agents(tmp_path):
    planner = PlannerAgent(_UnusedProvider(), tmp_path)
    plan = planner._parse_plan(
        """\
decisions: {}
tasks:
  - id: task_01
    name: "Backend"
    description: "Create API"
    agent: backend
    files: [backend/main.py]
  - id: task_02
    name: "Frontend"
    description: "Create UI"
    agent: frontend
    files: [frontend/src/App.jsx]
"""
    )

    assert [task["agent"] for task in plan["tasks"]] == ["builder", "builder"]
    assert [task["specialization"] for task in plan["tasks"]] == ["backend", "frontend"]


def test_parse_plan_preserves_builder_specialization(tmp_path):
    planner = PlannerAgent(_UnusedProvider(), tmp_path)
    plan = planner._parse_plan(
        """\
decisions: {}
tasks:
  - id: task_01
    name: "Setup"
    description: "Create project skeleton"
    agent: builder
    specialization: setup
    files: [pyproject.toml]
"""
    )

    assert plan["tasks"][0]["agent"] == "builder"
    assert plan["tasks"][0]["specialization"] == "setup"
