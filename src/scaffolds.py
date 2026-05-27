"""Deterministic bootstrap scaffolds for supported local template families.

These scaffolds only create the structural skeleton for supported local builds.
They do not hardcode domain-specific business logic. The model still owns the
variable project work after bootstrap.
"""

from __future__ import annotations

import json
import re


def scaffold_supported_task(task: dict, spec: str, decisions: dict) -> str | None:
    """Return deterministic bootstrap files for supported local setup tasks."""
    specialization = str(task.get("specialization", "")).strip().lower()
    if specialization != "setup":
        return None

    family = _template_family(decisions)
    title = _project_title(spec)
    styling = _stack_value(decisions, "styling")

    if family == "web-app":
        return _web_app_setup_response(title, styling=styling, spec=spec)
    if family == "api-only":
        return _api_only_setup_response(title, spec=spec)
    if family == "static-site":
        return _static_site_setup_response(title, spec=spec)
    return None


def _template_family(decisions: dict) -> str:
    if not isinstance(decisions, dict):
        return ""
    family = str(decisions.get("template_family", "")).strip().lower()
    if family:
        return family

    stack = decisions.get("stack", {})
    framework = str(stack.get("framework", "")).strip().lower()
    frontend = str(stack.get("frontend", "")).strip().lower()

    if framework == "fastapi" and frontend == "react":
        return "web-app"
    if framework == "fastapi" and frontend in {"none", ""}:
        return "api-only"
    if framework == "static-html":
        return "static-site"
    return ""


def _stack_value(decisions: dict, key: str) -> str:
    if not isinstance(decisions, dict):
        return ""
    stack = decisions.get("stack", {})
    return str(stack.get(key, "")).strip().lower()


def _project_title(spec: str) -> str:
    match = re.search(r"^#\s*Project:\s*(.+)$", spec, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Forge Project"


def _web_app_setup_response(title: str, styling: str, spec: str = "") -> str:
    package_json = {
        "name": _slugify(title),
        "version": "0.1.0",
        "private": True,
        "type": "module",
        "scripts": {
            "dev": "vite",
            "build": "vite build",
            "preview": "vite preview",
        },
        "dependencies": {
            "react": "^18.3.1",
            "react-dom": "^18.3.1",
            "react-router-dom": "^6.28.0",
        },
        "devDependencies": {
            "@vitejs/plugin-react": "^4.3.4",
            "autoprefixer": "^10.4.20",
            "postcss": "^8.4.49",
            "tailwindcss": "^3.4.16",
            "vite": "^5.4.10",
        },
    }

    readme = _web_app_readme(title, spec)

    gitignore = """# Python
__pycache__/
*.py[cod]
.venv/
venv/

# Node
node_modules/
dist/

# Local config
.env
.env.local

# OS / editor
.DS_Store
.vscode/
"""

    backend_stub = f"""from fastapi import FastAPI

app = FastAPI(title="{_escape_py(title)}")


@app.get("/health")
def health():
    return {{"status": "ok"}}
"""

    env_example = """VITE_API_URL=
DATABASE_PATH=backend/site.db
"""

    vite_config = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
  },
})
"""

    index_html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
"""

    main_jsx = """import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
"""

    app_jsx = f"""export default function App() {{
  return (
    <main style={{{{ fontFamily: 'system-ui, sans-serif', padding: '2rem', lineHeight: 1.5 }}}}>
      <h1>{_escape_js(title)}</h1>
      <p>Forge created the project skeleton. Builder tasks will fill in the product-specific UI.</p>
    </main>
  )
}}
"""

    index_css = (
        """@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  margin: 0;
  min-width: 320px;
}
"""
        if styling == "tailwind"
        else "body { margin: 0; min-width: 320px; }\n"
    )

    files = [
        ("README.md", readme),
        (".gitignore", gitignore),
        ("backend/main.py", backend_stub),
        ("backend/.env.example", "DATABASE_PATH=backend/site.db\n"),
        ("frontend/package.json", json.dumps(package_json, indent=2) + "\n"),
        ("frontend/index.html", index_html),
        ("frontend/vite.config.js", vite_config),
        ("frontend/.env.example", env_example),
        ("frontend/src/main.jsx", main_jsx),
        ("frontend/src/App.jsx", app_jsx),
        ("frontend/src/index.css", index_css),
    ]
    if styling == "tailwind":
        files.extend([
            ("frontend/tailwind.config.js", """export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: { extend: {} },
  plugins: [],
}
"""),
            ("frontend/postcss.config.js", """export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
"""),
        ])

    return _files_response(files)


def _api_only_setup_response(title: str, spec: str = "") -> str:
    readme = _api_only_readme(title, spec)

    gitignore = """__pycache__/
*.py[cod]
.venv/
venv/
.env
.DS_Store
"""

    backend_stub = f"""from fastapi import FastAPI

app = FastAPI(title="{_escape_py(title)}")


@app.get("/health")
def health():
    return {{"status": "ok"}}
"""

    return _files_response([
        ("README.md", readme),
        (".gitignore", gitignore),
        ("backend/main.py", backend_stub),
        ("backend/.env.example", "DATABASE_PATH=backend/site.db\n"),
    ])


def _static_site_setup_response(title: str, spec: str = "") -> str:
    readme = _static_site_readme(title, spec)

    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
    <link rel="stylesheet" href="./styles.css" />
  </head>
  <body>
    <main class="page">
      <h1>{title}</h1>
      <p>Forge created the project skeleton. Builder tasks will fill in the product-specific content.</p>
    </main>
    <script src="./script.js"></script>
  </body>
</html>
"""

    css = """.page {
  font-family: system-ui, sans-serif;
  margin: 0 auto;
  max-width: 900px;
  padding: 2rem;
}
"""

    return _files_response([
        ("README.md", readme),
        (".gitignore", ".DS_Store\n"),
        ("index.html", html),
        ("styles.css", css),
        ("script.js", "console.log('Forge static-site bootstrap ready')\n"),
    ])


def _files_response(files: list[tuple[str, str]]) -> str:
    parts = []
    for path, content in files:
        parts.append(f"```file:{path}\n{content.rstrip()}\n```")
    return "\n\n".join(parts) + "\n"


def _web_app_readme(title: str, spec: str) -> str:
    what = _section_text(spec, "What") or "A small full-stack web application generated by Forge."
    users = _bullet_list(spec, "Users")
    features = _bullet_list(spec, "Features")
    pages = _bullet_list(spec, "Pages")
    endpoints = _bullet_list(spec, "API Endpoints")
    stack = _section_text(spec, "Stack") or "React + Vite, FastAPI, SQLite"

    sections = [
        f"# {title}",
        "",
        "## Overview",
        what,
        "",
        "## Stack",
        f"- {stack}",
    ]

    if users:
        sections.extend(["", "## Users", *[f"- {item}" for item in users]])
    if features:
        sections.extend(["", "## Initial Scope", *[f"- {item}" for item in features]])
    if pages:
        sections.extend(["", "## Pages", *[f"- {item}" for item in pages]])
    if endpoints:
        sections.extend(["", "## API Endpoints", *[f"- {item}" for item in endpoints]])

    sections.extend([
        "",
        "## Project Structure",
        "- `backend/main.py` starts the FastAPI application.",
        "- `backend/routes/` is where API route modules should live.",
        "- `frontend/src/App.jsx` is the frontend shell.",
        "- `frontend/src/pages/` is where page-level views should live.",
        "- `frontend/src/components/` is where shared UI components should live.",
        "- `frontend/src/api/` is where frontend API clients should live.",
        "",
        "## Development",
        "Backend:",
        "```bash",
        "python backend/main.py",
        "```",
        "",
        "Frontend:",
        "```bash",
        "cd frontend",
        "npm install",
        "npm run dev",
        "```",
        "",
        "Combined via Forge:",
        "```bash",
        "forge dev",
        "```",
        "",
        "## Environment",
        "- `backend/.env.example` documents backend-local settings.",
        "- `frontend/.env.example` documents frontend-local settings.",
        "- Forge can materialize local `.env` files from `.env.example` when policy allows it.",
        "- Fill in any real values locally and do not commit secrets.",
    ])
    return "\n".join(sections) + "\n"


def _api_only_readme(title: str, spec: str) -> str:
    what = _section_text(spec, "What") or "A small API service generated by Forge."
    features = _bullet_list(spec, "Features")
    endpoints = _bullet_list(spec, "API Endpoints")

    sections = [
        f"# {title}",
        "",
        "## Overview",
        what,
        "",
        "## Stack",
        "- FastAPI",
        "- SQLite",
    ]
    if features:
        sections.extend(["", "## Initial Scope", *[f"- {item}" for item in features]])
    if endpoints:
        sections.extend(["", "## API Endpoints", *[f"- {item}" for item in endpoints]])
    sections.extend([
        "",
        "## Project Structure",
        "- `backend/main.py` starts the FastAPI application.",
        "- `backend/routes/` is where route modules should live.",
        "",
        "## Development",
        "```bash",
        "python backend/main.py",
        "```",
        "",
        "## Environment",
        "- `backend/.env.example` documents backend-local settings.",
        "- Forge can materialize a local `.env` from `.env.example` when policy allows it.",
    ])
    return "\n".join(sections) + "\n"


def _static_site_readme(title: str, spec: str) -> str:
    what = _section_text(spec, "What") or "A static site generated by Forge."
    features = _bullet_list(spec, "Features")
    pages = _bullet_list(spec, "Pages")

    sections = [
        f"# {title}",
        "",
        "## Overview",
        what,
        "",
        "## Stack",
        "- Plain HTML",
        "- Plain CSS",
        "- Plain JavaScript",
    ]
    if features:
        sections.extend(["", "## Initial Scope", *[f"- {item}" for item in features]])
    if pages:
        sections.extend(["", "## Pages", *[f"- {item}" for item in pages]])
    sections.extend([
        "",
        "## Project Structure",
        "- `index.html` is the main document.",
        "- `styles.css` contains presentation styles.",
        "- `script.js` contains browser-side behavior.",
        "",
        "## Development",
        "Open `index.html` in a browser or serve the directory with a static server.",
    ])
    return "\n".join(sections) + "\n"


def _section_text(spec: str, header: str) -> str:
    pattern = rf"^##\s+{re.escape(header)}\s*$"
    match = re.search(pattern, spec, re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    remainder = spec[start:]
    next_header = re.search(r"^##\s+", remainder, re.MULTILINE)
    block = remainder[: next_header.start()] if next_header else remainder
    return " ".join(line.strip() for line in block.strip().splitlines() if line.strip())


def _bullet_list(spec: str, header: str) -> list[str]:
    pattern = rf"^##\s+{re.escape(header)}\s*$"
    match = re.search(pattern, spec, re.MULTILINE)
    if not match:
        return []
    start = match.end()
    remainder = spec[start:]
    next_header = re.search(r"^##\s+", remainder, re.MULTILINE)
    block = remainder[: next_header.start()] if next_header else remainder
    items: list[str] = []
    for line in block.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "forge-project"


def _escape_js(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _escape_py(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
