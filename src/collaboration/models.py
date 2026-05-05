"""Typed artifact models for inter-agent collaboration.

Every piece of data exchanged between agents flows through the ArtifactBus
as one of these immutable artifact types.  Frozen dataclasses ensure that
once an artifact is published it cannot be accidentally mutated by another
thread or consumer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Tuple, Union


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Plan artifacts — planner → builder handoff
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskPlanArtifact:
    """A machine-readable task manifest emitted by the planner."""

    task_id: str
    name: str
    description: str
    producer_agent: str = "planner"
    specialization: str = "coder"
    planned_files: Tuple[str, ...] = ()
    depends_on: Tuple[str, ...] = ()
    created_at: str = field(default_factory=_now)


# ---------------------------------------------------------------------------
# Code artifacts — generated source files
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CodeArtifact:
    """A generated source file published by an agent."""

    path: str
    content: str
    producer_agent: str
    task_id: str = ""
    artifact_type: str = "code"          # code | config | test | doc
    language: str = ""
    tags: Tuple[str, ...] = ()
    created_at: str = field(default_factory=_now)
    version: int = 1


# ---------------------------------------------------------------------------
# Build artifacts — builder → reviewer/verifier handoff
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BuildOutputArtifact:
    """A structured summary of one completed builder task."""

    task_id: str
    producer_agent: str = "builder"
    specialization: str = "coder"
    planned_files: Tuple[str, ...] = ()
    files_written: Tuple[str, ...] = ()
    contract_types: Tuple[str, ...] = ()
    created_at: str = field(default_factory=_now)


# ---------------------------------------------------------------------------
# Decision artifacts — architectural / tech-stack decisions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DecisionArtifact:
    """An architectural or technology decision made by an agent."""

    key: str                              # e.g. "stack", "architecture"
    value: Any
    producer_agent: str
    task_id: str = ""
    reasoning: str = ""
    created_at: str = field(default_factory=_now)


# ---------------------------------------------------------------------------
# Review artifacts — code-review or audit results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReviewArtifact:
    """A code-review or security-audit result."""

    target_path: str                      # "" for project-wide reviews
    producer_agent: str
    task_id: str = ""
    passed: bool = True
    issues: Tuple[Dict[str, Any], ...] = ()
    created_at: str = field(default_factory=_now)


# ---------------------------------------------------------------------------
# Review finding artifacts — reviewer/security → builder handoff
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReviewFindingArtifact:
    """A structured issue discovered during review."""

    target_path: str
    message: str
    severity: str
    producer_agent: str
    task_id: str = ""
    issue_type: str = "review"
    retryable: bool = True
    created_at: str = field(default_factory=_now)


# ---------------------------------------------------------------------------
# Contract artifacts — structured API / data contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContractArtifact:
    """A structured contract (API endpoint, data model, event) published to the bus."""

    contract_type: str                    # "api" | "model" | "event"
    data: Dict[str, Any] = field(default_factory=dict)
    producer_agent: str = ""
    task_id: str = ""
    created_at: str = field(default_factory=_now)


# ---------------------------------------------------------------------------
# Build-log artifacts — info / warning / error entries
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BuildLogArtifact:
    """A build-log entry that any agent or the orchestrator can emit."""

    message: str
    producer_agent: str = ""
    level: str = "info"                   # info | warning | error
    task_id: str = ""
    created_at: str = field(default_factory=_now)


# ---------------------------------------------------------------------------
# Rework request artifacts — feedback loop
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReworkRequestArtifact:
    """A request to rework a specific file, issued by reviewer or security agent.

    The orchestrator sends the file back to *original_agent* for a single
    rework attempt.  Capped at one retry per file to prevent infinite loops.
    """

    target_path: str
    original_agent: str
    issue: str
    producer_agent: str = ""              # who raised the rework (reviewer / security)
    task_id: str = ""
    created_at: str = field(default_factory=_now)


# ---------------------------------------------------------------------------
# Verification artifacts — verifier → orchestrator/builder handoff
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VerificationArtifact:
    """A machine-readable verification result published onto the bus."""

    verifier: str
    category: str
    passed: bool
    producer_agent: str = "verifier"
    severity: str = "error"
    summary: str = ""
    details: str = ""
    files: Tuple[str, ...] = ()
    retryable: bool = False
    created_at: str = field(default_factory=_now)


# ---------------------------------------------------------------------------
# Union alias
# ---------------------------------------------------------------------------

Artifact = Union[
    TaskPlanArtifact,
    CodeArtifact,
    BuildOutputArtifact,
    DecisionArtifact,
    ReviewArtifact,
    ReviewFindingArtifact,
    ContractArtifact,
    BuildLogArtifact,
    ReworkRequestArtifact,
    VerificationArtifact,
]
