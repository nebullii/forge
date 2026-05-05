"""Tests for ContractRegistry, contract types, and extraction."""

import json
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.collaboration.contracts import (
    ApiEndpointContract,
    DataModelContract,
    EventContract,
    UIDataDependency,
    ContractRegistry,
    extract_contracts_from_response,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry():
    return ContractRegistry()


@pytest.fixture
def populated_registry(registry):
    registry.register(ApiEndpointContract(
        method="GET", path="/users", auth="jwt", producer_agent="backend",
        response_schema={"type": "array", "items": "User"},
    ))
    registry.register(ApiEndpointContract(
        method="POST", path="/users", auth="none", producer_agent="backend",
        request_schema={"email": "str", "name": "str"},
    ))
    registry.register(ApiEndpointContract(
        method="DELETE", path="/users/{id}", auth="jwt", producer_agent="backend",
    ))
    registry.register(DataModelContract(
        name="User", fields={"id": "int", "email": "str", "name": "str"},
        producer_agent="backend",
    ))
    registry.register(EventContract(
        name="user.created", payload_schema={"user_id": "int"},
        producer_agent="backend",
    ))
    return registry


# ---------------------------------------------------------------------------
# Registration & queries
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_register_api(self, registry):
        registry.register(ApiEndpointContract(method="GET", path="/"))
        assert len(registry.get_api_contracts()) == 1

    def test_register_model(self, registry):
        registry.register(DataModelContract(name="Foo", fields={"id": "int"}))
        assert len(registry.get_model_contracts()) == 1

    def test_register_event(self, registry):
        registry.register(EventContract(name="foo.bar"))
        assert len(registry.get_event_contracts()) == 1

    def test_register_ui_dep(self, registry):
        registry.register(UIDataDependency(view_name="Home", endpoint="GET /"))
        assert len(registry.get_ui_dependencies()) == 1

    def test_register_unknown_type_raises(self, registry):
        with pytest.raises(TypeError):
            registry.register("not a contract")

    def test_register_many(self, registry):
        contracts = [
            ApiEndpointContract(method="GET", path="/a"),
            ApiEndpointContract(method="GET", path="/b"),
            DataModelContract(name="X"),
        ]
        registry.register_many(contracts)
        assert len(registry) == 3

    def test_len(self, populated_registry):
        # 3 api + 1 model + 1 event = 5
        assert len(populated_registry) == 5


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

class TestFormatting:
    def test_format_for_prompt(self, populated_registry):
        text = populated_registry.format_for_prompt()
        assert "GET /users" in text
        assert "POST /users" in text
        assert "User" in text
        assert "user.created" in text
        assert "[auth: jwt]" in text

    def test_format_empty(self, registry):
        assert registry.format_for_prompt() == "(no contracts registered)"

    def test_format_as_json(self, populated_registry):
        j = json.loads(populated_registry.format_as_json())
        assert len(j["api"]) == 3
        assert len(j["models"]) == 1
        assert len(j["events"]) == 1


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_frontend_validation_passes(self, populated_registry):
        populated_registry.register(UIDataDependency(
            view_name="UserList", endpoint="GET /users",
        ))
        result = populated_registry.validate_frontend_against_backend()
        assert result["passed"] is True

    def test_frontend_validation_fails(self, populated_registry):
        populated_registry.register(UIDataDependency(
            view_name="Profile", endpoint="GET /profile",
        ))
        result = populated_registry.validate_frontend_against_backend()
        assert result["passed"] is False
        assert any("Profile" in i for i in result["issues"])

    def test_security_coverage_flags_unauthed_writes(self, populated_registry):
        result = populated_registry.validate_security_coverage()
        assert result["passed"] is False
        # POST /users has auth="none"
        assert any("POST /users" in i for i in result["issues"])

    def test_security_coverage_passes_when_all_authed(self, registry):
        registry.register(ApiEndpointContract(method="POST", path="/x", auth="jwt"))
        registry.register(ApiEndpointContract(method="GET", path="/y", auth="none"))
        result = registry.validate_security_coverage()
        assert result["passed"] is True  # GET is fine without auth

    def test_diff_expected_vs_actual(self, populated_registry):
        populated_registry.register(UIDataDependency(
            view_name="A", endpoint="GET /users",
        ))
        populated_registry.register(UIDataDependency(
            view_name="B", endpoint="GET /missing",
        ))
        diffs = populated_registry.diff_expected_vs_actual()
        assert len(diffs) == 1
        assert "missing" in diffs[0]


# ---------------------------------------------------------------------------
# Persistence (save / load)
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_load_roundtrip(self, populated_registry, tmp_path):
        populated_registry.register(UIDataDependency(
            view_name="Test", endpoint="GET /users", producer_agent="frontend",
        ))
        path = tmp_path / "contracts.json"
        populated_registry.save(path)
        assert path.exists()

        loaded = ContractRegistry.load(path)
        assert len(loaded.get_api_contracts()) == 3
        assert len(loaded.get_model_contracts()) == 1
        assert len(loaded.get_event_contracts()) == 1
        assert len(loaded.get_ui_dependencies()) == 1

    def test_load_preserves_producer_agent(self, populated_registry, tmp_path):
        path = tmp_path / "c.json"
        populated_registry.save(path)
        loaded = ContractRegistry.load(path)
        assert loaded.get_api_contracts()[0].producer_agent == "backend"
        assert loaded.get_model_contracts()[0].producer_agent == "backend"

    def test_load_preserves_auth(self, populated_registry, tmp_path):
        path = tmp_path / "c.json"
        populated_registry.save(path)
        loaded = ContractRegistry.load(path)
        jwt_endpoints = [c for c in loaded.get_api_contracts() if c.auth == "jwt"]
        assert len(jwt_endpoints) == 2

    def test_load_missing_file_returns_empty(self, tmp_path):
        loaded = ContractRegistry.load(tmp_path / "nope.json")
        assert len(loaded) == 0

    def test_load_invalid_json_returns_empty(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json {{{")
        loaded = ContractRegistry.load(bad)
        assert len(loaded) == 0

    def test_export_openapi(self, populated_registry, tmp_path):
        path = tmp_path / "openapi.json"
        populated_registry.export_openapi(path, title="Test API", version="9.9.9")
        data = json.loads(path.read_text())
        assert data["openapi"] == "3.1.0"
        assert data["info"]["title"] == "Test API"
        assert data["info"]["version"] == "9.9.9"
        assert "/users" in data["paths"]
        assert "User" in data["components"]["schemas"]
        assert "BearerAuth" in data["components"]["securitySchemes"]


# ---------------------------------------------------------------------------
# Contract extraction
# ---------------------------------------------------------------------------

class TestExtraction:
    def test_explicit_contracts_block(self):
        response = '''
Some code here...

```contracts
{
  "api": [
    {"method": "GET", "path": "/items", "auth": "jwt", "response_schema": {"type": "array"}},
    {"method": "POST", "path": "/items", "request_schema": {"name": "str"}, "auth": "none"}
  ],
  "models": [
    {"name": "Item", "fields": {"id": "int", "name": "str"}}
  ]
}
```
'''
        result = extract_contracts_from_response(response, "backend")
        assert len(result["api"]) == 2
        assert result["api"][0].auth == "jwt"
        assert result["api"][1].method == "POST"
        assert len(result["models"]) == 1
        assert result["models"][0].name == "Item"
        assert result["models"][0].fields == {"id": "int", "name": "str"}

    def test_fastapi_regex_fallback(self):
        response = '''
```file:app/main.py
from fastapi import FastAPI
app = FastAPI()

@app.get("/users")
def list_users():
    pass

@app.post("/users")
def create_user():
    pass

@app.delete("/users/{id}")
def delete_user(id: int):
    pass
```
'''
        result = extract_contracts_from_response(response, "backend")
        assert len(result["api"]) == 3
        methods = {c.method for c in result["api"]}
        assert methods == {"GET", "POST", "DELETE"}

    def test_pydantic_model_extraction(self):
        response = '''
class User(BaseModel):
    id: int
    email: str
    name: str
    created_at: datetime

class Item(BaseModel):
    id: int
    title: str
'''
        result = extract_contracts_from_response(response, "backend")
        assert len(result["models"]) == 2
        names = {m.name for m in result["models"]}
        assert names == {"User", "Item"}

    def test_explicit_block_takes_priority_over_regex(self):
        response = '''
@app.get("/ignored")
def ignored():
    pass

```contracts
{"api": [{"method": "GET", "path": "/real"}], "models": []}
```
'''
        result = extract_contracts_from_response(response)
        assert len(result["api"]) == 1
        assert result["api"][0].path == "/real"

    def test_malformed_json_falls_back_to_regex(self):
        response = '''
```contracts
{not valid json}
```
@app.get("/fallback")
def fb():
    pass
'''
        result = extract_contracts_from_response(response)
        assert len(result["api"]) == 1
        assert result["api"][0].path == "/fallback"

    def test_no_contracts_returns_empty(self):
        result = extract_contracts_from_response("just some text, no code")
        assert result == {"api": [], "models": [], "events": []}

    def test_express_route_extraction(self):
        response = '''
app.get("/api/users", (req, res) => {});
app.post("/api/users", (req, res) => {});
router.put("/api/users/:id", (req, res) => {});
'''
        result = extract_contracts_from_response(response, "backend")
        assert len(result["api"]) == 3

    def test_producer_agent_set(self):
        response = '@app.get("/x")\ndef x(): pass'
        result = extract_contracts_from_response(response, "my_agent")
        assert result["api"][0].producer_agent == "my_agent"


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestRegistryThreadSafety:
    def test_concurrent_registration(self, registry):
        def register_batch(prefix):
            for i in range(100):
                registry.register(ApiEndpointContract(
                    method="GET", path=f"/{prefix}/{i}",
                ))

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(register_batch, ["a", "b", "c", "d"]))

        assert len(registry.get_api_contracts()) == 400
