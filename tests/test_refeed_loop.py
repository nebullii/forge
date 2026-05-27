"""Tests for the validate-and-refeed loop helpers."""

from __future__ import annotations

from pathlib import Path

from src.orchestrator import BuildOrchestrator
from src.state import TaskState
from src.verification.html_behavior import HTMLBehaviorVerifier
from src.verification.javascript import JavaScriptVerifier


def test_build_refeed_prompt_lists_files_and_issues(tmp_path):
    # Construct just enough of the orchestrator surface to exercise the helper
    orch = BuildOrchestrator.__new__(BuildOrchestrator)

    files = [("index.html", "<html><script>missing()</script></html>")]

    class FakeResult:
        verifier = "javascript_static"
        logs = ("index.html:1 [undefined_call] Function 'missing' is called",)

    prompt = orch._build_refeed_prompt(
        task=TaskState(id="t1", name="My task"),
        files=files,
        failures=[FakeResult()],
    )

    assert "My task" in prompt
    assert "```file:index.html" in prompt
    assert "missing()" in prompt
    assert "javascript_static" in prompt
    assert "Fix ONLY" in prompt
    assert "do not rename" in prompt.lower()


def test_inline_verifiers_class_constants_present():
    # Sanity: the constants are set and reference the right verifier classes
    assert JavaScriptVerifier in BuildOrchestrator._INLINE_VERIFIERS
    assert HTMLBehaviorVerifier in BuildOrchestrator._INLINE_VERIFIERS
    assert BuildOrchestrator.MAX_REFEED_ATTEMPTS >= 1


def test_refeed_stops_when_no_failures_present(tmp_path):
    # Make a minimal orchestrator wired only with the bits the loop touches
    from src.collaboration import ArtifactBus, ArtifactStore, ContractRegistry
    from src.audit import BuildAuditLogger
    from src.state import BuildState

    orch = BuildOrchestrator.__new__(BuildOrchestrator)
    orch.bus = ArtifactBus()
    orch.artifact_store = ArtifactStore(tmp_path)
    orch.registry = ContractRegistry()
    orch.project_root = tmp_path
    orch.audit = BuildAuditLogger(tmp_path)
    orch.state = BuildState(build_id="test")
    orch.ui = None
    import threading
    orch._state_lock = threading.Lock()

    # A clean HTML file — no undefined symbols, no external URLs
    files = [(
        "index.html",
        '<html><body><button id="b">Hi</button>'
        '<script>document.getElementById("b").addEventListener("click", () => {});</script>'
        '</body></html>',
    )]

    result_files, history = orch._refeed_until_clean(
        task=TaskState(id="t", name="t", planned_files=["index.html"]),
        files=files,
        spec="", rules="",
    )

    assert result_files == files
    assert history == []   # never had to refeed
