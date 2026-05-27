"""Tests for local response evaluation helpers."""

from pathlib import Path

from src.evals import run_eval, run_smoke_eval


def test_eval_planner_accepts_json_response():
    response = """{
      "decisions": {
        "stack": {"language": "Python", "framework": "FastAPI", "database": "sqlite3", "frontend": "react", "styling": "tailwind"},
        "architecture": "FastAPI serves a React frontend.",
        "reasoning": "Complexity level 2.",
        "directory_structure": "/\\n├── backend/\\n└── frontend/"
      },
      "tasks": [
        {"id": "task_01", "name": "Setup", "description": "Create skeleton", "agent": "builder", "specialization": "setup", "files": ["backend/main.py"]}
      ]
    }"""
    result = run_eval("planner", response)
    assert result.passed
    assert result.score >= 70


def test_eval_reviewer_accepts_json_response():
    response = '{"passed": true, "issues": []}'
    result = run_eval("reviewer", response)
    assert result.passed


def test_eval_backend_requires_contracts():
    response = '{"files": [{"path": "backend/main.py", "content": "print(1)\\n"}]}'
    result = run_eval("backend", response)
    assert not result.passed


def test_eval_backend_accepts_structured_response():
    response = """{
      "files": [{"path": "backend/main.py", "content": "print(1)\\n"}],
      "contracts": {
        "api": [{"method": "GET", "path": "/health", "response_schema": {"ok": "bool"}, "auth": "none"}],
        "models": [],
        "events": []
      }
    }"""
    result = run_eval("backend", response)
    assert result.passed


def test_eval_fixture_corpus_files_parse():
    fixture_dir = Path(__file__).parent / "fixtures" / "evals"
    for file_path in fixture_dir.iterdir():
        kind = file_path.stem.split("-", 1)[0]
        result = run_eval(kind, file_path.read_text())
        assert result.passed, f"{file_path.name}: {result.summary}"


def test_smoke_eval_writes_artifact(tmp_path):
    result = run_smoke_eval("crm-basic", output_dir=tmp_path)

    assert result.passed
    assert (tmp_path / "crm-basic.json").exists()
