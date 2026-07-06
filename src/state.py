"""Build state management -- YAML-based, file-stored, resumable."""

import hashlib
import logging
import os
import tempfile
import yaml
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TaskState:
    """State of a single build task."""
    id: str
    name: str
    description: str = ""
    status: str = "pending"
    agent: str = ""
    specialization: str = ""
    planned_files: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    prompt: str = ""        # optional task-specific prompt override
    contracts: str = ""     # API contracts this task exposes
    files_written: list[str] = field(default_factory=list)
    error: str = ""
    started_at: str = ""
    completed_at: str = ""


@dataclass
class BuildState:
    """Full build state, serialized to .forge/build-state.yaml."""
    schema_version: int = 2
    build_id: str = ""
    status: str = "not_started"
    started_at: str = ""
    completed_at: str = ""
    provider: str = ""
    model: str = ""
    spec_hash: str = ""
    tasks: list[TaskState] = field(default_factory=list)
    decisions: str = ""
    current_task_index: int = 0
    files_written: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


STATE_FILE = "build-state.yaml"

# Fields present in each schema version. Missing fields get their dataclass default.
_TASK_STATE_FIELDS = {f.name for f in TaskState.__dataclass_fields__.values()}  # type: ignore[attr-defined]
_BUILD_STATE_FIELDS = {f.name for f in BuildState.__dataclass_fields__.values()}  # type: ignore[attr-defined]


def _load_task(t: dict) -> TaskState:
    """Construct TaskState tolerantly — ignore unknown keys, fill missing ones with defaults."""
    known = {k: v for k, v in t.items() if k in _TASK_STATE_FIELDS}
    return TaskState(**known)


def _load_build(data: dict) -> BuildState:
    """Construct BuildState tolerantly — ignore unknown keys, fill missing ones with defaults."""
    known = {k: v for k, v in data.items() if k in _BUILD_STATE_FIELDS}
    return BuildState(**known)


def load_build_state(forge_path: Path) -> BuildState:
    """Load build state from .forge/build-state.yaml, or return fresh state.

    Handles corrupted YAML gracefully — logs a warning and returns fresh state
    rather than crashing the CLI.
    """
    state_path = forge_path / STATE_FILE
    if not state_path.exists():
        return BuildState()

    try:
        with open(state_path) as f:
            data = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("Corrupted build state at %s (%s), starting fresh", state_path, exc)
        return BuildState()

    if not isinstance(data, dict):
        logger.warning("Invalid build state (expected dict), starting fresh")
        return BuildState()

    tasks = [_load_task(t) for t in data.pop("tasks", []) if isinstance(t, dict)]
    data["tasks"] = tasks

    return _load_build(data)


def save_build_state(forge_path: Path, state: BuildState):
    """Persist build state to .forge/build-state.yaml.

    Uses atomic write (temp file + rename) so a crash mid-write can't corrupt
    the state file.
    """
    state_path = forge_path / STATE_FILE
    data = asdict(state)
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=forge_path, prefix=".state-", suffix=".tmp",
        )
        with os.fdopen(fd, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        os.replace(tmp_path, state_path)
    except OSError:
        # Fallback: direct write (e.g., filesystem doesn't support rename)
        with open(state_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def compute_spec_hash(forge_path: Path) -> str:
    """SHA256 hash of spec.md for change detection."""
    spec_path = forge_path / "spec.md"
    if not spec_path.exists():
        return ""
    return hashlib.sha256(spec_path.read_text().encode()).hexdigest()[:16]
