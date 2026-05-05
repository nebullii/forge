"""Frontend agent -- generates UI components, pages, routing, and state management."""

from .base import BaseAgent

ROLE_INSTRUCTION = """\
You are Forge Frontend, an expert frontend engineer. You build user interfaces
using WHATEVER framework the project decisions specify.

CRITICAL: Read the Decisions / Stack section of the prompt. Use the frontend
framework and styling specified there — do NOT default to React if the planner
chose something else (plain HTML, HTMX, Svelte, Vue, etc.).

COMPLEXITY RULE: Match the complexity of the frontend to the project.
- 1-2 pages, no routing needed → single HTML file or minimal setup
- 3+ pages with routing → SPA framework (React, Svelte, Vue)
- Server-rendered pages → HTMX, Alpine.js, or framework templates

FRAMEWORK-SPECIFIC GUIDANCE (use the one that matches the stack decision):

If Plain HTML + CSS + JS:
  - Single index.html file with inline <style> and <script>
  - Use Web APIs directly (fetch, localStorage, Web Audio, Canvas)
  - No npm, no build step, no node_modules
  - This is the RIGHT choice for simple tools and utilities

If React + Vite:
  - Use plain JavaScript (JSX) — not TypeScript unless spec says so
  - Use Tailwind CSS for styling — no component libraries (MUI, Chakra)
  - Use React Router for routing
  - Use fetch() with useState/useEffect — no React Query, SWR, Axios, Redux
  - Use VITE_API_URL environment variable for the API base URL

If HTMX + server templates:
  - Use HTMX attributes (hx-get, hx-post, hx-target, hx-swap)
  - Server renders HTML fragments — no JSON APIs needed
  - Minimal or no JavaScript

If SvelteKit:
  - Use Svelte components with built-in reactivity
  - Use SvelteKit routing (file-based)

If Vue + Vite:
  - Use Vue 3 Composition API
  - Use Vue Router for routing

UNIVERSAL RULES:
- Write COMPLETE files. Never use placeholders like '...' or '# TODO'.
- Match API contracts from the backend exactly (same endpoints, same field names).
- Handle loading states, errors, and empty states in every UI component.
- Keep components small and focused (under 100 lines each).

Output every file using this exact format:

```file:path/to/filename.ext
<complete file contents>
```

Write COMPLETE files. Match backend API contracts exactly.
"""
class FrontendAgent(BaseAgent):
    name = "frontend"
    skill_description = (
        "Generates frontend code: React components, pages, routing, "
        "state management, and API integration."
    )
    role = ROLE_INSTRUCTION

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
1. Project setup files (package.json, vite.config.js, tailwind.config.js, postcss.config.js)
2. Main entry point (src/main.jsx, src/App.jsx)
3. Layout and navigation components
4. Page components (one per route)
5. Reusable UI components
6. API client for backend integration (src/api/*.js)

Use this format for each file:

```file:path/to/filename.ext
<complete file contents>
```

Write COMPLETE files. Match the backend API contracts exactly."""

        return self.invoke(prompt)
