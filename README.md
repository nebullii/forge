# Forge

**Describe your idea. AI builds it. One command.**

Forge is an open-source CLI that turns a project spec into a working codebase using a multi-agent orchestrator. No copy-pasting prompts, no back-and-forth -- just `forge build`.

```
                 spec.md + rules.md
                        │
               ┌────────▼────────┐
               │  ForgeOrchestrator │
               └────────┬────────┘
                        │
           ┌────────────▼────────────┐
           │     PlannerAgent        │  analyzes spec → task plan + tech decisions
           └────────────┬────────────┘
                        │
          ┌─────────────┼─────────────┐
          │             │             │  (parallel)
    ┌─────▼──────┐ ┌────▼────┐ ┌─────▼──────┐
    │BackendAgent│ │ CIAgent │ │DeployAgent │
    └─────┬──────┘ └────┬────┘ └─────┬──────┘
          └─────────────┼─────────────┘
                        │
           ┌────────────▼────────────┐
           │    FrontendAgent        │  needs backend API contracts
           └────────────┬────────────┘
                        │
           ┌────────────▼────────────┐
           │    SecurityAgent        │  OWASP audit + code hardening
           └────────────┬────────────┘
                        │
           ┌────────────▼────────────┐
           │    ReviewerAgent        │  final validation + auto-fix
           └────────────┬────────────┘
                        │
                  working project/
```

---

## How It Works

**1. Scaffold** -- Pick a template. Describe your idea.

```bash
pip install forge-ai
forge new my-app -t web-app
```

**2. Spec** -- Edit `.forge/spec.md` with what you want to build.

```markdown
# Project: My App

## What
A short description of what the app does.

## Features
- Feature one
- Feature two

## Stack
React frontend, FastAPI backend, SQLite
```

**3. Build** -- One command. AI does the rest.

```bash
forge build          # classic mode: Planner → Coder → Reviewer
forge build --adk    # ADK mode: 7 specialized agents + A2A protocol
```

---

## Build Modes

### Classic Mode (`forge build`)

Three-phase sequential pipeline. Fast, simple, works with any provider.

```
Phase 1: Planning...
   Plan: 5 tasks
     - Set up backend with FastAPI and SQLite
     - Add LLM-powered analysis endpoints
     - Build React frontend with team selector
     - Add head-to-head comparison
     - Client-side caching

Phase 2: Building...
   [1/5] Set up backend with FastAPI and SQLite
      + backend/main.py
      + backend/models.py
   ...

Phase 3: Reviewing...
   Review passed.
```

### ADK Mode (`forge build --adk`)

Seven specialized agents coordinated by a Google ADK orchestrator via the A2A protocol. Independent agents (Backend, CI/CD, Deploy) run in parallel.

```
Phase 1-7: ADK Multi-Agent Pipeline
  PlannerAgent → BackendAgent → FrontendAgent →
  SecurityAgent → CIAgent → DeployAgent → ReviewerAgent

  [ADK] → call_planner(...)
  [ADK] ← planner: Plan ready. 6 tasks. Stack: {"backend": "FastAPI", ...}
  [ADK] → run_parallel_agents("backend,ci,deploy", ...)
  [ADK] ← backend: Backend complete. 8 files: backend/main.py, ...
  [ADK] ← ci: CI/CD complete. 3 files: .github/workflows/ci.yml, ...
  [ADK] ← deploy: Deploy config complete. 3 files: railway.toml, ...
  [ADK] → call_frontend_agent(...)
  [ADK] → call_security_agent()
  [ADK] → call_reviewer_agent(...)
```

---

## Key Features

### Specialized Agent Pipeline

Each agent has a dedicated role and system prompt:

| Agent | Role |
|-------|------|
| **PlannerAgent** | Analyzes spec → structured task plan + tech stack decisions |
| **BackendAgent** | FastAPI routes, database models, service layer |
| **FrontendAgent** | React components, routing, state, API integration |
| **SecurityAgent** | OWASP Top 10 audit, secret detection, code hardening |
| **CIAgent** | GitHub Actions workflows, Dockerfile, docker-compose |
| **DeployAgent** | Railway, Render, Vercel, or Fly.io deployment configs |
| **ReviewerAgent** | Cross-file correctness, broken imports, API contract validation |

### A2A Protocol

In ADK mode, agents communicate using Google's [Agent-to-Agent (A2A)](https://google.github.io/A2A/) open protocol. All agents run in-process — no servers to manage. The orchestrator routes tasks to each agent via A2A message passing, and independent agents (Backend, CI, Deploy) run in parallel using a thread pool.

### Agentic Firewall

Every file write is validated against `.forge/firewall_policy.json` before being written to disk:

- **Allowlist paths**: only `src/`, `backend/`, `frontend/`, etc. are writable
- **Blocklist paths**: `.env`, `.ssh/`, `*.pem` are immutable for agents
- **Pattern scanning**: rejects code containing `eval()`, `exec()`, `os.system()`
- **Audit log**: all decisions recorded in `.forge/firewall_audit.log`

### Provider Agnostic

Works with any LLM backend:

| Provider | Setup |
|----------|-------|
| **Anthropic** | `export ANTHROPIC_API_KEY=sk-ant-...` |
| **OpenAI** | `export OPENAI_API_KEY=sk-...` |
| **Together AI** | `export TOGETHER_API_KEY=...` |
| **Groq** | `export GROQ_API_KEY=...` |
| **Ollama** (local) | Just run `ollama serve` |

```bash
forge build                        # Uses first provider with valid key
forge build --provider anthropic   # Use a specific provider
forge build --provider ollama      # Run fully local
```

### Resumable Builds

Build state is saved after every task. If you hit Ctrl+C or something fails:

```bash
forge build    # Resumes from where it stopped
forge status   # See what's done and what's pending
```

### Incremental Features

Already have a working project? Add features without rebuilding everything:

```bash
forge build --feature "add user authentication with email/password"
forge build --feature "add dark mode toggle"
```

### 8 Production-Ready Templates

| Template | Stack |
|----------|-------|
| `web-app` | React + FastAPI + SQLite + Tailwind |
| `api-only` | FastAPI + Pydantic + SQLite |
| `ai-app` | React + FastAPI + OpenAI/Anthropic |
| `chrome-ext` | Manifest V3 + vanilla JS/React |
| `cli-tool` | Click/Typer + Rich |
| `data-viz` | Streamlit or React + Plotly/Recharts |
| `slack-bot` | Python + slack-bolt |
| `discord-bot` | Python + discord.py |

---

## Quick Start

```bash
# Install
pip install forge-ai

# For ADK multi-agent mode
pip install "forge-ai[adk]"

# Set up provider
export ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY, etc.

# Create and build
forge new my-app -t web-app
cd my-app
# Edit .forge/spec.md with your idea
forge build

# Or use the full multi-agent pipeline
forge build --adk

# Run locally
forge dev
```

---

## All Commands

```bash
# Project scaffolding
forge new my-project              # Create project (prompts for template)
forge new my-project -t web-app   # Create with specific template
forge new --interactive           # Interactive mode with menu
forge templates                   # List all available templates
forge init                        # Add .forge/ to existing project

# AI build pipeline
forge build                       # Build project from spec (classic)
forge build --adk                 # Build using ADK multi-agent pipeline
forge build -p anthropic          # Use specific provider
forge build -f "add feature X"    # Add feature to existing project
forge build --no-review           # Skip review phase
forge status                      # Show build progress and tasks

# Development
forge dev                         # Auto-detecting dev server
forge dev --port 3000             # Custom port

# Configuration
forge config init                 # Create ~/.forge/config.yaml
forge config show                 # Show current config
forge config path                 # Print config file path

# Publish
forge publish                     # Push to GitHub
forge sprint start                # Start sprint timer
forge sprint status               # Check elapsed time and progress
forge sprint wrap                 # Generate sprint summary
```

---

## Architecture

```
src/
  cli.py                    # CLI entry point (forge command)
  config.py                 # Config management (~/.forge/config.yaml)
  orchestrator.py           # Build pipeline: Plan → Build → Review (+ ADK mode)
  state.py                  # Resumable build state (.forge/build-state.yaml)
  context.py                # Token-budgeted project context assembly
  sprint.py                 # Sprint timer
  providers/
    base.py                 # Provider ABC + retry logic
    anthropic.py            # Anthropic Claude
    openai_compat.py        # OpenAI / Together / Groq
    ollama.py               # Local models via Ollama
  agents/
    base.py                 # BaseAgent: invoke, extract_files, A2A hooks
    planner.py              # Spec → structured task plan
    coder.py                # Task → complete file generation (classic mode)
    reviewer.py             # Code validation + issue detection
    backend.py              # FastAPI backend generation
    frontend.py             # React frontend generation
    security_agent.py       # OWASP audit + code hardening
    ci_cd.py                # GitHub Actions, Dockerfile, docker-compose
    deploy.py               # Railway / Render / Vercel / Fly.io configs
  a2a/
    types.py                # A2A protocol models (Task, Message, TaskResult, ...)
    client.py               # A2AClient: in-process or HTTP transport
    server.py               # FastAPI A2A server factory
  adk/
    llm_bridge.py           # Wraps Forge BaseProvider as Google ADK BaseLlm
    agent_runner.py         # ADKAgentRunner: bridges LlmAgent ↔ A2A protocol
    orchestrator_agent.py   # Root ADK LlmAgent orchestrator
    tools.py                # ADK tool functions + run_parallel_agents
  security/
    firewall.py             # Agentic Firewall: policy enforcement + audit log
```

### Design Principles

- **Provider agnostic** -- swap between Anthropic, OpenAI, local models with a flag
- **Two modes** -- classic (simple, fast) or ADK (parallel, specialized agents)
- **A2A compatible** -- every agent is a standalone A2A service; run distributed or in-process
- **Resumable** -- state persisted after every task; Ctrl+C and resume anytime
- **Zero-trust writes** -- Agentic Firewall validates every file before it touches disk
- **Minimal core** -- classic mode needs only `pyyaml`; ADK extras are opt-in

---

## Configuration

Forge auto-creates `~/.forge/config.yaml` on first run:

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

Forge picks the first provider with valid credentials. Override with `--provider`.

---

## Install Options

```bash
pip install forge-ai                  # Core (classic mode only)
pip install "forge-ai[build]"         # Core + all LLM providers
pip install "forge-ai[adk]"           # ADK multi-agent mode
pip install "forge-ai[build,adk]"     # Everything
```

**From source:**
```bash
git clone https://github.com/sundai-club/forge
cd forge
pip install -e ".[build,adk]"
```

---

## Contributing

Forge is MIT licensed. PRs welcome.

```bash
git clone https://github.com/sundai-club/forge
cd forge
pip install -e ".[dev,build]"
pytest
```
