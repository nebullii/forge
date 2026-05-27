"""Compile Spec API primitives into a deterministic task graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import SpecDocument, SpecPrimitive


@dataclass
class Task:
    id: str
    role: str
    specialization: str
    name: str = ""
    description: str = ""
    inputs: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name or self.id,
            "description": self.description,
            "role": self.role,
            "specialization": self.specialization,
            "inputs": self.inputs,
            "depends_on": self.depends_on,
            "expected_outputs": self.expected_outputs,
        }


@dataclass
class TaskGraph:
    valid: bool
    tasks: list[Task] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "tasks": [task.to_dict() for task in self.tasks],
            "diagnostics": self.diagnostics,
        }


def compile_task_graph(doc: SpecDocument) -> TaskGraph:
    """Compile primitives into role-specific tasks."""
    graph = TaskGraph(
        valid=doc.valid,
        diagnostics=[item.to_dict() for item in doc.diagnostics],
    )
    if not doc.valid:
        return graph

    tasks: list[Task] = []
    setup_inputs = [item.ref for item in doc.primitives if item.type in {"project", "auth.email_password"}]
    if setup_inputs:
        tasks.append(Task(
            id="setup.project",
            role="builder",
            specialization="setup",
            name="Set up project scaffold",
            description="Create the base project structure and configuration from project/auth primitives.",
            inputs=setup_inputs,
            expected_outputs=["project_scaffold", "config_files"],
        ))

    backend_tasks = _backend_tasks(doc)
    tasks.extend(backend_tasks)
    frontend_tasks = _frontend_tasks(doc, backend_tasks)
    tasks.extend(frontend_tasks)
    tasks.extend(_test_tasks(doc, backend_tasks, frontend_tasks))
    tasks.extend(_deploy_tasks(doc))

    graph.tasks = tasks
    return graph


def _backend_tasks(doc: SpecDocument) -> list[Task]:
    models = {item.name: item for item in doc.primitives if item.type == "db.model"}
    tasks: list[Task] = []
    for resource in _primitives(doc, "api.resource"):
        model = str(resource.body.get("model") or "")
        inputs = [resource.ref]
        if model in models:
            inputs.insert(0, models[model].ref)
        auth = [item.ref for item in doc.primitives if item.type == "auth.email_password"]
        inputs.extend(auth)
        tasks.append(Task(
            id=f"backend.{resource.name}",
            role="backend",
            specialization="backend",
            name=f"Build {resource.name} backend resource",
            description="Implement database models, API routes, validation, and machine-readable contracts for this resource.",
            inputs=inputs,
            depends_on=["setup.project"] if _has_setup(doc) else [],
            expected_outputs=["backend_files", "api_contracts", "model_contracts"],
        ))

    standalone_models = [
        item for item in models.values()
        if not any(str(res.body.get("model") or "") == item.name for res in _primitives(doc, "api.resource"))
    ]
    for model in standalone_models:
        tasks.append(Task(
            id=f"backend.model.{model.name}",
            role="backend",
            specialization="backend",
            name=f"Build {model.name} data model",
            description="Implement this data model and publish its model contract.",
            inputs=[model.ref],
            depends_on=["setup.project"] if _has_setup(doc) else [],
            expected_outputs=["backend_files", "model_contracts"],
        ))
    return tasks


def _frontend_tasks(doc: SpecDocument, backend_tasks: list[Task]) -> list[Task]:
    deps = [task.id for task in backend_tasks]
    tasks: list[Task] = []
    for primitive in doc.primitives:
        if primitive.type not in {"ui.page", "ui.table", "ui.form"}:
            continue
        role_id = primitive.type.replace("ui.", "frontend.")
        tasks.append(Task(
            id=f"{role_id}.{primitive.name}",
            role="frontend",
            specialization="frontend",
            name=f"Build {primitive.name} {primitive.type}",
            description="Implement the UI primitive using backend contracts exactly where data access is required.",
            inputs=[primitive.ref],
            depends_on=deps,
            expected_outputs=["frontend_files", "ui_contract_usage"],
        ))
    return tasks


def _test_tasks(doc: SpecDocument, backend_tasks: list[Task], frontend_tasks: list[Task]) -> list[Task]:
    deps = [task.id for task in backend_tasks + frontend_tasks]
    return [
        Task(
            id=f"test.{primitive.name}",
            role="tester",
            specialization="test",
            name=f"Create {primitive.name} tests",
            description="Generate tests or verification requirements for this declared behavior.",
            inputs=[primitive.ref],
            depends_on=deps,
            expected_outputs=["tests", "verification_requirements"],
        )
        for primitive in _primitives(doc, "test.case")
    ]


def _deploy_tasks(doc: SpecDocument) -> list[Task]:
    return [
        Task(
            id=f"deploy.{primitive.name}",
            role="deploy",
            specialization="deploy",
            name=f"Create {primitive.name} deployment config",
            description="Generate deployment configuration for this target.",
            inputs=[primitive.ref],
            depends_on=[],
            expected_outputs=["deployment_config"],
        )
        for primitive in _primitives(doc, "deploy.target")
    ]


def _primitives(doc: SpecDocument, primitive_type: str) -> list[SpecPrimitive]:
    return [item for item in doc.primitives if item.type == primitive_type]


def _has_setup(doc: SpecDocument) -> bool:
    return any(item.type in {"project", "auth.email_password"} for item in doc.primitives)
