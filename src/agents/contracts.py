"""Schema validation for structured agent outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any


@dataclass
class AgentFile:
    path: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "content": self.content}


@dataclass
class AgentOutput:
    status: str
    files: list[AgentFile] = field(default_factory=list)
    contracts: dict[str, Any] = field(default_factory=dict)
    uses_contracts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "files": [item.to_dict() for item in self.files],
            "contracts": self.contracts,
            "uses_contracts": self.uses_contracts,
            "notes": self.notes,
            "requires": self.requires,
        }


def validate_agent_output(payload: dict[str, Any], *, role: str = "") -> AgentOutput:
    """Validate and normalize the JSON contract expected from specialist agents."""
    if not isinstance(payload, dict):
        raise ValueError("agent output must be a JSON object")
    status = str(payload.get("status") or "").strip()
    if status not in {"success", "needs_input", "failed"}:
        raise ValueError("agent output status must be success, needs_input, or failed")

    files = payload.get("files") or []
    if not isinstance(files, list):
        raise ValueError("agent output files must be a list")
    parsed_files: list[AgentFile] = []
    for idx, item in enumerate(files):
        if not isinstance(item, dict):
            raise ValueError(f"files[{idx}] must be an object")
        path = str(item.get("path") or "").strip()
        content = item.get("content")
        if not path:
            raise ValueError(f"files[{idx}] requires path")
        if not isinstance(content, str):
            raise ValueError(f"files[{idx}] requires string content")
        parsed_files.append(AgentFile(path=path, content=content))

    contracts = payload.get("contracts") or {}
    if not isinstance(contracts, dict):
        raise ValueError("agent output contracts must be an object")
    if role == "backend" and status == "success":
        has_contracts = any(contracts.get(key) for key in ("api", "models", "events"))
        if not has_contracts:
            raise ValueError("backend agent output must include api, model, or event contracts")

    return AgentOutput(
        status=status,
        files=parsed_files,
        contracts=contracts,
        uses_contracts=_string_list(payload.get("uses_contracts") or []),
        notes=_string_list(payload.get("notes") or []),
        requires=_string_list(payload.get("requires") or []),
    )


def parse_agent_output_json(response: str) -> dict[str, Any]:
    """Parse a strict JSON object from a model response."""
    if not response or "{" not in response:
        raise ValueError("model returned no JSON object")
    candidates = [response.strip()]
    start = response.find("{")
    end = response.rfind("}")
    if 0 <= start < end:
        candidates.append(response[start:end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("model returned invalid JSON; expected an object with status, files, contracts, uses_contracts")


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value else []
