"""Forge CLI - Project scaffolding for LLM-assisted development."""

import os
import sys
import shutil
import argparse
import subprocess
from pathlib import Path

import yaml


FORGE_DIR = ".forge"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Template descriptions for the templates command and interactive mode
TEMPLATES = {
    "web-app":    "Full-stack web app (React + FastAPI + SQLite)",
    "api-only":   "REST API backend (FastAPI + SQLite)",
    "ai-app":     "AI/LLM application (OpenAI/Anthropic + chat UI)",
    "chrome-ext": "Chrome browser extension (Manifest V3)",
    "cli-tool":   "Command-line tool (Click/Typer + packaging)",
    "data-viz":   "Dashboard/visualization (Streamlit or React + charts)",
    "slack-bot":  "Slack bot (slack-bolt)",
    "discord-bot":"Discord bot (discord.py)",
}

# Detailed stack info shown during interactive spec building
TEMPLATE_STACKS = {
    "web-app":    "React · FastAPI · SQLite · Tailwind · Railway",
    "api-only":   "FastAPI · Pydantic · SQLite · Railway",
    "ai-app":     "React · FastAPI · OpenAI/Anthropic · Railway",
    "chrome-ext": "Manifest V3 · JavaScript/React · Chrome Storage",
    "cli-tool":   "Python · Click/Typer · Rich · PyPI",
    "data-viz":   "Streamlit or React · Plotly/Recharts · Railway",
    "slack-bot":  "Python · slack-bolt · Railway",
    "discord-bot":"Python · discord.py · Railway",
}


def _interactive_new(default_name=None):
    """Interactive project creation: template picker + spec builder."""
    template_list = list(TEMPLATES.keys())
    divider = "─" * 50

    # ── Step 1: Pick template ──────────────────────────────
    print()
    print("What kind of project are you building?\n")
    for i, (name, desc) in enumerate(TEMPLATES.items(), 1):
        stack = TEMPLATE_STACKS.get(name, "")
        print(f"  {i}. {name:12}  {desc}")
        print(f"     {'':12}  Stack: {stack}")
        print()
    print(f"  {len(TEMPLATES) + 1}. (blank)       Start from scratch")
    print()

    while True:
        try:
            choice = input(f"Choose a template (1-{len(TEMPLATES) + 1}): ").strip()
            choice_num = int(choice)
            if 1 <= choice_num <= len(TEMPLATES):
                template = template_list[choice_num - 1]
                break
            elif choice_num == len(TEMPLATES) + 1:
                template = None
                break
            else:
                print(f"  Please enter a number between 1 and {len(TEMPLATES) + 1}.")
        except (ValueError, KeyboardInterrupt):
            print("\nCancelled.")
            sys.exit(0)

    # ── Step 2: Project name ───────────────────────────────
    print()
    if template:
        stack = TEMPLATE_STACKS.get(template, "")
        print(f"  Template : {template}")
        print(f"  Stack    : {stack}")
        print()

    if default_name:
        project_name = default_name
        print(f"Project name: {project_name}")
    else:
        while True:
            try:
                project_name = input("Project name: ").strip()
                if project_name:
                    break
                print("  Project name cannot be empty.")
            except KeyboardInterrupt:
                print("\nCancelled.")
                sys.exit(0)

    # ── Step 3: Spec builder ───────────────────────────────
    print()
    print(divider)
    if template:
        stack = TEMPLATE_STACKS.get(template, "")
        print(f"  Building with: {stack}")
    print(divider)
    print()
    print("Let's fill in your project spec.\n")

    try:
        what = input("Describe your project in one or two sentences:\n> ").strip()
        print()

        users = input("Who will use it?\n> ").strip()
        print()

        print("Key features (one per line, empty line when done):")
        features = []
        while True:
            line = input("  - ").strip()
            if not line:
                break
            features.append(line)
        print()

        vibe = input("Vibe / tone (e.g. minimal, fun, professional) [optional]:\n> ").strip()
        print()

    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)

    # ── Step 4: Summary + confirm ──────────────────────────
    print(divider)
    print("  Summary")
    print(divider)
    print(f"  Name     : {project_name}")
    if template:
        print(f"  Template : {template}  ({TEMPLATE_STACKS.get(template, '')})")
    if what:
        print(f"  What     : {what}")
    if users:
        print(f"  Users    : {users}")
    if features:
        print(f"  Features :")
        for f in features:
            print(f"               - {f}")
    if vibe:
        print(f"  Vibe     : {vibe}")
    print(divider)
    print()

    try:
        confirm = input("Create project? [Y/n]: ").strip().lower()
        if confirm in ("n", "no"):
            print("Cancelled.")
            sys.exit(0)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)

    spec_answers = {
        "what": what,
        "users": users,
        "features": features,
        "vibe": vibe,
    }

    return template, project_name, spec_answers


def cmd_new(args):
    """Create a new project with .forge/ structure."""
    interactive = getattr(args, 'interactive', False)
    template = getattr(args, 'template', None)
    project_name = getattr(args, 'name', None)
    spec_answers = None

    if interactive:
        template, project_name, spec_answers = _interactive_new(project_name)

    if not project_name:
        print("Error: Project name is required")
        sys.exit(1)

    project_path = Path(project_name)

    if project_path.exists():
        print(f"Error: {project_name} already exists")
        sys.exit(1)

    # Create project directory
    project_path.mkdir(parents=True)
    forge_path = project_path / FORGE_DIR
    forge_path.mkdir()

    if template:
        template_path = TEMPLATES_DIR / template / ".forge"
        if template_path.exists():
            for f in template_path.iterdir():
                if f.is_file():
                    shutil.copy(f, forge_path / f.name)
        else:
            print(f"Warning: Template '{template}' not found, using default")
            _create_default_files(forge_path, project_name)
    else:
        _create_default_files(forge_path, project_name)

    # Overwrite spec.md with interactive answers if provided
    if spec_answers:
        _write_spec(forge_path, project_name, spec_answers, template)

    # Copy firewall policy
    policy_src = TEMPLATES_DIR / "common" / "firewall_policy.json"
    if policy_src.exists():
        shutil.copy(policy_src, forge_path / "firewall_policy.json")

    print(f"Created {project_name}/")
    print(f"  .forge/spec.md    ✓")
    print(f"  .forge/rules.md   ✓")
    if (forge_path / "deploy.md").exists():
        print(f"  .forge/deploy.md  ✓")
    print()
    print(f"Next steps:")
    print(f"  cd {project_name}")
    print(f"  forge build")


def _write_spec(forge_path: Path, project_name: str, answers: dict, template: str = None):
    """Write spec.md from interactive answers."""
    lines = [f"# Project: {project_name}", ""]

    if template:
        stack = TEMPLATE_STACKS.get(template, "")
        lines += [f"## Stack", f"{stack}", ""]

    what = answers.get("what", "").strip()
    lines += ["## What", what if what else "[Describe what you're building]", ""]

    users = answers.get("users", "").strip()
    lines += ["## Users", f"- {users}" if users else "- [Who will use this?]", ""]

    features = answers.get("features") or []
    lines.append("## Features")
    if features:
        for f in features:
            lines.append(f"- {f}")
    else:
        lines.append("- [Feature 1]")
    lines.append("")

    vibe = answers.get("vibe", "").strip()
    if vibe:
        lines += ["## Vibe", vibe, ""]

    (forge_path / "spec.md").write_text("\n".join(lines))


def _create_default_files(forge_path: Path, project_name: str):
    """Create default spec.md and rules.md."""
    (forge_path / "spec.md").write_text(f"""# Project: {project_name}

## What
[Describe what you're building in 1-2 sentences]

## Users
- [Who will use this?]

## Features
- [Feature 1]
- [Feature 2]
- [Feature 3]

## Vibe
[What should it feel like? Fast? Minimal? Fun?]
""")

    (forge_path / "rules.md").write_text("""# Build Rules

## Stack Defaults
- Backend:  FastAPI + sqlite3 (raw SQL, no ORM)
- Frontend: React + Vite + plain JavaScript (not TypeScript)
- Styling:  Tailwind CSS
- Deploy:   Railway (single service, free tier)

## Constraints
- Free tiers only — no paid services or credit card required
- Single deployable unit — no microservices
- SQLite for all persistence — no Postgres, Redis, or external DBs
- Environment variables for all secrets — never hardcode

## What NOT to use
- ORMs (SQLAlchemy, Prisma) — use sqlite3 directly
- TypeScript — use plain JavaScript/JSX
- Redux, Zustand, React Query — use useState/useEffect + fetch()
- Celery or message queues
- GraphQL — use REST
- Complex auth (OAuth2, social login) — use simple JWT if needed

## Use when appropriate
- Redis — for caching high-read data or improving page load
- Docker + docker-compose — when stack has multiple services (e.g. app + Redis)

## Code Style
- Clear over clever
- Small files, small functions
- Basic error handling at boundaries
- No premature abstraction
""")

    print(f"Created {project_name}/")


def cmd_init(args):
    """Initialize .forge/ in current directory."""
    forge_path = Path(FORGE_DIR)

    if forge_path.exists():
        print(".forge/ already exists")
        return

    forge_path.mkdir()
    project_name = Path.cwd().name
    _create_default_files(forge_path, project_name)

    print("")
    print("Next: Edit .forge/spec.md with your idea")


def cmd_dev(args):
    """Run local development server."""
    from .dev_server import DevServer

    server = DevServer(Path.cwd())
    port = getattr(args, 'port', None) or 8080
    server.run(port=port)


def cmd_sprint(args):
    """Sprint management commands."""
    from .sprint import cmd_sprint_start, cmd_sprint_status, cmd_sprint_wrap

    if args.sprint_cmd == "start":
        cmd_sprint_start(args)
    elif args.sprint_cmd == "status":
        cmd_sprint_status(args)
    elif args.sprint_cmd == "wrap":
        cmd_sprint_wrap(args)
    else:
        print("Usage: forge sprint <start|status|wrap>")



def cmd_feedback(args):
    """Add feedback to the Forge knowledge base."""
    from .knowledge import add, KNOWLEDGE_FILE

    # If feedback passed as argument, save directly
    if getattr(args, 'message', None):
        add(args.message)
        print(f"Saved to {KNOWLEDGE_FILE}")
        return

    # Otherwise show current knowledge base or open interactive prompt
    subcmd = getattr(args, 'feedback_cmd', 'add')

    if subcmd == 'show':
        if KNOWLEDGE_FILE.exists():
            print(KNOWLEDGE_FILE.read_text())
        else:
            print("No feedback saved yet. Run 'forge feedback' after a build.")
        return

    if subcmd == 'clear':
        if KNOWLEDGE_FILE.exists():
            confirm = input(f"Clear {KNOWLEDGE_FILE}? [y/N]: ").strip().lower()
            if confirm == 'y':
                KNOWLEDGE_FILE.unlink()
                print("Knowledge base cleared.")
        else:
            print("Nothing to clear.")
        return

    # Default: interactive add
    from .knowledge import collect_feedback
    collect_feedback()


def cmd_templates(args):
    """List available project templates."""
    print("\nAvailable templates:\n")
    for name, desc in TEMPLATES.items():
        print(f"  {name:12} - {desc}")
    print()
    print("Usage: forge new my-project --template <template-name>")
    print("   or: forge new --interactive")
    print()


def cmd_build(args):
    """Build the project using AI agents."""
    forge_path = Path(FORGE_DIR)

    if not forge_path.exists():
        print("No .forge/ directory found.")
        print("Run 'forge new <name>' or 'forge init' first.")
        sys.exit(1)

    from .config import ensure_config, get_provider_config
    from .orchestrator import BuildOrchestrator

    config = ensure_config()

    try:
        provider_config = get_provider_config(config, getattr(args, 'provider', None))
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    feature = getattr(args, 'feature', None)
    no_review = getattr(args, 'no_review', False)
    verbose = getattr(args, 'verbose', False)
    use_adk = getattr(args, 'adk', False)

    if use_adk:
        print(f"Building with {provider_config} [ADK multi-agent mode]...")
    else:
        print(f"Building with {provider_config}...")
    print("")

    orchestrator = BuildOrchestrator(
        provider_config=provider_config,
        forge_path=forge_path,
        review=not no_review,
        verbose=verbose,
        use_adk=use_adk,
    )

    try:
        orchestrator.run(feature=feature)
        print("Build complete!")
        print("")
        print("Next steps:")
        print("  forge dev          # Run locally")
        print("  forge build --feature 'add user auth'  # Add features")
    except KeyboardInterrupt:
        print("")
        print("Build paused. Run 'forge build' to resume.")
    except Exception as e:
        print(f"Build failed: {e}")
        sys.exit(1)



def cmd_config(args):
    """Manage Forge configuration."""
    from .config import CONFIG_FILE, ensure_config

    config_cmd = getattr(args, 'config_cmd', 'show')

    if config_cmd == "show":
        if CONFIG_FILE.exists():
            print(CONFIG_FILE.read_text())
        else:
            print(f"No config found at {CONFIG_FILE}")
            print("Run 'forge config init' to create one.")
    elif config_cmd == "init":
        ensure_config()
        print(f"Config at: {CONFIG_FILE}")
    elif config_cmd == "path":
        print(CONFIG_FILE)


def cmd_status(args):
    """Show current build status."""
    forge_path = Path(FORGE_DIR)
    if not forge_path.exists():
        print("No .forge/ directory found.")
        return

    from .state import load_build_state

    state = load_build_state(forge_path)

    if state.status == "not_started":
        print("No build started yet. Run 'forge build'.")
        return

    print(f"Build: {state.build_id}")
    print(f"Status: {state.status}")
    print(f"Provider: {state.provider} ({state.model})")
    print(f"Started: {state.started_at}")
    if state.completed_at:
        print(f"Completed: {state.completed_at}")
    print("")

    if state.tasks:
        completed = sum(1 for t in state.tasks if t.status == "completed")
        total = len(state.tasks)
        print(f"Tasks: {completed}/{total}")
        for t in state.tasks:
            icons = {"completed": "+", "failed": "X", "in_progress": ">", "pending": " "}
            print(f"  [{icons.get(t.status, '?')}] {t.name}")
            if t.error:
                print(f"      Error: {t.error}")
        print("")

    if state.files_written:
        print(f"Files written: {len(state.files_written)}")
        for f in state.files_written:
            print(f"  {f}")


def cmd_publish(args):
    """Publish project to GitHub."""
    if not shutil.which("gh"):
        print("Requires GitHub CLI: https://cli.github.com")
        sys.exit(1)

    project_name = Path.cwd().name

    # Initialize git if needed
    if not Path(".git").exists():
        subprocess.run(["git", "init"], check=True)
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], check=True)

    print(f"Creating GitHub repo: {project_name}")
    result = subprocess.run(
        ["gh", "repo", "create", project_name, "--public", "--source=.", "--push"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print("Published!")
        for line in result.stdout.splitlines():
            if "github.com" in line:
                print(f"  {line.strip()}")
                break
    else:
        # Try pushing to existing repo
        subprocess.run(["git", "push", "-u", "origin", "main"], check=True)
        print("Pushed to existing repo")


def main():
    parser = argparse.ArgumentParser(
        prog="forge",
        description="Project scaffolding for LLM-assisted development"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # forge new
    new_parser = subparsers.add_parser("new", help="Create new project")
    new_parser.add_argument("name", nargs="?", help="Project name")
    new_parser.add_argument("--template", "-t", help="Template name (use 'forge templates' to list)")
    new_parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode with template picker")
    new_parser.set_defaults(func=cmd_new)

    # forge templates
    templates_parser = subparsers.add_parser("templates", help="List available templates")
    templates_parser.set_defaults(func=cmd_templates)

    # forge init
    init_parser = subparsers.add_parser("init", help="Initialize .forge/ in current directory")
    init_parser.set_defaults(func=cmd_init)

    # forge dev
    dev_parser = subparsers.add_parser("dev", help="Run local dev server")
    dev_parser.add_argument("--port", "-p", type=int, default=8080, help="Port number")
    dev_parser.set_defaults(func=cmd_dev)

    # forge sprint
    sprint_parser = subparsers.add_parser("sprint", help="Sprint timer")
    sprint_parser.add_argument("sprint_cmd", choices=["start", "status", "wrap"], help="Sprint command")
    sprint_parser.set_defaults(func=cmd_sprint)

    # forge feedback
    feedback_parser = subparsers.add_parser("feedback", help="Add feedback to the knowledge base")
    feedback_parser.add_argument("feedback_cmd", nargs="?", default="add",
                                 choices=["add", "show", "clear"],
                                 help="add (default), show, or clear")
    feedback_parser.add_argument("--message", "-m", help="Feedback message (skips interactive prompt)")
    feedback_parser.set_defaults(func=cmd_feedback)

    # forge publish
    publish_parser = subparsers.add_parser("publish", help="Publish to GitHub")
    publish_parser.set_defaults(func=cmd_publish)

    # forge build
    build_parser = subparsers.add_parser("build", help="Build project using AI agents")
    build_parser.add_argument("--provider", "-p", help="AI provider (anthropic, openai, together, ollama)")
    build_parser.add_argument("--feature", "-f", help="Add a specific feature (incremental build)")
    build_parser.add_argument("--no-review", action="store_true", help="Skip review phase")
    build_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    build_parser.add_argument("--adk", action="store_true",
                              help="Use ADK multi-agent pipeline (Backend, Frontend, Security, CI, Deploy)")
    build_parser.set_defaults(func=cmd_build)

    # forge config
    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_parser.add_argument("config_cmd", nargs="?", default="show",
                               choices=["show", "init", "path"],
                               help="Config subcommand")
    config_parser.set_defaults(func=cmd_config)

    # forge status
    status_parser = subparsers.add_parser("status", help="Show build status")
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
