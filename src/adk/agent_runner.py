"""ADKAgentRunner -- bridges a Google ADK LlmAgent to Forge's A2A protocol.

Each specialized agent (Planner, Backend, Frontend, etc.) is a proper
google.adk.agents.LlmAgent. This runner:

  1. Accepts an A2A Task
  2. Runs the LlmAgent via ADK's Runner
  3. Collects the text response
  4. Extracts ```file:path``` blocks (Forge file format)
  5. Returns a TaskResult with text + file artifacts

This is the glue between ADK's world and the A2A protocol.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Optional

from ..a2a.types import (
    AgentCard, AgentSkill, Artifact, FilePart, Message,
    Task, TaskResult, TaskStatus, TextPart,
)

if TYPE_CHECKING:
    pass


class ADKAgentRunner:
    """Wraps a google.adk.agents.LlmAgent as an A2A-compatible service.

    Usage:
        llm = create_forge_llm(provider)
        agent = create_backend_agent(llm)          # LlmAgent
        runner = ADKAgentRunner(agent, name="backend",
                                skill="Generates FastAPI backend code")

        # In-process A2A call (no HTTP)
        result = runner.handle_a2a_task(task)

        # Or start as HTTP server
        runner.serve(port=8102)
    """

    def __init__(self, agent, name: str, skill_description: str):
        """
        Args:
            agent: google.adk.agents.LlmAgent instance
            name: agent identifier (e.g. "backend")
            skill_description: one-line description for the AgentCard
        """
        self.agent = agent
        self.name = name
        self.skill_description = skill_description
        self._runner = None
        self._session_service = None

    def _ensure_runner(self):
        """Lazy-init the ADK Runner (imports google-adk only when needed)."""
        if self._runner is not None:
            return

        try:
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
        except ImportError:
            raise ImportError(
                "google-adk is required for ADK agent mode.\n"
                "Install with: pip install 'forge-ai[adk]'"
            )

        self._session_service = InMemorySessionService()
        self._runner = Runner(
            agent=self.agent,
            app_name=f"forge-{self.name}",
            session_service=self._session_service,
        )

    def handle_a2a_task(self, task: Task) -> TaskResult:
        """A2A entry point — run the ADK agent and return a TaskResult."""
        try:
            return asyncio.run(self._handle_async(task))
        except Exception as e:
            return TaskResult(id=task.id, status=TaskStatus.failed, error=str(e))

    async def _handle_async(self, task: Task) -> TaskResult:
        """Async implementation: runs the ADK LlmAgent for one task."""
        try:
            from google.genai import types as genai_types
        except ImportError:
            raise ImportError(
                "google-genai is required. Install with: pip install 'forge-ai[adk]'"
            )

        self._ensure_runner()

        # Build prompt from task message + context
        prompt_parts = [p.text for p in task.message.parts if hasattr(p, "text")]
        prompt = "\n".join(prompt_parts)

        if task.context:
            prompt += "\n\n" + _format_context(task.context)

        # Create a fresh session per task
        session = await self._session_service.create_session(
            app_name=f"forge-{self.name}",
            user_id="forge-build",
        )

        message = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=prompt)],
        )

        # Run the ADK agent and collect the final text response
        response_text = ""
        async for event in self._runner.run_async(
            user_id="forge-build",
            session_id=session.id,
            new_message=message,
        ):
            if hasattr(event, "is_final_response") and event.is_final_response():
                if event.content:
                    for part in getattr(event.content, "parts", []):
                        t = getattr(part, "text", None)
                        if t:
                            response_text += t

        # Extract ```file:path``` blocks from the response
        files = _extract_files(response_text)

        artifacts = [
            Artifact(type="text", name="response", parts=[TextPart(text=response_text)])
        ]
        if files:
            artifacts.append(Artifact(
                type="files",
                name="generated_files",
                parts=[FilePart(path=path, content=content) for path, content in files],
            ))

        return TaskResult(
            id=task.id,
            status=TaskStatus.completed,
            artifacts=artifacts,
        )

    def get_agent_card(self, host: str = "localhost", port: int = 8100) -> AgentCard:
        """Return A2A AgentCard for /.well-known/agent.json."""
        return AgentCard(
            name=self.name,
            description=self.skill_description,
            url=f"http://{host}:{port}",
            version="0.1.0",
            capabilities={"streaming": False, "pushNotifications": False},
            skills=[
                AgentSkill(
                    id=f"{self.name}-main",
                    name=self.name,
                    description=self.skill_description,
                )
            ],
        )

    def serve(self, port: int = 8100, host: str = "0.0.0.0"):
        """Start this agent as an A2A HTTP server (blocks)."""
        from ..a2a.server import serve_agent
        serve_agent(self, host=host, port=port)


# ── File extraction (same logic as BaseAgent.extract_files) ──────────────────

def _extract_files(response: str) -> list[tuple[str, str]]:
    """Extract ```file:path``` blocks from LLM response."""
    files = []

    # Primary: ```file:path/to/file.ext
    pattern = r'```(?:file:)([^\n`]+)\n(.*?)```'
    for m in re.finditer(pattern, response, re.DOTALL):
        path = m.group(1).strip().lstrip("/")
        content = m.group(2).rstrip() + "\n"
        files.append((path, content))
    if files:
        return files

    # Fallback: ```path/to/file.ext (must contain /)
    pattern2 = r'```([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)\n(.*?)```'
    for m in re.finditer(pattern2, response, re.DOTALL):
        path = m.group(1).strip()
        if "/" in path:
            files.append((path.lstrip("/"), m.group(2).rstrip() + "\n"))
    return files


def _format_context(context: dict) -> str:
    """Format task context dict into a prompt section."""
    import json
    parts = []
    for key, value in context.items():
        if key == "files" and isinstance(value, dict):
            parts.append(f"## Existing Files\n{', '.join(value.keys())}")
        elif isinstance(value, str) and value:
            parts.append(f"## {key.replace('_', ' ').title()}\n{value}")
        elif isinstance(value, (dict, list)):
            parts.append(f"## {key.replace('_', ' ').title()}\n{json.dumps(value, indent=2)}")
    return "\n\n".join(parts)
