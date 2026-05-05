# Forge

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

## The Problem

Going from idea to working code is slow. You spend hours on boilerplate, wiring up
APIs, configuring CI/CD, and fixing the mismatches between frontend and backend that
inevitably happen when one person (or one LLM prompt) tries to hold the full picture.

Copy-pasting ChatGPT output into files is tedious and error-prone. Existing code
generators produce scaffolds, not working applications. And single-agent LLM tools
hit context limits, hallucinate API contracts, and can't self-correct.

## What Forge Does Differently

**A small set of specialist layers that actually collaborate.** A planner picks the
right stack. A builder executes specialized implementation slices like backend,
frontend, CI/CD, and deploy. A reviewer catches bugs and routes fixes back to the
right producer. A verifier runs deterministic checks before the build is considered done.

**Structured contracts, not prose.** The backend agent outputs machine-readable API
contracts (endpoints, request/response schemas, auth requirements). The frontend agent
receives these contracts and generates code that matches exactly. No more `POST /api/users`
vs `POST /users` mismatches.

**Real impact:**
- A markdown spec becomes a working project in one command — API routes, DB models,
  React frontend, CI/CD pipeline, deployment config, security audit, and code review
- Frontend/backend API contracts are validated automatically before the reviewer runs
- Independent agents (backend, CI, deploy) run in parallel, cutting build time
- Incremental builds (`--feature "add dark mode"`) know what endpoints already exist
- Every file write goes through a security firewall — no `eval()`, no path traversal,
  no hardcoded secrets

## System Design at a Glance

```
                     .forge/spec.md
                           |
                     +-----------+
                     |  Planner  |  Picks stack: Rails / FastAPI / Go / Phoenix / ...
                     +-----+-----+
                           |
                   +-------+--------+
                   |   Builder      |  Runs setup/backend/frontend/ci/deploy
                   +-------+--------+
                           |
          +----------------+----------------+
          |                |                |         (parallel where safe)
      setup done       backend + ci      deploy
                           |
                           | API contracts (structured JSON)
                           v
                        frontend
          |
    +-----------+
    | Reviewer  |   Reads artifacts, finds issues, routes rework
    +-----------+
          |
    +-----------+
    | Verifier  |   Deterministic syntax / contract / runtime checks
    +-----------+
```

**Key infrastructure:**

| Layer | What it does |
|-------|-------------|
| **ArtifactBus** | Thread-safe shared store. Agents publish typed artifacts (code, decisions, reviews). Consumers query by path, agent, or type. Source of truth during the build. |
| **ContractRegistry** | Structured API/model/event contracts extracted from backend output. Frontend gets exact endpoint shapes. Security gets auth coverage checks. Persisted to `.forge/contracts.json` for incremental builds. |
| **Parallel Scheduler** | Computes dependency graph from agent assignments. Runs independent tasks concurrently (ThreadPoolExecutor). Same-agent tasks stay sequential. |
| **Agentic Firewall** | Every file write checked against path allowlist, blocklist, and content patterns. Audit log at `.forge/firewall_audit.log`. |
| **Providers** | Anthropic (default), OpenAI, Together, Groq, Ollama. Swap with `--provider` flag. |

---

## Quick Start

### 1. Install

```bash
pip install forge-ai
```

Or from source:

```bash
git clone https://github.com/nebullii/forge
cd forge
pip install -e .
```

### 2. Set your API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# OR
export OPENAI_API_KEY=sk-...
# OR
export TOGETHER_API_KEY=...
# OR run Ollama locally (no key needed): ollama serve
```

### 3. Create a project

```bash
forge new my-app -t web-app       # from template
# OR
forge new my-app                  # interactive picker
```

### 4. Write your spec

Edit `.forge/spec.md` — describe what you want in plain English:

```bash
cd my-app
nano .forge/spec.md          # or: vim, code, open — any text editor
```

Example spec:

```markdown
# Project: Task Tracker

## What
A web app for managing personal tasks with user accounts.

## Features
- Email + password login (JWT)
- Create, complete, and delete tasks
- Dashboard showing pending vs completed counts

## Stack
React + Vite, FastAPI, SQLite

## Non-goals
No team features. No notifications.
```

### 5. Build

```bash
forge build                       # Plan → Build → Review → Verify
forge build -p openai             # use a specific provider
forge build -v                    # verbose output (see agent tool calls)
```

### 6. Run locally

```bash
forge dev                         # auto-detects project type, starts dev server
```

### 7. Add features incrementally

```bash
forge build --feature "add dark mode toggle"
forge build --feature "add JWT refresh tokens"
```

Contracts from the previous build are loaded automatically so agents know what endpoints already exist.

---

## Contents

- [System Design](#system-design)
- [Incremental Builds](#incremental-builds)
- [Agent Reference](#agent-reference)
- [Security Model](#security-model)
- [Templates](#templates)
- [CLI Reference](#cli-reference)
- [Configuration](#configuration)
- [Installation](#installation)
- [Contributing](#contributing)

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
│    PlannerAgent → BuilderAgent → ReviewerAgent → Verifier       │
│    BuilderAgent internally uses backend/frontend/ci/deploy      │
│    generators but exposes one build surface to the control      │
│    plane.                                                       │
└────────────────────────┬────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
  Provider Layer    Agent Layer      State Layer
  (src/providers/)  (src/agents/)    (src/state.py)
  Anthropic         BaseAgent        BuildState
  OpenAI-compat     Build roles      TaskState
  Ollama            Artifact flow    YAML persistence
```

### Build Pipeline

Forge exposes one workflow with a deterministic control plane. The planner emits
top-level `builder` tasks with a `specialization`, the scheduler runs them with
dependency awareness, and the build ends with review plus deterministic
verification.

```
.forge/spec.md
      │
      ▼
┌─────────────────┐
│  PlannerAgent   │  Analyzes spec → chooses stack → ordered task list
└────────┬────────┘
         │  {decisions, tasks[]}
         ▼
┌──────────────────────────────────────────────────────┐
│ BuilderAgent + scheduler                             │
│                                                      │
│ setup                                                │
│ backend + ci + deploy   (parallel where safe)        │
│ frontend                                              │
│ integration                                           │
│                                                      │
│ files → firewall → disk + ArtifactBus                │
│ contracts → ContractRegistry + .forge/openapi.json   │
└────────┬─────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  ReviewerAgent                        │
│    Reads all code from ArtifactBus    │
│    Contract validation + findings     │
│    Rework routes back to builder      │
└────────┬───────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│ Verifier                               │
│   Deterministic machine checks         │
│   Structured pass/fail output          │
└────────────────────────────────────────┘
```

**How layers share data (ArtifactBus + ContractRegistry):**
- Planner publishes `TaskPlanArtifact` and stack decisions
- Builder publishes `CodeArtifact`, `BuildOutputArtifact`, and backend contracts
- Reviewer publishes `ReviewArtifact`, `ReviewFindingArtifact`, and rework requests
- Verifier publishes `VerificationArtifact` with machine-readable results

**Why this ordering is parallel-safe:**
`backend`, `ci`, and `deploy` depend only on `setup`, so they can run concurrently.
`frontend` waits on `backend` because it reads contracts. `integration` waits on the
implementation slices. All shared state goes through the thread-safe ArtifactBus.

### Collaboration Layer

Forge does not use free-form agent chat as its protocol. The collaboration layer is
the handoff boundary between phases.

```
planner -> TaskPlanArtifact
builder -> BuildOutputArtifact + contracts
reviewer -> ReviewFindingArtifact + ReworkRequestArtifact
verifier -> VerificationArtifact
```

**ArtifactBus** (`src/collaboration/artifact_bus.py`) — Thread-safe store for all
generated content. Backed by `threading.RLock`. Roles publish artifacts; consumers
query by path, task, agent, or type. The bus is the in-memory source of truth during a
build.

**ArtifactStore** (`src/collaboration/store.py`) — Durable JSONL + JSON snapshots
under `.forge/`. This is what makes the pipeline resumable and debuggable:

- `.forge/artifacts.jsonl`
- `.forge/artifacts.json`

**ContractRegistry** (`src/collaboration/contracts.py`) — Structured API/model/event
contracts extracted from backend output. The frontend agent gets exact endpoint shapes
(method, path, request/response schema, auth). The reviewer gets automated
frontend-vs-backend mismatch detection.

Contract extraction works two ways:
1. **Explicit** — the backend agent outputs a `contracts` JSON block (preferred)
2. **Fallback** — regex extraction from FastAPI/Flask/Express/Rails route decorators

Contracts persist to `.forge/contracts.json` after each build, so incremental builds
(`forge build --feature "..."`) know what endpoints already exist.

### Feedback Loop

When the reviewer finds issues, fixes route back to the **original producer**:

```
ReviewerAgent
    │  "app/routes/users.py has SQL injection"
    │
    ▼  lookup: who wrote this file?
ArtifactBus.latest("app/routes/users.py")
    │  → producer_agent = "backend"
    │
    ▼  route fix to backend builder specialization
BuilderAgent.rework_task("backend", "Fix this SQL injection in ...")
    │
    ▼  publish fixed version (version + 1)
ArtifactBus.publish(CodeArtifact(version=2, ...))
```

Capped at one retry per file to prevent infinite loops. Tracked via
`ReworkRequestArtifact` for observability.

### Parallel Task Scheduling

Forge runs independent builder slices concurrently when the plan spans multiple
specializations. The scheduler computes a dependency graph from task specializations:

```
Task dependencies (computed automatically):
─────────────────────────────────────────
  setup tasks       → no dependencies (run first)
  backend tasks     → wait for setup
  ci tasks          → wait for setup       ┐
  deploy tasks      → wait for setup       ├── run in parallel
  backend tasks     → (also parallel w/ ci)┘
  frontend tasks → wait for backend
  integration    → wait for backend + frontend + ci + deploy
```

Same-specialization tasks run sequentially (in plan order). Cross-specialization
tasks respect the dependency rules above. Falls back to sequential when all tasks
land in the same specialization.

### Layer Map

```
src/
  cli.py                    — Entry point for forge commands.
  orchestrator.py           — Single workflow control plane.
  scheduler.py              — Dependency-aware builder specialization scheduler.
  router.py                 — Capability-based model routing.
  config.py                 — Provider config (~/.forge/config.yaml).
  state.py                  — Resumable build state (schema-versioned YAML).
  audit.py                  — Build audit + summary reporting.
  policy.py                 — Build policy + approval gates.
  context.py                — Token-budgeted project context assembly.

  collaboration/
    models.py               — Typed artifact models and handoff contracts.
    artifact_bus.py         — Thread-safe shared artifact store (RLock-backed).
    store.py                — Durable artifact log and snapshot persistence.
    contracts.py            — ContractRegistry + extraction + persistence.

  providers/
    base.py                 — BaseProvider ABC + exponential backoff retry.
    anthropic.py            — Anthropic Claude.
    openai_compat.py        — OpenAI / Together / Groq / any OpenAI-compatible.
    ollama.py               — Local Ollama models.

  agents/
    base.py                 — Base agent abstractions.
    planner.py              — Spec → task plan. Framework-aware stack selection.
    builder.py              — Unified implementation surface for setup/backend/frontend/ci/deploy.
    reviewer.py             — Code validation, severity classification, rework routing.
    coder.py                — General-purpose file generation used by BuilderAgent.
    backend.py              — API routes, DB models, service layer + contract output.
    frontend.py             — UI generation, contract-aware API integration.
    ci_cd.py                — GitHub Actions, Dockerfile, docker-compose.
    deploy.py               — Railway / Render / Vercel / Fly.io configs.
    security_agent.py       — Optional hardening analyzer.

  verification/
    models.py               — VerificationResult + report types.
    registry.py             — Applicable verifier selection.
    ...                     — Stack-specific deterministic checks.

  security/
    firewall.py             — AgenticFirewall: policy enforcement + audit log.
```

---

## Incremental Builds

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

- Selects the technology stack based on the project type
- Breaks the build into ordered `builder` tasks
- Emits stack decisions and machine-readable task plans

**Stack selection logic:**

| Project type | Likely stack |
|---|---|
| Single-page tool / utility | Plain HTML + CSS + JS (one file) |
| Full-stack web app (CRUD, admin, forms) | Rails, Django, Laravel |
| Real-time features (chat, live updates) | Phoenix (Elixir) |
| Complex interactive SPA | React + Vite, SvelteKit |
| Simple web app, light interactivity | HTMX + FastAPI/Flask |
| API-only backend | FastAPI, Go (Gin/Chi), Rust (Axum) |
| CLI tool | Python (Click/Typer), Go (cobra) |
| Data pipeline or ML | Python + Pandas/SQLAlchemy |
| Static site or docs | Plain HTML, 11ty, Hugo |

**Not supported yet:** Native mobile apps (iOS/Android). Forge can't generate Xcode
projects or Gradle builds. For mobile-like experiences, use a PWA (Progressive Web App).

### BuilderAgent

The planner emits top-level `builder` tasks. Each task carries a `specialization`
such as:

- `setup`
- `backend`
- `frontend`
- `ci`
- `deploy`
- `integration`

The control plane treats `builder` as one role, but the implementation can still use
narrower internal generators where that improves output quality.

### ReviewerAgent

Final validation pass over all generated files. Reads code from the ArtifactBus
(not disk) so it sees the exact content every agent produced.

- Broken imports and missing dependencies
- API contract mismatches between frontend and backend
- Incomplete implementations and placeholders
- Severity classification: `error` vs `warning`
- Rework requests that route back to the appropriate builder specialization

### Verifier

Deterministic post-review checking layer.

- Runs machine-readable checks after review
- Produces structured pass/fail output
- Stops the build on hard verification failures
- Persists results to `.forge/verification.json`

---

## Security Model

Every file write goes through `AgenticFirewall` before touching disk. The firewall
reads its policy from `.forge/firewall_policy.json`.

### What the firewall enforces

**Path blocklist** — agents cannot write to sensitive paths regardless of content:

```
.env, .env.local, .env.production, .ssh/, .aws/, .gnupg/,
.kube/, .git/, .npmrc, .pypirc, config/secrets.json,
/etc/, /var/, /private/
```

All other paths within the project root are allowed. This lets agents generate
any project structure (e.g., `MicAmplifier/`, `backend/`, `my-app/src/`) without
hitting false positives from a rigid allowlist.

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
forge build                        # Plan → Build → Review → Verify
forge build -p anthropic           # Use a specific provider
forge build -f "add feature X"     # Incremental: add a feature to existing project
forge build --no-review            # Skip the review phase
forge status                       # Show current build progress and task list
```

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
  "blocked_paths": [
    "^\\.env$",
    "\\.env\\.local",
    "\\.ssh/.*",
    "\\.git/.*"
  ],
  "blocked_patterns": [
    "eval\\(",
    "exec\\(",
    "os\\.system\\(",
    "__import__"
  ],
  "shell_blocked_patterns": [
    "curl\\s+.*\\|\\s*(?:sh|bash)",
    "chmod\\s+777"
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
    contracts.json       — Persisted API/model contracts (for incremental builds)
    review.yaml          — ReviewerAgent output
    firewall_audit.log   — All file write decisions with timestamps
  <generated project files>
```

---

## Installation

### From PyPI

```bash
pip install forge-ai               # Core package
pip install "forge-ai[build]"      # Core package + provider SDKs
```

### From source

```bash
git clone https://github.com/nebullii/forge
cd forge
pip install -e ".[build]"
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
pip install -e ".[dev,build]"
pytest
```

### How the codebase is organized

- `src/providers/` — add a new LLM provider by subclassing `BaseProvider`
- `src/agents/` — add a new specialized agent by subclassing `BaseAgent`
- `src/collaboration/` — artifact bus, contract registry, typed models
- `src/scheduler.py` — dependency graph and parallel task execution
- `templates/` — add a new project template with a `.forge/` directory

### Design principles

- **Provider agnostic** — swap Anthropic, OpenAI, or local Ollama with a flag
- **One workflow** — planner, builder, reviewer, verifier
- **Agents collaborate** — shared artifact bus + structured contracts, not just file lists
- **Resumable** — build state persisted after every task, resume on interrupt
- **Zero-trust writes** — Agentic Firewall validates every file before disk
- **Thread-safe** — all shared state behind `RLock`; safe for parallel execution
- **Minimal core** — provider SDKs remain opt-in

---

## License

MIT. See [LICENSE](LICENSE) for details.
