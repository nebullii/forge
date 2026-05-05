"""Base verifier interface."""

from __future__ import annotations

from .models import VerificationContext, VerificationResult


class BaseVerifier:
    name = "base"
    category = "generic"

    def applies_to(self, context: VerificationContext) -> bool:
        return True

    def run(self, context: VerificationContext) -> VerificationResult:
        raise NotImplementedError
