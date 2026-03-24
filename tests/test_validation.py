"""Tests for agent output validation."""

import pytest
from src.collaboration.validation import validate_agent_output, ValidationResult


class TestValidateAgentOutput:
    def test_empty_response_fails(self):
        r = validate_agent_output("backend", "", [])
        assert not r.valid
        assert "empty response" in r.reason

    def test_whitespace_only_response_fails(self):
        r = validate_agent_output("backend", "   \n\n  ", [])
        assert not r.valid

    def test_backend_needs_files(self):
        r = validate_agent_output("backend", "some text", [])
        assert not r.valid
        assert "0 file(s)" in r.reason

    def test_backend_with_files_passes(self):
        r = validate_agent_output("backend", "code", [("app.py", "print(1)")])
        assert r.valid
        assert r.files_found == 1

    def test_frontend_needs_files(self):
        r = validate_agent_output("frontend", "code", [])
        assert not r.valid

    def test_reviewer_no_files_ok(self):
        r = validate_agent_output("reviewer", "passed: true", [])
        assert r.valid

    def test_security_no_files_ok(self):
        r = validate_agent_output("security", "audit report", [])
        assert r.valid

    def test_planner_no_files_ok(self):
        r = validate_agent_output("planner", "plan yaml", [])
        assert r.valid

    def test_empty_file_content_fails(self):
        r = validate_agent_output("backend", "code", [("app.py", "")])
        assert not r.valid
        assert "empty file" in r.reason

    def test_whitespace_file_content_fails(self):
        r = validate_agent_output("backend", "code", [("app.py", "  \n  ")])
        assert not r.valid

    def test_multiple_files_pass(self):
        files = [("a.py", "x=1"), ("b.py", "y=2"), ("c.py", "z=3")]
        r = validate_agent_output("backend", "code", files)
        assert r.valid
        assert r.files_found == 3

    def test_unknown_agent_defaults_to_no_min(self):
        r = validate_agent_output("custom_agent", "response", [])
        assert r.valid
