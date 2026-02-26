# A2A Protocol Reference

A2A (Agent-to-Agent) is Google's open standard for inter-agent communication.
Forge implements A2A in `src/a2a/` using Pydantic types + FastAPI + httpx.

## Why A2A

- Standard message format so any A2A-compatible agent can call Forge agents
- Same code path works in-process (no HTTP) and over-the-network (HTTP)
- Enables distributed builds: each agent as an independent service

---

## Core Types (`src/a2a/types.py`)

### Task — sent TO an agent
```python
Task(
    id: str,                    # auto-generated UUID hex
    message: Message,           # the actual request
    context: dict | None,       # structured context from previous agents
    metadata: dict | None,      # arbitrary metadata
)
```

### Message — the request body
```python
Message(
    role: "user" | "agent",
    parts: list[TextPart | FilePart]
)
TextPart(type="text", text: str)
FilePart(type="file", path: str, content: str)
```

### TaskResult — returned FROM an agent
```python
TaskResult(
    id: str,                    # matches Task.id
    status: TaskStatus,         # submitted | working | completed | failed
    artifacts: list[Artifact],  # outputs
    error: str | None,
)

# Convenience methods:
result.success              # bool: status == completed
result.get_text()           # str: concat all TextPart text
result.get_files()          # list[tuple[str,str]]: all (path, content) pairs
result.get_data()           # dict | None: first Artifact.data
```

### Artifact — typed output
```python
Artifact(
    type: str,              # "text", "files", "plan", "review", "audit"
    name: str | None,       # e.g. "backend_files", "build_plan"
    parts: list[Part],      # TextPart or FilePart list
    data: dict | None,      # structured data (e.g. plan dict, review dict)
)
```

### AgentCard — agent discovery
```python
AgentCard(
    name: str,
    description: str,
    url: str,               # e.g. "http://localhost:8102"
    version: str,
    capabilities: dict,     # {streaming: bool, pushNotifications: bool}
    skills: list[AgentSkill],
)
AgentSkill(id, name, description, input_modes, output_modes)
```

---

## Transport: In-Process vs HTTP

### In-process (default in `forge build --adk`)
```python
client = A2AClient.for_agent(my_agent_instance)
result = client.send_task(task)
# → calls my_agent.handle_a2a_task(task) directly
```
Zero overhead. Best for single-machine builds.

### HTTP (distributed mode)
```python
client = A2AClient.for_url("http://localhost:8102")
result = client.send_task(task)
# → POST http://localhost:8102/tasks/send
# → deserializes TaskResult from JSON response
```
Requires agent server to be running (`forge agents start`).

---

## Server API (`src/a2a/server.py`)

Each agent server exposes:

```
GET  /.well-known/agent.json
  → AgentCard JSON (agent name, description, skills, URL)

POST /tasks/send
  Body: Task (JSON)
  Response: TaskResult (JSON)

GET  /health
  → {"status": "ok", "agent": "backend"}
```

### Starting a single agent server
```python
# From Python
agent = BackendAgent(provider, project_root)
agent.serve(port=8102)   # blocks

# From CLI (all agents)
forge agents start
```

### Testing with curl
```bash
# Check agent identity
curl http://localhost:8101/.well-known/agent.json

# Send a task
curl -X POST http://localhost:8102/tasks/send \
  -H 'Content-Type: application/json' \
  -d '{
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "Generate a FastAPI CRUD API for a todo app"}]
    },
    "context": {
      "spec": "A simple todo list API",
      "rules": "Use SQLite, FastAPI, Pydantic"
    }
  }'
```

---

## Message Flow in ADK Mode

```
ForgeADKOrchestrator.run(spec, rules)
  │
  ├── 1. Task(message=Message("Analyze spec..."), context={})
  │         → PlannerAgent.handle_a2a_task()
  │         ← TaskResult(artifacts=[Artifact(type="plan", data={decisions, tasks})])
  │
  ├── 2. Task(message=Message("Generate backend..."),
  │          context={spec, rules, decisions})
  │         → BackendAgent.handle_a2a_task()
  │         ← TaskResult(artifacts=[text_artifact, files_artifact])
  │
  ├── 3. Task(message=Message("Generate frontend..."),
  │          context={spec, rules, decisions, backend_files=[...]})
  │         → FrontendAgent.handle_a2a_task()
  │         ← TaskResult(artifacts=[text_artifact, files_artifact])
  │
  ├── 4. Task(message=Message("Security audit..."),
  │          context={files: {path: content}})
  │         → SecurityAgent.handle_a2a_task()
  │         ← TaskResult(artifacts=[audit_text, patched_files?])
  │
  ├── 5. Task(message=Message("Generate CI/CD..."),
  │          context={decisions, spec})
  │         → CIAgent.handle_a2a_task()
  │         ← TaskResult(artifacts=[text, files])
  │
  ├── 6. Task(message=Message("Generate deploy config..."),
  │          context={decisions, spec, deploy_template})
  │         → DeployAgent.handle_a2a_task()
  │         ← TaskResult(artifacts=[text, files])
  │
  └── 7. Task(message=Message("Review all code..."),
             context={files: {all generated files}, spec, rules})
           → ReviewerAgent.handle_a2a_task()
           ← TaskResult(artifacts=[Artifact(type="review", data={passed, issues})])
```

---

## Implementing handle_a2a_task

`BaseAgent` provides a default implementation that:
1. Extracts text from `task.message.parts`
2. Appends context as formatted prompt sections
3. Calls `self.invoke(prompt)`
4. Extracts file blocks from response
5. Returns `TaskResult` with text + file artifacts

Override for specialized behavior:
```python
def handle_a2a_task(self, task) -> TaskResult:
    context = task.context or {}
    spec = context.get("spec", "")

    # Extract prompt
    prompt_text = "\n".join(
        p.text for p in task.message.parts if hasattr(p, "text")
    )

    response = self.my_specialized_method(spec, ...)
    files = self.extract_files(response)

    from ..a2a.types import TaskResult, TaskStatus, Artifact, TextPart, FilePart
    return TaskResult(
        id=task.id,
        status=TaskStatus.completed,
        artifacts=[
            Artifact(type="text", parts=[TextPart(text=response)]),
            Artifact(type="files", parts=[FilePart(path=p, content=c) for p, c in files]),
        ]
    )
```

---

## Error Handling

If `handle_a2a_task` raises, the default BaseAgent catches it:
```python
TaskResult(id=task.id, status=TaskStatus.failed, error=str(e))
```

The orchestrator checks `result.success` and logs errors to `result["errors"]`.
Non-critical failures (e.g. CI/CD generation) don't abort the build.
