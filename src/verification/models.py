"""Machine-readable verification models."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class VerificationResult:
    verifier: str
    category: str
    passed: bool
    severity: str = "error"
    summary: str = ""
    details: str = ""
    logs: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    retryable: bool = False


@dataclass
class VerificationContext:
    project_root: Path
    files: Dict[str, str]
    decisions: Dict[str, Any] = field(default_factory=dict)
    contracts: Any = None


@dataclass
class VerificationReport:
    results: List[VerificationResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(result.passed or result.severity == "warning" for result in self.results)

    def failed_results(self) -> List[VerificationResult]:
        return [result for result in self.results if not result.passed and result.severity != "warning"]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "results": [asdict(result) for result in self.results],
        }
