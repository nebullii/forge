# Google ADK Integration

Forge integrates with Google ADK (Agent Development Kit) to use its LlmAgent
framework while routing LLM calls through Forge's own provider system.

## Why ADK

- LlmAgent provides tool-calling, multi-turn reasoning, and session management
- ADK handles the "decide which agent to call next" logic via LLM tool use
- Standard framework = other ADK-compatible tools can plug into Forge agents

## Dependency

```bash
pip install 'forge-ai[adk]'
# Installs: google-adk, google-genai, fastapi, uvicorn, httpx, pydantic
```

ADK is **optional**. Classic `forge build` never imports it.
It's only loaded when `--adk` is passed or `forge agents start` is run.

---

## LLM Bridge (`src/adk/llm_bridge.py`)

Google ADK expects a `BaseLlm` implementation. Forge provides one that wraps
any `BaseProvider` (Anthropic, OpenAI, Ollama).

```
BaseProvider (Forge)          BaseLlm (Google ADK)
  chat(messages, system)  ←→  generate_content_async(LlmRequest)
  → str                       → AsyncGenerator[LlmResponse]
```

### Translation

**ADK → Forge:**
```
LlmRequest.contents   (list[Content])  → messages: list[{"role", "content"}]
LlmRequest.system_instruction (Content) → system: str
```

**Forge → ADK:**
```
provider.chat_with_retry() → str
→ Content(role="model", parts=[Part(text=response)])
→ LlmResponse(content=...)
```

### Usage
```python
from src.adk.llm_bridge import create_forge_llm
from src.providers.anthropic import AnthropicProvider

provider = AnthropicProvider(config)
llm = create_forge_llm(provider)  # → BaseLlm instance
```

---

## ForgeADKAgent (`src/adk/forge_adk_agent.py`)

Factory + mixin for creating ADK `LlmAgent` instances backed by Forge providers.

```python
# Factory function
adk_agent = build_forge_adk_agent(
    name="backend",
    description="Generates FastAPI backend code",
    instruction="You are Forge Backend...",
    provider=provider,
    tools=[my_tool_fn],   # optional ADK tools
)
# → google.adk.agents.LlmAgent

# Mixin
class BackendAgent(BaseAgent, ForgeADKAgent):
    adk_description = "Generates FastAPI backend code"

agent = BackendAgent(provider, project_root)
adk_agent = agent.as_adk_agent()
```

---

## ADK Tools (`src/adk/tools.py`)

Tool functions that the ADK orchestrator LLM can call. Each tool:
- Makes an A2A call to a specialized agent
- Writes results into shared `BuildArtifacts` state
- Returns a plain string summary to the LLM

```python
BuildArtifacts          # shared state: decisions, tasks, files, errors, review
make_agent_tools(clients, artifacts, deploy_md) → list[callable]
    # returns: [call_planner, call_backend_agent, call_frontend_agent,
    #           call_security_agent, call_ci_agent, call_deploy_agent,
    #           call_reviewer_agent]
```

Tool docstrings are used as descriptions shown to the ADK LLM.

---

## ForgeADKOrchestrator (`src/adk/orchestrator_agent.py`)

The orchestrator is a real Google ADK `LlmAgent` — not hardcoded Python logic.
The LLM reads the spec and decides which tools to call.

### Initialization
```python
from src.adk.orchestrator_agent import ForgeADKOrchestrator

orchestrator = ForgeADKOrchestrator(
    provider=provider,
    forge_path=forge_path,
    agents={                          # BaseAgent instances
        "planner": planner_agent,
        "backend": backend_agent,
        "frontend": frontend_agent,
        "security": security_agent,
        "ci": ci_agent,
        "deploy": deploy_agent,
        "reviewer": reviewer_agent,
    },
    distributed=False,               # True = use HTTP instead of in-process
)
result = orchestrator.run(spec, rules, verbose=True)
```

### Agent Port Map (for `distributed=True`)
```python
AGENT_PORTS = {
    "planner":  8101,
    "backend":  8102,
    "frontend": 8103,
    "security": 8104,
    "ci":       8105,
    "deploy":   8106,
    "reviewer": 8107,
}
```

### Result shape
```python
{
    "decisions": dict,            # from PlannerAgent
    "tasks": list,                # task list from PlannerAgent
    "files_written": [(str,str)], # all (path, content) from all agents
    "errors": [str],              # non-fatal errors from any agent
    "review": dict | None,        # from ReviewerAgent
}
```

---

## Running an ADK Build

```bash
# Requires google-adk installed
forge build --adk

# Verbose output shows each agent being called
forge build --adk --verbose
```

Internally:
```python
BuildOrchestrator(use_adk=True).run()
  → _run_adk(spec, rules)
  → ForgeADKOrchestrator.run(spec, rules)
  → write all files through AgenticFirewall
```

---

## Distributed Agent Servers

```bash
# Start all 7 agents (background processes)
forge agents start

# Each agent is a FastAPI A2A server
# PID file written to .forge/agent_pids.yaml

forge agents status   # show running/stopped status per agent
forge agents stop     # SIGTERM all agent processes
```

When agents are running as servers, you can switch the orchestrator to HTTP:
```python
orchestrator = ForgeADKOrchestrator(
    provider=provider,
    forge_path=forge_path,
    agents={},          # no local agents
    distributed=True,   # use HTTP to localhost:8101-8107
)
```

---

## Current Limitations

- **Sequential only:** ADK orchestrator calls agents one at a time.
  Backend → Frontend could be parallel in theory (they're independent).
  Tracked as future work.

- **No ADK session persistence:** The orchestrator doesn't use ADK's
  `SessionService` yet — state is managed by Forge's own `BuildState`.

- **Tool calling not wired:** `ForgeADKAgent.as_adk_agent()` creates an
  `LlmAgent` but the orchestrator uses direct A2A calls, not ADK tool use.
  The ADK tool-based routing is a future enhancement.

- **Synchronous provider in async context:** `generate_content_async` runs
  `provider.chat_with_retry()` in an `asyncio` executor. Works but not
  true async — a native async provider would be faster.
