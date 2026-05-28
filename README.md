# Forge

Forge is a local-first AI software builder. It turns a structured `.forge/spec.md`
file into a working codebase through a deterministic task graph, specialist model
routing, API contracts, verification, and policy-controlled file writes.

For teams comparing AI app builders: Forge is an inspectable, local-first
alternative to prompt-only generators. It is built around specs, agents, audit
logs, model routing, and a small API plane that can be run privately.

The current production-ready MVP focuses on:

- Forge Spec API primitives inside markdown specs
- local model support through Ollama or OpenAI-compatible providers
- role-based model routing for backend, frontend, tester, reviewer, and deploy tasks
- a REST control plane for builds, tasks, contracts, artifacts, models, and events
- deterministic validation before and after model generation
- optional dashboard and durable queued worker mode for the local REST API

## Status

Core architecture is implemented and test-green. This is a local-first MVP for
technical review and iteration; generated application quality still depends on
the configured model.

```bash
pytest -q
# expected: all tests pass
```

## Requirements

- Python 3.10+
- `pip`
- Optional: Ollama for local-model testing
- Optional: OpenAI/Anthropic/Together credentials for cloud fallback

## Install From Source

```bash
git clone https://github.com/nebullii/forge
cd forge
python -m pip install -e .
```

For test/development work:

```bash
python -m pip install -e ".[dev]"
pytest -q
```

## Local Model Setup

Start Ollama:

```bash
ollama serve
```

Pull at least one modern local model:

```bash
ollama pull qwen3:latest
```

Recommended options if your machine can handle them:

```bash
ollama pull gpt-oss:20b
ollama pull gemma3:12b
ollama pull llama3.1:8b
```

Run Forge setup or create config manually:

```bash
forge setup
```

Example `~/.forge/config.yaml`:

```yaml
providers:
  - name: ollama
    base_url: http://localhost:11434
    model: qwen3:latest
    profiles:
      primary:
        model: qwen3:latest
        capabilities: [code, reasoning, local]
      coder:
        model: qwen3:latest
        capabilities: [code, reasoning, local]
      reviewer:
        model: llama3.1:8b
        capabilities: [review, reasoning, local]

model_routing:
  planner: ollama:primary
  builder: ollama:coder
  backend: ollama:coder
  frontend: ollama:coder
  tester: ollama:coder
  test: ollama:coder
  ci: ollama:coder
  deploy: ollama:coder
  reviewer: ollama:reviewer
  security: ollama:reviewer
```

Check readiness:

```bash
forge doctor -p ollama
```

## Quick Test: Spec API Without Model Calls

Run the built-in smoke evals. These validate the Spec API parser and task graph
compiler without calling a model.

```bash
forge eval smoke --scenario crm-basic
forge eval smoke --scenario api-only-crud
forge eval smoke --scenario frontend-contracts
```

Artifacts are written to:

```text
.forge/evals/
```

## Build A Real Test App

Create a project:

```bash
forge new freelancer-crm -t web-app
cd freelancer-crm
```

Replace `.forge/spec.md` with:

```markdown
# Project: Freelancer CRM

.project
  spec_api_version: 0.1
  type: web_app
  stack: react_fastapi_sqlite

.auth.email_password
  sessions: jwt
  roles: user

.db.model Client
  fields:
    name: string required
    email: email required
    status: enum[lead,active,inactive]

.api.resource clients
  model: Client
  actions: list, create, update, delete
  auth: required

.ui.table client_list
  source: GET /api/clients
  columns: name, email, status

.ui.form create_client
  submit: POST /api/clients
  fields: name, email, status

.test.case client_crud
  covers: clients
```

Validate and compile the spec:

```bash
forge spec validate
forge spec compile --output .forge/compiled-spec.json
```

Expected outputs:

- validation succeeds
- `.forge/compiled-spec.json` exists
- `.forge/task-graph.json` is created during `forge build`

Build with a local model:

```bash
forge build -p ollama -v
```

Run the generated project:

```bash
forge dev
```

Export contracts:

```bash
forge contracts export --format openapi
```

## REST Control Plane Test

From a Forge project directory:

```bash
forge serve --port 4123
```

In another terminal:

```bash
curl -s http://127.0.0.1:4123/api/health
curl -s http://127.0.0.1:4123/api/tasks
curl -s http://127.0.0.1:4123/api/models/health
curl -s -X POST http://127.0.0.1:4123/api/builds \
  -H 'Content-Type: application/json' \
  -d '{"provider":"ollama","no_review":true}'
curl -s http://127.0.0.1:4123/api/builds
curl -s http://127.0.0.1:4123/api/events
```

Event stream:

```bash
curl -N http://127.0.0.1:4123/api/events/stream?once=true
```

Run a specific task:

```bash
curl -s -X POST http://127.0.0.1:4123/api/tasks/backend.clients/run \
  -H 'Content-Type: application/json' \
  -d '{"provider":"ollama","no_review":true}'
```

Retry a failed task:

```bash
curl -s -X POST http://127.0.0.1:4123/api/tasks/backend.clients/retry \
  -H 'Content-Type: application/json' \
  -d '{"provider":"ollama","no_review":true}'
```

## Positioning

Use this when explaining Forge to teams evaluating AI software builders:

> Forge is a local-first agentic software builder. A developer writes a spec,
> Forge compiles it into a task graph, then specialist agents generate, verify,
> and audit the project. It supports private Ollama models, OpenAI-compatible
> providers, guarded file writes, resumable state, and a REST/API plane for
> builds, tasks, contracts, artifacts, models, and events.

Forge is strongest when the buyer cares about:

- private or local model execution
- auditable agent behavior
- spec-driven project generation
- enterprise controls around file writes and model routing
- API access instead of a closed app-only workflow

## Forge Spec API

Spec API primitives are structured directives inside `.forge/spec.md`.

Supported MVP primitives:

- `.project`
- `.auth.email_password`
- `.db.model`
- `.api.resource`
- `.ui.page`
- `.ui.table`
- `.ui.form`
- `.test.case`
- `.deploy.target`

Rules:

- `spec_api_version` defaults to `0.1`.
- `.api.resource actions` must use supported actions: `list`, `get`, `create`, `update`, `delete`.
- `.ui.table source` must look like `GET /api/resource`.
- `.ui.form submit` must use a write method like `POST /api/resource`.
- `.db.model` fields use supported types like `string`, `email`, `integer`, `boolean`, `money`, `json`, or `enum[...]`.

More detail: [docs/spec-api.md](docs/spec-api.md)

## How Forge Works

```text
.forge/spec.md
  -> Spec API parser
  -> deterministic task graph
  -> specialist model routing
  -> structured agent output contract
  -> artifact bus and contract registry
  -> firewall-checked writes
  -> review and deterministic verification
  -> build state, events, audit logs
```

Spec API builds skip the broad LLM planning step. Forge compiles primitives into
tasks locally, then routes each task to the configured role model.

## Structured Agent Output

Spec API tasks require models to return JSON:

```json
{
  "status": "success",
  "files": [
    {
      "path": "relative/path",
      "content": "complete file contents"
    }
  ],
  "contracts": {
    "api": [],
    "models": [],
    "events": []
  },
  "uses_contracts": [],
  "notes": [],
  "requires": []
}
```

Backend tasks must include at least one API, model, or event contract.

## Important Files

Inside generated projects:

```text
.forge/spec.md              Product spec and Spec API primitives
.forge/rules.md             Build rules
.forge/policy.yaml          Policy and approval settings
.forge/task-graph.json      Compiled Spec API task graph
.forge/build-state.yaml     Resumable build state
.forge/contracts.json       Persisted contracts
.forge/openapi.json         Optional OpenAPI export
.forge/build_audit.jsonl    Build audit log
.forge/control_audit.jsonl  REST control-plane audit log
.forge/verification.json    Verification report
```

## CLI Reference

```bash
forge new <name> [-t template]
forge templates
forge setup
forge doctor [-p provider]

forge spec validate
forge spec compile [-o output.json]

forge build [-p provider] [--model model] [-v]
forge build --feature "add feature"

forge dev
forge contracts export --format openapi

forge serve --port 4123
forge serve --port 4123 --ui
forge worker --once
forge eval smoke --scenario crm-basic
```

## Troubleshooting

### `forge doctor -p ollama` fails

Check that Ollama is running:

```bash
ollama serve
ollama list
```

If no model is installed:

```bash
ollama pull qwen3:latest
```

### Spec validation fails

Run:

```bash
forge spec validate
```

Common issues:

- unsupported primitive name
- `.api.resource` references a model that does not exist
- invalid endpoint format, such as `clients` instead of `GET /api/clients`
- unsupported field type
- unsupported `spec_api_version`

### Model returned invalid JSON

Spec API tasks require structured JSON. If a model returns markdown fences or
prose, use a stronger code model or lower-temperature local model. For Ollama,
prefer `qwen3:latest`, `gpt-oss:20b`, `gemma3:12b`, or another current
code-capable model available on your machine.

### Task is blocked by dependencies

REST task execution respects dependencies. For example, frontend tasks wait for
backend tasks because they need API contracts.

Check tasks:

```bash
curl -s http://127.0.0.1:4123/api/tasks
```

### Contract mismatch

Export and inspect contracts:

```bash
forge contracts export --format openapi
cat .forge/openapi.json
```

Frontend calls must match backend contracts exactly.

## Development

Run all tests:

```bash
pytest -q
```

Run focused tests:

```bash
pytest tests/test_specapi.py tests/test_orchestrator.py tests/test_agent_contracts.py -q
```

## Known Limits

- Spec API versions `0.1` and `0.2` are accepted; `0.2` is currently forward-compatible with `0.1`.
- Local model quality still matters.
- Non-Spec API builds still support the legacy planner-first path.
- REST jobs run in-process by default; pass `{"queue": true}` to the REST API and run `forge worker` for durable local worker execution.
- SSE is available for event streaming, and `forge serve --ui` serves a local dashboard.

## Technical Review Brief

For a concise architecture and readiness summary, see
[docs/review-brief.md](docs/review-brief.md).

## License

MIT
