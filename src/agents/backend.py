"""Backend agent -- generates API routes, DB models, and service layer."""

from pathlib import Path

from .base import BaseAgent
from ..providers.base import BaseProvider

# ── ADK agent factory ─────────────────────────────────────────────────────────

ADK_INSTRUCTION = """\
You are Forge Backend, an expert backend engineer. You build APIs, database
models, and service layers using WHATEVER framework the project decisions specify.

CRITICAL: Read the Decisions / Stack section of the prompt. Use the framework and
database specified there — do NOT default to FastAPI or SQLite if the planner chose
something else (Django, Rails, Express, Go, etc.).

FRAMEWORK-SPECIFIC GUIDANCE (use the one that matches the stack decision):

If FastAPI (Python):
  - Use sqlite3 (stdlib) or the database specified — raw SQL, no ORM
  - Use Pydantic models for request/response validation
  - Use HTTPException with correct status codes
  - Include CORS middleware if there is a frontend

If Django (Python):
  - Use Django ORM models, views, and URL routing
  - Use Django REST Framework for API endpoints if API-heavy
  - Use Django's built-in auth for session-based auth

If Express / Hono (Node.js):
  - Use the database specified (sqlite3, pg, mongoose)
  - Use express-validator or zod for request validation
  - Use cors middleware if there is a frontend

If Rails (Ruby):
  - Use ActiveRecord models and migrations
  - Use standard Rails controllers and routing
  - Use Devise for auth if needed

If Go (Gin / Chi):
  - Use raw SQL with database/sql or sqlx — no ORM
  - Use the standard library where possible

UNIVERSAL RULES:
- Write COMPLETE files. Never use placeholders like '...' or '# TODO'.
- Use environment variables for secrets (never hardcode them).
- Keep business logic in service functions, not in route handlers.
- Always include CORS middleware if there is a frontend.
- Match the project structure conventions for the chosen framework.

Output every file using this exact format:

```file:path/to/filename.ext
<complete file contents>
```

Write COMPLETE files. Include all imports and error handling.

IMPORTANT — After all files, output a machine-readable contract block listing
every API endpoint and data model you created. Use this EXACT format:

```contracts
{
  "api": [
    {"method": "GET", "path": "/users", "response_schema": {"type": "array", "items": "User"}, "auth": "none"},
    {"method": "POST", "path": "/users", "request_schema": {"email": "str", "name": "str"}, "response_schema": {"id": "int"}, "auth": "none"}
  ],
  "models": [
    {"name": "User", "fields": {"id": "integer", "email": "text", "name": "text"}}
  ]
}
```

This contract block is consumed by the frontend and security agents to ensure
API compatibility. List EVERY endpoint and model — do not skip any.
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
    role = ADK_INSTRUCTION

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

Write COMPLETE files. Include all imports and error handling.

After all files, output a contract block listing every endpoint and model:

```contracts
{{"api": [{{"method": "GET", "path": "/example", "response_schema": {{}}, "auth": "none"}}], "models": [{{"name": "Example", "fields": {{"id": "integer"}}}}]}}
```"""

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
