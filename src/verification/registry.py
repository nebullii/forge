"""Verifier registry and runner."""

from __future__ import annotations

from .contracts import AuthCoverageVerifier, ContractConsistencyVerifier
from .models import VerificationContext, VerificationReport
from .python import PythonSyntaxVerifier


class VerificationRegistry:
    def __init__(self) -> None:
        self._verifiers = [
            ContractConsistencyVerifier(),
            AuthCoverageVerifier(),
            PythonSyntaxVerifier(),
        ]

    def applicable(self, context: VerificationContext):
        return [verifier for verifier in self._verifiers if verifier.applies_to(context)]

    def run(self, context: VerificationContext) -> VerificationReport:
        report = VerificationReport()
        for verifier in self.applicable(context):
            report.results.append(verifier.run(context))
        return report
