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


class _ExplodingLocalProvider(BaseProvider):
    def __init__(self):
        super().__init__(ProviderConfig(name="ollama", model="qwen2.5:3b"))

    def chat(self, messages, system=""):
        raise AssertionError("local deterministic planner should not call the provider")

    def stream(self, messages, system=""):
        raise AssertionError("stream should not be used")


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


def test_parse_plan_accepts_json_response(tmp_path):
    planner = PlannerAgent(_UnusedProvider(), tmp_path)
    plan = planner._parse_plan(
        """{
  "decisions": {
    "stack": {"language": "Python", "framework": "FastAPI", "database": "sqlite3", "frontend": "react", "styling": "tailwind"},
    "architecture": "FastAPI serves a React frontend.",
    "reasoning": "Complexity Level 2.",
    "directory_structure": "/\\n├── backend/\\n└── frontend/"
  },
  "tasks": [
    {"id": "task_01", "name": "Setup", "description": "Create skeleton", "agent": "builder", "specialization": "setup", "files": ["backend/main.py"]}
  ]
}"""
    )
    assert plan["tasks"][0]["agent"] == "builder"
    assert plan["tasks"][0]["specialization"] == "setup"


def test_local_planner_uses_supported_fastapi_react_path_without_llm(tmp_path):
    planner = PlannerAgent(_ExplodingLocalProvider(), tmp_path)
    spec = """\
# Project: Neighborhood Bakery

## What
A simple marketing website for a neighborhood bakery.

## Features
- Homepage
- Menu page
- Contact form

## Stack
React + Vite, FastAPI, SQLite
"""
    plan = planner.analyze_and_plan(spec, "Use environment variables for secrets.", "(No project files yet)")

    assert plan["template_family"] == "web-app"
    assert plan["decisions"]["stack"]["framework"] == "FastAPI"
    assert plan["decisions"]["stack"]["frontend"] == "react"
    assert [task["specialization"] for task in plan["tasks"]] == [
        "setup", "backend", "frontend", "integration",
    ]
    assert ".gitignore" in plan["tasks"][0]["files"]
    assert "frontend/.env.example" in plan["tasks"][0]["files"]


def test_local_planner_uses_static_site_path_for_simple_marketing_specs(tmp_path):
    planner = PlannerAgent(_ExplodingLocalProvider(), tmp_path)
    spec = """\
# Project: Bakery Site

## What
A simple marketing website for a neighborhood bakery with a homepage and contact section.
"""
    plan = planner.analyze_and_plan(spec, "Keep it simple.", "")

    assert plan["template_family"] == "static-site"
    assert plan["decisions"]["stack"]["framework"] == "static-html"
    assert plan["decisions"]["stack"]["frontend"] == "html"
    assert [task["specialization"] for task in plan["tasks"]] == ["setup", "frontend"]
