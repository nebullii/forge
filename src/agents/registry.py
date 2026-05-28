"""Local agent capability registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentCapability:
    name: str
    roles: tuple[str, ...]
    specializations: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "roles": list(self.roles),
            "specializations": list(self.specializations),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "constraints": list(self.constraints),
            "description": self.description,
        }


CAPABILITIES: tuple[AgentCapability, ...] = (
    AgentCapability(
        name="planner",
        roles=("planner",),
        inputs=("spec", "rules", "existing_context"),
        outputs=("decisions", "task_plan"),
        description="Turns free-form specs into architecture decisions and tasks.",
    ),
    AgentCapability(
        name="builder",
        roles=("builder", "coder"),
        specializations=("setup", "integration"),
        inputs=("task", "spec", "rules", "decisions", "project_context"),
        outputs=("files", "contracts"),
        constraints=("policy_checked_writes",),
        description="Builds project files through specialist implementation lanes.",
    ),
    AgentCapability(
        name="backend",
        roles=("backend",),
        specializations=("backend",),
        inputs=("spec", "rules", "decisions", "project_context"),
        outputs=("backend_files", "api_contracts", "model_contracts", "event_contracts"),
        description="Generates API routes, data models, schemas, and backend contracts.",
    ),
    AgentCapability(
        name="frontend",
        roles=("frontend",),
        specializations=("frontend",),
        inputs=("spec", "rules", "decisions", "api_contracts", "project_context"),
        outputs=("frontend_files",),
        description="Generates contract-aware frontend code.",
    ),
    AgentCapability(
        name="ci",
        roles=("ci",),
        specializations=("ci",),
        inputs=("spec", "rules", "decisions"),
        outputs=("ci_files",),
        description="Generates CI, Docker, and local automation configuration.",
    ),
    AgentCapability(
        name="deploy",
        roles=("deploy",),
        specializations=("deploy",),
        inputs=("spec", "rules", "decisions", "deploy_template"),
        outputs=("deploy_files",),
        description="Generates deployment configuration and instructions.",
    ),
    AgentCapability(
        name="reviewer",
        roles=("reviewer",),
        inputs=("files", "spec", "rules", "contracts"),
        outputs=("review_findings", "rework_requests"),
        description="Reviews generated code and requests targeted rework.",
    ),
    AgentCapability(
        name="verifier",
        roles=("tester", "test"),
        specializations=("test", "tester"),
        inputs=("files", "contracts"),
        outputs=("verification_results",),
        constraints=("deterministic",),
        description="Runs deterministic checks after generation.",
    ),
    AgentCapability(
        name="security",
        roles=("security",),
        specializations=("security",),
        inputs=("files", "contracts", "policy"),
        outputs=("security_findings",),
        description="Reviews cross-cutting security concerns.",
    ),
)


def list_capabilities() -> list[dict[str, Any]]:
    return [item.to_dict() for item in CAPABILITIES]


def agent_card() -> dict[str, Any]:
    return {
        "name": "forge",
        "version": "0.1",
        "description": "Local-first AI software builder with Spec API, contracts, and deterministic verification.",
        "capabilities": list_capabilities(),
    }


def resolve_agent_for_task(role: str = "", specialization: str = "") -> str:
    """Return the best registered agent name for a task role/specialization."""
    normalized_role = str(role or "").strip().lower()
    normalized_spec = str(specialization or "").strip().lower()
    for capability in CAPABILITIES:
        if normalized_spec and normalized_spec in capability.specializations:
            return capability.name
    for capability in CAPABILITIES:
        if normalized_role and normalized_role in capability.roles:
            return capability.name
    return "builder"
