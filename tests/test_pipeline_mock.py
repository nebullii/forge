"""Full pipeline integration test with a mock LLM provider.

Exercises the four-layer flow at a high level and the legacy generators
behind it, verifying that files are written, contracts are extracted, and
the bus contains the expected artifacts. No real API calls.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.providers.base import BaseProvider, ProviderConfig
from src.agents.planner import PlannerAgent
from src.agents.backend import BackendAgent
from src.agents.frontend import FrontendAgent
from src.agents.reviewer import ReviewerAgent
from src.collaboration import (
    ArtifactBus, ContractRegistry, CodeArtifact,
    extract_contracts_from_response, validate_agent_output,
)


# ---------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------

class MockLLMProvider(BaseProvider):
    """Returns canned responses keyed by substring match on the prompt."""

    def __init__(self, responses: dict[str, str]):
        super().__init__(ProviderConfig(name="mock", model="mock-1"))
        self._responses = responses

    def chat(self, messages, system="", **options):
        prompt = (messages[-1]["content"] if messages else "") + " " + system
        for key, response in self._responses.items():
            if key.lower() in prompt.lower():
                return response
        return "No matching response"

    def stream(self, messages, system="", **options):
        yield self.chat(messages, system, **options)


# ---------------------------------------------------------------------------
# Canned responses
# ---------------------------------------------------------------------------

PLANNER_RESPONSE = """\
decisions:
  stack:
    language: "python"
    framework: "fastapi"
    database: "sqlite"
    frontend: "react"
    styling: "tailwind"
  architecture: "FastAPI backend with React frontend"
  reasoning: "Simple CRUD app, FastAPI is ideal"

tasks:
  - id: task_01
    name: "Set up project"
    description: "Create project structure"
    agent: builder
    specialization: setup
    files: [requirements.txt]
  - id: task_02
    name: "Build API"
    description: "Create REST API"
    agent: builder
    specialization: backend
    files: [app/main.py]
  - id: task_03
    name: "Build UI"
    description: "Create React frontend"
    agent: builder
    specialization: frontend
    files: [src/App.jsx]
"""

BACKEND_RESPONSE = """\
{
  "files": [
    {
      "path": "app/main.py",
      "content": "from fastapi import FastAPI\\napp = FastAPI()\\n\\n@app.get(\\"/users\\")\\ndef list_users():\\n    return [{\\"id\\": 1, \\"name\\": \\"Alice\\"}]\\n\\n@app.post(\\"/users\\")\\ndef create_user(name: str):\\n    return {\\"id\\": 2, \\"name\\": name}\\n"
    },
    {
      "path": "app/models.py",
      "content": "import sqlite3\\n\\ndef get_db():\\n    return sqlite3.connect(\\"app.db\\")\\n"
    }
  ],
  "contracts": {
    "api": [
      {"method": "GET", "path": "/users", "response_schema": {"type": "array"}, "auth": "none"},
      {"method": "POST", "path": "/users", "request_schema": {"name": "str"}, "auth": "none"}
    ],
    "models": [
      {"name": "User", "fields": {"id": "integer", "name": "text"}}
    ],
    "events": []
  }
}
"""

FRONTEND_RESPONSE = """\
{
  "files": [
    {
      "path": "src/App.jsx",
      "content": "import React from 'react';\\n\\nexport default function App() {\\n  const [users, setUsers] = React.useState([]);\\n  React.useEffect(() => {\\n    fetch('/users').then(r => r.json()).then(setUsers);\\n  }, []);\\n  return <ul>{users.map(u => <li key={u.id}>{u.name}</li>)}</ul>;\\n}\\n"
    },
    {
      "path": "src/main.jsx",
      "content": "import React from 'react';\\nimport ReactDOM from 'react-dom/client';\\nimport App from './App';\\nReactDOM.createRoot(document.getElementById('root')).render(<App />);\\n"
    }
  ]
}
"""

REVIEWER_RESPONSE = """\
{
  "passed": true,
  "issues": []
}
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFullPipelineMock:
    @pytest.fixture
    def provider(self):
        return MockLLMProvider({
            "technology stack": PLANNER_RESPONSE,
            "forge planner": PLANNER_RESPONSE,
            "forge backend": BACKEND_RESPONSE,
            "forge frontend": FRONTEND_RESPONSE,
            "forge reviewer": REVIEWER_RESPONSE,
            "review these files": REVIEWER_RESPONSE,
        })

    @pytest.fixture
    def project_root(self, tmp_path):
        forge = tmp_path / ".forge"
        forge.mkdir()
        (forge / "spec.md").write_text("# Test App\nA simple user list app.")
        (forge / "rules.md").write_text("Use FastAPI and React.")
        return tmp_path

    def test_planner_produces_plan(self, provider, project_root):
        planner = PlannerAgent(provider, project_root)
        plan = planner.analyze_and_plan("A user list app", "Use FastAPI")
        assert "tasks" in plan
        assert len(plan["tasks"]) >= 2
        assert "decisions" in plan
        assert plan["decisions"]["stack"]["framework"] == "fastapi"
        assert all(task["agent"] == "builder" for task in plan["tasks"])
        assert {task["specialization"] for task in plan["tasks"]} >= {"setup", "backend", "frontend"}

    def test_backend_produces_files_and_contracts(self, provider, project_root):
        backend = BackendAgent(provider, project_root)
        response = backend.generate_backend("spec", "rules", "{}")
        files = backend.extract_files(response)
        assert len(files) >= 2
        paths = [f[0] for f in files]
        assert "app/main.py" in paths

        # Contract extraction
        contracts = extract_contracts_from_response(response, "backend")
        assert len(contracts["api"]) == 2
        assert len(contracts["models"]) == 1
        assert contracts["api"][0].path == "/users"

    def test_frontend_produces_files(self, provider, project_root):
        frontend = FrontendAgent(provider, project_root)
        response = frontend.generate_frontend("spec", "rules", "{}")
        files = frontend.extract_files(response)
        assert len(files) >= 1
        paths = [f[0] for f in files]
        assert "src/App.jsx" in paths

    def test_reviewer_parses_review(self, provider, project_root):
        reviewer = ReviewerAgent(provider, project_root)
        review = reviewer.review_files(
            {"app/main.py": "from fastapi import FastAPI"},
            "spec", "rules",
        )
        assert review["passed"] is True
        assert review["issues"] == []

    def test_end_to_end_with_bus(self, provider, project_root):
        """Full pipeline through the artifact bus and contract registry."""
        bus = ArtifactBus()
        registry = ContractRegistry()

        # 1. Plan
        planner = PlannerAgent(provider, project_root)
        plan = planner.analyze_and_plan("A user list app", "Use FastAPI")
        assert len(plan["tasks"]) >= 2

        # 2. Backend
        backend = BackendAgent(provider, project_root)
        response = backend.generate_backend("spec", "rules", "{}")
        files = backend.extract_files(response)

        # Validate output
        validation = validate_agent_output("backend", response, files)
        assert validation.valid, validation.reason

        # Publish to bus
        for path, content in files:
            bus.publish(CodeArtifact(
                path=path, content=content, producer_agent="backend",
            ))

        # Extract and register contracts
        contracts = extract_contracts_from_response(response, "backend")
        registry.register_many(contracts["api"])
        registry.register_many(contracts["models"])
        assert len(registry) == 3  # 2 api + 1 model

        # 3. Frontend — gets contracts
        prompt_with_contracts = registry.format_for_prompt()
        assert "GET /users" in prompt_with_contracts

        frontend = FrontendAgent(provider, project_root)
        response = frontend.generate_frontend("spec", "rules", "{}")
        files = frontend.extract_files(response)
        for path, content in files:
            bus.publish(CodeArtifact(
                path=path, content=content, producer_agent="frontend",
            ))

        # 4. Verify bus state
        assert bus.code_count() == 4  # 2 backend + 2 frontend
        all_code = bus.export_files_dict()
        assert "app/main.py" in all_code
        assert "src/App.jsx" in all_code

        # 5. Review — reads from bus
        reviewer = ReviewerAgent(provider, project_root)
        review = reviewer.review_files(all_code, "spec", "rules")
        assert review["passed"] is True

        # 6. Contract validation
        sec = registry.validate_security_coverage()
        assert not sec["passed"]  # POST /users has no auth
        assert any("POST /users" in i for i in sec["issues"])

    def test_validation_catches_empty_backend(self, project_root):
        """If backend returns nothing useful, validation catches it."""
        empty_provider = MockLLMProvider({"generate backend": "I'm not sure what to do"})
        backend = BackendAgent(empty_provider, project_root)
        response = backend.generate_backend("spec", "rules", "{}")
        files = backend.extract_files(response)
        validation = validate_agent_output("backend", response, files)
        assert not validation.valid
        assert "0 file(s)" in validation.reason
