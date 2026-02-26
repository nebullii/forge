# Forge Architecture

## System Overview

Forge is a multi-agent code generation CLI. It reads a project spec (markdown) and
produces working code by routing tasks through a pipeline of specialized LLM agents.

```
User
 │
 ▼
forge CLI (src/cli.py)
 │
 ▼
BuildOrchestrator (src/orchestrator.py)
 │
 ├── [classic mode]
 │     PlannerAgent → CoderAgent (×N tasks) → ReviewerAgent
 │
 └── [ADK mode: --adk flag]
       ForgeADKOrchestrator
         │
         ├──► PlannerAgent    (spec → task plan + tech decisions)
         ├──► BackendAgent    (API, DB, services)
         ├──► FrontendAgent   (UI, routing, hooks)
         ├──► SecurityAgent   (OWASP audit, secret detection)
         ├──► CIAgent         (GitHub Actions, Docker)
         ├──► DeployAgent     (Railway/Render/Vercel configs)
         └──► ReviewerAgent   (cross-cutting review + fix)
```

---

## Layer Architecture

### 1. Provider Layer (`src/providers/`)

Abstract over different LLM backends. All agents use `BaseProvider`.

```
BaseProvider (ABC)
  ├── chat(messages, system) → str
  ├── stream(messages, system) → Generator[str]
  └── chat_with_retry(messages, system, max_retries=3) → str
        └── exponential backoff on rate limits / timeouts

Implementations:
  AnthropicProvider   → claude-3-5-sonnet, claude-opus-4, etc.
  OpenAICompatProvider → gpt-4o, together.ai, local OpenAI-compatible
  OllamaProvider      → llama3, mistral, etc. (local)
```

Provider is selected from `~/.forge/config.yaml` via `get_provider_config()`.

### 2. Agent Layer (`src/agents/`)

Each agent = system prompt + methods for its specific task domain.

```
BaseAgent
  ├── role: str              — system prompt
  ├── name: str              — agent identifier
  ├── skill_description: str — one-line A2A capability description
  │
  ├── invoke(prompt) → str           — LLM call with system prompt
  ├── extract_files(response) → list — parse ```file:path blocks
  ├── write_files(files) → list      — safe write to project_root
  │
  └── [A2A support]
       ├── handle_a2a_task(task) → TaskResult  — A2A entry point
       ├── get_agent_card(host, port) → AgentCard
       └── serve(port)                         — start FastAPI server

Specialized agents (all extend BaseAgent):
  PlannerAgent      — YAML plan parser, incremental planning
  CoderAgent        — file generation, fix_file()
  ReviewerAgent     — YAML review parser, severity classification
  BackendAgent      — FastAPI/SQLAlchemy/Pydantic generation
  FrontendAgent     — React/TypeScript/Tailwind generation
  SecurityAgent     — OWASP audit, patched file output
  CIAgent           — GitHub Actions, Dockerfile, docker-compose
  DeployAgent       — platform-specific deploy configs
```

### 3. A2A Protocol Layer (`src/a2a/`)

Google's Agent-to-Agent open protocol. Pure Pydantic + HTTP.

```
types.py
  Task         → {id, message: Message, context: dict}
  Message      → {role, parts: [TextPart | FilePart]}
  TextPart     → {type="text", text: str}
  FilePart     → {type="file", path: str, content: str}
  TaskResult   → {id, status: TaskStatus, artifacts: [Artifact], error}
  Artifact     → {type, name, parts: [Part], data: dict}
  AgentCard    → {name, description, url, version, skills: [AgentSkill]}

client.py
  A2AClient(base_url=None, agent=None)
    ├── for_agent(agent)   → in-process client (no HTTP)
    ├── for_url(base_url)  → HTTP client via httpx
    └── send_task(task) → TaskResult

server.py
  create_a2a_app(agent, host, port) → FastAPI app
    GET  /.well-known/agent.json  → AgentCard
    POST /tasks/send              → TaskResult
    GET  /health                  → {status, agent}
  serve_agent(agent, host, port)  → blocks (uvicorn)
```

### 4. Google ADK Layer (`src/adk/`)

Bridges Forge to Google's Agent Development Kit.

```
llm_bridge.py
  create_forge_llm(provider: BaseProvider) → BaseLlm
    — wraps any Forge provider as an ADK-compatible LLM
    — translates LlmRequest.contents → Forge messages
    — calls provider.chat_with_retry() in asyncio executor

forge_adk_agent.py
  build_forge_adk_agent(name, description, instruction, provider, tools)
    → google.adk.agents.LlmAgent
  ForgeADKAgent (mixin)
    — adds as_adk_agent() to any BaseAgent subclass

orchestrator_agent.py
  ForgeADKOrchestrator
    — holds A2AClient for each agent (in-process or HTTP)
    — run(spec, rules, verbose) → {decisions, tasks, files_written, errors, review}
    — routes: planner → backend → frontend → security → ci → deploy → reviewer
    — each agent's output fed as context to next agent
```

### 5. Security Layer (`src/security/`)

```
AgenticFirewall
  validate_file_write(path, content) → (permitted: bool, reason: str)
    — loaded from .forge/firewall_policy.json
    — audit log written to .forge/firewall_audit.log
    — runs on EVERY file write regardless of build mode
```

### 6. State Layer (`src/state.py`)

```
BuildState
  build_id, status, started_at, completed_at
  provider, model, spec_hash
  tasks: [TaskState]
  files_written: [str]
  errors: [str]
  decisions: str

TaskState
  id, name, description, agent
  status: pending | in_progress | completed | failed
  files_written: [str], error: str

Persisted at .forge/build_state.yaml
compute_spec_hash() — detects spec changes to invalidate resume
```

---

## Build Pipeline: Classic Mode

```
1. Read .forge/spec.md + .forge/rules.md
2. Warn on suspicious patterns (exfiltrate, token, password, etc.)
3. Check if resumable (same spec hash + pending tasks)
4. PlannerAgent.analyze_and_plan(spec, rules) → {decisions, tasks[]}
   - Writes .forge/decisions.md
5. For each task:
   a. CoderAgent.generate_files(task, spec, rules, decisions, context)
   b. AgenticFirewall.validate_file_write() for each file
   c. Write allowed files to disk
   d. Save state after each task (enables resume)
6. ReviewerAgent.review_files(all_files, spec, rules)
   - Auto-fix errors via CoderAgent.fix_file()
   - Write .forge/review.yaml
```

## Build Pipeline: ADK Mode

```
1. Same spec/rules reading + firewall setup
2. ForgeADKOrchestrator.run(spec, rules):

   Phase 1 [sequential]
     PlannerAgent   → task list + tech decisions (as Artifact.data)

   Phase 2 [parallel — ThreadPoolExecutor, max_workers=4]
     BackendAgent   → backend files       (context: decisions, spec)
     CIAgent        → CI/CD files         (context: decisions, spec)
     DeployAgent    → deploy configs      (context: decisions + deploy.md)

   Phase 3 [sequential — needs backend output]
     FrontendAgent  → frontend files      (context: decisions + backend file paths)

   Phase 4 [sequential — needs backend + frontend]
     SecurityAgent  → audit + patched files (context: all backend+frontend files)

   Phase 5 [sequential — needs all files]
     ReviewerAgent  → review dict         (context: all files)

3. Write all files through AgenticFirewall
4. Persist state
```

**Why these phases are parallel-safe:**
- Backend, CI, Deploy all depend only on PlannerAgent output (decisions). They
  don't read each other's output, so they can run concurrently.
- Frontend needs backend file paths to match API contracts → must come after.
- Security audits application code (not CI/deploy configs) → after backend+frontend.
- Reviewer sees everything → last.

---

## Context Flow in ADK Mode

```
PlannerAgent output:
  {decisions: {stack: {}, architecture: "", reasoning: ""}, tasks: [...]}
                    │
                    ▼
BackendAgent receives: spec + rules + decisions JSON
BackendAgent output: [(path, content), ...]
                    │
                    ▼
FrontendAgent receives: spec + rules + decisions + [backend file paths]
FrontendAgent output: [(path, content), ...]
                    │
                    ▼
SecurityAgent receives: {files: {path: content}} (all files so far)
SecurityAgent output: audit YAML + optional patched files
                    │
                    ▼
CIAgent receives: decisions + spec
CIAgent output: [(path, content), ...]
                    │
                    ▼
DeployAgent receives: decisions + spec + deploy.md template
DeployAgent output: [(path, content), ...]
                    │
                    ▼
ReviewerAgent receives: {files: all_files, spec, rules}
ReviewerAgent output: {passed, issues: [{file, severity, message}]}
```

---

## File Output Format (LLM Convention)

All agents instruct the LLM to output files using:
```
```file:path/to/file.ext
<complete file contents>
```
```
`BaseAgent.extract_files()` parses this with regex fallbacks for other formats.

---

## A2A Port Assignments (Distributed Mode)

| Agent | Port |
|-------|------|
| PlannerAgent | 8101 |
| BackendAgent | 8102 |
| FrontendAgent | 8103 |
| SecurityAgent | 8104 |
| CIAgent | 8105 |
| DeployAgent | 8106 |
| ReviewerAgent | 8107 |

---

## Project Directory Structure (Generated Projects)

```
my-project/
  .forge/
    spec.md              — project description (user-written)
    rules.md             — build constraints (user-written)
    deploy.md            — deployment target template
    firewall_policy.json — AgenticFirewall rules
    build_state.yaml     — persisted build state (auto-generated)
    decisions.md         — tech stack decisions from PlannerAgent
    review.yaml          — reviewer output
    firewall_audit.log   — all file write decisions
    agent_pids.yaml      — running agent PIDs (forge agents start)
  <generated project files>
```
