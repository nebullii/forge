"""Local evaluation helpers for structured agent responses."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

from .specapi import compile_task_graph, parse_spec_text
from .agents.planner import PlannerAgent
from .agents.reviewer import ReviewerAgent
from .agents.base import BaseAgent
from .collaboration.validation import validate_agent_output


@dataclass(frozen=True)
class EvalResult:
    kind: str
    passed: bool
    score: int
    summary: str


def evaluate_planner_response(response: str) -> EvalResult:
    agent = PlannerAgent.__new__(PlannerAgent)
    agent._TOP_LEVEL_AGENT = PlannerAgent._TOP_LEVEL_AGENT
    agent._LEGACY_SPECIALIZATIONS = PlannerAgent._LEGACY_SPECIALIZATIONS
    try:
        plan = PlannerAgent._parse_plan(agent, response)
    except Exception as exc:
        return EvalResult("planner", False, 0, f"invalid planner response: {exc}")

    tasks = plan.get("tasks", [])
    decisions = plan.get("decisions", {})
    missing_structure = not bool(decisions.get("directory_structure"))
    if missing_structure:
        return EvalResult("planner", False, 40, "plan parsed but missing directory_structure")
    return EvalResult("planner", True, min(100, 60 + len(tasks) * 10), f"parsed {len(tasks)} task(s)")


def evaluate_reviewer_response(response: str) -> EvalResult:
    agent = ReviewerAgent.__new__(ReviewerAgent)
    parsed = ReviewerAgent._parse_review(agent, response)
    issues = parsed.get("issues", [])
    passed = isinstance(parsed.get("passed"), bool) and isinstance(issues, list)
    return EvalResult(
        "reviewer",
        passed,
        100 if passed else 0,
        f"parsed review with {len(issues)} issue(s)" if passed else "invalid reviewer response",
    )


def evaluate_backend_response(response: str) -> EvalResult:
    agent = BaseAgent.__new__(BaseAgent)
    files = BaseAgent.extract_files(agent, response)
    validation = validate_agent_output("backend", response, files)
    return EvalResult(
        "backend",
        validation.valid,
        100 if validation.valid else 0,
        validation.reason or f"validated {len(files)} file(s)",
    )


def run_eval(kind: str, response: str) -> EvalResult:
    evaluators: dict[str, Callable[[str], EvalResult]] = {
        "planner": evaluate_planner_response,
        "reviewer": evaluate_reviewer_response,
        "backend": evaluate_backend_response,
    }
    try:
        evaluator = evaluators[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported eval kind: {kind}") from exc
    return evaluator(response)


SMOKE_SPECS = {
    "crm-basic": """# Project: Freelancer CRM

.project
  spec_api_version: 0.1
  type: web_app
  stack: react_fastapi_sqlite

.auth.email_password
  sessions: jwt
  roles: user

.db.model Client
  fields:
    name: string required
    email: email required
    status: enum[lead,active,inactive]

.api.resource clients
  model: Client
  actions: list, create, update, delete
  auth: required

.ui.table client_list
  source: GET /api/clients
  columns: name, email, status

.ui.form create_client
  submit: POST /api/clients
  fields: name, email, status

.test.case client_crud
  covers: clients
""",
    "api-only-crud": """# Project: API Contacts

.project
  spec_api_version: 0.1
  type: api
  stack: fastapi_sqlite

.db.model Contact
  fields:
    name: string required
    email: email required

.api.resource contacts
  model: Contact
  actions: list, create, update, delete
  auth: public

.test.case contact_crud
  covers: contacts
""",
    "frontend-contracts": """# Project: Client Portal

.project
  spec_api_version: 0.1
  type: web_app
  stack: react_fastapi_sqlite

.db.model Client
  fields:
    name: string required

.api.resource clients
  model: Client
  actions: list, create
  auth: public

.ui.table client_list
  source: GET /api/clients
  columns: name

.ui.form create_client
  submit: POST /api/clients
  fields: name
""",
}


def run_smoke_eval(name: str, output_dir: Path | None = None) -> EvalResult:
    """Evaluate one production-readiness Spec API smoke scenario without model calls."""
    try:
        spec = SMOKE_SPECS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported smoke eval: {name}") from exc

    doc = parse_spec_text(spec)
    graph = compile_task_graph(doc)
    passed = doc.valid and graph.valid and bool(graph.tasks)
    summary = f"{len(graph.tasks)} task(s), {len(doc.diagnostics)} diagnostic(s)"
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{name}.json").write_text(json.dumps({
            "spec": doc.to_dict(),
            "task_graph": graph.to_dict(),
        }, indent=2, sort_keys=True) + "\n")
    return EvalResult(name, passed, 100 if passed else 0, summary)
