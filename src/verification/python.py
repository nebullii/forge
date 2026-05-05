"""Python syntax verifier."""

from __future__ import annotations

from .base import BaseVerifier
from .models import VerificationContext, VerificationResult


class PythonSyntaxVerifier(BaseVerifier):
    name = "python_syntax"
    category = "syntax"

    def applies_to(self, context: VerificationContext) -> bool:
        return any(path.endswith(".py") for path in context.files)

    def run(self, context: VerificationContext) -> VerificationResult:
        failures: list[str] = []
        failed_files: list[str] = []
        for path, content in context.files.items():
            if not path.endswith(".py"):
                continue
            try:
                compile(content, path, "exec")
            except SyntaxError as exc:
                failures.append(f"{path}:{exc.lineno} {exc.msg}")
                failed_files.append(path)

        return VerificationResult(
            verifier=self.name,
            category=self.category,
            passed=not failures,
            severity="error",
            summary="Python syntax compilation",
            details="\n".join(failures),
            logs=tuple(failures),
            files=tuple(failed_files),
            retryable=True,
        )
