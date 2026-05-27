"""Tests for persistent model quality tracking."""

import json

from src.providers.base import ProviderConfig
from src.quality import QualityTracker


def test_quality_tracker_persists_outcomes_and_evals(tmp_path):
    tracker = QualityTracker(tmp_path)
    cfg = ProviderConfig(name="ollama", model="qwen3:latest", profile="reviewer")
    tracker.record_outcome("reviewer", cfg, True)
    tracker.record_outcome("reviewer", cfg, False)
    tracker.record_eval("reviewer", cfg, passed=True, score=80, summary="parsed review")

    saved = json.loads((tmp_path / "model_quality.json").read_text())
    record = next(iter(saved["records"].values()))
    assert record["attempts"] == 2
    assert record["successes"] == 1
    assert record["failures"] == 1
    assert record["eval_count"] == 1
    assert record["eval_score_total"] == 80


def test_quality_tracker_sorts_best_role_first(tmp_path):
    tracker = QualityTracker(tmp_path)
    weak = ProviderConfig(name="ollama", model="small", profile="a")
    strong = ProviderConfig(name="ollama", model="large", profile="b")
    tracker.record_outcome("planner", weak, False)
    tracker.record_eval("planner", weak, passed=False, score=10, summary="bad")
    tracker.record_outcome("planner", strong, True)
    tracker.record_eval("planner", strong, passed=True, score=90, summary="good")

    best = tracker.best_for_role("planner")
    assert best[0]["model"] == "large"
