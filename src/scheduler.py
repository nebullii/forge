"""Dependency-aware parallel task scheduler for classic builds.

Computes a dependency graph from agent assignments and runs independent tasks
concurrently via ``ThreadPoolExecutor``, while respecting ordering constraints.

Dependency rules:
- Tasks assigned to the **same agent** run sequentially (in plan order).
- Tasks assigned to **different agents** follow ``AGENT_DEPENDENCIES``
  (e.g., frontend waits for backend; security waits for backend + frontend).
- Tasks with no upstream dependencies run in parallel.

Falls back to sequential execution when all tasks use the same agent.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Dependency rules (agent-level)
# ---------------------------------------------------------------------------

AGENT_DEPENDENCIES: Dict[str, Set[str]] = {
    "coder":    set(),                          # setup tasks — no deps
    "backend":  {"coder"},                      # needs project setup
    "ci":       {"coder"},                      # needs project setup
    "deploy":   {"coder"},                      # needs project setup
    "frontend": {"backend"},                    # needs API contracts
    "security": {"backend", "frontend"},        # needs all code
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


def build_dependency_graph(tasks: list) -> List[TaskNode]:
    """Build a dependency graph from a list of task dicts or TaskState objects.

    Each element must have ``id`` (or ``.id``) and ``agent`` (or ``.agent``)
    attributes/keys.  Returns an ordered list of ``TaskNode`` objects.
    """
    nodes: List[TaskNode] = []
    last_by_agent: Dict[str, str] = {}          # agent → most-recent task ID

    for task in tasks:
        tid = task["id"] if isinstance(task, dict) else task.id
        agent = (task.get("agent", "coder") if isinstance(task, dict)
                 else getattr(task, "agent", "coder")) or "coder"
        deps: Set[str] = set()

        # Same-agent sequential ordering
        if agent in last_by_agent:
            deps.add(last_by_agent[agent])

        # Cross-agent dependencies
        for dep_agent in AGENT_DEPENDENCIES.get(agent, set()):
            if dep_agent in last_by_agent:
                deps.add(last_by_agent[dep_agent])

        nodes.append(TaskNode(task_id=tid, agent=agent, depends_on=deps))
        last_by_agent[agent] = tid

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
