"""Contract-oriented verifiers."""

from __future__ import annotations

from .base import BaseVerifier
from .models import VerificationContext, VerificationResult


class ContractConsistencyVerifier(BaseVerifier):
    name = "contract_consistency"
    category = "contract"

    def applies_to(self, context: VerificationContext) -> bool:
        return context.contracts is not None and len(context.contracts) > 0

    def run(self, context: VerificationContext) -> VerificationResult:
        result = context.contracts.validate_frontend_against_backend()
        issues = result.get("issues", [])
        return VerificationResult(
            verifier=self.name,
            category=self.category,
            passed=result.get("passed", True),
            severity="error",
            summary="Frontend/backend contract consistency",
            details="\n".join(issues),
            logs=tuple(issues),
            retryable=True,
        )


class AuthCoverageVerifier(BaseVerifier):
    name = "auth_coverage"
    category = "security"

    def applies_to(self, context: VerificationContext) -> bool:
        return context.contracts is not None and len(context.contracts) > 0

    def run(self, context: VerificationContext) -> VerificationResult:
        result = context.contracts.validate_security_coverage()
        issues = result.get("issues", [])
        return VerificationResult(
            verifier=self.name,
            category=self.category,
            passed=result.get("passed", True),
            severity="warning",
            summary="Write-endpoint auth coverage",
            details="\n".join(issues),
            logs=tuple(issues),
            retryable=True,
        )
