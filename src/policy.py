"""Build governance policy for approvals, stack restrictions, and exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml


@dataclass
class BuildPolicy:
    """Project-level governance policy loaded from .forge/policy.yaml."""

    schema_version: int = 1
    mode: str = "balanced"
    approval_mode: str = "off"           # off | interactive
    approval_gates: list[str] = field(default_factory=list)
    allowed_frameworks: list[str] = field(default_factory=list)
    allowed_agents: list[str] = field(default_factory=list)
    allow_adk: bool = True
    require_review: bool = False
    auto_export_openapi: bool = True
    openapi_title: str = "Forge Generated API"

    def should_gate(self, gate: str) -> bool:
        return gate in set(self.approval_gates)

    def normalized_frameworks(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_frameworks if item.strip()}

    def normalized_agents(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_agents if item.strip()}

    def validate_stack(self, stack: dict) -> list[str]:
        if not self.allowed_frameworks:
            return []

        allowed = self.normalized_frameworks()
        seen = []
        for key in ("framework", "frontend"):
            value = str(stack.get(key, "")).strip()
            if value and value.lower() not in ("none",):
                seen.append((key, value))

        errors = []
        for key, value in seen:
            if value.lower() not in allowed:
                errors.append(
                    f"Policy blocked stack {key}='{value}'. Allowed frameworks: "
                    f"{', '.join(sorted(allowed))}."
                )
        return errors

    def validate_agents(self, agents: Iterable[str]) -> list[str]:
        if not self.allowed_agents:
            return []

        allowed = self.normalized_agents()
        errors = []
        for agent in agents:
            name = (agent or "").strip().lower()
            if name and name not in allowed:
                errors.append(
                    f"Policy blocked agent '{agent}'. Allowed agents: "
                    f"{', '.join(sorted(allowed))}."
                )
        return errors

    def validate_plan(self, stack: dict, agents: Iterable[str], use_adk: bool) -> list[str]:
        errors = []
        if use_adk and not self.allow_adk:
            errors.append("Policy blocked ADK multi-agent mode for this project.")
        errors.extend(self.validate_stack(stack))
        errors.extend(self.validate_agents(agents))
        return errors


_POLICY_FIELDS = {f.name for f in BuildPolicy.__dataclass_fields__.values()}  # type: ignore[attr-defined]


def load_build_policy(forge_path: Path) -> BuildPolicy:
    """Load .forge/policy.yaml if present, otherwise return defaults."""
    policy_path = forge_path / "policy.yaml"
    if not policy_path.exists():
        return BuildPolicy()

    try:
        data = yaml.safe_load(policy_path.read_text()) or {}
    except (yaml.YAMLError, OSError):
        return BuildPolicy()

    if not isinstance(data, dict):
        return BuildPolicy()

    known = {k: v for k, v in data.items() if k in _POLICY_FIELDS}
    return BuildPolicy(**known)


def write_default_policy(path: Path) -> None:
    """Write a default policy file for new projects."""
    policy = BuildPolicy()
    data = {
        "schema_version": policy.schema_version,
        "mode": policy.mode,
        "approval_mode": policy.approval_mode,
        "approval_gates": policy.approval_gates,
        "allowed_frameworks": policy.allowed_frameworks,
        "allowed_agents": policy.allowed_agents,
        "allow_adk": policy.allow_adk,
        "require_review": policy.require_review,
        "auto_export_openapi": policy.auto_export_openapi,
        "openapi_title": policy.openapi_title,
    }
    path.write_text(
        "# Forge build policy\n"
        "# approval_gates can include: plan, build, review, task_write\n"
        "# allowed_frameworks and allowed_agents are optional allowlists\n"
        + yaml.dump(data, default_flow_style=False, sort_keys=False)
    )
