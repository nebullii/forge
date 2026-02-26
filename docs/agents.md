# Forge Agents Reference

Each agent is a Python class extending `BaseAgent`. All agents:
- Have a `role` (system prompt) and `name`
- Can call `invoke(prompt)` to hit the LLM
- Support A2A protocol via `handle_a2a_task(task) → TaskResult`
- Can be served as HTTP via `agent.serve(port)`

---

## Classic Pipeline Agents

### PlannerAgent
**File:** `src/agents/planner.py`
**Port (distributed):** 8101

**Skill:** Analyzes spec + rules, produces a structured YAML build plan.

**Key methods:**
- `analyze_and_plan(spec, rules, existing_files) → dict` — full build plan
- `plan_incremental(spec, rules, feature, existing_files) → dict` — feature add
- `_parse_plan(response) → dict` — YAML parser with fallback handling

**Output format:**
```yaml
decisions:
  stack: {language, framework, database, styling}
  architecture: "how components connect"
  reasoning: "why these choices"
tasks:
  - id: task_01
    name: "Set up project"
    description: "..."
    agent: coder
    files: [requirements.txt, main.py]
```

**A2A behavior:** Extracts spec from `task.message`, runs `analyze_and_plan()`,
returns plan dict in `Artifact.data`.

---

### CoderAgent
**File:** `src/agents/coder.py`
**Port (distributed):** N/A (used internally by orchestrator, not a standalone A2A agent)

**Skill:** Generates complete file contents for a given build task.

**Key methods:**
- `generate_files(task, spec, rules, decisions, project_context) → str`
- `fix_file(filepath, current_content, issue, spec, rules) → str`

**System prompt emphasis:** Complete files only, no placeholders, all imports included.
Uses ````file:path/to/file.ext` format.

---

### ReviewerAgent
**File:** `src/agents/reviewer.py`
**Port (distributed):** 8107

**Skill:** Cross-cutting code review — correctness, consistency, API contracts, security.

**Key methods:**
- `review_files(files_written: dict[str, str], spec, rules) → dict`
- `_parse_review(response) → dict`

**Output format:**
```yaml
passed: true/false
issues:
  - file: "path/to/file"
    severity: error|warning
    message: "description"
```

**A2A behavior:** Reads `context.files` dict, runs `review_files()`, returns review
dict in `Artifact.data`.

---

## ADK Specialized Agents

### BackendAgent
**File:** `src/agents/backend.py`
**Port (distributed):** 8102

**Skill:** FastAPI routes, SQLAlchemy models, Pydantic schemas, service layer.

**System prompt focus:**
- FastAPI + SQLAlchemy + Pydantic stack
- Business logic in service functions (not route handlers)
- CORS middleware when frontend exists
- Environment variables for secrets (never hardcode)
- SQLite default unless spec says otherwise

**Key method:** `generate_backend(spec, rules, decisions, project_context) → str`

**A2A context expected:**
```python
{
  "spec": str,
  "rules": str,
  "decisions": dict  # from PlannerAgent
}
```

**Produces:** Backend source files (routes, models, schemas, services, main.py, config)

---

### FrontendAgent
**File:** `src/agents/frontend.py`
**Port (distributed):** 8103

**Skill:** React/TypeScript UI — components, pages, routing, API integration.

**System prompt focus:**
- React + TypeScript + Tailwind CSS
- React Router for routing
- React Query / SWR for server state
- Must match backend API contracts exactly
- Handle loading, error, and empty states
- `VITE_API_URL` env var for API base URL

**Key method:** `generate_frontend(spec, rules, decisions, backend_files, project_context) → str`

**A2A context expected:**
```python
{
  "spec": str,
  "rules": str,
  "decisions": dict,
  "backend_files": [str]  # list of backend file paths (for contract awareness)
}
```

**Produces:** package.json, vite config, tsconfig, App.tsx, pages, components, hooks, API client

---

### SecurityAgent
**File:** `src/agents/security_agent.py`
**Port (distributed):** 8104

**Skill:** OWASP Top 10 audit, secret detection, injection flaw analysis.

**System prompt focus:**
- OWASP Top 10 (injection, auth, XSS, IDOR, misconfig, etc.)
- Hardcoded secrets, API keys, passwords
- SQL/NoSQL injection
- Missing auth/authz checks
- Reports issues AND provides fixed files

**Key method:** `audit_files(files: dict[str, str], spec, rules) → dict`

**Output format:**
```python
{
  "passed": bool,
  "issues": [{"file", "severity", "message", "fix"}],
  "patched_files": [(path, content)]  # fixed versions
}
```

**A2A context expected:**
```python
{
  "files": {"path": "content", ...},  # all generated files
  "spec": str,
  "rules": str
}
```

**Severity levels:** `critical`, `high`, `medium`, `low`

---

### CIAgent
**File:** `src/agents/ci_cd.py`
**Port (distributed):** 8105

**Skill:** GitHub Actions workflows, Dockerfile, docker-compose.

**System prompt focus:**
- Multi-stage Dockerfile (minimize image size)
- GitHub Actions: lint + test on PR, build+deploy on main
- Pin dependency versions for reproducibility
- Use GitHub Secrets for credentials

**Key method:** `generate_ci(spec, decisions, rules) → str`

**A2A context expected:**
```python
{
  "spec": str,
  "decisions": dict,
  "rules": str
}
```

**Produces:**
- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml`
- `Dockerfile`
- `.dockerignore`
- `docker-compose.yml`

---

### DeployAgent
**File:** `src/agents/deploy.py`
**Port (distributed):** 8106

**Skill:** Cloud deployment configs for Railway, Render, Vercel, Fly.io.

**System prompt focus:**
- Default to Railway (free tier, easiest)
- Reads `.forge/deploy.md` template to detect target platform
- Always include `.env.example` and `DEPLOY.md`
- Health check endpoint required

**Key method:** `generate_deploy(spec, decisions, deploy_template, rules) → str`

**A2A context expected:**
```python
{
  "spec": str,
  "decisions": dict,
  "deploy_template": str,  # contents of .forge/deploy.md
  "rules": str
}
```

**Platform detection:** Scans `deploy_template` for keywords (railway, render, vercel, fly, heroku).

**Produces:** Platform config file + `.env.example` + `DEPLOY.md`

---

## Adding a New Agent

1. Create `src/agents/my_agent.py`:
```python
from .base import BaseAgent

class MyAgent(BaseAgent):
    name = "my_agent"
    skill_description = "One-line description of what this agent does."
    role = "You are Forge MyAgent, ..."

    def my_method(self, ...) -> str:
        return self.invoke(prompt)

    def handle_a2a_task(self, task):
        # optional: custom A2A handling
        # default BaseAgent.handle_a2a_task() works for simple cases
        ...
```

2. Export from `src/agents/__init__.py`

3. Register in `BuildOrchestrator._init_adk_agents()` in `src/orchestrator.py`

4. Add to `ForgeADKOrchestrator.AGENT_PORTS` and call in `run()` in `src/adk/orchestrator_agent.py`

5. Add to `AGENT_PORTS` dict in `src/cli.py` (`_agents_start`)
