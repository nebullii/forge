"""Frontend agent -- generates UI components, pages, routing, and state management."""

from pathlib import Path

from .base import BaseAgent
from ..providers.base import BaseProvider

# ── ADK agent factory ─────────────────────────────────────────────────────────

ADK_INSTRUCTION = """\
You are Forge Frontend, an expert frontend engineer specializing in
React, JavaScript, Tailwind CSS, and clean UI design.

RULES:
- Write COMPLETE files. Never use placeholders like '...' or '# TODO'.
- Use React with plain JavaScript (JSX) — not TypeScript.
- Use Tailwind CSS for styling.
- Use React Router for routing in SPAs.
- Use fetch() with useState/useEffect for data — no React Query, SWR, or Axios.
- Match API contracts from the backend exactly (same endpoints, same field names).
- Handle loading states, errors, and empty states in every UI component.
- Use VITE_API_URL environment variable for the API base URL.
- Keep components small and focused (under 100 lines each).

NEVER use:
- TypeScript — use plain JSX
- React Query, SWR, Tanstack, Redux, Zustand, or any state management library
- Axios — use fetch()
- Component libraries (MUI, Chakra, Ant Design) — use Tailwind

Output every file using this exact format:

```file:path/to/filename.ext
<complete file contents>
```

Write COMPLETE files. Match backend API contracts exactly.
"""


def create_frontend_agent(llm):
    """Create a Google ADK LlmAgent for the Frontend role.

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
        name="forge-frontend",
        description="Generates frontend code: React components, routing, state, API integration.",
        model=llm,
        instruction=ADK_INSTRUCTION,
    )


class FrontendAgent(BaseAgent):
    name = "frontend"
    skill_description = (
        "Generates frontend code: React components, pages, routing, "
        "state management, and API integration."
    )
    role = (
        "You are Forge Frontend, an expert frontend engineer specializing in "
        "React, TypeScript, Tailwind CSS, and modern web development.\n\n"
        "RULES:\n"
        "- Write COMPLETE files. Never use placeholders like '...' or '# TODO'.\n"
        "- Use React with TypeScript by default.\n"
        "- Use Tailwind CSS for styling unless spec says otherwise.\n"
        "- Use React Router for routing in SPAs.\n"
        "- Use React Query or SWR for server state management.\n"
        "- Match API contracts from the backend exactly (same endpoints, same fields).\n"
        "- Handle loading states, errors, and empty states in UI components.\n"
        "- Use environment variables for API base URLs (VITE_API_URL).\n"
        "- Keep components small and focused (< 100 lines each).\n\n"
        "When writing files, use this exact format for EACH file:\n\n"
        "```file:path/to/file.ext\n"
        "<complete file contents here>\n"
        "```\n\n"
        "Write every file in full. Do not skip any file."
    )

    def generate_frontend(
        self,
        spec: str,
        rules: str,
        decisions: str,
        backend_files: list[str] = None,
        project_context: str = "",
    ) -> str:
        """Generate all frontend files. Returns raw LLM response."""
        backend_context = ""
        if backend_files:
            backend_context = (
                "\n## Backend Files (match these API contracts)\n"
                + "\n".join(f"  - {f}" for f in backend_files)
            )

        prompt = f"""\
## Project Specification
{spec}

## Build Rules
{rules}

## Architecture Decisions
{decisions}
{backend_context}

## Existing Project Context
{project_context or "(No existing files)"}

Generate the COMPLETE frontend implementation:
1. Project setup files (package.json, vite.config.ts, tsconfig.json, tailwind.config.js)
2. Main entry point (src/main.tsx, src/App.tsx)
3. Layout and navigation components
4. Page components (one per route)
5. Reusable UI components
6. API client / hooks for backend integration
7. Type definitions

Use this format for each file:

```file:path/to/filename.ext
<complete file contents>
```

Write COMPLETE files. Match the backend API contracts exactly."""

        return self.invoke(prompt)

    def handle_a2a_task(self, task):
        """A2A entry point with frontend-specific context handling."""
        context = task.context or {}
        spec = context.get("spec", "")
        rules = context.get("rules", "")
        decisions = context.get("decisions", {})
        backend_files = context.get("backend_files", [])

        if isinstance(decisions, dict):
            import json
            decisions_str = json.dumps(decisions, indent=2)
        else:
            decisions_str = str(decisions)

        prompt_parts = [p.text for p in task.message.parts if hasattr(p, "text")]
        task_text = "\n".join(prompt_parts)

        if spec:
            response = self.generate_frontend(spec, rules, decisions_str, backend_files)
        else:
            response = self.invoke(task_text)

        files = self.extract_files(response)

        from ..a2a.types import TaskResult, TaskStatus, Artifact, TextPart, FilePart

        artifacts = [
            Artifact(type="text", name="response", parts=[TextPart(text=response)])
        ]
        if files:
            artifacts.append(Artifact(
                type="files",
                name="frontend_files",
                parts=[FilePart(path=fp, content=c) for fp, c in files],
            ))

        return TaskResult(id=task.id, status=TaskStatus.completed, artifacts=artifacts)
