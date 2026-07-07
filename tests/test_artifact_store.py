"""Tests for durable artifact persistence."""

import json
import logging
import threading

from src.collaboration import (
    ArtifactStore,
    TaskPlanArtifact,
    CodeArtifact,
    ReviewArtifact,
    VerificationArtifact,
)


def test_artifact_store_round_trip(tmp_path):
    store = ArtifactStore(tmp_path)
    store.append(TaskPlanArtifact(
        task_id="task_01",
        name="Build API",
        description="Create routes",
        specialization="backend",
        planned_files=("backend/main.py",),
    ))
    store.append(CodeArtifact(
        path="backend/main.py",
        content="print('ok')",
        producer_agent="backend",
        task_id="task_01",
        tags=("backend",),
    ))
    store.append(VerificationArtifact(
        verifier="python_syntax",
        category="syntax",
        passed=True,
        files=("backend/main.py",),
    ))

    loaded = store.load_all()
    assert len(loaded) == 3
    assert loaded[0].planned_files == ("backend/main.py",)
    assert loaded[1].tags == ("backend",)
    assert loaded[2].files == ("backend/main.py",)


def test_artifact_store_writes_snapshot(tmp_path):
    store = ArtifactStore(tmp_path)
    artifacts = [
        ReviewArtifact(
            target_path="",
            producer_agent="reviewer",
            passed=False,
            issues=({"file": "app.py", "message": "bad"},),
        )
    ]
    store.write_snapshot(artifacts)

    payload = json.loads((tmp_path / "artifacts.json").read_text())
    assert len(payload) == 1
    assert payload[0]["type"] == "ReviewArtifact"
    assert payload[0]["payload"]["issues"][0]["file"] == "app.py"


def test_artifact_store_reset(tmp_path):
    store = ArtifactStore(tmp_path)
    store.append(CodeArtifact(path="a.py", content="x=1", producer_agent="builder"))
    store.write_snapshot([])
    store.reset()

    assert not (tmp_path / "artifacts.jsonl").exists()
    assert not (tmp_path / "artifacts.json").exists()


def test_artifact_store_concurrent_appends_are_not_corrupted(tmp_path, caplog):
    store = ArtifactStore(tmp_path)
    thread_count, appends_per_thread = 8, 50

    def worker(worker_id):
        for i in range(appends_per_thread):
            store.append(CodeArtifact(
                path=f"src/worker_{worker_id}/file_{i}.py",
                content="x = 1\n" * 100,
                producer_agent="backend",
            ))

    threads = [
        threading.Thread(target=worker, args=(worker_id,))
        for worker_id in range(thread_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with caplog.at_level(logging.WARNING, logger="src.collaboration.store"):
        loaded = store.load_all()

    assert len(loaded) == thread_count * appends_per_thread
    assert not caplog.records  # no interleaved/corrupted log entries skipped
