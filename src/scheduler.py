"""Dependency-aware parallel task scheduler for builder specializations.

Computes a dependency graph from task lanes and runs independent tasks
concurrently via ``ThreadPoolExecutor``, while respecting ordering constraints.

Dependency rules:
- Tasks assigned to the **same lane** run sequentially (in plan order).
- Tasks assigned to **different lanes** follow ``TASK_DEPENDENCIES``
  (e.g., frontend waits for backend; integration waits for all implementation lanes).
- Tasks with no upstream dependencies run in parallel.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Dependency rules (builder-specialization level)
# ---------------------------------------------------------------------------

TASK_DEPENDENCIES: Dict[str, Set[str]] = {
    "setup":       set(),
    "backend":     {"setup"},
    "ci":          {"setup"},
    "deploy":      {"setup"},
    "frontend":    {"backend"},
    "integration": {"setup", "backend", "frontend", "ci", "deploy"},
    "security":    {"backend", "frontend"},
    "coder":       {"setup"},
}


# ---------------------------------------------------------------------------
# Dependency graph
# ---------------------------------------------------------------------------

@dataclass
class TaskNode:
    """A task in the dependency graph."""
    task_id: str
    agent: str
    depends_on: Set[str] = field(default_factory=set)   # upstream task IDs


def _task_lane(task) -> str:
    if isinstance(task, dict):
        agent = (task.get("agent") or "").strip().lower()
        specialization = (task.get("specialization") or "").strip().lower()
    else:
        agent = (getattr(task, "agent", "") or "").strip().lower()
        specialization = (getattr(task, "specialization", "") or "").strip().lower()

    if agent == "builder":
        return specialization or "coder"
    if agent:
        return agent
    return "setup"


def build_dependency_graph(tasks: list) -> List[TaskNode]:
    """Build a dependency graph from a list of task dicts or TaskState objects.

    Each element must have ``id`` (or ``.id``) and either ``specialization`` or
    ``agent`` (or attribute equivalents).
    attributes/keys.  Returns an ordered list of ``TaskNode`` objects.
    """
    nodes: List[TaskNode] = []
    last_by_lane: Dict[str, str] = {}           # lane → most-recent task ID

    for task in tasks:
        tid = task["id"] if isinstance(task, dict) else task.id
        agent = _task_lane(task)
        deps: Set[str] = set()

        # Same-lane sequential ordering
        if agent in last_by_lane:
            deps.add(last_by_lane[agent])

        # Cross-lane dependencies
        for dep_agent in TASK_DEPENDENCIES.get(agent, set()):
            if dep_agent in last_by_lane:
                deps.add(last_by_lane[dep_agent])

        nodes.append(TaskNode(task_id=tid, agent=agent, depends_on=deps))
        last_by_lane[agent] = tid

    return nodes


# ---------------------------------------------------------------------------
# Parallel scheduler
# ---------------------------------------------------------------------------

class ParallelScheduler:
    """Execute tasks respecting a dependency graph, with bounded parallelism."""

    def __init__(self, max_workers: int = 4) -> None:
        self.max_workers = max_workers

    def execute(
        self,
        nodes: List[TaskNode],
        run_fn: Callable[[str], Optional[str]],
    ) -> List[str]:
        """Run tasks in dependency order.

        *run_fn(task_id)* is called for each task.  It should return ``None``
        on success or raise an exception on failure.

        Returns a list of **failed** task IDs.  Transitive dependents of a
        failed task are skipped automatically.
        """
        if not nodes:
            return []

        # Build lookup structures
        id_to_node = {n.task_id: n for n in nodes}
        remaining = {n.task_id for n in nodes}
        completed: Set[str] = set()
        failed: Set[str] = set()
        skipped: Set[str] = set()

        # Reverse-dependency map: task_id → set of downstream task IDs
        downstream: Dict[str, Set[str]] = {n.task_id: set() for n in nodes}
        for n in nodes:
            for dep_id in n.depends_on:
                if dep_id in downstream:
                    downstream[dep_id].add(n.task_id)

        def _ready() -> List[str]:
            """Return task IDs whose dependencies are all complete."""
            return [
                tid for tid in remaining
                if tid not in skipped
                and id_to_node[tid].depends_on.issubset(completed)
            ]

        def _skip_descendants(tid: str) -> None:
            """Mark all transitive dependents of *tid* as skipped."""
            stack = list(downstream.get(tid, []))
            while stack:
                child = stack.pop()
                if child not in skipped:
                    skipped.add(child)
                    remaining.discard(child)
                    stack.extend(downstream.get(child, []))

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            in_flight: Dict[Future, str] = {}

            while remaining or in_flight:
                # Submit all ready tasks
                ready = _ready()
                for tid in ready:
                    if tid not in {v for v in in_flight.values()}:
                        future = pool.submit(run_fn, tid)
                        in_flight[future] = tid
                        remaining.discard(tid)

                if not in_flight:
                    # No tasks in flight and nothing ready → done (or deadlock)
                    break

                # Wait for at least one to finish
                done_futures = set()
                for future in as_completed(in_flight):
                    done_futures.add(future)
                    tid = in_flight[future]
                    try:
                        future.result()
                        completed.add(tid)
                    except Exception:
                        failed.add(tid)
                        _skip_descendants(tid)
                    break  # Re-check ready set after each completion

                for f in done_futures:
                    del in_flight[f]

        return sorted(failed | skipped)
