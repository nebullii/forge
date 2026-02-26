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

2. run_parallel_agents("backend,ci,deploy", spec, rules)
   — Backend, CI, and Deploy are all independent of each other.
   — Use the sub-orchestrator so they run concurrently and save time.

3. call_frontend_agent(spec, rules)
   — Must come after backend (needs the API contracts).

4. call_security_agent()
   — Must come after backend + frontend are both done.

5. call_reviewer_agent(spec, rules)
   — Always last. Reviews everything generated.

RULES:
- Always call every agent. Never skip any step.
- Prefer run_parallel_agents for step 2 — do not call backend/ci/deploy individually.
- After all tools have been called, summarize what was built in 2-3 sentences.
"""


class ForgeADKOrchestrator:
    """Orchestrates a multi-agent build using Google ADK LlmAgent + A2A protocol.

    Each specialized agent is wrapped as an ADK tool. The orchestrator LlmAgent
    uses the LLM to decide which tools to call and routes tasks to agents via A2A.

    Local mode (default): agents called in-process via A2AClient.for_agent()
    Distributed mode: agents called via HTTP to running A2A servers
    """

    AGENT_PORTS = {
        "planner":  8101,
        "backend":  8102,
        "frontend": 8103,
        "security": 8104,
        "ci":       8105,
        "deploy":   8106,
        "reviewer": 8107,
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

    def _build_adk_agent(self, artifacts: BuildArtifacts, deploy_md: str):
        """Create the ADK LlmAgent with all agent tools wired in."""
        try:
            from google.adk.agents import LlmAgent
        except ImportError:
            raise ImportError(
                "google-adk is required for ADK mode.\n"
                "Install with: pip install 'forge-ai[adk]'"
            )

        from .llm_bridge import create_forge_llm

        llm = create_forge_llm(self.provider)
        tools = make_agent_tools(self._clients, artifacts, deploy_md)

        return LlmAgent(
            name="forge-orchestrator",
            description="Coordinates specialized agents to build software projects",
            model=llm,
            instruction=ORCHESTRATOR_PROMPT,
            tools=tools,
        )

    def run(self, spec: str, rules: str, verbose: bool = False) -> Dict[str, Any]:
        """Run the full multi-agent build via ADK LlmAgent + A2A.

        Returns:
            {decisions, tasks, files_written, errors, review}
        """
        return asyncio.run(self.run_async(spec, rules, verbose=verbose))

    async def run_async(
        self, spec: str, rules: str, verbose: bool = False
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
        adk_agent = self._build_adk_agent(artifacts, deploy_md)

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

        # Load past learnings from the knowledge base
        from ..knowledge import load as load_knowledge
        knowledge = load_knowledge()
        knowledge_section = (
            f"\n\n## Past Learnings (apply these to this build)\n{knowledge}"
            if knowledge else ""
        )

        # Prompt: give the orchestrator the full spec + rules + learnings
        prompt = (
            f"Build this project using all available agents.\n\n"
            f"## Project Spec\n{spec}\n\n"
            f"## Build Rules\n{rules}"
            f"{knowledge_section}\n\n"
            f"Call every agent tool. Start with call_planner."
        )
        message = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=prompt)],
        )

        if verbose:
            print("  [ADK] Orchestrator starting...")

        # Run the ADK agent — it calls tools (→ A2A → agents) until done
        final_text = ""
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

        if verbose and final_text:
            print(f"\n  [ADK] {final_text.strip()}")

        return {
            "decisions": artifacts.decisions,
            "tasks": artifacts.tasks,
            "files_written": artifacts.files,
            "errors": artifacts.errors,
            "review": artifacts.review,
        }
