"""Backend agent -- generates API routes, DB models, and service layer."""

from pathlib import Path

from .base import BaseAgent
from ..providers.base import BaseProvider

# ── ADK agent factory ─────────────────────────────────────────────────────────

ADK_INSTRUCTION = """\
You are Forge Backend, an expert backend engineer specializing in
FastAPI, SQLite, Pydantic, and REST API design.

RULES:
- Write COMPLETE files. Never use placeholders like '...' or '# TODO'.
- Use FastAPI for APIs.
- Use sqlite3 (Python stdlib) for the database — raw SQL, no ORM.
- Use Pydantic models for request/response validation.
- Include proper error handling (HTTPException with correct status codes).
- Use environment variables for secrets (never hardcode them).
- Keep business logic in service functions, not in route handlers.
- Always include CORS middleware if there is a frontend.

NEVER use:
- SQLAlchemy, Tortoise, or any ORM — use sqlite3 directly
- Celery or task queues
- Complex auth libraries — use plain JWT with PyJWT if auth is needed

USE WHEN APPROPRIATE:
- Redis (via redis-py) — for caching frequently read data or session storage
- Docker + docker-compose — when the stack includes Redis or multiple services

Output every file using this exact format:

```file:path/to/filename.ext
<complete file contents>
```

Write COMPLETE files. Include all imports and error handling.
"""


def create_backend_agent(llm):
    """Create a Google ADK LlmAgent for the Backend role.

    Args:
        llm: A google.adk BaseLlm instance (e.g. from create_forge_llm())

    Returns:
        google.adk.agents.LlmAgent
    """
    try:
        from google.adk.agents import LlmAgent
    except ImportError:
        raise ImportError("google-adk required. Install: pip install 'forge-ai[adk]'")

    return LlmAgent(
        name="forge-backend",
        description="Generates backend code: API routes, database models, service layer.",
        model=llm,
        instruction=ADK_INSTRUCTION,
    )


class BackendAgent(BaseAgent):
    name = "backend"
    skill_description = (
        "Generates backend code: REST API routes, database models, "
        "service/business logic, and configuration."
    )
    role = (
        "You are Forge Backend, an expert backend engineer specializing in "
        "FastAPI, SQLAlchemy, Pydantic, and REST API design.\n\n"
        "RULES:\n"
        "- Write COMPLETE files. Never use placeholders like '...' or '# TODO'.\n"
        "- Use FastAPI for APIs, SQLAlchemy for DB (prefer SQLite unless spec says otherwise).\n"
        "- Use Pydantic models for request/response validation.\n"
        "- Include proper error handling (HTTPException with correct status codes).\n"
        "- Use environment variables for secrets (never hardcode them).\n"
        "- Keep business logic in service functions, not in route handlers.\n"
        "- Always include CORS middleware if there's a frontend.\n\n"
        "When writing files, use this exact format for EACH file:\n\n"
        "```file:path/to/file.ext\n"
        "<complete file contents here>\n"
        "```\n\n"
        "Write every file in full. Do not skip any file."
    )

    def generate_backend(
        self,
        spec: str,
        rules: str,
        decisions: str,
        project_context: str = "",
    ) -> str:
        """Generate all backend files. Returns raw LLM response."""
        prompt = f"""\
## Project Specification
{spec}

## Build Rules
{rules}

## Architecture Decisions
{decisions}

## Existing Project Context
{project_context or "(No existing files)"}

Generate the COMPLETE backend implementation:
1. Main application entry point (main.py or app/main.py)
2. Database models and setup
3. Pydantic schemas/models
4. API route handlers (organized by resource)
5. Service/business logic layer
6. Configuration and environment handling

Use this format for each file:

```file:path/to/filename.ext
<complete file contents>
```

Write COMPLETE files. Include all imports and error handling."""

        return self.invoke(prompt)

    def handle_a2a_task(self, task):
        """A2A entry point with backend-specific context handling."""
        context = task.context or {}
        spec = context.get("spec", "")
        rules = context.get("rules", "")
        decisions = context.get("decisions", {})

        if isinstance(decisions, dict):
            import json
            decisions_str = json.dumps(decisions, indent=2)
        else:
            decisions_str = str(decisions)

        # Extract task text
        prompt_parts = [p.text for p in task.message.parts if hasattr(p, "text")]
        task_text = "\n".join(prompt_parts)

        if spec:
            # Rich context available -- use specialized method
            response = self.generate_backend(spec, rules, decisions_str)
        else:
            # Fallback: use raw task text
            response = self.invoke(task_text)

        files = self.extract_files(response)

        from ..a2a.types import TaskResult, TaskStatus, Artifact, TextPart, FilePart

        artifacts = [
            Artifact(type="text", name="response", parts=[TextPart(text=response)])
        ]
        if files:
            artifacts.append(Artifact(
                type="files",
                name="backend_files",
                parts=[FilePart(path=fp, content=c) for fp, c in files],
            ))

        return TaskResult(id=task.id, status=TaskStatus.completed, artifacts=artifacts)
