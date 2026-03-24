"""Collaboration layer for inter-agent communication in Forge.

Provides:
- Typed artifact models (CodeArtifact, DecisionArtifact, ReviewArtifact, ...)
- Thread-safe ArtifactBus for shared state across agents
- Structured ContractRegistry for backend/frontend/security coordination
- Contract extraction from agent responses
"""

from .models import (
    CodeArtifact,
    DecisionArtifact,
    ReviewArtifact,
    ContractArtifact,
    BuildLogArtifact,
    ReworkRequestArtifact,
)
from .artifact_bus import ArtifactBus
from .contracts import (
    ApiEndpointContract,
    DataModelContract,
    EventContract,
    UIDataDependency,
    ContractRegistry,
    extract_contracts_from_response,
)

__all__ = [
    "CodeArtifact",
    "DecisionArtifact",
    "ReviewArtifact",
    "ContractArtifact",
    "BuildLogArtifact",
    "ReworkRequestArtifact",
    "ArtifactBus",
    "ApiEndpointContract",
    "DataModelContract",
    "EventContract",
    "UIDataDependency",
    "ContractRegistry",
    "extract_contracts_from_response",
]
