"""Backend agent -- generates API routes, DB models, and service layer."""

from .base import BaseAgent

ROLE_INSTRUCTION = """\
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
- If the spec includes user accounts, login, sessions, JWT, or authenticated user data,
  protect mutating endpoints by default. Do NOT mark write endpoints as public unless the
  spec clearly calls for anonymous writes.

Output ONLY a single JSON object with this exact shape:
{
  "files": [
    {"path": "path/to/file.ext", "content": "<complete file contents>"}
  ],
  "contracts": {
    "api": [
      {"method": "GET", "path": "/users", "response_schema": {"type": "array", "items": "User"}, "auth": "none"},
      {"method": "POST", "path": "/users", "request_schema": {"email": "str", "name": "str"}, "response_schema": {"id": "int"}, "auth": "required"}
    ],
    "models": [
      {"name": "User", "fields": {"id": "integer", "email": "text", "name": "text"}}
    ],
    "events": []
  }
}

Do not use markdown fences. This contract object is consumed by the frontend and
security agents to ensure API compatibility. List EVERY endpoint and model.
"""
class BackendAgent(BaseAgent):
    name = "backend"
    skill_description = (
        "Generates backend code: REST API routes, database models, "
        "service/business logic, and configuration."
    )
    role = ROLE_INSTRUCTION

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

Return ONLY this JSON object:
{{
  "files": [
    {{"path": "path/to/file.ext", "content": "<complete file contents>"}}
  ],
  "contracts": {{
    "api": [{{"method": "GET", "path": "/example", "response_schema": {{}}, "auth": "none"}}, {{"method": "POST", "path": "/example", "request_schema": {{}}, "response_schema": {{}}, "auth": "required"}}],
    "models": [{{"name": "Example", "fields": {{"id": "integer"}}}}],
    "events": []
  }}
}}"""

        return self.invoke_json(prompt)
