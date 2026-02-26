"""A2A Protocol types -- Pydantic models for Google's Agent-to-Agent spec."""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

try:
    from pydantic import BaseModel, Field
except ImportError:
    raise ImportError(
        "pydantic is required for A2A support. "
        "Install it with: pip install 'forge-ai[adk]'"
    )


class TaskStatus(str, Enum):
    submitted = "submitted"
    working = "working"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class FilePart(BaseModel):
    type: Literal["file"] = "file"
    path: str
    content: str


Part = Union[TextPart, FilePart]


class Message(BaseModel):
    role: Literal["user", "agent"]
    parts: List[Part]


class Artifact(BaseModel):
    """Output artifact from an agent (e.g., generated files)."""
    type: str = "text"
    name: Optional[str] = None
    description: Optional[str] = None
    parts: List[Part] = Field(default_factory=list)
    # Structured data artifacts (e.g., task plan, decisions)
    data: Optional[Dict[str, Any]] = None


class Task(BaseModel):
    """An A2A task request sent to an agent."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    message: Message
    # Optional context from previous agents
    context: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class TaskResult(BaseModel):
    """Result returned by an agent after processing a Task."""
    id: str
    status: TaskStatus
    artifacts: List[Artifact] = Field(default_factory=list)
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @property
    def success(self) -> bool:
        return self.status == TaskStatus.completed

    def get_text(self) -> str:
        """Return concatenated text from all text artifacts."""
        parts = []
        for artifact in self.artifacts:
            for part in artifact.parts:
                if isinstance(part, TextPart):
                    parts.append(part.text)
        return "\n".join(parts)

    def get_files(self) -> list[tuple[str, str]]:
        """Return list of (path, content) from all file artifacts."""
        files = []
        for artifact in self.artifacts:
            for part in artifact.parts:
                if isinstance(part, FilePart):
                    files.append((part.path, part.content))
        return files

    def get_data(self) -> Optional[Dict[str, Any]]:
        """Return structured data from first data artifact."""
        for artifact in self.artifacts:
            if artifact.data is not None:
                return artifact.data
        return None


class AgentSkill(BaseModel):
    """A skill/capability that an agent offers."""
    id: str
    name: str
    description: str
    input_modes: List[str] = Field(default_factory=lambda: ["text"])
    output_modes: List[str] = Field(default_factory=lambda: ["text"])


class AgentCard(BaseModel):
    """Agent metadata card -- served at /.well-known/agent.json."""
    name: str
    description: str
    url: str
    version: str = "0.1.0"
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    skills: List[AgentSkill] = Field(default_factory=list)
    provider: Optional[Dict[str, str]] = None
