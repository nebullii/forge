"""Parser for structured Forge Spec API directives embedded in markdown."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .models import SUPPORTED_PRIMITIVES, SpecDiagnostic, SpecDocument, SpecPrimitive


DIRECTIVE_RE = re.compile(r"^(?P<indent>\s*)\.(?P<type>[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?)(?:\s+(?P<name>[A-Za-z0-9_-]+))?\s*$")
API_ACTIONS = {"list", "get", "create", "update", "delete"}
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
FIELD_TYPES = {"string", "text", "email", "password", "integer", "number", "float", "boolean", "date", "datetime", "money", "uuid", "json"}


def parse_spec_file(path: Path) -> SpecDocument:
    """Parse a spec file into structured primitives."""
    return parse_spec_text(path.read_text(), source_path=path)


def parse_spec_text(text: str, source_path: Path | None = None) -> SpecDocument:
    """Parse Forge Spec API directives from markdown text.

    Directive blocks use markdown-friendly indentation:

        .db.model Client
          fields:
            name: string required
    """
    lines = text.splitlines()
    doc = SpecDocument()
    prose_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        match = DIRECTIVE_RE.match(line)
        if not match:
            prose_lines.append(line)
            i += 1
            continue

        primitive_type = match.group("type")
        name = match.group("name") or ""
        start_line = i + 1
        raw_lines = [line]
        body_lines: list[str] = []
        i += 1
        while i < len(lines):
            next_line = lines[i]
            if DIRECTIVE_RE.match(next_line):
                break
            if next_line.strip() and not next_line.startswith((" ", "\t")):
                break
            raw_lines.append(next_line)
            if next_line.strip():
                body_lines.append(next_line)
            i += 1

        body = _parse_body(body_lines, start_line, doc)
        primitive = SpecPrimitive(
            type=primitive_type,
            name=name,
            body=body,
            line=start_line,
            raw="\n".join(raw_lines),
        )
        doc.primitives.append(primitive)
        _validate_primitive(primitive, doc)

    doc.prose = "\n".join(prose_lines).strip()
    _validate_spec_api_version(doc)
    _validate_cross_refs(doc)
    return doc


def _parse_body(lines: list[str], start_line: int, doc: SpecDocument) -> dict[str, Any]:
    if not lines:
        return {}
    min_indent = min(len(line) - len(line.lstrip(" ")) for line in lines if line.strip())
    normalized = "\n".join(line[min_indent:] for line in lines)
    try:
        loaded = yaml.safe_load(normalized)
    except yaml.YAMLError as exc:
        doc.diagnostics.append(SpecDiagnostic(
            line=start_line,
            severity="error",
            message=f"invalid directive body YAML: {exc}",
        ))
        return {}
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        doc.diagnostics.append(SpecDiagnostic(
            line=start_line,
            severity="error",
            message="directive body must be a key/value map",
        ))
        return {}
    return _normalize_body(loaded)


def _normalize_body(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    if "fields" in normalized and isinstance(normalized["fields"], dict):
        normalized["fields"] = {
            str(name): _parse_field(str(value))
            for name, value in normalized["fields"].items()
        }
    if "actions" in normalized:
        normalized["actions"] = _list_value(normalized["actions"])
    if "columns" in normalized:
        normalized["columns"] = _list_value(normalized["columns"])
    if "roles" in normalized:
        normalized["roles"] = _list_value(normalized["roles"])
    return normalized


def _parse_field(value: str) -> dict[str, Any]:
    parts = str(value).split()
    if not parts:
        return {"type": "string", "required": False}
    field_type = parts[0]
    flags = {part.lower() for part in parts[1:]}
    return {
        "type": field_type,
        "required": "required" in flags,
        "optional": "optional" in flags,
    }


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _validate_primitive(primitive: SpecPrimitive, doc: SpecDocument) -> None:
    if primitive.type not in SUPPORTED_PRIMITIVES:
        doc.diagnostics.append(SpecDiagnostic(
            line=primitive.line,
            severity="error",
            message=f"unsupported primitive '.{primitive.type}'",
        ))
        return

    if primitive.type in {"db.model", "api.resource", "ui.page", "ui.table", "ui.form", "test.case", "deploy.target"} and not primitive.name:
        doc.diagnostics.append(SpecDiagnostic(
            line=primitive.line,
            severity="error",
            message=f"'.{primitive.type}' requires a name",
        ))

    if primitive.type == "db.model":
        fields = primitive.body.get("fields")
        if not isinstance(fields, dict) or not fields:
            doc.diagnostics.append(SpecDiagnostic(
                line=primitive.line,
                severity="error",
                message="'.db.model' requires a non-empty 'fields' map",
            ))
        elif fields:
            for field_name, field in fields.items():
                field_type = str(field.get("type") if isinstance(field, dict) else field)
                if not _valid_field_type(field_type):
                    doc.diagnostics.append(SpecDiagnostic(
                        line=primitive.line,
                        severity="error",
                        message=f".db.model field '{field_name}' uses unsupported type '{field_type}'",
                    ))

    if primitive.type == "api.resource":
        if not primitive.body.get("model"):
            doc.diagnostics.append(SpecDiagnostic(
                line=primitive.line,
                severity="error",
                message="'.api.resource' requires 'model'",
            ))
        if not primitive.body.get("actions"):
            doc.diagnostics.append(SpecDiagnostic(
                line=primitive.line,
                severity="error",
                message="'.api.resource' requires 'actions'",
            ))
        else:
            actions = primitive.body.get("actions")
            invalid = [action for action in actions if action not in API_ACTIONS] if isinstance(actions, list) else []
            if invalid:
                doc.diagnostics.append(SpecDiagnostic(
                    line=primitive.line,
                    severity="error",
                    message=f".api.resource has unsupported action(s): {', '.join(invalid)}",
                ))
        auth = primitive.body.get("auth")
        if auth and str(auth) not in {"required", "optional", "public"}:
            doc.diagnostics.append(SpecDiagnostic(
                line=primitive.line,
                severity="error",
                message=".api.resource auth must be required, optional, or public",
            ))

    if primitive.type == "ui.table":
        source = primitive.body.get("source")
        if not source:
            doc.diagnostics.append(SpecDiagnostic(
                line=primitive.line,
                severity="error",
                message="'.ui.table' requires 'source'",
            ))
        elif not _valid_endpoint_ref(str(source)):
            doc.diagnostics.append(SpecDiagnostic(
                line=primitive.line,
                severity="error",
                message="'.ui.table' source must look like 'GET /api/resource'",
            ))

    if primitive.type == "ui.form":
        submit = primitive.body.get("submit")
        if not submit:
            doc.diagnostics.append(SpecDiagnostic(
                line=primitive.line,
                severity="error",
                message="'.ui.form' requires 'submit'",
            ))
        elif not _valid_endpoint_ref(str(submit), allow_get=False):
            doc.diagnostics.append(SpecDiagnostic(
                line=primitive.line,
                severity="error",
                message="'.ui.form' submit must look like 'POST /api/resource'",
            ))


def _validate_cross_refs(doc: SpecDocument) -> None:
    model_names = {item.name for item in doc.primitives if item.type == "db.model"}
    for primitive in doc.primitives:
        if primitive.type == "api.resource":
            model = str(primitive.body.get("model") or "")
            if model and model not in model_names:
                doc.diagnostics.append(SpecDiagnostic(
                    line=primitive.line,
                    severity="error",
                    message=f".api.resource references unknown model '{model}'",
                ))


def _validate_spec_api_version(doc: SpecDocument) -> None:
    project = next((item for item in doc.primitives if item.type == "project"), None)
    version = str((project.body.get("spec_api_version") if project else "") or "0.1")
    doc.spec_api_version = version
    if version != "0.1":
        line = project.line if project else 1
        doc.diagnostics.append(SpecDiagnostic(
            line=line,
            severity="error",
            message=f"unsupported Spec API version '{version}' (supported: 0.1)",
        ))


def _valid_field_type(field_type: str) -> bool:
    if field_type.startswith("enum[") and field_type.endswith("]"):
        values = [item.strip() for item in field_type[5:-1].split(",") if item.strip()]
        return bool(values)
    if field_type.startswith("relation"):
        return True
    return field_type in FIELD_TYPES


def _valid_endpoint_ref(value: str, *, allow_get: bool = True) -> bool:
    parts = value.strip().split()
    if len(parts) != 2:
        return False
    method, path = parts[0].upper(), parts[1]
    methods = HTTP_METHODS if allow_get else (HTTP_METHODS - {"GET"})
    return method in methods and path.startswith("/") and " " not in path
