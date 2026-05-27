"""Typed models for Forge Spec API primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_PRIMITIVES = {
    "project",
    "auth.email_password",
    "db.model",
    "api.resource",
    "ui.page",
    "ui.table",
    "ui.form",
    "test.case",
    "deploy.target",
}


@dataclass(frozen=True)
class SpecDiagnostic:
    """Validation message tied to a source line."""

    line: int
    severity: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"line": self.line, "severity": self.severity, "message": self.message}


@dataclass
class SpecPrimitive:
    """One parsed Forge Spec API primitive."""

    type: str
    name: str = ""
    body: dict[str, Any] = field(default_factory=dict)
    line: int = 0
    raw: str = ""

    @property
    def ref(self) -> str:
        return f"{self.type}.{self.name}" if self.name else self.type

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "body": self.body,
            "line": self.line,
            "ref": self.ref,
        }


@dataclass
class SpecDocument:
    """Parsed spec plus diagnostics."""

    primitives: list[SpecPrimitive] = field(default_factory=list)
    diagnostics: list[SpecDiagnostic] = field(default_factory=list)
    prose: str = ""
    spec_api_version: str = "0.1"

    @property
    def valid(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "spec_api_version": self.spec_api_version,
            "primitives": [item.to_dict() for item in self.primitives],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }
