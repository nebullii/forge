"""Tests for deterministic verification."""

from src.collaboration import ContractRegistry, ApiEndpointContract, UIDataDependency
from src.verification import VerificationContext, VerificationRegistry


def test_verification_registry_runs_python_and_contract_checks(tmp_path):
    registry = ContractRegistry()
    registry.register(ApiEndpointContract(method="GET", path="/users", producer_agent="backend"))
    registry.register(UIDataDependency(view_name="Users", endpoint="GET /users", producer_agent="frontend"))

    context = VerificationContext(
        project_root=tmp_path,
        files={"app/main.py": "def ok():\n    return 1\n"},
        decisions={},
        contracts=registry,
    )
    report = VerificationRegistry().run(context)

    assert report.passed is True
    names = {result.verifier for result in report.results}
    assert "python_syntax" in names
    assert "contract_consistency" in names


def test_verification_report_fails_on_python_syntax_error(tmp_path):
    registry = ContractRegistry()
    context = VerificationContext(
        project_root=tmp_path,
        files={"app/main.py": "def broken(:\n    pass\n"},
        decisions={},
        contracts=registry,
    )
    report = VerificationRegistry().run(context)

    assert report.passed is False
    syntax = next(result for result in report.results if result.verifier == "python_syntax")
    assert syntax.passed is False
    assert "invalid syntax" in syntax.details
