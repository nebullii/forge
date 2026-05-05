"""Tests for build audit logging."""

import json

from src.audit import BuildAuditLogger


def test_audit_logger_writes_jsonl_and_report(tmp_path):
    audit = BuildAuditLogger(tmp_path)
    audit.log("build_started", build_id="abc123", provider="mock")
    audit.write_report({"build_id": "abc123", "status": "completed"})

    lines = (tmp_path / "build_audit.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "build_started"

    report = json.loads((tmp_path / "build_report.json").read_text())
    assert report["status"] == "completed"
