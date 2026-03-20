# Forge

[![CI](https://github.com/nebullii/forge/actions/workflows/ci.yml/badge.svg)](https://github.com/nebullii/forge/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Describe your idea. AI builds it.**

Forge is an open-source CLI that turns a markdown spec into a working codebase using a
pipeline of specialized LLM agents. No prompt engineering, no copy-pasting — just
`forge build`.

```
forge new my-app -t web-app
# Edit .forge/spec.md with your idea
forge build
```

---

## Contents

- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [System Design](#system-design)
- [Build Modes](#build-modes)
- [Agent Reference](#agent-reference)
- [Security Model](#security-model)
- [Templates](#templates)
- [CLI Reference](#cli-reference)
- [Configuration](#configuration)
- [Installation](#installation)
- [Contributing](#contributing)

---

## How It Works

**1. Write a spec.** Create a plain markdown file describing what you want to build.

```markdown
# Project: Invoice Tracker

## What
A web app for freelancers to track invoices and payments.

## Features
- Create and manage client invoices
- Mark invoices as paid/unpaid
- Dashboard with outstanding balance summary
- PDF export

## Users
Solo freelancers, small agencies
```

**2. Run the build.** Forge analyzes the spec, chooses the right technology stack,
breaks the project into tasks, and executes each task with a specialized agent.

```bash
forge build
```

**3. Get working code.** Every file is written through a security firewall, build
state is saved after each task, and a reviewer validates the output before finishing.

```
Phase 1: Planning...
   Plan: 6 tasks
     - Set up Rails project with PostgreSQL
     - Invoice model and database migrations
     - Client management (CRUD)
     - Invoice creation and status tracking
     - Dashboard with balance summary
     - PDF export with Prawn

Phase 2: Building...
   [1/6] Set up Rails project with PostgreSQL
      + Gemfile
      + config/database.yml
      + config/routes.rb
   [2/6] Invoice model and database migrations
      + db/migrate/001_create_invoices.rb
      + app/models/invoice.rb
   ...

Phase 3: Reviewing...
   Review passed.
```

---

## Quick Start

```bash
# Install from source
git clone https://github.com/nebullii/forge
cd forge
pip install -e ".[build,adk]"

# Set your LLM provider key
export ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY, TOGETHER_API_KEY, etc.

# Create a project from a template
forge new my-app -t web-app
cd my-app

# Edit the spec
$EDITOR .forge/spec.md

# Build
forge build

# Run locally
forge dev
```

---

## System Design

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  User                                                           │
│    forge build                                                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│  CLI  (src/cli.py)                                              │
│    Reads .forge/spec.md + .forge/rules.md                       │
│    Scans for suspicious patterns                                │
│    Delegates to BuildOrchestrator                               │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│  BuildOrchestrator  (src/orchestrator.py)                       │
│    Manages build phases, task state, and file writes            │
│    Enforces AgenticFirewall on every write                      │
│    Persists state to .forge/build-state.yaml after each task    │
│                                                                 │
│    classic mode              ADK mode (--adk)                   │
│    ────────────              ─────────────────                  │
│    PlannerAgent              ForgeADKOrchestrator               │
│    ProjectManagerAgent       (Google ADK LlmAgent)              │
│    CoderAgent × N tasks      7 specialized agents               │
│    ReviewerAgent             via A2A protocol                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
  Provider Layer    Agent Layer      State Layer
  (src/providers/)  (src/agents/)    (src/state.py)
  Anthropic         BaseAgent        BuildState
  OpenAI-compat     8 agents         TaskState
  Ollama            A2A hooks        YAML persistence
```

### Classic Mode Pipeline

Sequential three-phase pipeline. Fast, simple, works with any provider.

```
.forge/spec.md
      │
      ▼
┌─────────────────┐
│  PlannerAgent   │  Analyzes spec → chooses stack → ordered task list
└────────┬────────┘
         │  {decisions, tasks[]}
         ▼
┌─────────────────────┐
│ ProjectManagerAgent │  Assigns each task to the right specialized agent
│                     │  Generates a self-contained prompt per task
└────────┬────────────┘
         │  tasks[].agent + tasks[].prompt
         ▼
┌──────────────────────────────────────────┐
│  Task Executor                           │
│                                          │
│  for each task:                          │
│    agent = route(task.agent)             │
│    response = agent.invoke(task.prompt)  │
│    files = extract_files(response)       │
│    for each file:                        │
│      if firewall.allow(path, content):   │
│        write to disk                     │
│    save state                            │
└────────┬─────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  ReviewerAgent  │  Validates all files, auto-fixes errors
└─────────────────┘
```

### ADK Mode Pipeline

Seven specialized agents coordinated by a Google ADK LlmAgent orchestrator.
Independent agents run in parallel via a thread pool.

```
.forge/spec.md
      │
      ▼
┌────────────────────────────────────────────────────────────────┐
│  ForgeADKOrchestrator  (Google ADK LlmAgent)                   │
│                                                                │
│  The orchestrator is an LLM that decides which tools to call.  │
│  Each tool is an A2A call to a specialized agent.              │
└──────────┬─────────────────────────────────────────────────────┘
           │
           │  Step 1 [sequential]
           ▼
    ┌──────────────┐
    │ PlannerAgent │  spec → task plan + tech stack decisions
    └──────┬───────┘
           │
           │  Step 2 [sequential]
           ▼
    ┌─────────────────────┐
    │ ProjectManagerAgent │  plan → per-task agent assignments + prompts
    └──────┬──────────────┘
           │
           │  Step 3 [parallel — ThreadPoolExecutor]
           ├──────────────────────┬───────────────────┐
           ▼                      ▼                   ▼
    ┌─────────────┐      ┌──────────────┐    ┌──────────────┐
    │ BackendAgent│      │   CIAgent    │    │  DeployAgent │
    │ API, DB,    │      │ CI workflows,│    │ Railway /    │
    │ services    │      │ Dockerfile   │    │ Render /     │
    └──────┬──────┘      └──────────────┘    │ Vercel       │
           │                                 └──────────────┘
           │  Step 4 [sequential — needs backend API contracts]
           ▼
    ┌───────────────┐
    │ FrontendAgent │  React/Svelte/Vue UI matching backend endpoints
    └──────┬────────┘
           │
           │  Step 5 [sequential — audits all code]
           ▼
    ┌───────────────┐
    │ SecurityAgent │  OWASP audit, secret detection, patch generation
    └──────┬────────┘
           │
           │  Step 6 [sequential — reviews everything]
           ▼
    ┌───────────────┐
    │ ReviewerAgent │  Cross-file correctness, contract validation
    └───────────────┘
```

**Why this ordering is parallel-safe:**
Backend, CI, and Deploy all depend only on the planner's decisions. They don't read
each other's output, so they can safely run concurrently. Frontend needs the backend's
API contracts. Security audits the application code. Reviewer sees everything last.

### A2A Protocol

In ADK mode, the orchestrator talks to each agent using Google's
[Agent-to-Agent (A2A)](https://google.github.io/A2A/) open protocol.

```
Orchestrator
    │
    │  A2AClient.send_task(Task)
    ▼
Agent
    │
    │  handle_a2a_task(task) → TaskResult
    │
    ├── Task.message.parts     — prompt text
    ├── Task.context           — decisions, spec, backend files, etc.
    │
    └── TaskResult.artifacts
          ├── type="text"      — raw LLM response
          └── type="files"     — generated (path, content) pairs
```

By default, all agents run in-process — no network overhead, no server management.
Run `forge agents start` to expose each agent as a real HTTP server on its own port
(useful for distributed builds or debugging individual agents).

### Layer Map

```
src/
  cli.py                    — Entry point. All forge commands.
  orchestrator.py           — Build pipeline coordination.
  config.py                 — Provider config (~/.forge/config.yaml).
  state.py                  — Resumable build state (schema-versioned YAML).
  context.py                — Token-budgeted project context assembly.

  providers/
    base.py                 — BaseProvider ABC + exponential backoff retry.
    anthropic.py            — Anthropic Claude.
    openai_compat.py        — OpenAI / Together / Groq / any OpenAI-compatible.
    ollama.py               — Local Ollama models.

  agents/
    base.py                 — BaseAgent: invoke, extract_files, write_files, A2A hooks.
    planner.py              — Spec → task plan. Framework-agnostic stack selection.
    project_manager.py      — Plan → per-task agent assignments and prompts.
    coder.py                — General-purpose file generation (classic mode fallback).
    reviewer.py             — Code validation, severity classification, auto-fix.
    backend.py              — API routes, DB models, service layer.
    frontend.py             — React/Svelte/Vue components, routing, API integration.
    security_agent.py       — OWASP Top 10 audit, secret detection, patch generation.
    ci_cd.py                — GitHub Actions, Dockerfile, docker-compose.
    deploy.py               — Railway / Render / Vercel / Fly.io configs.

  a2a/
    types.py                — Pydantic models: Task, TaskResult, Artifact, AgentCard.
    client.py               — A2AClient: in-process or HTTP transport.
    server.py               — FastAPI A2A server factory (per agent).

  adk/
    llm_bridge.py           — Wraps BaseProvider as Google ADK BaseLlm.
    agent_runner.py         — ADKAgentRunner: bridges LlmAgent ↔ A2A protocol.
    orchestrator_agent.py   — Root ADK LlmAgent + tool routing.
    tools.py                — Tool functions + BuildArtifacts shared state.

  security/
    firewall.py             — AgenticFirewall: policy enforcement + audit log.
```

---

## Build Modes

### Classic Mode

```bash
forge build
```

Three-phase pipeline. Suitable for most projects. Works with any LLM provider including
local Ollama models. Generates one agent's output at a time, sequentially.

**When to use:** Standard projects, limited API budget, local models, or when you want
predictable sequential output.

### ADK Mode

```bash
forge build --adk
```

Seven specialized agents coordinated by a Google ADK orchestrator. Backend, CI, and
Deploy run in parallel. Each agent has a focused system prompt for its domain. Requires
the `adk` extras package.

**When to use:** Complex projects with distinct frontend/backend/infra concerns, when
build speed matters, or when you want domain-specialized code generation.

### Incremental Mode

```bash
forge build --feature "add user authentication with JWT"
forge build --feature "add dark mode toggle to the settings page"
```

Plans only the tasks needed for the new feature. Reads the existing project files as
context so the new code integrates correctly with what's already there.

---

## Agent Reference

### PlannerAgent

Analyzes the spec and produces a structured build plan.

- Selects the technology stack based on the project type — no hardcoded defaults
- Chooses between Rails, Django, FastAPI, Go, Phoenix, HTMX, React, SvelteKit, etc.
- Breaks the project into 3-8 focused tasks ordered by dependency
- Outputs YAML: `decisions` (stack, architecture, reasoning) + `tasks[]`

**Stack selection logic:**

| Project type | Likely stack |
|---|---|
| Full-stack web app (CRUD, admin, forms) | Rails, Django, Laravel |
| Real-time features (chat, live updates) | Phoenix (Elixir) |
| Complex interactive SPA | React + Vite, SvelteKit |
| Simple web app, light interactivity | HTMX + FastAPI/Flask |
| API-only backend | FastAPI, Go (Gin/Chi), Rust (Axum) |
| CLI tool | Python (Click/Typer), Go (cobra) |
| Data pipeline or ML | Python + Pandas/SQLAlchemy |
| Static site or docs | Plain HTML, 11ty, Hugo |

### ProjectManagerAgent

Sits between the Planner and the executor. Takes the raw task list and enriches each
task with:

- `agent` — which specialized agent should execute this task
- `prompt` — a self-contained, context-rich prompt for that agent including stack
  details, API contracts from upstream tasks, and exact file targets
- `contracts` — the API interfaces this task exposes (consumed by dependent tasks)

**Agent routing:**

| Task type | Assigned agent |
|---|---|
| Project setup, config files, utilities | `coder` |
| API routes, DB models, service layer | `backend` |
| UI components, pages, state management | `frontend` |
| GitHub Actions, Dockerfile | `ci` |
| Railway / Render / Vercel configs | `deploy` |
| Security audits | `security` |

### BackendAgent

Generates the full backend implementation.

- REST API routes with proper error handling (correct HTTP status codes)
- Database models using the framework's conventions (ActiveRecord, Django ORM, raw SQL)
- Service layer — business logic separated from route handlers
- Auth: session cookies for full-stack apps, JWT for API-only
- CORS middleware when a frontend is present
- Environment variable config — never hardcoded secrets

### FrontendAgent

Generates the full frontend implementation.

- React components in plain JavaScript (no TypeScript unless spec requires it)
- Tailwind CSS for styling — no component libraries
- React Router for SPA routing
- `fetch()` with `useState`/`useEffect` for data — no React Query, Axios, or Redux
- Matches backend API contracts exactly (same endpoints, same field names)
- Loading states, error states, and empty states in every component

### SecurityAgent

Audits all generated code for security issues.

- OWASP Top 10 checks (injection, auth bypass, XSS, IDOR, etc.)
- Hardcoded secret detection
- Insecure direct object reference patterns
- Missing input validation
- Returns patched files when issues are found (not just a report)

### CIAgent

Generates CI/CD infrastructure.

- GitHub Actions workflow: install, lint, test on every push and PR
- Single-stage Dockerfile for production
- `.dockerignore` to exclude dev files, secrets, and version control
- `docker-compose.yml` only when the stack includes Redis or multiple services
- Does not generate a separate deploy workflow — Railway, Render, and Vercel
  auto-deploy from GitHub on push

### DeployAgent

Generates deployment configuration.

- Railway (`railway.toml`, `Procfile`)
- Render (`render.yaml`)
- Vercel (`vercel.json`)
- Fly.io (`fly.toml`)
- Target platform read from `.forge/deploy.md`

### ReviewerAgent

Final validation pass over all generated files.

- Broken imports and missing dependencies
- API contract mismatches between frontend and backend
- Incomplete implementations (placeholders, missing error handling)
- Severity classification: `error` (auto-fix attempted) vs `warning`
- Auto-fix: passes each error back to the appropriate agent with context

---

## Security Model

Every file write goes through `AgenticFirewall` before touching disk. The firewall
reads its policy from `.forge/firewall_policy.json`.

### What the firewall enforces

**Path allowlist** — agents can only write to project-related paths:

```
src/, app/, backend/, frontend/, tests/, docs/, public/, static/,
scripts/, config/, infra/, .github/, and common root files
(Makefile, Dockerfile, docker-compose.yml, package.json, etc.)
```

**Path blocklist** — certain paths are immutable regardless of allowlist:

```
.env*, .ssh/, .aws/, .gnupg/, .kube/, .npmrc, .pypirc,
config/secrets.json, /etc/, /var/, /private/
```

**Content pattern scanning** — rejects files containing:

```
eval(), exec(), os.system(), subprocess.run(), __import__,
getattr(), setattr(), importlib.*
```

Shell scripts, CI configs, Dockerfiles, and Makefiles are exempt from pattern
scanning — these files legitimately use subprocess calls and shell commands.

**Audit log** — every file write decision (permitted or denied) is logged to
`.forge/firewall_audit.log` with timestamp and reason.

### Spec safety

Before any agent sees the spec or rules files, the CLI scans them for patterns that
suggest prompt injection or data exfiltration attempts: URLs, curl/wget commands,
references to credentials, exfiltrate, pastebin, etc. Matches trigger a warning.

---

## Templates

| Template | Stack | Use case |
|---|---|---|
| `web-app` | React + FastAPI + SQLite + Tailwind | General-purpose web application |
| `api-only` | FastAPI + Pydantic + SQLite | REST API with no frontend |
| `ai-app` | React + FastAPI + OpenAI/Anthropic SDK | LLM-powered applications |
| `chrome-ext` | Manifest V3 + vanilla JS | Browser extensions |
| `cli-tool` | Click/Typer + Rich | Command-line tools |
| `data-viz` | Streamlit or Plotly/Recharts | Dashboards and data exploration |
| `slack-bot` | Python + slack-bolt | Slack integrations |
| `discord-bot` | Python + discord.py | Discord bots |

```bash
forge new my-app -t web-app        # Create from template
forge templates                    # List all templates
forge new my-app                   # Interactive template picker
```

Each template ships with:
- `.forge/spec.md` — example spec for that project type
- `.forge/rules.md` — opinionated build constraints
- `.forge/deploy.md` — deployment target configuration

---

## CLI Reference

### Project setup

```bash
forge new <name>                   # Create project (interactive template picker)
forge new <name> -t web-app        # Create with specific template
forge init                         # Add .forge/ to an existing project
forge templates                    # List available templates
```

### Build

```bash
forge build                        # Classic mode: Plan → Build → Review
forge build --adk                  # ADK mode: 7 specialized agents in parallel
forge build -p anthropic           # Use a specific provider
forge build -f "add feature X"     # Incremental: add a feature to existing project
forge build --no-review            # Skip the review phase
forge status                       # Show current build progress and task list
```

### Agents (ADK distributed mode)

```bash
forge agents start                 # Start all agents as HTTP servers (ports 8101-8108)
forge agents status                # Show running agents and PIDs
forge agents stop                  # Gracefully stop all agents
```

Agent port assignments:

| Agent | Port |
|---|---|
| PlannerAgent | 8101 |
| BackendAgent | 8102 |
| FrontendAgent | 8103 |
| SecurityAgent | 8104 |
| CIAgent | 8105 |
| DeployAgent | 8106 |
| ReviewerAgent | 8107 |
| ProjectManagerAgent | 8108 |

### Development and config

```bash
forge dev                          # Auto-detect and start local dev server
forge dev --port 3000              # Custom port
forge config init                  # Create ~/.forge/config.yaml
forge config show                  # Show active configuration
forge config path                  # Print config file location
forge publish                      # Push project to GitHub
```

---

## Configuration

Forge reads provider configuration from `~/.forge/config.yaml`. Created automatically
on first run, or manually with `forge config init`.

```yaml
providers:
  - name: anthropic
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-sonnet-4-20250514

  - name: openai
    api_key: ${OPENAI_API_KEY}
    model: gpt-4o

  - name: together
    api_key: ${TOGETHER_API_KEY}
    model: meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo

  - name: ollama
    base_url: http://localhost:11434
    model: llama3.1
```

Forge tries providers in order and uses the first one with valid credentials. Override
with the `--provider` flag or `-p` shorthand.

### Firewall policy

Each project has its own `.forge/firewall_policy.json`. Override defaults by editing it:

```json
{
  "allowed_paths": [
    "src/.*",
    "app/.*",
    "your-custom-dir/.*"
  ],
  "blocked_paths": [
    ".env.*",
    ".ssh/.*"
  ],
  "blocked_patterns": [
    "eval\\(",
    "exec\\("
  ],
  "blocked_patterns_exempt_extensions": [
    ".sh", ".yml", ".yaml", "Dockerfile", "Makefile"
  ]
}
```

### Project directory layout

```
my-project/
  .forge/
    spec.md              — Project description (you write this)
    rules.md             — Build constraints (template defaults, editable)
    deploy.md            — Deployment target configuration
    firewall_policy.json — AgenticFirewall rules (editable)
    build-state.yaml     — Persisted build state (auto-generated, do not edit)
    decisions.md         — Tech stack decisions from PlannerAgent
    review.yaml          — ReviewerAgent output
    firewall_audit.log   — All file write decisions with timestamps
    agent_pids.yaml      — Running agent PIDs when using distributed mode
  <generated project files>
```

---

## Installation

```bash
git clone https://github.com/nebullii/forge
cd forge
pip install -e ".[build,adk]"      # Recommended: all LLM providers + ADK multi-agent mode
pip install -e ".[build]"          # Classic mode only (no ADK)
pip install -e ".[dev,build,adk]"  # Development (includes pytest)
```

### Provider setup

| Provider | Environment variable | Notes |
|---|---|---|
| Anthropic | `ANTHROPIC_API_KEY` | Recommended. Claude Sonnet is the default model. |
| OpenAI | `OPENAI_API_KEY` | GPT-4o default. |
| Together AI | `TOGETHER_API_KEY` | Cost-effective for longer builds. |
| Groq | `GROQ_API_KEY` | Fast inference. |
| Ollama | — | Run `ollama serve` locally, no key needed. |

---

## Contributing

Forge is MIT licensed. Contributions are welcome.

```bash
git clone https://github.com/nebullii/forge
cd forge
pip install -e ".[dev,build,adk]"
pytest
```

### How the codebase is organized

- `src/providers/` — add a new LLM provider by subclassing `BaseProvider`
- `src/agents/` — add a new specialized agent by subclassing `BaseAgent`
- `templates/` — add a new project template with a `.forge/` directory
- `src/adk/tools.py` — add a new orchestrator tool for ADK mode

### Design principles

- **Provider agnostic** — swap Anthropic, OpenAI, or local Ollama with a flag
- **Two modes** — classic (simple, sequential) or ADK (parallel, specialized)
- **A2A compatible** — every agent is a standalone A2A service
- **Resumable** — build state persisted after every task, resume on interrupt
- **Zero-trust writes** — Agentic Firewall validates every file before disk
- **Minimal core** — classic mode requires only `pyyaml`; all extras are opt-in

---

## License

MIT. See [LICENSE](LICENSE) for details.
