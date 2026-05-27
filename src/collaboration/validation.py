"""Agent output validation — catches garbage before it propagates through the pipeline.

Each agent type has minimum output requirements. If an agent's response doesn't
meet them, the orchestrator gets a clear error instead of silently passing bad
output to downstream agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .contracts import extract_contracts_from_response


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating an agent's output."""
    valid: bool
    reason: str = ""
    files_found: int = 0
    contracts_found: int = 0


# Minimum expectations per agent type
_MIN_FILES: Dict[str, int] = {
    "backend":  1,
    "builder":  1,
    "frontend": 1,
    "ci":       1,
    "deploy":   1,
    "coder":    1,
    "security": 0,   # security may only produce audit text, no files
    "reviewer": 0,   # reviewer produces review YAML, not files
    "planner":  0,   # planner produces structured data, not files
}


def validate_agent_output(
    agent_name: str,
    response_text: str,
    files: List[Tuple[str, str]],
) -> ValidationResult:
    """Validate that an agent produced minimally useful output.

    Args:
        agent_name: The agent role (e.g., "backend", "frontend")
        response_text: The raw LLM response text
        files: List of (path, content) tuples extracted from the response

    Returns:
        ValidationResult with valid=True if output meets minimum requirements.
    """
    if not response_text or not response_text.strip():
        return ValidationResult(
            valid=False,
            reason=f"{agent_name} returned an empty response",
        )

    min_files = _MIN_FILES.get(agent_name, 0)

    if len(files) < min_files:
        return ValidationResult(
            valid=False,
            reason=(
                f"{agent_name} produced {len(files)} file(s), "
                f"expected at least {min_files}"
            ),
            files_found=len(files),
            )

    # Check for placeholder/stub content in generated files
    for path, content in files:
        if not content.strip():
            return ValidationResult(
                valid=False,
                reason=f"{agent_name} produced an empty file: {path}",
                files_found=len(files),
            )

    if agent_name == "backend":
        contracts = extract_contracts_from_response(response_text, "backend")
        if not contracts["api"] and not contracts["models"] and not contracts["events"]:
            return ValidationResult(
                valid=False,
                reason="backend produced no machine-readable contracts",
                files_found=len(files),
            )

    return ValidationResult(
        valid=True,
        files_found=len(files),
    )
