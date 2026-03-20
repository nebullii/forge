"""ForgeADKOrchestrator -- Google ADK LlmAgent that orchestrates specialized agents via A2A.

Architecture:
    ForgeADKOrchestrator
        │  creates
        ▼
    google.adk.agents.LlmAgent   ← the actual orchestrator
        model = ForgeLlmBridge   ← wraps Forge's BaseProvider (Anthropic/OpenAI/Ollama)
        tools = [                ← agent tools + sub-orchestrator
            call_planner,
            run_parallel_agents,   ← fires backend/ci/deploy concurrently
            call_backend_agent,
            call_frontend_agent,
            call_security_agent,
            call_ci_agent,
            call_deploy_agent,
            call_reviewer_agent,
        ]
        │
        │  runner.run(spec + rules)
        │  LLM decides which tools to call and in what order
        │
        ├── call_planner(spec, rules)
        │       └── A2A POST → PlannerAgent → TaskResult
        │
        ├── call_backend_agent(spec, rules)
        │       └── A2A POST → BackendAgent → TaskResult
        │
        └── ... (LLM continues until build is complete)

Requires: pip install 'forge-ai[adk]'  (google-adk, google-genai)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from .tools import BuildArtifacts, make_agent_tools

if TYPE_CHECKING:
    from ..providers.base import BaseProvider


ORCHESTRATOR_PROMPT = """\
You are Forge Orchestrator, a master build coordinator for software projects.
You coordinate specialized AI agents to build complete, production-ready applications
from a project specification.

You have these tools available:
- call_planner            — Analyze spec → build plan + tech decisions. Call this FIRST.
- call_project_manager    — Enrich the plan: assign agents + write per-task prompts. Call SECOND.
- run_parallel_agents     — Run multiple independent agents concurrently (sub-orchestrator).
                            Pass agent_names as a comma-separated string e.g. "backend,ci,deploy".
- call_backend_agent      — Generate backend (API, DB, services).
- call_frontend_agent     — Generate frontend (React UI). Needs backend done first.
- call_security_agent     — Audit all generated code. Needs backend + frontend done.
- call_ci_agent           — Generate CI/CD config (GitHub Actions, Docker).
- call_deploy_agent       — Generate deployment config (Railway/Render/Vercel).
- call_reviewer_agent     — Final review of all code. Call LAST.

Execution order — follow this exactly:
1. call_planner(spec, rules)
   — Must be first. Produces the build plan and tech decisions.

2. call_project_manager(spec, rules)
   — Must be second. Enriches each task with the right agent assignment and a
     targeted prompt. This ensures each agent gets precise, self-contained instructions.

3. run_parallel_agents("backend,ci,deploy", spec, rules)
   — Backend, CI, and Deploy are all independent of each other.
   — Use the sub-orchestrator so they run concurrently and save time.

4. call_frontend_agent(spec, rules)
   — Must come after backend (needs the API contracts).

5. call_security_agent()
   — Must come after backend + frontend are both done.

6. call_reviewer_agent(spec, rules)
   — Always last. Reviews everything generated.

RULES:
- Always call every agent. Never skip any step.
- Prefer run_parallel_agents for step 3 — do not call backend/ci/deploy individually.
- After all tools have been called, summarize what was built in 2-3 sentences.
"""


# Maps user-facing agent names to their tool function names
_AGENT_TOOL_MAP: Dict[str, str] = {
    "backend":  "call_backend_agent",
    "frontend": "call_frontend_agent",
    "security": "call_security_agent",
    "ci":       "call_ci_agent",
    "deploy":   "call_deploy_agent",
}

# Infrastructure tools that always run regardless of agent selection
_INFRA_TOOLS = {
    "call_planner",
    "call_project_manager",
    "run_parallel_agents",
    "call_reviewer_agent",
}

_AGENT_DESCRIPTIONS: Dict[str, str] = {
    "backend":  "call_backend_agent  — Generate backend (API, DB, services).",
    "frontend": "call_frontend_agent — Generate frontend UI. Needs backend first.",
    "security": "call_security_agent — OWASP audit + code hardening.",
    "ci":       "call_ci_agent       — GitHub Actions, Dockerfile, docker-compose.",
    "deploy":   "call_deploy_agent   — Railway / Render / Vercel / Fly.io configs.",
}


def _constrain_to_agents(
    all_tools: list,
    allowed_agents: List[str],
) -> tuple:
    """Return (prompt, tools) filtered to only the selected content agents.

    Infrastructure tools (planner, project_manager, run_parallel_agents,
    reviewer) are always kept. Content agent tools are filtered by allowed_agents.
    The returned prompt is dynamically generated to match the filtered tool set.
    """
    allowed_set  = set(allowed_agents)
    active_names = _INFRA_TOOLS | {
        _AGENT_TOOL_MAP[n] for n in allowed_set if n in _AGENT_TOOL_MAP
    }
    tools = [t for t in all_tools if t.__name__ in active_names]

    # Build tool listing
    tool_lines = [
        "- call_planner            — Analyze spec → build plan. Call FIRST.",
        "- call_project_manager    — Enrich plan with agent assignments. Call SECOND.",
        "- run_parallel_agents     — Run independent agents concurrently.",
    ]
    for name in allowed_agents:
        if name in _AGENT_DESCRIPTIONS:
            tool_lines.append(f"- {_AGENT_DESCRIPTIONS[name]}")
    tool_lines.append("- call_reviewer_agent     — Final review. Call LAST.")

    # Build execution steps
    parallel = [n for n in ("backend", "ci", "deploy") if n in allowed_set]
    sequential = [n for n in ("frontend", "security") if n in allowed_set]

    steps = [
        "1. call_planner(spec, rules)",
        "2. call_project_manager(spec, rules)",
    ]
    step_n = 3
    if parallel:
        steps.append(
            f"{step_n}. run_parallel_agents(\"{','.join(parallel)}\", spec, rules)"
        )
        step_n += 1
    for name in sequential:
        steps.append(f"{step_n}. call_{name}_agent(spec, rules)")
        step_n += 1
    steps.append(f"{step_n}. call_reviewer_agent(spec, rules)")

    prompt = (
        "You are Forge Orchestrator, coordinating specialized AI agents to build "
        "software projects from a specification.\n\n"
        "Available tools:\n" + "\n".join(tool_lines) + "\n\n"
        "Execution order — follow exactly:\n" + "\n".join(steps) + "\n\n"
        "RULES:\n"
        "- Call every listed agent. Never skip a step.\n"
        "- Use run_parallel_agents for step 3 agents.\n"
        "- Summarize what was built in 2-3 sentences after all tools have been called.\n"
    )
    return prompt, tools


class ForgeADKOrchestrator:
    """Orchestrates a multi-agent build using Google ADK LlmAgent + A2A protocol.

    Each specialized agent is wrapped as an ADK tool. The orchestrator LlmAgent
    uses the LLM to decide which tools to call and routes tasks to agents via A2A.

    Local mode (default): agents called in-process via A2AClient.for_agent()
    Distributed mode: agents called via HTTP to running A2A servers
    """

    AGENT_PORTS = {
        "planner":         8101,
        "backend":         8102,
        "frontend":        8103,
        "security":        8104,
        "ci":              8105,
        "deploy":          8106,
        "reviewer":        8107,
        "project_manager": 8108,
    }

    def __init__(
        self,
        provider: "BaseProvider",
        forge_path: Path,
        agents: Optional[Dict[str, Any]] = None,
        distributed: bool = False,
    ):
        self.provider = provider
        self.forge_path = forge_path
        self.project_root = forge_path.parent
        self.agents = agents or {}
        self.distributed = distributed

        from ..a2a.client import A2AClient
        self._clients: Dict[str, "A2AClient"] = {}

        for name, agent in self.agents.items():
            if distributed:
                port = self.AGENT_PORTS.get(name, 8100)
                self._clients[name] = A2AClient.for_url(f"http://localhost:{port}")
            else:
                self._clients[name] = A2AClient.for_agent(agent)

    def _build_adk_agent(
        self,
        artifacts: BuildArtifacts,
        deploy_md: str,
        allowed_agents: Optional[List[str]] = None,
    ):
        """Create the ADK LlmAgent with tools filtered to the allowed agent set."""
        try:
            from google.adk.agents import LlmAgent
        except ImportError:
            raise ImportError(
                "google-adk is required for ADK mode.\n"
                "Install with: pip install 'forge-ai[adk]'"
            )

        from .llm_bridge import create_forge_llm

        llm       = create_forge_llm(self.provider)
        all_tools = make_agent_tools(self._clients, artifacts, deploy_md)

        if allowed_agents is not None:
            prompt, tools = _constrain_to_agents(all_tools, allowed_agents)
        else:
            prompt, tools = ORCHESTRATOR_PROMPT, all_tools

        return LlmAgent(
            name="forge-orchestrator",
            description="Coordinates specialized agents to build software projects",
            model=llm,
            instruction=prompt,
            tools=tools,
        )

    def run(
        self,
        spec: str,
        rules: str,
        verbose: bool = False,
        allowed_agents: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run the full multi-agent build via ADK LlmAgent + A2A.

        Returns:
            {decisions, tasks, files_written, errors, review}
        """
        return asyncio.run(
            self.run_async(spec, rules, verbose=verbose, allowed_agents=allowed_agents)
        )

    async def run_async(
        self,
        spec: str,
        rules: str,
        verbose: bool = False,
        allowed_agents: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Async version of run()."""
        try:
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from google.genai import types as genai_types
        except ImportError:
            raise ImportError(
                "google-adk and google-genai are required for ADK mode.\n"
                "Install with: pip install 'forge-ai[adk]'"
            )

        deploy_md = ""
        deploy_path = self.forge_path / "deploy.md"
        if deploy_path.exists():
            deploy_md = deploy_path.read_text()

        # Shared state that tools write into
        artifacts = BuildArtifacts()

        # Build the ADK agent with tools bound to this run's artifacts
        adk_agent = self._build_adk_agent(artifacts, deploy_md, allowed_agents=allowed_agents)

        # Set up runner + session
        session_service = InMemorySessionService()
        runner = Runner(
            agent=adk_agent,
            app_name="forge",
            session_service=session_service,
        )
        session = await session_service.create_session(
            app_name="forge",
            user_id="forge-build",
        )

        # Prompt: give the orchestrator the full spec + rules
        prompt = (
            f"Build this project using all available agents.\n\n"
            f"## Project Spec\n{spec}\n\n"
            f"## Build Rules\n{rules}\n\n"
            f"Call every agent tool. Start with call_planner."
        )
        message = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=prompt)],
        )

        if verbose:
            print("  [ADK] Orchestrator starting...")

        from .tools import PipelineAbortError

        # Run the ADK agent — it calls tools (→ A2A → agents) until done
        final_text = ""
        try:
            async for event in runner.run_async(
                user_id="forge-build",
                session_id=session.id,
                new_message=message,
            ):
                # Print tool calls in verbose mode
                if verbose and hasattr(event, "content") and event.content:
                    for part in getattr(event.content, "parts", []):
                        fn_call = getattr(part, "function_call", None)
                        fn_resp = getattr(part, "function_response", None)
                        if fn_call:
                            print(f"  [ADK] → {fn_call.name}(...)")
                        elif fn_resp:
                            resp_text = str(getattr(fn_resp, "response", ""))[:120]
                            print(f"  [ADK] ← {fn_resp.name}: {resp_text}")

                # Capture final text response
                if hasattr(event, "is_final_response") and event.is_final_response():
                    if event.content:
                        for part in getattr(event.content, "parts", []):
                            t = getattr(part, "text", None)
                            if t:
                                final_text += t
        except PipelineAbortError as exc:
            if verbose:
                print(f"\n  [ADK] Pipeline aborted: {exc}")
            artifacts.errors.append(f"Pipeline aborted: {exc}")

        if verbose and final_text:
            print(f"\n  [ADK] {final_text.strip()}")

        return {
            "decisions": artifacts.decisions,
            "tasks": artifacts.tasks,
            "files_written": artifacts.files,
            "errors": artifacts.errors,
            "review": artifacts.review,
            "aborted": artifacts.aborted,
        }
