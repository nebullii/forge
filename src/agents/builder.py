"""Builder agent -- consolidates backend/frontend/ci/deploy/coder generation."""

from __future__ import annotations

from .base import BaseAgent
from .backend import BackendAgent
from .frontend import FrontendAgent
from .ci_cd import CIAgent
from .deploy import DeployAgent
from .coder import CoderAgent
from ..scaffolds import scaffold_supported_task


class BuilderAgent(BaseAgent):
    """Unified build agent that internally delegates to specialized generators."""

    name = "builder"
    skill_description = (
        "Builds the project implementation by coordinating backend, frontend, "
        "CI/CD, deployment, and general code generation inside a single build role."
    )
    role = (
        "You are Forge Builder, the implementation engine for Forge.\n\n"
        "You translate planned tasks into complete project files. Internally you "
        "may switch between backend, frontend, infrastructure, and general coding "
        "concerns, but you present a single build surface to the orchestrator.\n\n"
        "Always write complete files and follow the project plan exactly."
    )

    def __init__(self, provider, project_root, skills_loader=None):
        super().__init__(provider, project_root, skills_loader=skills_loader)
        self._backend = BackendAgent(provider, project_root, skills_loader=skills_loader)
        self._frontend = FrontendAgent(provider, project_root, skills_loader=skills_loader)
        self._ci = CIAgent(provider, project_root, skills_loader=skills_loader)
        self._deploy = DeployAgent(provider, project_root, skills_loader=skills_loader)
        self._coder = CoderAgent(provider, project_root, skills_loader=skills_loader)

    def build_task(
        self,
        task: dict,
        spec: str,
        rules: str,
        decisions,
        project_context: str = "",
        backend_files: list[str] | None = None,
        deploy_template: str = "",
    ) -> str:
        """Execute a planned task using the appropriate internal specialization."""
        specialization = (
            task.get("specialization")
            or task.get("agent")
            or "coder"
        )

        deterministic = scaffold_supported_task(task, spec, decisions if isinstance(decisions, dict) else {})
        if deterministic is not None:
            return deterministic

        if specialization == "backend":
            return self._backend.generate_backend(spec, rules, str(decisions), project_context)
        if specialization == "frontend":
            return self._frontend.generate_frontend(
                spec,
                rules,
                str(decisions),
                backend_files=backend_files or [],
                project_context=project_context,
            )
        if specialization == "ci":
            return self._ci.generate_ci(spec, decisions, rules)
        if specialization == "deploy":
            return self._deploy.generate_deploy(spec, decisions, deploy_template, rules)

        build_task = {
            "name": task.get("name", "Build task"),
            "description": task.get("description", ""),
            "files": task.get("files", []),
        }
        return self._coder.generate_files(build_task, spec, rules, str(decisions), project_context)
