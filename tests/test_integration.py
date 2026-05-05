"""Integration tests — verify the full collaboration layer works end-to-end."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pytest

from src.collaboration import (
    ArtifactBus,
    ContractRegistry,
    CodeArtifact,
    DecisionArtifact,
    ReviewArtifact,
    BuildLogArtifact,
    ReworkRequestArtifact,
    ApiEndpointContract,
    DataModelContract,
    UIDataDependency,
    extract_contracts_from_response,
)
from src.scheduler import build_dependency_graph, ParallelScheduler


@dataclass
class BuildContext:
    bus: ArtifactBus = field(default_factory=ArtifactBus)
    registry: ContractRegistry = field(default_factory=ContractRegistry)
    decisions: dict = field(default_factory=dict)
    tasks: list = field(default_factory=list)
    aborted: bool = False
    task_prompts: dict = field(default_factory=dict)
    task_agents: dict = field(default_factory=dict)

    @property
    def files(self):
        return self.bus.export_files_list()

    @property
    def errors(self):
        return self.bus.get_errors()

    @property
    def review(self):
        return self.bus.get_review()


class TestBuildContextIntegration:
    """Verify BuildContext wires bus + registry correctly."""

    def test_empty_context(self):
        ctx = BuildContext()
        assert ctx.files == []
        assert ctx.errors == []
        assert ctx.review is None
        assert ctx.decisions == {}
        assert ctx.tasks == []
        assert ctx.aborted is False

    def test_files_property(self):
        ctx = BuildContext()
        ctx.bus.publish(CodeArtifact(path="a.py", content="1", producer_agent="x"))
        assert ctx.files == [("a.py", "1")]

    def test_errors_property(self):
        ctx = BuildContext()
        ctx.bus.publish(BuildLogArtifact(message="err", level="error", producer_agent="x"))
        assert ctx.errors == ["err"]

    def test_review_property(self):
        ctx = BuildContext()
        ctx.bus.publish(ReviewArtifact(
            target_path="", producer_agent="r", passed=True,
        ))
        assert ctx.review["passed"] is True

    def test_pm_prompt_fields(self):
        ctx = BuildContext()
        ctx.task_prompts["t1"] = "do the thing"
        ctx.task_agents["t1"] = "backend"
        assert ctx.task_prompts["t1"] == "do the thing"
        assert ctx.task_agents["t1"] == "backend"


class TestEndToEndPipeline:
    """Simulate a simplified build pipeline through the collaboration layer."""

    def test_full_pipeline_flow(self):
        bus = ArtifactBus()
        registry = ContractRegistry()

        # Step 1: Planner publishes decisions
        bus.publish(DecisionArtifact(
            key="stack", value={"lang": "python", "framework": "fastapi"},
            producer_agent="planner",
        ))
        assert bus.get_decisions()["stack"]["framework"] == "fastapi"

        # Step 2: Backend publishes code + contracts
        backend_response = '''
```file:app/main.py
from fastapi import FastAPI
app = FastAPI()

@app.get("/users")
def list_users():
    return []

@app.post("/users")
def create_user():
    return {"id": 1}
```

```contracts
{
  "api": [
    {"method": "GET", "path": "/users", "response_schema": {"type": "array"}, "auth": "none"},
    {"method": "POST", "path": "/users", "request_schema": {"name": "str"}, "auth": "none"}
  ],
  "models": [
    {"name": "User", "fields": {"id": "int", "name": "str"}}
  ]
}
```
'''
        bus.publish(CodeArtifact(
            path="app/main.py", content="from fastapi import ...",
            producer_agent="backend", task_id="t_backend",
        ))

        contracts = extract_contracts_from_response(backend_response, "backend")
        registry.register_many(contracts["api"])
        registry.register_many(contracts["models"])

        assert len(registry.get_api_contracts()) == 2
        assert len(registry.get_model_contracts()) == 1

        # Step 3: Frontend can see contracts
        prompt = registry.format_for_prompt()
        assert "GET /users" in prompt
        assert "POST /users" in prompt

        # Frontend publishes its code
        bus.publish(CodeArtifact(
            path="src/App.jsx", content="<App/>",
            producer_agent="frontend", task_id="t_frontend",
        ))

        # Step 4: Security gets full code
        all_code = bus.export_files_dict()
        assert "app/main.py" in all_code
        assert "src/App.jsx" in all_code

        # Security validation
        sec = registry.validate_security_coverage()
        assert not sec["passed"]  # POST /users has no auth

        # Step 5: Reviewer gets everything
        assert bus.code_count() == 2

        # Simulate reviewer finding an issue
        bus.publish(ReviewArtifact(
            target_path="app/main.py", producer_agent="reviewer",
            passed=False, issues=({"file": "app/main.py", "msg": "SQL injection"},),
        ))

        # Step 6: Rework — send back to backend
        bus.publish(ReworkRequestArtifact(
            target_path="app/main.py", original_agent="backend",
            issue="SQL injection", producer_agent="reviewer",
        ))
        bus.publish(CodeArtifact(
            path="app/main.py", content="from fastapi import ... # fixed",
            producer_agent="backend", version=2,
        ))

        assert bus.latest("app/main.py").version == 2
        assert "fixed" in bus.latest("app/main.py").content

    def test_contract_persistence_across_builds(self, tmp_path):
        """Simulate two builds — contracts from build 1 available in build 2."""
        contracts_file = tmp_path / "contracts.json"

        # Build 1
        reg1 = ContractRegistry()
        reg1.register(ApiEndpointContract(
            method="GET", path="/users", auth="jwt", producer_agent="backend",
        ))
        reg1.register(DataModelContract(
            name="User", fields={"id": "int"}, producer_agent="backend",
        ))
        reg1.save(contracts_file)

        # Build 2 (incremental)
        reg2 = ContractRegistry.load(contracts_file)
        assert len(reg2.get_api_contracts()) == 1
        assert reg2.get_api_contracts()[0].path == "/users"

        # New feature adds endpoint
        reg2.register(ApiEndpointContract(
            method="GET", path="/users/{id}", auth="jwt", producer_agent="backend",
        ))
        assert len(reg2.get_api_contracts()) == 2


class TestSchedulerWithBus:
    """Verify the scheduler works with the artifact bus in a realistic scenario."""

    def test_parallel_build_with_bus(self):
        bus = ArtifactBus()
        registry = ContractRegistry()

        tasks = [
            {"id": "t1", "agent": "coder"},
            {"id": "t2", "agent": "backend"},
            {"id": "t3", "agent": "ci"},
            {"id": "t4", "agent": "deploy"},
            {"id": "t5", "agent": "frontend"},
        ]
        graph = build_dependency_graph(tasks)

        def run_task(tid):
            task = next(t for t in tasks if t["id"] == tid)
            agent = task["agent"]
            # Simulate each agent writing files
            bus.publish(CodeArtifact(
                path=f"{agent}/output.py", content=f"# {agent}",
                producer_agent=agent, task_id=tid,
            ))
            # Backend registers contracts
            if agent == "backend":
                registry.register(ApiEndpointContract(
                    method="GET", path="/api", producer_agent="backend",
                ))

        failed = ParallelScheduler(max_workers=4).execute(graph, run_task)
        assert failed == []
        assert bus.code_count() == 5
        assert len(registry.get_api_contracts()) == 1

        # Verify all agents' output is in the bus
        for agent in ["coder", "backend", "ci", "deploy", "frontend"]:
            art = bus.latest(f"{agent}/output.py")
            assert art is not None
            assert art.producer_agent == agent
