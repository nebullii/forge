"""Deterministic project-structure verifiers for supported stacks."""

from __future__ import annotations

import json
import posixpath
import re
from pathlib import PurePosixPath

from .base import BaseVerifier
from .models import VerificationContext, VerificationResult


class SupportedStackStructureVerifier(BaseVerifier):
    name = "supported_stack_structure"
    category = "structure"

    def applies_to(self, context: VerificationContext) -> bool:
        stack = context.decisions.get("stack", {}) if isinstance(context.decisions, dict) else {}
        framework = str(stack.get("framework", "")).strip().lower()
        frontend = str(stack.get("frontend", "")).strip().lower()
        if framework == "fastapi" and frontend == "react":
            return True
        return "backend/main.py" in context.files and any(
            path.startswith("frontend/") for path in context.files
        )

    def run(self, context: VerificationContext) -> VerificationResult:
        required = (
            "backend/main.py",
            "frontend/package.json",
            "frontend/index.html",
        )

        frontend_entry_candidates = (
            "frontend/src/main.jsx",
            "frontend/src/main.js",
        )

        missing = [path for path in required if path not in context.files]
        if not any(path in context.files for path in frontend_entry_candidates):
            missing.append("frontend/src/main.jsx|frontend/src/main.js")

        return VerificationResult(
            verifier=self.name,
            category=self.category,
            passed=not missing,
            severity="error",
            summary="Supported-stack structure check",
            details="\n".join(f"Missing required file: {path}" for path in missing),
            logs=tuple(f"missing:{path}" for path in missing),
            files=tuple(missing),
            retryable=True,
        )


class FrontendProjectVerifier(BaseVerifier):
    name = "frontend_project"
    category = "frontend"

    def applies_to(self, context: VerificationContext) -> bool:
        return any(
            path == "package.json"
            or path == "frontend/package.json"
            or path.endswith((".jsx", ".tsx", ".js", ".ts"))
            for path in context.files
        )

    def run(self, context: VerificationContext) -> VerificationResult:
        failures: list[str] = []
        affected_files: list[str] = []

        package_path = self._package_path(context)
        package_json = None
        if package_path:
            try:
                package_json = json.loads(context.files[package_path])
            except json.JSONDecodeError as exc:
                failures.append(f"{package_path}: invalid JSON ({exc.msg})")
                affected_files.append(package_path)
        else:
            failures.append("Missing package.json for frontend project")

        if package_json is not None:
            scripts = package_json.get("scripts")
            if not isinstance(scripts, dict):
                failures.append(f"{package_path}: missing scripts section")
                affected_files.append(package_path)
            else:
                for script_name in ("dev", "build"):
                    if not isinstance(scripts.get(script_name), str) or not scripts.get(script_name, "").strip():
                        failures.append(f"{package_path}: missing '{script_name}' script")
                        affected_files.append(package_path)

        import_failures = _collect_missing_relative_imports(context.files)
        failures.extend(import_failures)
        affected_files.extend(_extract_files_from_import_failures(import_failures))

        unique_files = tuple(dict.fromkeys(affected_files))
        return VerificationResult(
            verifier=self.name,
            category=self.category,
            passed=not failures,
            severity="error",
            summary="Frontend package and import structure",
            details="\n".join(failures),
            logs=tuple(failures),
            files=unique_files,
            retryable=True,
        )

    def _package_path(self, context: VerificationContext) -> str:
        if "frontend/package.json" in context.files:
            return "frontend/package.json"
        if "package.json" in context.files and any(path.startswith("frontend/") for path in context.files):
            return "package.json"
        if "package.json" in context.files and any(path.endswith((".jsx", ".tsx")) for path in context.files):
            return "package.json"
        return ""


_IMPORT_RE = re.compile(r"""^\s*import\s+.+?\s+from\s+['"](.+?)['"]""", re.MULTILINE)
_IMPORT_SUFFIXES = (".js", ".jsx", ".ts", ".tsx")


def _collect_missing_relative_imports(files: dict[str, str]) -> list[str]:
    failures: list[str] = []
    file_set = set(files)

    for path, content in files.items():
        if not path.endswith((".js", ".jsx", ".ts", ".tsx")):
            continue
        for target in _IMPORT_RE.findall(content):
            if not target.startswith("."):
                continue
            if _import_target_exists(path, target, file_set):
                continue
            failures.append(f"{path}: missing import target '{target}'")
    return failures


def _import_target_exists(source_path: str, target: str, file_set: set[str]) -> bool:
    base = PurePosixPath(source_path).parent
    resolved = posixpath.normpath((base / target).as_posix())
    candidates = [resolved]
    if not PurePosixPath(resolved).suffix:
        candidates.extend(f"{resolved}{suffix}" for suffix in _IMPORT_SUFFIXES)
        candidates.extend(f"{resolved}/index{suffix}" for suffix in _IMPORT_SUFFIXES)
    return any(candidate in file_set for candidate in candidates)


def _extract_files_from_import_failures(failures: list[str]) -> list[str]:
    files: list[str] = []
    for failure in failures:
        if ":" in failure:
            files.append(failure.split(":", 1)[0])
    return files
