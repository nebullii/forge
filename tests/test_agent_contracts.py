"""Tests for structured specialist agent outputs."""

import pytest

from src.agents.contracts import parse_agent_output_json, validate_agent_output


def test_validate_backend_agent_output_requires_contracts():
    payload = {
        "status": "success",
        "files": [{"path": "backend/app/main.py", "content": "print('ok')"}],
        "contracts": {"api": [{"method": "GET", "path": "/api/clients"}]},
    }

    output = validate_agent_output(payload, role="backend")

    assert output.status == "success"
    assert output.files[0].path == "backend/app/main.py"


def test_validate_backend_agent_output_rejects_missing_contracts():
    with pytest.raises(ValueError, match="backend agent output must include"):
        validate_agent_output(
            {
                "status": "success",
                "files": [{"path": "backend/app/main.py", "content": "print('ok')"}],
            },
            role="backend",
        )


def test_validate_agent_output_rejects_bad_file_shape():
    with pytest.raises(ValueError, match="requires string content"):
        validate_agent_output(
            {
                "status": "success",
                "files": [{"path": "frontend/src/App.tsx", "content": None}],
            },
            role="frontend",
        )


def test_parse_agent_output_json_extracts_embedded_object():
    parsed = parse_agent_output_json('Here:\n{"status":"success","files":[]}\n')

    assert parsed["status"] == "success"


def test_parse_agent_output_json_rejects_prose():
    with pytest.raises(ValueError, match="no JSON object"):
        parse_agent_output_json("use markdown fences")
