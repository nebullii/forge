"""Build audit logging and summary report generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class BuildAuditLogger:
    """Append-only JSONL audit log plus per-build summary report."""

    def __init__(self, forge_path: Path) -> None:
        self.forge_path = forge_path
        self.audit_path = forge_path / "build_audit.jsonl"
        self.report_path = forge_path / "build_report.json"

    def log(self, event: str, **data: Any) -> None:
        entry = {"event": event, **data}
        with open(self.audit_path, "a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    def write_report(self, report: dict[str, Any]) -> None:
        self.report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
