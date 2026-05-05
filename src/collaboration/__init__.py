"""Collaboration layer for inter-agent communication in Forge.

Provides:
- Typed artifact models (CodeArtifact, DecisionArtifact, ReviewArtifact, ...)
- Thread-safe ArtifactBus for shared state across agents
- Structured ContractRegistry for backend/frontend/security coordination
- Contract extraction from agent responses
"""

from .models import (
    TaskPlanArtifact,
    CodeArtifact,
    BuildOutputArtifact,
    DecisionArtifact,
    ReviewArtifact,
    ReviewFindingArtifact,
    ContractArtifact,
    BuildLogArtifact,
    ReworkRequestArtifact,
    VerificationArtifact,
)
from .artifact_bus import ArtifactBus
from .store import ArtifactStore
from .contracts import (
    ApiEndpointContract,
    DataModelContract,
    EventContract,
    UIDataDependency,
    ContractRegistry,
    extract_contracts_from_response,
)
from .validation import validate_agent_output, ValidationResult

__all__ = [
    "CodeArtifact",
    "TaskPlanArtifact",
    "BuildOutputArtifact",
    "DecisionArtifact",
    "ReviewArtifact",
    "ReviewFindingArtifact",
    "ContractArtifact",
    "BuildLogArtifact",
    "ReworkRequestArtifact",
    "VerificationArtifact",
    "ArtifactBus",
    "ArtifactStore",
    "ApiEndpointContract",
    "DataModelContract",
    "EventContract",
    "UIDataDependency",
    "ContractRegistry",
    "extract_contracts_from_response",
    "validate_agent_output",
    "ValidationResult",
]
