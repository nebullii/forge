"""Tests for the new local-first executable verifiers.

Both verifiers are pointed at synthetic 'pomodoro-like' buggy code that
mirrors what local 7B-class models produce in practice. The assertions
encode the *kinds* of failures we expect to catch, not the literal output.
"""

from __future__ import annotations

from pathlib import Path

from src.verification.html_behavior import HTMLBehaviorVerifier
from src.verification.javascript import JavaScriptVerifier
from src.verification.models import VerificationContext


# ---------- JS verifier --------------------------------------------------

def _js_context(files):
    return VerificationContext(project_root=Path("."), files=files)


def test_js_verifier_catches_undefined_function_call(tmp_path):
    src = """
    function start() {
      doTheThing();   // <-- never defined
    }
    """
    result = JavaScriptVerifier().run(_js_context({"app.js": src}))
    assert not result.passed
    assert any("doTheThing" in log for log in result.logs)
    assert any("undefined_call" in log for log in result.logs)


def test_js_verifier_catches_pseudo_element_selector():
    src = """
    const ring = document.querySelector('.progress::before');
    """
    result = JavaScriptVerifier().run(_js_context({"app.js": src}))
    assert not result.passed
    assert any("pseudo-element" in log for log in result.logs)


def test_js_verifier_ignores_methods_on_objects():
    # foo.bar() shouldn't trip the "undefined function" check
    src = """
    const obj = { bar() { return 1; } };
    obj.bar();
    document.getElementById('x').focus();
    """
    result = JavaScriptVerifier().run(_js_context({"app.js": src}))
    assert result.passed


def test_js_verifier_scans_inline_html_scripts():
    html = """
    <html><body>
      <script>
        function ok() { return 1; }
        ok();
        missing();    // <-- undefined
      </script>
    </body></html>
    """
    result = JavaScriptVerifier().run(_js_context({"index.html": html}))
    assert not result.passed
    assert any("missing" in log for log in result.logs)


def test_js_verifier_skips_external_scripts():
    html = '<html><body><script src="https://cdn.example/lib.js"></script></body></html>'
    result = JavaScriptVerifier().run(_js_context({"index.html": html}))
    # External scripts can't be inspected — no errors raised for them
    assert result.passed


def test_js_verifier_handles_pomodoro_exact_pattern():
    # Reproduces the qwen3-produced pomodoro app pattern that motivated this work.
    src = """
    let timeLeft = 25 * 60;
    document.getElementById('resetBtn').addEventListener('click', () => {
      resetTimer();   // <-- declared nowhere
    });
    """
    result = JavaScriptVerifier().run(_js_context({"app.js": src}))
    assert not result.passed
    assert any("resetTimer" in log for log in result.logs)


# ---------- HTML behaviour verifier --------------------------------------

def _html_context(files, *, framework="static-html"):
    return VerificationContext(
        project_root=Path("."),
        files=files,
        decisions={"stack": {"framework": framework, "backend": "none"}},
    )


def test_html_verifier_flags_external_audio_on_static_site():
    html = """
    <html><body>
      <audio id="chime" src="https://example.com/sound.mp3"></audio>
    </body></html>
    """
    result = HTMLBehaviorVerifier().run(_html_context({"index.html": html}))
    assert not result.passed
    assert any("external URL" in log for log in result.logs)


def test_html_verifier_allows_external_resources_on_full_stack():
    # FastAPI+React project, external URLs are fine
    html = '<html><body><img src="https://example.com/logo.png"></body></html>'
    ctx = VerificationContext(
        project_root=Path("."),
        files={"frontend/index.html": html, "backend/main.py": ""},
        decisions={"stack": {"framework": "fastapi", "frontend": "react"}},
    )
    result = HTMLBehaviorVerifier().run(ctx)
    assert result.passed


def test_html_verifier_flags_empty_audio_element():
    html = "<html><body><audio id=\"chime\"></audio></body></html>"
    result = HTMLBehaviorVerifier().run(_html_context({"index.html": html}))
    assert not result.passed
    assert any("silently inert" in log for log in result.logs)


def test_html_verifier_passes_audio_with_source_child():
    html = """
    <html><body>
      <audio id="chime">
        <source src="data:audio/wav;base64,..." type="audio/wav">
      </audio>
    </body></html>
    """
    result = HTMLBehaviorVerifier().run(_html_context({"index.html": html}))
    assert result.passed


def test_html_verifier_flags_dead_button():
    html = """
    <html><body>
      <button id="ghostBtn">Do something</button>
      <script>
        // does not reference #ghostBtn
        console.log('hello');
      </script>
    </body></html>
    """
    result = HTMLBehaviorVerifier().run(_html_context({"index.html": html}))
    assert not result.passed
    assert any("dead control" in log for log in result.logs)


def test_html_verifier_accepts_button_bound_by_id():
    html = """
    <html><body>
      <button id="startBtn">Start</button>
      <script>
        document.getElementById('startBtn').addEventListener('click', () => {});
      </script>
    </body></html>
    """
    result = HTMLBehaviorVerifier().run(_html_context({"index.html": html}))
    assert result.passed


def test_html_verifier_accepts_button_with_onclick_attr():
    html = '<html><body><button onclick="go()">Go</button></body></html>'
    result = HTMLBehaviorVerifier().run(_html_context({"index.html": html}))
    assert result.passed


def test_html_verifier_doesnt_apply_when_no_html_files():
    ctx = VerificationContext(
        project_root=Path("."),
        files={"main.py": "print('hi')"},
    )
    assert not HTMLBehaviorVerifier().applies_to(ctx)


# ---------- Registry integration -----------------------------------------

def test_registry_includes_new_verifiers():
    from src.verification.registry import VerificationRegistry

    reg = VerificationRegistry()
    names = {v.name for v in reg._verifiers}
    assert "javascript_static" in names
    assert "html_behavior" in names


def test_registry_runs_new_verifiers_on_static_site():
    from src.verification.registry import VerificationRegistry

    buggy_html = """
    <html><body>
      <audio id="chime" src="https://example.com/sound.mp3"></audio>
      <button id="reset">Reset</button>
      <script>
        document.getElementById('reset').addEventListener('click', () => {
          resetTimer();
        });
      </script>
    </body></html>
    """
    ctx = VerificationContext(
        project_root=Path("."),
        files={"index.html": buggy_html},
        decisions={"stack": {"framework": "static-html", "backend": "none"}},
    )
    report = VerificationRegistry().run(ctx)
    assert not report.passed
    # At least one failure from each new verifier
    failed_verifiers = {r.verifier for r in report.results if not r.passed}
    assert "javascript_static" in failed_verifiers
    assert "html_behavior" in failed_verifiers
