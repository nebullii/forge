"""Structured contract registry for inter-agent coordination.

Contracts are the machine-readable description of what one agent promises
(produces) and what another agent expects (consumes).  The registry is
populated after each agent runs and is used to:

1. Give the frontend agent the exact endpoint shapes the backend created.
2. Let the security agent know which endpoints require auth.
3. Let the reviewer validate cross-cutting consistency.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple


# ---------------------------------------------------------------------------
# Contract types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApiEndpointContract:
    """A single REST API endpoint published by the backend."""

    method: str                                      # GET | POST | PUT | DELETE | PATCH
    path: str                                        # e.g. "/users/{id}"
    request_schema: Dict[str, Any] = field(default_factory=dict)
    response_schema: Dict[str, Any] = field(default_factory=dict)
    auth: str = "none"                               # none | jwt | session | api_key
    errors: Tuple[str, ...] = ()
    producer_agent: str = ""
    source_files: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DataModelContract:
    """A data model / database table schema."""

    name: str
    fields: Dict[str, str] = field(default_factory=dict)
    relationships: Tuple[str, ...] = ()
    constraints: Tuple[str, ...] = ()
    producer_agent: str = ""


@dataclass(frozen=True)
class EventContract:
    """An event / message / webhook contract."""

    name: str
    payload_schema: Dict[str, Any] = field(default_factory=dict)
    producer_agent: str = ""
    consumers: Tuple[str, ...] = ()


@dataclass(frozen=True)
class UIDataDependency:
    """Declares that a frontend view depends on a backend endpoint."""

    view_name: str
    endpoint: str                                    # e.g. "GET /users"
    expected_shape: Dict[str, Any] = field(default_factory=dict)
    producer_agent: str = ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ContractRegistry:
    """Thread-safe registry of inter-agent contracts."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._api: List[ApiEndpointContract] = []
        self._models: List[DataModelContract] = []
        self._events: List[EventContract] = []
        self._ui_deps: List[UIDataDependency] = []

    # -- mutation ----------------------------------------------------------

    def register(self, contract: Any) -> None:
        """Register a single contract."""
        with self._lock:
            if isinstance(contract, ApiEndpointContract):
                self._api.append(contract)
            elif isinstance(contract, DataModelContract):
                self._models.append(contract)
            elif isinstance(contract, EventContract):
                self._events.append(contract)
            elif isinstance(contract, UIDataDependency):
                self._ui_deps.append(contract)
            else:
                raise TypeError(f"Unknown contract type: {type(contract)}")

    def register_many(self, contracts: List[Any]) -> None:
        """Register multiple contracts atomically."""
        with self._lock:
            for c in contracts:
                self.register(c)

    # -- queries -----------------------------------------------------------

    def get_api_contracts(self) -> List[ApiEndpointContract]:
        with self._lock:
            return list(self._api)

    def get_model_contracts(self) -> List[DataModelContract]:
        with self._lock:
            return list(self._models)

    def get_event_contracts(self) -> List[EventContract]:
        with self._lock:
            return list(self._events)

    def get_ui_dependencies(self) -> List[UIDataDependency]:
        with self._lock:
            return list(self._ui_deps)

    # -- formatting for prompts --------------------------------------------

    def format_for_prompt(self) -> str:
        """Render all contracts as a human-readable block for agent prompts."""
        with self._lock:
            parts: List[str] = []

            if self._api:
                parts.append("## API Endpoints")
                for c in self._api:
                    line = f"  {c.method} {c.path}"
                    if c.auth != "none":
                        line += f"  [auth: {c.auth}]"
                    parts.append(line)
                    if c.request_schema:
                        parts.append(f"    Request:  {json.dumps(c.request_schema)}")
                    if c.response_schema:
                        parts.append(f"    Response: {json.dumps(c.response_schema)}")

            if self._models:
                parts.append("\n## Data Models")
                for m in self._models:
                    parts.append(f"  {m.name}")
                    for fname, ftype in m.fields.items():
                        parts.append(f"    {fname}: {ftype}")

            if self._events:
                parts.append("\n## Events")
                for e in self._events:
                    parts.append(f"  {e.name}: {json.dumps(e.payload_schema)}")

            return "\n".join(parts) if parts else "(no contracts registered)"

    def format_as_json(self) -> str:
        """Serialize all contracts to a JSON string (for context dicts)."""
        with self._lock:
            return json.dumps({
                "api": [
                    {
                        "method": c.method,
                        "path": c.path,
                        "request_schema": c.request_schema,
                        "response_schema": c.response_schema,
                        "auth": c.auth,
                    }
                    for c in self._api
                ],
                "models": [
                    {"name": m.name, "fields": m.fields}
                    for m in self._models
                ],
                "events": [
                    {"name": e.name, "payload_schema": e.payload_schema}
                    for e in self._events
                ],
            }, indent=2)

    # -- validation --------------------------------------------------------

    def diff_expected_vs_actual(self) -> List[str]:
        """Compare UI dependencies against registered API endpoints.

        Returns a list of mismatch descriptions (empty = all good).
        """
        with self._lock:
            api_set = {f"{c.method} {c.path}" for c in self._api}
            return [
                f"UI view '{d.view_name}' expects {d.endpoint} "
                f"but no matching API endpoint is registered."
                for d in self._ui_deps
                if d.endpoint not in api_set
            ]

    def validate_frontend_against_backend(self) -> Dict[str, Any]:
        """Validate that frontend dependencies match backend contracts."""
        issues = self.diff_expected_vs_actual()
        return {"passed": len(issues) == 0, "issues": issues}

    def validate_security_coverage(self) -> Dict[str, Any]:
        """Flag write endpoints that have no auth configured."""
        with self._lock:
            issues = [
                f"{c.method} {c.path} has no auth configured."
                for c in self._api
                if c.method in ("POST", "PUT", "DELETE", "PATCH")
                and c.auth == "none"
            ]
            return {"passed": len(issues) == 0, "issues": issues}

    def __len__(self) -> int:
        with self._lock:
            return len(self._api) + len(self._models) + len(self._events)

    # -- persistence -------------------------------------------------------

    def save(self, path: "Path") -> None:
        """Serialize all contracts to a JSON file at *path*."""
        from pathlib import Path as _Path
        path = _Path(path)
        with self._lock:
            data = {
                "api": [
                    {
                        "method": c.method, "path": c.path,
                        "request_schema": c.request_schema,
                        "response_schema": c.response_schema,
                        "auth": c.auth,
                        "errors": list(c.errors),
                        "producer_agent": c.producer_agent,
                        "source_files": list(c.source_files),
                    }
                    for c in self._api
                ],
                "models": [
                    {
                        "name": m.name, "fields": m.fields,
                        "relationships": list(m.relationships),
                        "constraints": list(m.constraints),
                        "producer_agent": m.producer_agent,
                    }
                    for m in self._models
                ],
                "events": [
                    {
                        "name": e.name, "payload_schema": e.payload_schema,
                        "producer_agent": e.producer_agent,
                        "consumers": list(e.consumers),
                    }
                    for e in self._events
                ],
                "ui_deps": [
                    {
                        "view_name": d.view_name, "endpoint": d.endpoint,
                        "expected_shape": d.expected_shape,
                        "producer_agent": d.producer_agent,
                    }
                    for d in self._ui_deps
                ],
            }
        path.write_text(json.dumps(data, indent=2))

    def to_openapi_dict(
        self,
        title: str = "Forge Generated API",
        version: str = "1.0.0",
    ) -> Dict[str, Any]:
        """Export API and model contracts as a minimal OpenAPI 3.1 document."""
        with self._lock:
            doc: Dict[str, Any] = {
                "openapi": "3.1.0",
                "info": {"title": title, "version": version},
                "paths": {},
                "components": {"schemas": {}, "securitySchemes": {}},
            }

            for model in self._models:
                doc["components"]["schemas"][model.name] = {
                    "type": "object",
                    "properties": {
                        name: _field_type_to_schema(field_type)
                        for name, field_type in model.fields.items()
                    },
                }

            for endpoint in self._api:
                path_item = doc["paths"].setdefault(endpoint.path, {})
                operation: Dict[str, Any] = {
                    "operationId": _operation_id(endpoint.method, endpoint.path),
                    "responses": {
                        _success_status(endpoint.method): {
                            "description": "Successful response",
                            "content": {
                                "application/json": {
                                    "schema": _json_schema(endpoint.response_schema)
                                }
                            },
                        }
                    },
                }
                if endpoint.request_schema:
                    operation["requestBody"] = {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": _json_schema(endpoint.request_schema)
                            }
                        },
                    }

                if endpoint.auth == "jwt":
                    doc["components"]["securitySchemes"]["BearerAuth"] = {
                        "type": "http",
                        "scheme": "bearer",
                    }
                    operation["security"] = [{"BearerAuth": []}]
                elif endpoint.auth == "api_key":
                    doc["components"]["securitySchemes"]["ApiKeyAuth"] = {
                        "type": "apiKey",
                        "in": "header",
                        "name": "X-API-Key",
                    }
                    operation["security"] = [{"ApiKeyAuth": []}]
                elif endpoint.auth == "session":
                    doc["components"]["securitySchemes"]["SessionCookie"] = {
                        "type": "apiKey",
                        "in": "cookie",
                        "name": "session",
                    }
                    operation["security"] = [{"SessionCookie": []}]

                path_item[endpoint.method.lower()] = operation

            if not doc["components"]["schemas"]:
                doc["components"].pop("schemas", None)
            if not doc["components"]["securitySchemes"]:
                doc["components"].pop("securitySchemes", None)
            if not doc["components"]:
                doc.pop("components", None)

            return doc

    def export_openapi(
        self,
        path: "Path",
        title: str = "Forge Generated API",
        version: str = "1.0.0",
    ) -> None:
        path = Path(path)
        path.write_text(json.dumps(self.to_openapi_dict(title=title, version=version), indent=2) + "\n")

    @classmethod
    def load(cls, path: "Path") -> "ContractRegistry":
        """Load contracts from a JSON file. Returns empty registry if missing."""
        from pathlib import Path as _Path
        path = _Path(path)
        registry = cls()
        if not path.exists():
            return registry

        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return registry

        parsed = _parse_raw_contracts(data, "")
        registry.register_many(parsed.get("api", []))
        registry.register_many(parsed.get("models", []))
        registry.register_many(parsed.get("events", []))

        # Load UI dependencies (not covered by _parse_raw_contracts)
        for d in data.get("ui_deps", []):
            registry.register(UIDataDependency(
                view_name=d.get("view_name", ""),
                endpoint=d.get("endpoint", ""),
                expected_shape=d.get("expected_shape", {}),
                producer_agent=d.get("producer_agent", ""),
            ))

        return registry


# ---------------------------------------------------------------------------
# Contract extraction from agent responses
# ---------------------------------------------------------------------------

def extract_contracts_from_response(
    response: str,
    producer_agent: str = "backend",
) -> Dict[str, List[Any]]:
    """Extract structured contracts from an agent's response text.

    Strategy (in priority order):
    1. Look for an explicit ``\\`\\`\\`contracts`` JSON block emitted by the agent.
    2. Fall back to regex-based extraction from route decorators in code.

    Returns ``{"api": [...], "models": [...], "events": [...]}``.
    """
    # 1. Explicit contract block
    match = re.search(r"```contracts\s*\n(.*?)```", response, re.DOTALL)
    if match:
        try:
            raw = json.loads(match.group(1))
            return _parse_raw_contracts(raw, producer_agent)
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    # 2. Fallback: code-level extraction
    return _extract_from_code(response, producer_agent)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_raw_contracts(
    raw: Dict[str, Any],
    producer: str = "",
) -> Dict[str, List[Any]]:
    """Convert a raw JSON dict into typed contract objects.

    If *producer* is non-empty it overrides the ``producer_agent`` in each
    entry; otherwise the value from the JSON is used (for ``load()``).
    """
    result: Dict[str, List[Any]] = {"api": [], "models": [], "events": []}

    for ep in raw.get("api", []):
        result["api"].append(ApiEndpointContract(
            method=ep.get("method", "GET").upper(),
            path=ep.get("path", ""),
            request_schema=ep.get("request_schema", {}),
            response_schema=ep.get("response_schema", {}),
            auth=ep.get("auth", "none"),
            errors=tuple(ep.get("errors", [])),
            producer_agent=producer or ep.get("producer_agent", ""),
            source_files=tuple(ep.get("source_files", [])),
        ))

    for m in raw.get("models", []):
        result["models"].append(DataModelContract(
            name=m.get("name", ""),
            fields=m.get("fields", {}),
            relationships=tuple(m.get("relationships", [])),
            constraints=tuple(m.get("constraints", [])),
            producer_agent=producer or m.get("producer_agent", ""),
        ))

    for e in raw.get("events", []):
        result["events"].append(EventContract(
            name=e.get("name", ""),
            payload_schema=e.get("payload_schema", {}),
            producer_agent=producer or e.get("producer_agent", ""),
            consumers=tuple(e.get("consumers", [])),
        ))

    return result


def _extract_from_code(
    response: str,
    producer: str,
) -> Dict[str, List[Any]]:
    """Best-effort extraction of contracts from route decorators in code."""
    apis: List[ApiEndpointContract] = []
    models: List[DataModelContract] = []
    seen_endpoints: set = set()

    # FastAPI / Flask decorator patterns
    for match in re.finditer(
        r"@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*[\"']([^\"']+)[\"']",
        response,
        re.IGNORECASE,
    ):
        method = match.group(1).upper()
        path = match.group(2)
        key = (method, path)
        if key not in seen_endpoints:
            seen_endpoints.add(key)
            apis.append(ApiEndpointContract(
                method=method, path=path, producer_agent=producer,
            ))

    # Express.js / Hono patterns  (app.get("/path", ...))
    for match in re.finditer(
        r"(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*[\"']([^\"']+)[\"']",
        response,
        re.IGNORECASE,
    ):
        method = match.group(1).upper()
        path = match.group(2)
        key = (method, path)
        if key not in seen_endpoints:
            seen_endpoints.add(key)
            apis.append(ApiEndpointContract(
                method=method, path=path, producer_agent=producer,
            ))

    # Rails-style route patterns  (get "/users", to: "users#index")
    for match in re.finditer(
        r'^\s*(get|post|put|patch|delete)\s+["\']([^"\']+)["\']',
        response,
        re.IGNORECASE | re.MULTILINE,
    ):
        method = match.group(1).upper()
        path = match.group(2)
        key = (method, path)
        if key not in seen_endpoints:
            seen_endpoints.add(key)
            apis.append(ApiEndpointContract(
                method=method, path=path, producer_agent=producer,
            ))

    # Pydantic BaseModel / SQLAlchemy Model / dataclass patterns
    for match in re.finditer(
        r"class\s+(\w+)\s*\(\s*(?:BaseModel|Base|db\.Model)\s*\)",
        response,
    ):
        name = match.group(1)
        # Try to extract fields from the class body
        fields = _extract_class_fields(response, match.end())
        models.append(DataModelContract(
            name=name, fields=fields, producer_agent=producer,
        ))

    return {"api": apis, "models": models, "events": []}


def _extract_class_fields(source: str, start_pos: int) -> Dict[str, str]:
    """Extract field names and type hints from a class body starting at *start_pos*."""
    fields: Dict[str, str] = {}
    remaining = source[start_pos:]
    # Match lines like:  name: str  or  name: str = "default"
    for line_match in re.finditer(
        r"^\s+(\w+)\s*:\s*([A-Za-z_][\w\[\], |]*)",
        remaining,
        re.MULTILINE,
    ):
        fname = line_match.group(1)
        ftype = line_match.group(2).strip()
        # Stop if we hit the next class definition
        if line_match.start() > 500:
            break
        if fname.startswith("_"):
            continue
        fields[fname] = ftype
    return fields


def _field_type_to_schema(field_type: Any) -> Dict[str, Any]:
    field = str(field_type).strip().lower()
    if field in {"int", "integer"}:
        return {"type": "integer"}
    if field in {"float", "double", "number", "decimal"}:
        return {"type": "number"}
    if field in {"bool", "boolean"}:
        return {"type": "boolean"}
    if field in {"list", "array"}:
        return {"type": "array", "items": {}}
    if field in {"dict", "object", "map"}:
        return {"type": "object"}
    return {"type": "string"}


def _json_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    if not data:
        return {"type": "object"}
    if "type" in data:
        schema = dict(data)
        if schema.get("items") and isinstance(schema["items"], str):
            schema["items"] = {"$ref": f"#/components/schemas/{schema['items']}"}
        return schema
    return {
        "type": "object",
        "properties": {
            key: (
                {"$ref": f"#/components/schemas/{value}"}
                if isinstance(value, str) and value[:1].isupper()
                else _field_type_to_schema(value)
            )
            for key, value in data.items()
        },
    }


def _success_status(method: str) -> str:
    method = method.upper()
    if method == "POST":
        return "201"
    if method == "DELETE":
        return "204"
    return "200"


def _operation_id(method: str, path: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_")
    return f"{method.lower()}_{cleaned or 'root'}"
