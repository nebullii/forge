"""Tests for build state — atomic writes, corrupted file recovery."""

import os
import yaml
import pytest
from pathlib import Path

from src.state import (
    BuildState, TaskState, load_build_state, save_build_state, compute_spec_hash,
)


class TestAtomicSave:
    def test_save_creates_file(self, tmp_path):
        state = BuildState(build_id="abc", status="building")
        save_build_state(tmp_path, state)
        assert (tmp_path / "build-state.yaml").exists()

    def test_save_is_valid_yaml(self, tmp_path):
        state = BuildState(build_id="abc", status="building")
        state.tasks = [TaskState(id="t1", name="Test")]
        save_build_state(tmp_path, state)
        with open(tmp_path / "build-state.yaml") as f:
            data = yaml.safe_load(f)
        assert data["build_id"] == "abc"
        assert len(data["tasks"]) == 1

    def test_save_no_temp_files_left(self, tmp_path):
        state = BuildState(build_id="abc")
        save_build_state(tmp_path, state)
        # No .tmp files should remain
        temps = list(tmp_path.glob(".state-*.tmp"))
        assert temps == []

    def test_save_overwrite_preserves_atomicity(self, tmp_path):
        # Write initial state
        state1 = BuildState(build_id="v1", status="building")
        save_build_state(tmp_path, state1)
        # Overwrite
        state2 = BuildState(build_id="v2", status="completed")
        save_build_state(tmp_path, state2)
        loaded = load_build_state(tmp_path)
        assert loaded.build_id == "v2"


class TestLoadRecovery:
    def test_load_missing_file(self, tmp_path):
        state = load_build_state(tmp_path)
        assert state.status == "not_started"

    def test_load_empty_file(self, tmp_path):
        (tmp_path / "build-state.yaml").write_text("")
        state = load_build_state(tmp_path)
        assert state.status == "not_started"

    def test_load_corrupted_yaml(self, tmp_path):
        (tmp_path / "build-state.yaml").write_text("{{{{invalid yaml::::")
        state = load_build_state(tmp_path)
        assert state.status == "not_started"  # graceful fallback

    def test_load_non_dict_yaml(self, tmp_path):
        (tmp_path / "build-state.yaml").write_text("- item1\n- item2\n")
        state = load_build_state(tmp_path)
        assert state.status == "not_started"

    def test_load_valid_state(self, tmp_path):
        data = {
            "build_id": "abc",
            "status": "completed",
            "tasks": [{"id": "t1", "name": "Test", "status": "completed"}],
        }
        with open(tmp_path / "build-state.yaml", "w") as f:
            yaml.dump(data, f)
        state = load_build_state(tmp_path)
        assert state.build_id == "abc"
        assert state.status == "completed"
        assert len(state.tasks) == 1

    def test_load_ignores_unknown_fields(self, tmp_path):
        data = {"build_id": "abc", "future_field": "value", "tasks": []}
        with open(tmp_path / "build-state.yaml", "w") as f:
            yaml.dump(data, f)
        state = load_build_state(tmp_path)
        assert state.build_id == "abc"

    def test_load_skips_malformed_tasks(self, tmp_path):
        data = {
            "build_id": "abc",
            "tasks": [
                {"id": "t1", "name": "Good"},
                "not a dict",
                {"id": "t2", "name": "Also good"},
            ],
        }
        with open(tmp_path / "build-state.yaml", "w") as f:
            yaml.dump(data, f)
        state = load_build_state(tmp_path)
        assert len(state.tasks) == 2


class TestRoundtrip:
    def test_full_roundtrip(self, tmp_path):
        state = BuildState(
            build_id="test",
            status="building",
            tasks=[
                TaskState(id="t1", name="Setup", status="completed", agent="coder"),
                TaskState(id="t2", name="Backend", status="pending", agent="backend"),
            ],
            files_written=["a.py", "b.py"],
            errors=["something failed"],
        )
        save_build_state(tmp_path, state)
        loaded = load_build_state(tmp_path)
        assert loaded.build_id == "test"
        assert len(loaded.tasks) == 2
        assert loaded.tasks[0].agent == "coder"
        assert loaded.files_written == ["a.py", "b.py"]
        assert loaded.errors == ["something failed"]
