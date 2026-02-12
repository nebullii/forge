# Forge

**Describe your idea. AI builds it. One command.**

Forge is an open-source CLI that turns a project spec into a working codebase using a multi-agent orchestrator. No copy-pasting prompts, no back-and-forth -- just `forge build`.

```
                 spec.md + rules.md
                        |
                   [ Planner Agent ]  ── analyzes spec, creates task plan
                        |
                   [ Coder Agent ]    ── generates complete files per task
                        |
                   [ Reviewer Agent ] ── validates code, auto-fixes errors
                        |
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
# Project: StudyBuddy

## What
A flashcard app that helps students memorize vocabulary.

## Features
- Create flashcard decks with terms and definitions
- Quiz mode with spaced repetition
- Track which cards you get wrong most often

## Vibe
Simple, distraction-free, encouraging
```

**3. Build** -- One command. AI does the rest.

```bash
forge build
```

Forge reads your spec, plans the architecture, generates every file, reviews the code, and fixes issues -- all automatically.

```
Building with anthropic (claude-sonnet-4-20250514)...

Phase 1: Planning...
   Plan: 5 tasks
     - Set up backend structure and dependencies
     - Create database models and API routes
     - Set up frontend with React and Tailwind
     - Build flashcard components and quiz mode
     - Integration, README, and environment config

Phase 2: Building...
   [1/5] Set up backend structure and dependencies
      + backend/main.py
      + backend/requirements.txt
      + backend/db.py
   [2/5] Create database models and API routes
      + backend/routes/decks.py
      + backend/routes/cards.py
   [3/5] Set up frontend with React and Tailwind
      + frontend/package.json
      + frontend/vite.config.js
      + frontend/src/App.jsx
   [4/5] Build flashcard components and quiz mode
      + frontend/src/components/DeckList.jsx
      + frontend/src/components/FlashCard.jsx
      + frontend/src/components/QuizMode.jsx
   [5/5] Integration, README, and environment config
      + README.md
      + .env.example

Phase 3: Reviewing...
   Review passed.

Build complete!
```

---

## Key Features

### Multi-Agent Orchestrator

Forge doesn't just dump your spec into a single prompt. It runs a **three-phase pipeline**:

- **Planner Agent** -- Analyzes your spec and rules, produces a structured task plan (3-8 tasks ordered by dependency)
- **Coder Agent** -- Executes each task sequentially, generating complete files with full context of what's been built so far
- **Reviewer Agent** -- Validates all generated code for missing imports, broken API contracts, and security issues. Auto-fixes errors.

### Provider Agnostic

Works with any LLM backend. Set an environment variable and go:

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

### Agentic Firewall (AFW) 🛡️

Forge includes a general-purpose **Agentic Firewall** that works for any app you generate. Every tool call and file write is intercepted to enforce a "Least Privilege" sandbox:
- **Zero-Trust Validation**: Every file change is checked against `.forge/firewall_policy.json`.
- **Protected Paths**: Critical files like `.env` and `.ssh/` are immutable for agents.
- **Malicious Pattern Scanning**: AFW scans generated code for dangerous primitives like `eval()` and `os.system()` before writing to disk.
- **Audit Logging**: All security decisions are recorded in `.forge/firewall_audit.log`.

### Incremental Features

Already have a working project? Add features without rebuilding:

```bash
forge build --feature "add user authentication with email/password"
forge build --feature "add dark mode toggle"
```

The planner analyzes your existing code and plans only the changes needed.

### 8 Production-Ready Templates

Each template includes a pre-configured `.forge/` directory with tech stack rules, deployment guides, and AI prompts:

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

# Install your preferred AI provider SDK
pip install anthropic          # or: pip install openai
export ANTHROPIC_API_KEY=...   # or: export OPENAI_API_KEY=...

# Create and build
forge new my-app -t web-app
cd my-app
# Edit .forge/spec.md with your idea
forge build

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
forge build                       # Build project from spec
forge build -p anthropic          # Use specific provider
forge build -f "add feature X"   # Add feature to existing project
forge build --no-review           # Skip review phase
forge status                      # Show build progress and tasks

# Development
forge dev                         # Auto-detecting dev server
forge dev --port 3000             # Custom port

# Configuration
forge config init                 # Create ~/.forge/config.yaml
forge config show                 # Show current config
forge config path                 # Print config file path

# Deployment & sharing
forge publish                     # Push to GitHub
forge demo <url>                  # Generate QR code for demo

# Hackathon tools
forge sprint start                # Start sprint timer
forge sprint status               # Check elapsed time and progress
forge sprint wrap                 # Generate sprint summary
```

---

## Architecture

```
src/
  cli.py                  # CLI entry point (forge command)
  config.py               # Config management (~/.forge/config.yaml)
  orchestrator.py         # Build pipeline: Plan -> Build -> Review
  state.py                # Resumable build state (.forge/build-state.yaml)
  context.py              # Token-budgeted project context assembly
  providers/
    base.py               # Provider ABC + retry logic
    anthropic.py          # Anthropic Claude
    openai_compat.py      # OpenAI / Together / Groq
    ollama.py             # Local models via Ollama
  agents/
    base.py               # Agent base class + file extraction
    planner.py            # Spec -> structured YAML task plan
    coder.py              # Task -> complete file generation
    reviewer.py           # Code validation + issue detection
```

### Design Principles

- **Provider agnostic** -- Swap between Anthropic, OpenAI, local models with a flag
- **Resumable** -- State persisted after every task; Ctrl+C and resume anytime
- **Context aware** -- Token-budgeted context window management; each task sees what was built before it
- **Template driven** -- Rules and constraints are per-template, not hardcoded
- **Minimal dependencies** -- Core needs only `pyyaml`; provider SDKs are optional

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

## Example: Full Workflow

```bash
# Create an API project
forge new seo-analyzer -t api-only
cd seo-analyzer

# Write your spec
cat > .forge/spec.md << 'EOF'
# Project: SEO Analyzer

## What
A REST API that analyzes any website URL for SEO issues --
checks meta tags, load times, heading structure, and link health.

## Users
- Businesses trying to improve their search rankings
- Developers validating their sites before launch

## Endpoints
- POST /api/analyze - Submit a URL for analysis
- GET /api/reports/{id} - Get analysis results
- GET /api/reports - List recent analyses

## Vibe
Fast, reliable, well-documented
EOF

# Build it
forge build

# Check what was built
forge status

# Run it
forge dev

# Add a feature later
forge build --feature "add a score out of 100 for each analyzed page"

# Ship it
forge publish
```

---

## Manual Mode

Don't want to use `forge build`? Forge also works as a scaffolding tool with any AI assistant:

**Claude Code:**
```bash
claude "Read .forge/spec.md and .forge/rules.md, then build this project"
```

**Cursor:** Open the project, press `Cmd+I`, type: "Read .forge/spec.md and rules.md, build this project"

**Aider:**
```bash
aider --read .forge/spec.md --read .forge/rules.md
```

Each template includes `.forge/prompts.md` with copy-paste commands for common tasks.

---

## Install Options

**pip (recommended):**
```bash
pip install forge-ai
```

**With AI provider support:**
```bash
pip install "forge-ai[build]"      # All providers
pip install "forge-ai[anthropic]"  # Anthropic only
pip install "forge-ai[openai]"     # OpenAI only
```

**From source:**
```bash
git clone https://github.com/sundai-club/forge
cd forge
pip install -e ".[build]"
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

---

Made with coffee by [Sundai Club](https://sundai.club)
