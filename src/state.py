"""Build state management -- YAML-based, file-stored, resumable."""

import hashlib
import yaml
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path


@dataclass
class TaskState:
    """State of a single build task."""
    id: str
    name: str
    description: str = ""
    status: str = "pending"
    agent: str = ""
    files_written: list[str] = field(default_factory=list)
    error: str = ""
    started_at: str = ""
    completed_at: str = ""


@dataclass
class BuildState:
    """Full build state, serialized to .forge/build-state.yaml."""
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


def load_build_state(forge_path: Path) -> BuildState:
    """Load build state from .forge/build-state.yaml, or return fresh state."""
    state_path = forge_path / STATE_FILE
    if not state_path.exists():
        return BuildState()

    with open(state_path) as f:
        data = yaml.safe_load(f) or {}

    tasks = []
    for t in data.pop("tasks", []):
        tasks.append(TaskState(**t))
    data["tasks"] = tasks

    return BuildState(**data)


def save_build_state(forge_path: Path, state: BuildState):
    """Persist build state to .forge/build-state.yaml."""
    state_path = forge_path / STATE_FILE
    data = asdict(state)
    with open(state_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def compute_spec_hash(forge_path: Path) -> str:
    """SHA256 hash of spec.md for change detection."""
    spec_path = forge_path / "spec.md"
    if not spec_path.exists():
        return ""
    return hashlib.sha256(spec_path.read_text().encode()).hexdigest()[:16]
