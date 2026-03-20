"""Tests for BuildState / TaskState loading, defaults, and schema compatibility."""

import pytest

from src.state import (
    TaskState,
    BuildState,
    _load_task,
    _load_build,
    load_build_state,
    save_build_state,
)


class TestTaskStateDefaults:
    def test_required_fields_only(self):
        t = TaskState(id="t1", name="Do stuff")
        assert t.status        == "pending"
        assert t.agent         == ""
        assert t.prompt        == ""
        assert t.contracts     == ""
        assert t.files_written == []
        assert t.error         == ""
        assert t.description   == ""

    def test_explicit_values_stored(self):
        t = TaskState(id="t1", name="X", status="completed", agent="backend")
        assert t.status == "completed"
        assert t.agent  == "backend"


class TestBuildStateDefaults:
    def test_schema_version_is_two(self):
        assert BuildState().schema_version == 2

    def test_status_defaults_to_not_started(self):
        assert BuildState().status == "not_started"

    def test_tasks_default_to_empty_list(self):
        assert BuildState().tasks == []


class TestLoadTask:
    def test_tolerates_extra_unknown_fields(self):
        raw = {
            "id":                 "t1",
            "name":               "Foo",
            "description":        "Bar",
            "status":             "pending",
            "future_field_v3":    "should be ignored",
        }
        t = _load_task(raw)
        assert t.id == "t1"
        assert not hasattr(t, "future_field_v3")

    def test_tolerates_missing_prompt_and_contracts(self):
        """Simulates a state file written before prompt/contracts were added."""
        raw = {"id": "t1", "name": "Legacy task", "description": "Old school"}
        t = _load_task(raw)
        assert t.prompt    == ""
        assert t.contracts == ""

    def test_tolerates_missing_agent_field(self):
        """Simulates state from before per-task agent routing existed."""
        raw = {"id": "t1", "name": "X", "description": "Y"}
        t = _load_task(raw)
        assert t.agent == ""


class TestLoadBuild:
    def test_tolerates_extra_unknown_fields(self):
        raw = {
            "build_id":          "abc",
            "status":            "completed",
            "future_build_flag": True,
        }
        b = _load_build(raw)
        assert b.build_id == "abc"
        assert not hasattr(b, "future_build_flag")


class TestRoundTrip:
    def test_save_and_reload(self, tmp_path):
        forge_path = tmp_path / ".forge"
        forge_path.mkdir()

        state = BuildState(
            build_id="abc123",
            status="completed",
            tasks=[
                TaskState(id="t1", name="Setup",  status="completed"),
                TaskState(id="t2", name="Models", status="completed"),
            ],
        )
        save_build_state(forge_path, state)
        loaded = load_build_state(forge_path)

        assert loaded.build_id      == "abc123"
        assert loaded.status        == "completed"
        assert loaded.schema_version == 2
        assert len(loaded.tasks)    == 2
        assert loaded.tasks[1].name == "Models"

    def test_missing_state_file_returns_fresh(self, tmp_path):
        forge_path = tmp_path / ".forge"
        forge_path.mkdir()
        state = load_build_state(forge_path)
        assert state.status == "not_started"
        assert state.tasks  == []
