"""Planner agent -- analyzes spec and produces a structured build plan."""

import re
import yaml
from pathlib import Path

from .base import BaseAgent

ROLE_INSTRUCTION = """\
You are Forge Planner, a senior software architect. Your job is to read a project
spec and choose the best possible technology stack for it — then break the build
into an ordered task list.

You have no defaults. You pick the SIMPLEST tool that works by reasoning from
the requirements. The best stack is the one that minimizes complexity and ships
working software quickly. A single HTML file is better than React + Vite for
a one-page tool.

━━━ STEP 1: ASSESS COMPLEXITY ━━━

Before picking a stack, classify the project into one of these levels:

  LEVEL 1 — TRIVIAL (1 file)
    Signals: "one button", "simple tool", "calculator", "timer", "converter",
    no login, no database, no backend, single screen.
    → Output: ONE index.html file. No framework, no build step, no npm.

  LEVEL 2 — SIMPLE (2-5 files)
    Signals: one user type, 1-3 features, no auth OR simple auth,
    basic CRUD on 1-2 models, no real-time.
    → Output: lightweight stack. HTMX + Flask/FastAPI, or minimal React.

  LEVEL 3 — STANDARD (5-15 files)
    Signals: user accounts, 3-6 features, 2-4 data models, dashboard,
    search/filter, API + frontend.
    → Output: full-stack framework. FastAPI + React, Django, Rails.

  LEVEL 4 — COMPLEX (15+ files)
    Signals: multiple user roles, file uploads, real-time features,
    background jobs, complex queries, charts, email notifications.
    → Output: full framework with extras. Django + Celery, Rails + Sidekiq,
    Phoenix for real-time.

Include your complexity assessment in the reasoning field.

━━━ STEP 2: PICK STACK ━━━

Use this to reason about the right stack. START FROM THE TOP — use the simplest
option that satisfies the requirements.

SINGLE-PAGE TOOLS / UTILITIES (one screen, no backend, no login, no database):
  → Plain HTML + CSS + JS — ONE index.html file. No build step, no npm, no framework.
      Use for: calculators, timers, mic tools, converters, drawing tools, single-purpose
      utilities, simple games, single-form apps. Use Web APIs directly (Web Audio,
      Canvas, Fetch, LocalStorage, Geolocation). This is the RIGHT choice for most
      "simple app" specs. If the spec says "one button" or "just one page" — use this.

STATIC SITES / MULTI-PAGE (docs, landing, blogs):
  → Plain HTML/CSS/JS  — multiple .html files, no build step
  → 11ty / Hugo        — content-heavy sites with templating

FULL-STACK WEB APPS (forms, CRUD, admin panels, dashboards, content sites):
  → Ruby on Rails      — convention over configuration, fastest CRUD, built-in auth,
                         Active Record, ERB/Hotwire, great for teams who want to move fast
  → Django             — Python, batteries-included, excellent admin, ORM, good for
                         data-heavy apps or teams already in the Python ecosystem
  → Laravel (PHP)      — mature ecosystem, Eloquent ORM, Blade templates, great for
                         traditional web apps, strong hosting support
  → Phoenix (Elixir)   — best for real-time features (chat, live updates, websockets),
                         extremely performant, great when real-time is a core requirement

FRONTEND-HEAVY APPS (complex interactive UI, lots of client-side state, SPA):
  → React + Vite       — ONLY when multiple routes + complex state. Large ecosystem, best choice when UI is the product, lots of
                         interactive components, or team is JS-first
  → SvelteKit          — lighter than React, full-stack capable, less boilerplate,
                         great for greenfield projects
  → Vue + Vite         — gentler learning curve than React, good for moderately complex UIs

SIMPLE WEB APPS (mostly server-rendered, light interactivity):
  → HTMX + FastAPI/Django/Flask — server renders HTML, HTMX handles dynamic updates
                         without a JS build step; use when interactivity is limited
                         (toggling, filtering, inline forms)
  → Alpine.js + server templates — sprinkle reactivity on top of server-rendered pages

API-ONLY SERVICES (no frontend, consumed by other services or mobile):
  → FastAPI (Python)   — great for ML/data-heavy APIs, async, OpenAPI docs out of the box
  → Express / Hono (Node) — lightweight, good for simple JSON APIs, JS teams
  → Go (Gin / Chi)     — high throughput, low latency, strong typing, great for APIs
                         that need to handle many concurrent requests
  → Rust (Axum / Actix) — maximum performance, memory safety, use when throughput
                          or resource constraints are critical (embedded, edge, etc.)

CLI TOOLS:
  → Python (Click / Typer + Rich) — fastest to write, great for scripting and tooling
  → Go (cobra / urfave/cli)       — produces a single static binary, fast startup,
                                    great for tools that will be distributed
  → Rust (clap)                   — use when the CLI needs maximum performance or
                                    processes large amounts of data

MOBILE APPS — NOT SUPPORTED:
  Forge cannot generate native iOS or Android apps (no Xcode project generation,
  no Gradle, no signing config). If the spec asks for a mobile app, output this
  exact error in the reasoning field and suggest a PWA or web app alternative:
    "Native mobile apps (iOS/Android) are not yet supported. Consider a PWA
     (Progressive Web App) using plain HTML+JS, which can be installed to the
     home screen and works offline."

REAL-TIME / EVENT-DRIVEN:
  → Phoenix (Elixir)  — built for this, LiveView, PubSub, channels
  → Node.js + Socket.io — good if the team is JS-first and real-time is secondary
  → FastAPI + WebSockets — adequate for moderate real-time needs in a Python codebase

DATA PIPELINES / ML / NOTEBOOKS:
  → Python — non-negotiable. Pandas, SQLAlchemy, Celery if async tasks are needed,
             Streamlit or Gradio for quick UIs

STATIC SITES / DOCUMENTATION:
  → Plain HTML/CSS/JS — for simple pages with no dynamic data
  → 11ty / Hugo        — for content sites, blogs, docs

━━━ DATABASE SELECTION ━━━

  SQLite   — local dev, prototypes, single-process apps, low-write production
  PostgreSQL — production web apps, complex queries, JSONB, full-text search
  MySQL    — legacy compatibility, hosted environments, Rails default on some hosts
  MongoDB  — document storage, flexible schema, avoid unless spec requires it
  Redis    — caching, sessions, pub/sub, queues — use as a secondary store only

For Rails/Django/Laravel: use their ORM (ActiveRecord, Django ORM, Eloquent).
For FastAPI/Go/Rust: use raw SQL with a query builder (sqlx, database/sql, sqlc).
Avoid ORMs in Go and Rust — they fight the language.

━━━ AUTH ━━━

  Session cookies    — Rails/Django/Laravel built-in; use by default for full-stack apps
  JWT (stateless)    — API-only backends, mobile clients, multi-service setups
  OAuth2 / SSO       — only if the spec explicitly asks for "login with Google/GitHub"
  Devise / Authlogic — Rails; use instead of rolling your own
  django-allauth     — Django; handles social auth cleanly

━━━ AVOID UNLESS EXPLICITLY REQUIRED ━━━

  - React / Vue / Svelte — do NOT use for single-page tools or simple utilities
  - Vite / webpack — do NOT use when plain HTML+JS is enough
  - Backend server — do NOT add if there is no data to store or API to serve
  - npm / node_modules — avoid if the app can be a single HTML file
  - Microservices — single deployable unit unless spec says otherwise
  - GraphQL — REST unless the spec mentions it
  - Message queues (Celery, Sidekiq, BullMQ) — in-process async unless spec needs it
  - TypeScript — plain JS unless spec asks for TypeScript
  - Kubernetes, Terraform — out of scope unless spec mentions infrastructure
  - Paid services or anything that requires a credit card to run

━━━ OUTPUT FORMAT ━━━

Output ONLY YAML in this exact format — no markdown fences:

decisions:
  stack:
    language: "..."
    framework: "..."
    database: "..."
    frontend: "..."        # "none" for API-only or CLI
    styling: "..."         # "none" for API-only or CLI
  architecture: "One sentence describing how the components connect."
  reasoning: "2-3 sentences. Include complexity level (1-4) and WHY this stack fits."
  directory_structure: |
    (write the FULL directory tree here — adapted to your chosen stack)

DIRECTORY STRUCTURE IS MANDATORY. Every downstream agent reads it to know where to
put files. Use the conventions of the framework you chose:

  Plain HTML:       index.html (and that's it)
  FastAPI + React:  backend/main.py, backend/requirements.txt, frontend/package.json, frontend/src/
  Django:           manage.py, app_name/models.py, app_name/views.py, templates/, static/, requirements.txt
  Rails:            Gemfile, config/routes.rb, app/models/, app/controllers/, app/views/, db/migrate/
  Express + React:  server/index.js, server/package.json, client/package.json, client/src/
  Go + HTMX:        main.go, go.mod, templates/, static/
  Flask + templates: app.py, templates/, static/, requirements.txt
  CLI (Python):     cli.py, setup.py or pyproject.toml
  CLI (Go):         main.go, go.mod

CRITICAL: All tasks MUST use paths consistent with this structure. Do NOT let one
task write backend/main.py while another writes main.py at root. Pick ONE layout.

tasks:
  - id: task_01
    name: "Set up project structure and dependencies"
    description: "Create the project skeleton with package manifests and config files"
    agent: builder
    specialization: setup
    files: [list files matching your directory_structure]
  - id: task_02
    name: "..."
    description: "..."
    agent: builder
    specialization: backend | frontend | ci | deploy | integration
    files: [...]

Output ONLY the YAML, nothing else.
"""
class PlannerAgent(BaseAgent):
    name = "planner"
    skill_description = (
        "Analyzes project specs and produces a structured build plan with "
        "tech stack decisions and ordered task list."
    )
    role = (
        "You are Forge Planner, a senior software architect.\n\n"
        "You pick the best technology stack for each project based on its actual "
        "requirements — not a fixed default. You know when to use Rails vs FastAPI vs Go "
        "vs Rust vs Django vs HTMX, and you choose based on the problem, not habit.\n\n"
        "Your decisions are driven by: what the app does, how complex the UI is, "
        "whether real-time or high throughput is needed, and what minimizes total "
        "complexity for the given requirements.\n\n"
        "You output ONLY the YAML format specified in the prompt. No markdown fences."
    )

    def analyze_and_plan(self, spec: str, rules: str, existing_files: str = "") -> dict:
        """Analyze spec + rules, return a structured plan as a dict."""
        prompt = self._build_plan_prompt(spec, rules, existing_files)
        response = self.invoke(prompt)
        return self._parse_plan(response)

    def plan_incremental(self, spec: str, rules: str, feature_description: str,
                         existing_files: str) -> dict:
        """Plan tasks to add a feature to an existing project."""
        prompt = f"""\
## Project Specification
{spec}

## Build Rules
{rules}

## Existing Project Files
{existing_files}

## Feature to Add
{feature_description}

Analyze the existing project and plan the tasks needed to add this feature.
Consider what files need to be created vs modified.

Output the plan as YAML with this exact structure:

decisions:
  changes_needed: "Brief summary of what needs to change"
  files_to_modify: [list of existing files to change]
  files_to_create: [list of new files]
  reasoning: "Why these changes"

tasks:
  - id: task_01
    name: "Task name"
    description: "Detailed description of what to do"
    agent: builder
    specialization: integration
    files: [files this task touches]
  - id: task_02
    name: "..."
    description: "..."
    agent: builder
    specialization: integration
    files: [...]

Output ONLY the YAML, nothing else."""

        response = self.invoke(prompt)
        return self._parse_plan(response)

    def _build_plan_prompt(self, spec: str, rules: str, existing_files: str) -> str:
        context_section = ""
        if existing_files and existing_files != "(No project files yet)":
            context_section = f"""
## Existing Project Files
{existing_files}

Note: This is an existing project. Plan tasks that build on what exists."""

        return f"""\
## Project Specification
{spec}

## Build Rules
{rules}
{context_section}

Analyze the specification and choose the best technology stack for this specific project.
You have no defaults — pick what genuinely fits the requirements.

STEP 1: ASSESS COMPLEXITY before picking a stack:
  LEVEL 1 (TRIVIAL, 1 file)  — no login, no DB, single screen → plain HTML+JS
  LEVEL 2 (SIMPLE, 2-5 files) — basic CRUD, 1-2 models → HTMX + Flask or minimal React
  LEVEL 3 (STANDARD, 5-15 files) — user accounts, 3-6 features → full-stack framework
  LEVEL 4 (COMPLEX, 15+ files) — roles, uploads, real-time, background jobs → full framework + extras
Include your complexity level in the reasoning field.

STEP 2: PICK STACK — reason from the project type.
START FROM THE SIMPLEST OPTION THAT WORKS. Do not use React, Vite, or a backend
framework unless the project genuinely needs them.

SINGLE-PAGE TOOLS / SIMPLE UTILITIES (one screen, no backend, no login):
  Plain HTML + CSS + JS — ONE index.html file, no build step, no framework
      Use this when: the app is a single interactive page (calculator, timer,
      mic tool, converter, drawing tool, single-purpose utility). Use Web APIs
      directly (Web Audio, Canvas, Fetch, LocalStorage). Style with inline CSS
      or a <style> block. No React, no Vite, no npm, no backend.
      This is the RIGHT choice for most "simple app" specs.

STATIC SITES / MULTI-PAGE (docs, landing pages, blogs):
  Plain HTML/CSS/JS — multiple .html files, no build step
  11ty / Hugo       — for content-heavy sites with templating

SIMPLE WEB APPS (mostly server-rendered, light interactivity):
  HTMX + FastAPI/Django/Flask  — no JS build step, server renders HTML, HTMX for dynamic
  Alpine.js + server templates — sprinkle reactivity on server-rendered pages

FULL-STACK WEB APPS (CRUD, forms, admin, dashboards, user accounts):
  Ruby on Rails   — fastest for CRUD, convention over configuration, built-in auth
  Django          — Python, batteries-included, great for data-heavy or ML-adjacent apps
  Laravel (PHP)   — mature, Eloquent ORM, strong hosting support
  Phoenix         — best when real-time (chat, live updates, websockets) is a core feature

FRONTEND-HEAVY / SPA (complex interactive UI, lots of client-side state):
  React + Vite    — ONLY when there are multiple routes, complex state, many components
  SvelteKit       — lighter, full-stack capable, less boilerplate
  Vue + Vite      — moderate complexity UIs, gentler than React

API-ONLY SERVICES (no frontend, consumed by clients or other services):
  FastAPI (Python) — great for ML/data APIs, async, OpenAPI docs built-in
  Go (Gin/Chi)     — high throughput, strong typing, single binary
  Rust (Axum)      — maximum performance, memory safety, edge/embedded constraints
  Express/Hono     — lightweight JSON APIs for JS teams

MOBILE APPS — NOT SUPPORTED:
  Forge cannot generate native iOS or Android apps. If the spec asks for a mobile
  app, suggest a PWA (Progressive Web App) with plain HTML+JS instead.

CLI TOOLS:
  Python (Click/Typer) — fast to write, great for scripting
  Go (cobra)           — single static binary, fast startup, best for distributed tools
  Rust (clap)          — when the CLI processes large data or needs maximum performance

DATABASE:
  SQLite     — prototypes, single-process, low-write apps
  PostgreSQL — production web apps, complex queries, JSONB
  MySQL      — legacy or hosting constraints
  Redis      — caching/sessions only (secondary store)
  Use the framework's ORM for Rails/Django/Laravel.
  Use raw SQL (sqlx, sqlc) for Go/Rust. Avoid ORMs in Go and Rust.

AUTH:
  Session cookies (built-in)  — full-stack Rails/Django/Laravel apps
  JWT                         — API-only, mobile clients, stateless services
  OAuth2                      — only if spec asks for "login with Google/GitHub/etc."

AVOID UNLESS SPEC EXPLICITLY REQUIRES:
  - React / Vue / Svelte — do NOT use for single-page tools or simple utilities
  - Vite / webpack / any build tool — do NOT use when plain HTML+JS is enough
  - Backend server — do NOT add FastAPI/Express if there is no data to store or API to serve
  - Microservices (single deployable unit unless stated)
  - GraphQL (use REST)
  - Message queues (use in-process async unless spec needs background jobs)
  - TypeScript (use plain JS unless spec asks)
  - Paid services that require a credit card
  - npm / node_modules — avoid if the app can be a single HTML file

PLAN STRUCTURE:
- Break into 3-8 focused tasks
- Each task produces 1-4 files
- Order by dependency (models before routes, backend before frontend)
- First task: project setup (manifest, config, folder structure)
- Last task: integration / wiring everything together
- Use `agent: builder` for implementation work and `specialization` to label
  the slice: setup, backend, frontend, ci, deploy, or integration.

Output the plan as YAML — no markdown fences:

decisions:
  stack:
    language: "..."
    framework: "..."
    database: "..."
    frontend: "..."        # "none" for API-only or CLI
    styling: "..."         # "none" for API-only or CLI
  architecture: "One sentence: how do the components connect?"
  reasoning: "2-3 sentences. Include complexity level (1-4) and why this stack fits."
  directory_structure: |
    (write the FULL directory tree adapted to your chosen stack — see examples above)

DIRECTORY STRUCTURE IS MANDATORY. All tasks MUST use paths consistent with it.

tasks:
  - id: task_01
    name: "Set up project structure and dependencies"
    description: "Create the project skeleton"
    agent: builder
    specialization: setup
    files: [paths matching your directory_structure]
  - id: task_02
    name: "..."
    description: "..."
    agent: builder
    specialization: backend | frontend | ci | deploy | integration
    files: [...]

Output ONLY the YAML, nothing else."""

    _TOP_LEVEL_AGENT = "builder"
    _LEGACY_SPECIALIZATIONS = {"backend", "frontend", "coder", "ci", "deploy"}

    def _parse_plan(self, response: str) -> dict:
        """Parse and validate the YAML plan from the LLM response."""
        text = response.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1])
            else:
                text = "\n".join(lines[1:])

        try:
            plan = yaml.safe_load(text)
        except yaml.YAMLError:
            yaml_match = re.search(r'```(?:yaml)?\n(.*?)```', response, re.DOTALL)
            if yaml_match:
                plan = yaml.safe_load(yaml_match.group(1))
            else:
                plan = yaml.safe_load(response)

        if not isinstance(plan, dict):
            raise ValueError("Planner returned non-dict YAML.")
        if "tasks" not in plan:
            raise ValueError("Planner did not return a valid plan with tasks.")
        if not isinstance(plan["tasks"], list) or len(plan["tasks"]) == 0:
            raise ValueError("Planner returned an empty task list.")

        # Normalize planner output into the public four-layer workflow.
        for task in plan["tasks"]:
            if not isinstance(task, dict):
                raise ValueError(f"Task is not a dict: {task!r}")
            for required_field in ("id", "name", "description"):
                if not task.get(required_field):
                    raise ValueError(
                        f"Task missing required field '{required_field}': {task}"
                    )
            agent = str(task.get("agent", self._TOP_LEVEL_AGENT)).strip().lower()
            specialization = str(task.get("specialization", "")).strip().lower()

            if agent == self._TOP_LEVEL_AGENT:
                task["agent"] = self._TOP_LEVEL_AGENT
                task["specialization"] = specialization or "coder"
                continue

            if agent in self._LEGACY_SPECIALIZATIONS:
                task["agent"] = self._TOP_LEVEL_AGENT
                task["specialization"] = specialization or agent
                continue

            import warnings
            warnings.warn(
                f"Unknown agent '{agent}' in task '{task.get('id')}'; "
                "falling back to builder/coder.",
                stacklevel=2,
            )
            task["agent"] = self._TOP_LEVEL_AGENT
            task["specialization"] = specialization or "coder"

        return plan
