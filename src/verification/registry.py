"""Verifier registry and runner."""

from __future__ import annotations

from .contracts import AuthCoverageVerifier, ContractConsistencyVerifier
from .html_behavior import HTMLBehaviorVerifier
from .javascript import JavaScriptVerifier
from .models import VerificationContext, VerificationReport
from .python import PythonSyntaxVerifier
from .structure import FrontendProjectVerifier, SupportedStackStructureVerifier


class VerificationRegistry:
    def __init__(self) -> None:
        self._verifiers = [
            ContractConsistencyVerifier(),
            AuthCoverageVerifier(),
            PythonSyntaxVerifier(),
            JavaScriptVerifier(),
            HTMLBehaviorVerifier(),
            SupportedStackStructureVerifier(),
            FrontendProjectVerifier(),
        ]

    def applicable(self, context: VerificationContext):
        return [verifier for verifier in self._verifiers if verifier.applies_to(context)]

    def run(self, context: VerificationContext) -> VerificationReport:
        report = VerificationReport()
        for verifier in self.applicable(context):
            report.results.append(verifier.run(context))
        return report
