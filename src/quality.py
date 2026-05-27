"""Persistent model quality tracking across Forge builds."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .providers.base import ProviderConfig


QUALITY_FILE = "model_quality.json"


class QualityTracker:
    """Persist lightweight model outcome/eval stats under `.forge/`."""

    def __init__(self, forge_path: Path) -> None:
        self.forge_path = forge_path
        self.path = forge_path / QUALITY_FILE
        self._records = self._load()

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {key: dict(value) for key, value in self._records.items()}

    def record_outcome(self, role: str, config: ProviderConfig, success: bool) -> None:
        record = self._ensure(role, config)
        record["attempts"] += 1
        if success:
            record["successes"] += 1
        else:
            record["failures"] += 1
        self._save()

    def record_eval(
        self,
        role: str,
        config: ProviderConfig,
        *,
        passed: bool,
        score: int,
        summary: str = "",
    ) -> None:
        record = self._ensure(role, config)
        record["eval_count"] += 1
        record["eval_score_total"] += int(score)
        if passed:
            record["eval_passes"] += 1
        if summary:
            record["last_summary"] = summary
        self._save()

    def best_for_role(self, role: str) -> list[dict[str, Any]]:
        items = [item for item in self._records.values() if item.get("role") == role]
        items.sort(key=self._sort_key, reverse=True)
        return items

    def model_summary(self, provider: str, model: str) -> list[dict[str, Any]]:
        items = [
            item for item in self._records.values()
            if item.get("provider") == provider and item.get("model") == model
        ]
        items.sort(key=self._sort_key, reverse=True)
        return items

    @classmethod
    def load_snapshot(cls, forge_path: Path) -> dict[str, dict[str, Any]]:
        return cls(forge_path).snapshot()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
        records = data.get("records", {})
        if not isinstance(records, dict):
            return {}
        return {
            key: value for key, value in records.items()
            if isinstance(value, dict)
        }

    def _save(self) -> None:
        payload = {"records": self._records}
        self.forge_path.mkdir(parents=True, exist_ok=True)
        try:
            fd, tmp_path = tempfile.mkstemp(dir=self.forge_path, prefix=".quality-", suffix=".tmp")
            with os.fdopen(fd, "w") as handle:
                handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            os.replace(tmp_path, self.path)
        except OSError:
            self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def _ensure(self, role: str, config: ProviderConfig) -> dict[str, Any]:
        key = self._key(role, config)
        if key not in self._records:
            self._records[key] = {
                "role": role,
                "provider": config.name,
                "profile": config.profile,
                "model": config.model,
                "attempts": 0,
                "successes": 0,
                "failures": 0,
                "eval_count": 0,
                "eval_passes": 0,
                "eval_score_total": 0,
                "last_summary": "",
            }
        return self._records[key]

    @staticmethod
    def _key(role: str, config: ProviderConfig) -> str:
        return "|".join([role, config.name, config.profile or "", config.model])

    @staticmethod
    def _sort_key(item: dict[str, Any]) -> tuple[float, float, int]:
        attempts = max(1, int(item.get("attempts", 0)))
        eval_count = max(1, int(item.get("eval_count", 0)))
        success_rate = int(item.get("successes", 0)) / attempts
        eval_avg = int(item.get("eval_score_total", 0)) / eval_count
        return (success_rate, eval_avg, int(item.get("attempts", 0)))
