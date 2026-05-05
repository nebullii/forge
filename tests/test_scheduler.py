"""Tests for the dependency-aware parallel task scheduler."""

import threading
import time

import pytest

from src.scheduler import (
    TASK_DEPENDENCIES,
    TaskNode,
    build_dependency_graph,
    ParallelScheduler,
)


# ---------------------------------------------------------------------------
# Dependency graph construction
# ---------------------------------------------------------------------------

class TestBuildDependencyGraph:
    def test_single_agent_sequential(self):
        tasks = [
            {"id": "t1", "agent": "builder", "specialization": "setup"},
            {"id": "t2", "agent": "builder", "specialization": "setup"},
            {"id": "t3", "agent": "builder", "specialization": "setup"},
        ]
        graph = build_dependency_graph(tasks)
        assert graph[0].depends_on == set()
        assert graph[1].depends_on == {"t1"}
        assert graph[2].depends_on == {"t2"}

    def test_independent_agents_no_cross_deps(self):
        """Backend, CI, Deploy are all independent (depend only on coder)."""
        tasks = [
            {"id": "t1", "agent": "builder", "specialization": "setup"},
            {"id": "t2", "agent": "builder", "specialization": "backend"},
            {"id": "t3", "agent": "builder", "specialization": "ci"},
            {"id": "t4", "agent": "builder", "specialization": "deploy"},
        ]
        graph = build_dependency_graph(tasks)
        # All three depend on coder (t1), not on each other
        assert graph[1].depends_on == {"t1"}
        assert graph[2].depends_on == {"t1"}
        assert graph[3].depends_on == {"t1"}

    def test_frontend_depends_on_backend(self):
        tasks = [
            {"id": "t1", "agent": "builder", "specialization": "backend"},
            {"id": "t2", "agent": "builder", "specialization": "frontend"},
        ]
        graph = build_dependency_graph(tasks)
        assert graph[1].depends_on == {"t1"}

    def test_security_depends_on_backend_and_frontend(self):
        tasks = [
            {"id": "t1", "agent": "builder", "specialization": "backend"},
            {"id": "t2", "agent": "builder", "specialization": "frontend"},
            {"id": "t3", "agent": "security"},
        ]
        graph = build_dependency_graph(tasks)
        assert graph[2].depends_on == {"t1", "t2"}

    def test_full_pipeline(self):
        tasks = [
            {"id": "t1", "agent": "builder", "specialization": "setup"},
            {"id": "t2", "agent": "builder", "specialization": "backend"},
            {"id": "t3", "agent": "builder", "specialization": "ci"},
            {"id": "t4", "agent": "builder", "specialization": "deploy"},
            {"id": "t5", "agent": "builder", "specialization": "frontend"},
            {"id": "t6", "agent": "builder", "specialization": "integration"},
        ]
        graph = build_dependency_graph(tasks)
        assert graph[0].depends_on == set()         # setup: no deps
        assert graph[1].depends_on == {"t1"}        # backend: setup
        assert graph[2].depends_on == {"t1"}        # ci: setup
        assert graph[3].depends_on == {"t1"}        # deploy: setup
        assert graph[4].depends_on == {"t2"}        # frontend: backend
        assert "t2" in graph[5].depends_on          # integration: backend
        assert "t5" in graph[5].depends_on          # integration: frontend
        assert "t3" in graph[5].depends_on          # integration: ci
        assert "t4" in graph[5].depends_on          # integration: deploy

    def test_missing_agent_defaults_to_setup(self):
        tasks = [{"id": "t1"}]  # no agent field
        graph = build_dependency_graph(tasks)
        assert graph[0].agent == "setup"

    def test_empty_tasks(self):
        assert build_dependency_graph([]) == []

    def test_accepts_objects_with_attributes(self):
        """Scheduler should handle TaskState-like objects, not just dicts."""
        class FakeTask:
            def __init__(self, id, agent, specialization=""):
                self.id = id
                self.agent = agent
                self.specialization = specialization

        tasks = [FakeTask("t1", "builder", "setup"), FakeTask("t2", "builder", "backend")]
        graph = build_dependency_graph(tasks)
        assert graph[1].depends_on == {"t1"}


# ---------------------------------------------------------------------------
# Parallel scheduler execution
# ---------------------------------------------------------------------------

class TestParallelScheduler:
    def test_all_tasks_complete(self):
        tasks = [
            {"id": "t1", "agent": "builder", "specialization": "setup"},
            {"id": "t2", "agent": "builder", "specialization": "backend"},
            {"id": "t3", "agent": "builder", "specialization": "frontend"},
        ]
        graph = build_dependency_graph(tasks)
        completed = []

        def run(tid):
            completed.append(tid)

        failed = ParallelScheduler(max_workers=2).execute(graph, run)
        assert failed == []
        assert set(completed) == {"t1", "t2", "t3"}

    def test_ordering_respected(self):
        tasks = [
            {"id": "t1", "agent": "builder", "specialization": "setup"},
            {"id": "t2", "agent": "builder", "specialization": "backend"},
            {"id": "t3", "agent": "builder", "specialization": "frontend"},
        ]
        graph = build_dependency_graph(tasks)
        order = []
        lock = threading.Lock()

        def run(tid):
            with lock:
                order.append(("start", tid))
            time.sleep(0.02)
            with lock:
                order.append(("end", tid))

        ParallelScheduler(max_workers=4).execute(graph, run)

        ends = {tid: i for i, (ev, tid) in enumerate(order) if ev == "end"}
        starts = {tid: i for i, (ev, tid) in enumerate(order) if ev == "start"}

        assert starts["t2"] > ends["t1"], "backend must wait for setup"
        assert starts["t3"] > ends["t2"], "frontend must wait for backend"

    def test_parallel_agents_overlap(self):
        """Backend, CI, Deploy should start before any of them finishes."""
        tasks = [
            {"id": "t1", "agent": "builder", "specialization": "setup"},
            {"id": "t2", "agent": "builder", "specialization": "backend"},
            {"id": "t3", "agent": "builder", "specialization": "ci"},
            {"id": "t4", "agent": "builder", "specialization": "deploy"},
        ]
        graph = build_dependency_graph(tasks)
        order = []
        lock = threading.Lock()

        def run(tid):
            with lock:
                order.append(("start", tid))
            time.sleep(0.05)
            with lock:
                order.append(("end", tid))

        ParallelScheduler(max_workers=4).execute(graph, run)

        starts = {tid: i for i, (ev, tid) in enumerate(order) if ev == "start"}
        ends = {tid: i for i, (ev, tid) in enumerate(order) if ev == "end"}

        # t2, t3, t4 should all start before the first of them ends
        parallel_starts = [starts["t2"], starts["t3"], starts["t4"]]
        parallel_ends = [ends["t2"], ends["t3"], ends["t4"]]
        assert max(parallel_starts) < min(parallel_ends), \
            "backend/ci/deploy should run in parallel"

    def test_failure_propagation(self):
        tasks = [
            {"id": "t1", "agent": "builder", "specialization": "setup"},
            {"id": "t2", "agent": "builder", "specialization": "backend"},
            {"id": "t3", "agent": "builder", "specialization": "frontend"},  # depends on t2
        ]
        graph = build_dependency_graph(tasks)

        def run(tid):
            if tid == "t2":
                raise RuntimeError("backend crashed")

        failed = ParallelScheduler(max_workers=2).execute(graph, run)
        assert "t2" in failed
        assert "t3" in failed  # skipped because t2 failed

    def test_failure_doesnt_skip_independent(self):
        tasks = [
            {"id": "t1", "agent": "builder", "specialization": "setup"},
            {"id": "t2", "agent": "builder", "specialization": "backend"},  # will fail
            {"id": "t3", "agent": "builder", "specialization": "ci"},        # independent, should still run
        ]
        graph = build_dependency_graph(tasks)
        completed = []

        def run(tid):
            if tid == "t2":
                raise RuntimeError("crash")
            completed.append(tid)

        failed = ParallelScheduler(max_workers=4).execute(graph, run)
        assert "t2" in failed
        assert "t1" in completed
        assert "t3" in completed  # CI is independent of backend

    def test_empty_graph(self):
        failed = ParallelScheduler().execute([], lambda tid: None)
        assert failed == []

    def test_single_task(self):
        graph = [TaskNode(task_id="t1", agent="setup")]
        result = []

        def run(tid):
            result.append(tid)

        ParallelScheduler().execute(graph, run)
        assert result == ["t1"]
