"""JavaScript static verifier — runs a Node helper to catch dead references.

Targets the class of bugs that local 7B-class models reliably produce:
  - calling functions that are never defined in the file
  - querySelector('.foo::before') — pseudo-elements aren't selectable
  - syntax errors that slip past simple regex extraction

Falls back to a pure-Python check when Node isn't available, so the verifier
never silently disappears in environments without a Node toolchain.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .base import BaseVerifier
from .models import VerificationContext, VerificationResult


_JS_CHECK_SCRIPT = Path(__file__).with_name("js_check.js")

# Match inline <script>...</script> blocks (case-insensitive). Skip script
# tags that are external src= references or non-JS types.
_INLINE_SCRIPT_RE = re.compile(
    r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)


class JavaScriptVerifier(BaseVerifier):
    name = "javascript_static"
    category = "javascript"

    def applies_to(self, context: VerificationContext) -> bool:
        return any(self._is_js_carrier(path) for path in context.files)

    def run(self, context: VerificationContext) -> VerificationResult:
        sources = self._gather_sources(context.files)
        if not sources:
            return _passed(self.name, self.category, "No JS sources to analyse")

        node_path = shutil.which("node")
        if node_path:
            errors_by_file = self._run_node_check(node_path, sources)
        else:
            errors_by_file = self._run_python_fallback(sources)

        all_failures: list[str] = []
        failed_paths: list[str] = []
        for path, errors in errors_by_file.items():
            for err in errors:
                line = err.get("line", 0)
                kind = err.get("kind", "error")
                msg = err.get("message", "")
                all_failures.append(f"{path}:{line} [{kind}] {msg}")
                if path not in failed_paths:
                    failed_paths.append(path)

        return VerificationResult(
            verifier=self.name,
            category=self.category,
            passed=not all_failures,
            severity="error",
            summary="JavaScript static analysis (syntax + undefined symbols)",
            details="\n".join(all_failures),
            logs=tuple(all_failures),
            files=tuple(failed_paths),
            retryable=True,
        )

    # ------------------------------------------------------------------
    def _is_js_carrier(self, path: str) -> bool:
        return path.endswith((".js", ".mjs", ".cjs", ".html", ".htm"))

    def _gather_sources(self, files: dict[str, str]) -> dict[str, str]:
        """Return {logical_path: source} pairs including inline HTML scripts."""
        out: dict[str, str] = {}
        for path, content in files.items():
            if self._should_skip_file(path, content):
                continue
            if path.endswith((".js", ".mjs", ".cjs")):
                out[path] = content
            elif path.endswith((".html", ".htm")):
                for idx, body in enumerate(self._extract_inline_scripts(content)):
                    out[f"{path}#script-{idx}"] = body
        return out

    def _should_skip_file(self, path: str, source: str) -> bool:
        """Skip module/transpiled files the verifier is not equipped to parse.

        This verifier targets plain browser JavaScript and inline scripts. It is
        not a JSX/ESM parser, so Vite/React bootstrap files would otherwise
        create false-positive syntax failures and trigger useless refeed loops.
        """
        lowered = path.lower()
        if lowered.endswith(".jsx"):
            return True
        if lowered.endswith(("vite.config.js", "tailwind.config.js", "postcss.config.js")):
            return True
        # Skip obvious ESM modules; this verifier is aimed at direct browser JS.
        if lowered.endswith((".js", ".mjs", ".cjs")) and re.search(
            r"^\s*(import|export)\b", source, re.MULTILINE
        ):
            return True
        return False

    def _extract_inline_scripts(self, html: str) -> list[str]:
        bodies: list[str] = []
        for match in _INLINE_SCRIPT_RE.finditer(html):
            attrs = match.group("attrs") or ""
            if "src=" in attrs.lower():
                continue
            # Skip non-JS script types (template, ld+json, etc.)
            type_match = re.search(r"""type\s*=\s*['"]([^'"]+)['"]""", attrs, re.IGNORECASE)
            if type_match:
                type_val = type_match.group(1).lower()
                if "javascript" not in type_val and "module" not in type_val:
                    continue
            bodies.append(match.group("body"))
        return bodies

    def _run_node_check(self, node_path: str, sources: dict[str, str]) -> dict[str, list[dict]]:
        payload = json.dumps({"files": sources})
        try:
            result = subprocess.run(
                [node_path, str(_JS_CHECK_SCRIPT)],
                input=payload,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, OSError):
            return self._run_python_fallback(sources)

        if result.returncode != 0:
            # Node helper crashed — fall back so the verifier still does something
            return self._run_python_fallback(sources)

        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            return self._run_python_fallback(sources)

        out: dict[str, list[dict]] = {}
        for entry in parsed.get("results", []):
            out[entry["path"]] = entry.get("errors", [])
        return out

    def _run_python_fallback(self, sources: dict[str, str]) -> dict[str, list[dict]]:
        """Pure-Python subset: undefined-call scan + pseudo-element selector.

        Reduced accuracy vs. the Node path (no syntax check, simpler regex),
        but still catches the bugs we observed in the smoke build.
        """
        out: dict[str, list[dict]] = {}
        for path, source in sources.items():
            errors: list[dict] = []
            declared = _python_declared(source)
            for match in _PY_CALL_RE.finditer(source):
                name = match.group(1)
                if name in _PY_BUILTINS or name in declared:
                    continue
                line = source[:match.start()].count("\n") + 1
                errors.append({
                    "kind": "undefined_call",
                    "line": line,
                    "message": f"Function '{name}' is called but never defined in this file",
                    "name": name,
                })
                # Only flag each name once per file to keep output readable
                declared.add(name)
            for match in _PY_SELECTOR_RE.finditer(source):
                selector = match.group(2)
                if "::" in selector and re.search(r"::[a-z-]", selector, re.IGNORECASE):
                    line = source[:match.start()].count("\n") + 1
                    errors.append({
                        "kind": "broken_selector",
                        "line": line,
                        "message": (
                            f"querySelector cannot match pseudo-element '{selector}' — "
                            "returns null at runtime"
                        ),
                    })
            out[path] = errors
        return out


_PY_CALL_RE = re.compile(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(")
_PY_SELECTOR_RE = re.compile(r"\.querySelector(?:All)?\s*\(\s*(['\"])(.*?)\1")

_PY_DECL_RE_LIST = (
    re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"\bclass\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"\bimport\s+([A-Za-z_$][\w$]*)"),
    # Method shorthand: matches `name(args) {` anchored on a delimiter so we
    # don't pick up `if (x) {`. `if`/`while`/etc. are in _PY_BUILTINS anyway.
    re.compile(r"(?:^|[{,;:])\s*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{"),
)

_PY_BUILTINS = {
    "if", "else", "while", "for", "do", "switch", "case", "default",
    "return", "break", "continue", "function", "class", "const", "let",
    "var", "new", "this", "super", "try", "catch", "finally", "throw",
    "typeof", "instanceof", "in", "of", "void", "delete", "yield", "await",
    "async", "static", "extends", "export", "import", "from", "as",
    "window", "document", "navigator", "location", "history", "screen",
    "console", "alert", "confirm", "prompt",
    "fetch", "XMLHttpRequest", "WebSocket", "EventSource",
    "setTimeout", "clearTimeout", "setInterval", "clearInterval",
    "requestAnimationFrame", "cancelAnimationFrame",
    "localStorage", "sessionStorage", "indexedDB",
    "Audio", "Image", "Notification",
    "URL", "URLSearchParams", "FormData", "Blob", "File", "FileReader",
    "AudioContext", "webkitAudioContext",
    "Event", "CustomEvent", "MouseEvent", "KeyboardEvent",
    "Math", "Date", "JSON", "Object", "Array", "String", "Number", "Boolean",
    "Error", "TypeError", "RangeError", "SyntaxError", "ReferenceError",
    "Promise", "Symbol", "Map", "Set", "WeakMap", "WeakSet",
    "Proxy", "Reflect", "parseInt", "parseFloat", "isNaN", "isFinite",
    "encodeURI", "encodeURIComponent", "decodeURI", "decodeURIComponent",
    "undefined", "null", "true", "false", "NaN", "Infinity",
    "require", "module", "exports", "process", "Buffer", "globalThis",
    "React", "ReactDOM", "Vue",
}


def _python_declared(source: str) -> set[str]:
    declared: set[str] = set()
    for regex in _PY_DECL_RE_LIST:
        for match in regex.finditer(source):
            declared.add(match.group(1))
    # Assignment targets: `foo = ...`
    for match in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*=", source):
        declared.add(match.group(1))
    return declared


def _passed(name: str, category: str, summary: str) -> VerificationResult:
    return VerificationResult(
        verifier=name,
        category=category,
        passed=True,
        severity="info",
        summary=summary,
    )
