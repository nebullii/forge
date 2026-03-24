"""Thread-safe artifact exchange bus for inter-agent collaboration.

The ArtifactBus is the single source of truth for all data produced during a
build.  Every agent publishes its outputs here; every consumer reads from here.
All mutations go through an ``RLock`` so the bus is safe for concurrent use
from ``ThreadPoolExecutor`` workers.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from .models import (
    Artifact,
    CodeArtifact,
    DecisionArtifact,
    ReviewArtifact,
    ContractArtifact,
    BuildLogArtifact,
)


class ArtifactBus:
    """Central, thread-safe artifact store shared by all agents during a build.

    Read methods return *copies / snapshots* so callers never hold the lock
    while processing results.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._artifacts: List[Artifact] = []
        # Latest code artifact per file path (highest version wins)
        self._code_by_path: Dict[str, CodeArtifact] = {}
        # Secondary indexes
        self._by_task: Dict[str, List[Artifact]] = defaultdict(list)
        self._by_agent: Dict[str, List[Artifact]] = defaultdict(list)
        self._by_type: Dict[Type, List[Artifact]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(self, artifact: Artifact) -> None:
        """Publish a single artifact to the bus."""
        with self._lock:
            self._artifacts.append(artifact)

            if hasattr(artifact, "task_id") and artifact.task_id:
                self._by_task[artifact.task_id].append(artifact)
            if hasattr(artifact, "producer_agent") and artifact.producer_agent:
                self._by_agent[artifact.producer_agent].append(artifact)

            self._by_type[type(artifact)].append(artifact)

            if isinstance(artifact, CodeArtifact):
                existing = self._code_by_path.get(artifact.path)
                if existing is None or artifact.version >= existing.version:
                    self._code_by_path[artifact.path] = artifact

    def publish_many(self, artifacts: List[Artifact]) -> None:
        """Publish multiple artifacts atomically."""
        with self._lock:
            for artifact in artifacts:
                self.publish(artifact)

    # ------------------------------------------------------------------
    # Querying — code artifacts
    # ------------------------------------------------------------------

    def latest(self, path: str) -> Optional[CodeArtifact]:
        """Return the latest ``CodeArtifact`` for *path*, or ``None``."""
        with self._lock:
            return self._code_by_path.get(path)

    def all_code(self) -> List[CodeArtifact]:
        """Return all latest ``CodeArtifact`` objects (one per path)."""
        with self._lock:
            return list(self._code_by_path.values())

    def export_files_dict(self) -> Dict[str, str]:
        """Export latest code artifacts as ``{path: content}``."""
        with self._lock:
            return {p: a.content for p, a in self._code_by_path.items()}

    def export_files_list(self) -> List[Tuple[str, str]]:
        """Export latest code artifacts as ``[(path, content), ...]``."""
        with self._lock:
            return [(a.path, a.content) for a in self._code_by_path.values()]

    # ------------------------------------------------------------------
    # Querying — by index
    # ------------------------------------------------------------------

    def by_task(self, task_id: str) -> List[Artifact]:
        """Return all artifacts for *task_id* (snapshot)."""
        with self._lock:
            return list(self._by_task.get(task_id, []))

    def by_agent(self, agent_name: str) -> List[Artifact]:
        """Return all artifacts produced by *agent_name* (snapshot)."""
        with self._lock:
            return list(self._by_agent.get(agent_name, []))

    def by_type(self, artifact_type: Type) -> List[Artifact]:
        """Return all artifacts of the given type (snapshot)."""
        with self._lock:
            return list(self._by_type.get(artifact_type, []))

    # ------------------------------------------------------------------
    # Querying — filtered snapshots
    # ------------------------------------------------------------------

    def snapshot(
        self,
        filter_fn: Optional[Callable[[Artifact], bool]] = None,
    ) -> List[Artifact]:
        """Return a snapshot of all artifacts, optionally filtered."""
        with self._lock:
            if filter_fn is None:
                return list(self._artifacts)
            return [a for a in self._artifacts if filter_fn(a)]

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def get_decisions(self) -> Dict[str, Any]:
        """Aggregate all ``DecisionArtifact`` values into ``{key: value}``."""
        with self._lock:
            decisions: Dict[str, Any] = {}
            for art in self._by_type.get(DecisionArtifact, []):
                decisions[art.key] = art.value
            return decisions

    def get_errors(self) -> List[str]:
        """Return all error-level log messages."""
        with self._lock:
            return [
                art.message
                for art in self._by_type.get(BuildLogArtifact, [])
                if art.level == "error"
            ]

    def get_warnings(self) -> List[str]:
        """Return all warning-level log messages."""
        with self._lock:
            return [
                art.message
                for art in self._by_type.get(BuildLogArtifact, [])
                if art.level == "warning"
            ]

    def get_review(self) -> Optional[Dict[str, Any]]:
        """Return the latest review result, or ``None``."""
        with self._lock:
            reviews = self._by_type.get(ReviewArtifact, [])
            if not reviews:
                return None
            last: ReviewArtifact = reviews[-1]
            return {
                "passed": last.passed,
                "issues": list(last.issues),
            }

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        with self._lock:
            return len(self._artifacts)

    def code_count(self) -> int:
        """Number of unique file paths published."""
        with self._lock:
            return len(self._code_by_path)

    def summary(self) -> Dict[str, int]:
        """Return counts by artifact type name."""
        with self._lock:
            return {
                t.__name__: len(items) for t, items in self._by_type.items()
            }
