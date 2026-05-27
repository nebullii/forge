# Forge Spec API

Forge Spec API is a small structured layer inside `.forge/spec.md`. It lets Forge parse product intent into typed tasks before local models generate code.

## Example

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

## Commands

```bash
forge spec validate
forge spec compile
forge build --provider ollama
forge serve --port 4123
forge eval smoke --scenario crm-basic
```

## Supported Primitives

- `.project`: project metadata. `spec_api_version` defaults to `0.1`.
- `.auth.email_password`: email/password auth requirements.
- `.db.model Name`: fields for a data model.
- `.api.resource name`: CRUD API for a model.
- `.ui.page name`: frontend page.
- `.ui.table name`: table bound to an API source like `GET /api/clients`.
- `.ui.form name`: form bound to a write endpoint like `POST /api/clients`.
- `.test.case name`: expected behavior to test.
- `.deploy.target name`: deployment config target.

## Local Model Config

Use role-specific local models where possible:

```yaml
providers:
  - name: ollama
    base_url: http://localhost:11434
    model: qwen2.5-coder:14b
    profiles:
      backend:
        model: qwen2.5-coder:14b
        capabilities: [code, reasoning, local]
      frontend:
        model: deepseek-coder-v2:16b
        capabilities: [code, reasoning, local]
      reviewer:
        model: llama3.1:8b
        capabilities: [review, reasoning, local]

model_routing:
  backend: ollama:backend
  frontend: ollama:frontend
  reviewer: ollama:reviewer
  tester: ollama:backend
```

## REST Control Plane

Start it:

```bash
forge serve --port 4123
```

Useful endpoints:

- `POST /api/spec/validate`
- `POST /api/spec/compile`
- `POST /api/builds`
- `GET /api/builds`
- `GET /api/tasks`
- `POST /api/tasks/{task_id}/run`
- `POST /api/tasks/{task_id}/retry`
- `GET /api/events`
- `GET /api/events/stream`
- `GET /api/contracts`
- `GET /api/artifacts`
- `GET /api/audit`
- `POST /api/models/route`
- `GET /api/models/health`

## Output Contract

Spec API tasks require models to return structured JSON:

```json
{
  "status": "success",
  "files": [
    {"path": "relative/path", "content": "complete file contents"}
  ],
  "contracts": {"api": [], "models": [], "events": []},
  "uses_contracts": [],
  "notes": [],
  "requires": []
}
```

Backend tasks must include at least one API, model, or event contract.

## Known Limits

- Spec API version `0.1` is the only supported version.
- The local model must still be capable enough to generate valid code.
- Streaming events are Server-Sent Events; distributed workers are not implemented.
- Non-Spec API builds still use the legacy planner-first path.
