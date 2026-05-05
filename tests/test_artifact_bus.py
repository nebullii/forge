"""Tests for the ArtifactBus — thread-safe artifact store."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.collaboration.artifact_bus import ArtifactBus
from src.collaboration.models import (
    TaskPlanArtifact,
    CodeArtifact,
    BuildOutputArtifact,
    DecisionArtifact,
    ReviewArtifact,
    ReviewFindingArtifact,
    BuildLogArtifact,
    ReworkRequestArtifact,
    VerificationArtifact,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bus():
    return ArtifactBus()


@pytest.fixture
def populated_bus(bus):
    bus.publish(TaskPlanArtifact(
        task_id="t1",
        name="Build backend",
        description="Create API",
        specialization="backend",
        planned_files=("app.py",),
    ))
    bus.publish(CodeArtifact(path="app.py", content="x=1", producer_agent="backend", task_id="t1"))
    bus.publish(CodeArtifact(path="ui.jsx", content="<App/>", producer_agent="frontend", task_id="t2"))
    bus.publish(DecisionArtifact(key="stack", value={"lang": "python"}, producer_agent="planner"))
    bus.publish(BuildLogArtifact(message="all good", level="info", producer_agent="ci"))
    bus.publish(BuildLogArtifact(message="oops", level="error", producer_agent="ci"))
    return bus


# ---------------------------------------------------------------------------
# Publish & query
# ---------------------------------------------------------------------------

class TestPublish:
    def test_publish_single(self, bus):
        art = CodeArtifact(path="a.py", content="1", producer_agent="x")
        bus.publish(art)
        assert len(bus) == 1

    def test_publish_many(self, bus):
        arts = [
            CodeArtifact(path=f"f{i}.py", content=str(i), producer_agent="x")
            for i in range(5)
        ]
        bus.publish_many(arts)
        assert len(bus) == 5
        assert bus.code_count() == 5

    def test_publish_replaces_latest_by_version(self, bus):
        bus.publish(CodeArtifact(path="a.py", content="v1", producer_agent="b", version=1))
        bus.publish(CodeArtifact(path="a.py", content="v2", producer_agent="s", version=2))
        assert bus.latest("a.py").content == "v2"
        assert bus.latest("a.py").producer_agent == "s"
        assert bus.code_count() == 1  # still one path

    def test_lower_version_does_not_replace(self, bus):
        bus.publish(CodeArtifact(path="a.py", content="v2", producer_agent="s", version=2))
        bus.publish(CodeArtifact(path="a.py", content="v1", producer_agent="b", version=1))
        assert bus.latest("a.py").content == "v2"


class TestQuery:
    def test_latest_returns_none_for_missing(self, bus):
        assert bus.latest("nope.py") is None

    def test_by_task(self, populated_bus):
        arts = populated_bus.by_task("t1")
        assert len(arts) == 2
        assert any(isinstance(art, TaskPlanArtifact) for art in arts)
        assert any(isinstance(art, CodeArtifact) and art.path == "app.py" for art in arts)

    def test_by_agent(self, populated_bus):
        arts = populated_bus.by_agent("ci")
        assert len(arts) == 2  # info + error logs

    def test_by_type(self, populated_bus):
        codes = populated_bus.by_type(CodeArtifact)
        assert len(codes) == 2
        decisions = populated_bus.by_type(DecisionArtifact)
        assert len(decisions) == 1

    def test_snapshot_unfiltered(self, populated_bus):
        snap = populated_bus.snapshot()
        assert len(snap) == 6

    def test_snapshot_filtered(self, populated_bus):
        errors = populated_bus.snapshot(
            filter_fn=lambda a: isinstance(a, BuildLogArtifact) and a.level == "error"
        )
        assert len(errors) == 1
        assert errors[0].message == "oops"


class TestExport:
    def test_export_files_dict(self, populated_bus):
        d = populated_bus.export_files_dict()
        assert d == {"app.py": "x=1", "ui.jsx": "<App/>"}

    def test_export_files_list(self, populated_bus):
        lst = populated_bus.export_files_list()
        paths = {p for p, _ in lst}
        assert paths == {"app.py", "ui.jsx"}

    def test_all_code(self, populated_bus):
        codes = populated_bus.all_code()
        assert len(codes) == 2


class TestConvenience:
    def test_get_decisions(self, populated_bus):
        d = populated_bus.get_decisions()
        assert d == {"stack": {"lang": "python"}}

    def test_get_errors(self, populated_bus):
        assert populated_bus.get_errors() == ["oops"]

    def test_get_warnings_empty(self, populated_bus):
        assert populated_bus.get_warnings() == []

    def test_get_review_none(self, bus):
        assert bus.get_review() is None

    def test_get_review(self, bus):
        bus.publish(ReviewArtifact(
            target_path="", producer_agent="reviewer", passed=False,
            issues=({"file": "a.py", "msg": "bad"},),
        ))
        rev = bus.get_review()
        assert rev["passed"] is False
        assert len(rev["issues"]) == 1

    def test_get_task_plans(self, populated_bus):
        plans = populated_bus.get_task_plans()
        assert len(plans) == 1
        assert plans[0].task_id == "t1"

    def test_get_build_outputs(self, bus):
        bus.publish(BuildOutputArtifact(
            task_id="t1",
            specialization="backend",
            planned_files=("app.py",),
            files_written=("app.py",),
            contract_types=("api",),
        ))
        outputs = bus.get_build_outputs()
        assert len(outputs) == 1
        assert outputs[0].contract_types == ("api",)

    def test_get_review_findings(self, bus):
        bus.publish(ReviewFindingArtifact(
            target_path="app.py",
            message="bad",
            severity="error",
            producer_agent="reviewer",
        ))
        findings = bus.get_review_findings()
        assert len(findings) == 1
        assert findings[0].target_path == "app.py"

    def test_get_verification_results(self, bus):
        bus.publish(VerificationArtifact(
            verifier="python_syntax",
            category="syntax",
            passed=True,
            summary="ok",
        ))
        results = bus.get_verification_results()
        assert len(results) == 1
        assert results[0].verifier == "python_syntax"

    def test_summary(self, populated_bus):
        s = populated_bus.summary()
        assert s["CodeArtifact"] == 2
        assert s["BuildLogArtifact"] == 2


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_publishes(self, bus):
        """400 concurrent writes should not corrupt the bus."""
        def write(agent):
            for i in range(100):
                bus.publish(CodeArtifact(
                    path=f"{agent}/f{i}.py", content="x",
                    producer_agent=agent, task_id=f"{agent}_{i}",
                ))

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(write, ["a", "b", "c", "d"]))

        assert bus.code_count() == 400
        assert len(bus) == 400

    def test_concurrent_reads_during_writes(self, bus):
        """Reads shouldn't block or crash during concurrent writes."""
        stop = threading.Event()
        errors = []

        def writer():
            for i in range(200):
                bus.publish(CodeArtifact(
                    path=f"w{i}.py", content="x", producer_agent="w",
                ))
            stop.set()

        def reader():
            while not stop.is_set():
                try:
                    bus.export_files_dict()
                    bus.get_errors()
                    bus.all_code()
                except Exception as e:
                    errors.append(str(e))

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert errors == [], f"Reader errors: {errors}"
