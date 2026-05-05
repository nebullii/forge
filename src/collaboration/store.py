"""Durable artifact persistence for Forge builds."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .models import (
    Artifact,
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
)

logger = logging.getLogger(__name__)

ARTIFACTS_FILE = "artifacts.jsonl"
ARTIFACT_SNAPSHOT_FILE = "artifacts.json"

_ARTIFACT_TYPES: dict[str, type] = {
    "TaskPlanArtifact": TaskPlanArtifact,
    "CodeArtifact": CodeArtifact,
    "BuildOutputArtifact": BuildOutputArtifact,
    "DecisionArtifact": DecisionArtifact,
    "ReviewArtifact": ReviewArtifact,
    "ReviewFindingArtifact": ReviewFindingArtifact,
    "ContractArtifact": ContractArtifact,
    "BuildLogArtifact": BuildLogArtifact,
    "ReworkRequestArtifact": ReworkRequestArtifact,
    "VerificationArtifact": VerificationArtifact,
}

_TUPLE_FIELDS: dict[str, set[str]] = {
    "TaskPlanArtifact": {"planned_files", "depends_on"},
    "CodeArtifact": {"tags"},
    "BuildOutputArtifact": {"planned_files", "files_written", "contract_types"},
    "ReviewArtifact": {"issues"},
    "ReviewFindingArtifact": set(),
    "ContractArtifact": set(),
    "BuildLogArtifact": set(),
    "ReworkRequestArtifact": set(),
    "VerificationArtifact": {"files"},
    "DecisionArtifact": set(),
}


class ArtifactStore:
    """Append-only JSONL artifact log plus latest snapshot export."""

    def __init__(self, forge_path: Path) -> None:
        self.forge_path = forge_path
        self.jsonl_path = forge_path / ARTIFACTS_FILE
        self.snapshot_path = forge_path / ARTIFACT_SNAPSHOT_FILE

    def append(self, artifact: Artifact) -> None:
        entry = self._serialize_artifact(artifact)
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    def load_all(self) -> list[Artifact]:
        if not self.jsonl_path.exists():
            return []

        artifacts: list[Artifact] = []
        try:
            lines = self.jsonl_path.read_text().splitlines()
        except OSError as exc:
            logger.warning("Could not read artifact log at %s (%s)", self.jsonl_path, exc)
            return []

        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                artifacts.append(self._deserialize_artifact(payload))
            except Exception as exc:
                logger.warning("Skipping invalid artifact log entry (%s)", exc)
        return artifacts

    def reset(self) -> None:
        for path in (self.jsonl_path, self.snapshot_path):
            try:
                if path.exists():
                    path.unlink()
            except OSError as exc:
                logger.warning("Could not reset artifact store file %s (%s)", path, exc)

    def write_snapshot(self, artifacts: list[Artifact]) -> None:
        payload = [self._serialize_artifact(artifact) for artifact in artifacts]
        data = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=self.forge_path,
                prefix=".artifacts-",
                suffix=".tmp",
            )
            with os.fdopen(fd, "w") as f:
                f.write(data)
            os.replace(tmp_path, self.snapshot_path)
        except OSError:
            self.snapshot_path.write_text(data)

    def _serialize_artifact(self, artifact: Artifact) -> dict[str, Any]:
        if not is_dataclass(artifact):
            raise TypeError(f"Expected dataclass artifact, got {type(artifact)!r}")
        return {
            "type": type(artifact).__name__,
            "payload": asdict(artifact),
        }

    def _deserialize_artifact(self, entry: dict[str, Any]) -> Artifact:
        name = entry.get("type", "")
        payload = dict(entry.get("payload", {}))
        cls = _ARTIFACT_TYPES.get(name)
        if cls is None or not isinstance(payload, dict):
            raise ValueError(f"Unknown artifact type: {name}")
        for key in _TUPLE_FIELDS.get(name, set()):
            if isinstance(payload.get(key), list):
                payload[key] = tuple(payload[key])
        return cls(**payload)
