"""Forge CLI - Project scaffolding for LLM-assisted development."""

import os
import sys
import shutil
import argparse
import subprocess
import webbrowser
from pathlib import Path

import yaml


FORGE_DIR = ".forge"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Template descriptions for the templates command and interactive mode
TEMPLATES = {
    "web-app": "Full-stack web app (React + FastAPI + SQLite)",
    "api-only": "REST API backend (FastAPI + SQLite)",
    "ai-app": "AI/LLM application (OpenAI/Anthropic + chat UI)",
    "chrome-ext": "Chrome browser extension (Manifest V3)",
    "cli-tool": "Command-line tool (Click/Typer + packaging)",
    "data-viz": "Dashboard/visualization (Streamlit or React + charts)",
    "slack-bot": "Slack bot (slack-bolt)",
    "discord-bot": "Discord bot (discord.py)",
}


def _interactive_new(default_name=None):
    """Interactive project creation with template picker."""
    print("\nAvailable templates:\n")
    template_list = list(TEMPLATES.keys())
    for i, (name, desc) in enumerate(TEMPLATES.items(), 1):
        print(f"  {i}. {name:12} - {desc}")
    print(f"  {len(TEMPLATES) + 1}. (blank)       - Start from scratch")
    print()

    # Get template choice
    while True:
        try:
            choice = input("Choose a template (1-9): ").strip()
            choice_num = int(choice)
            if 1 <= choice_num <= len(TEMPLATES):
                template = template_list[choice_num - 1]
                break
            elif choice_num == len(TEMPLATES) + 1:
                template = None
                break
            else:
                print("Invalid choice. Try again.")
        except (ValueError, KeyboardInterrupt):
            print("\nCancelled.")
            sys.exit(0)

    # Get project name
    if default_name:
        project_name = default_name
    else:
        project_name = input("Project name: ").strip()
        if not project_name:
            print("Error: Project name is required")
            sys.exit(1)

    return template, project_name


def cmd_new(args):
    """Create a new project with .forge/ structure."""
    # Handle interactive mode
    interactive = getattr(args, 'interactive', False)
    template = getattr(args, 'template', None)
    project_name = getattr(args, 'name', None)

    if interactive:
        template, project_name = _interactive_new(project_name)

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
            print(f"Created {project_name}/ from '{template}' template")
        else:
            print(f"Warning: Template '{template}' not found, using default")
            _create_default_files(forge_path, project_name)
    else:
        _create_default_files(forge_path, project_name)

    print(f"")
    print(f"Next steps:")
    print(f"  1. cd {project_name}")
    print(f"  2. Edit .forge/spec.md with your idea")
    print(f"  3. Use your LLM CLI to build it")
    print(f"")
    print(f"Example with Claude Code:")
    print(f"  claude \"Read .forge/spec.md and .forge/rules.md, then build this project\"")


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

## Constraints
- Use free tiers only (no paid services)
- Single deployable unit (no microservices)
- No complex infrastructure
- Prefer SQLite for data persistence

## Tech Preferences
- Pick boring, proven technology
- Minimize dependencies
- Prioritize simplicity over scalability
- Use environment variables for secrets

## Code Style
- Clear over clever
- Small files, small functions
- Include basic error handling
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


def cmd_demo(args):
    """Generate demo QR code for a URL."""
    url = args.url

    if not url:
        # Try to get from sundai.yaml
        sundai_path = Path(FORGE_DIR) / "sundai.yaml"
        if sundai_path.exists():
            with open(sundai_path) as f:
                config = yaml.safe_load(f) or {}
                url = config.get("deployed_url")

    if not url:
        print("Usage: forge demo <url>")
        print("   or: forge demo (if URL saved from previous deploy)")
        return

    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        qr_path = Path("demo-qr.png")
        img.save(qr_path)
        print(f"QR code saved: {qr_path}")
    except ImportError:
        print("QR code requires: pip install 'qrcode[pil]'")

    print(f"URL: {url}")
    webbrowser.open(url)


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

    print(f"Building with {provider_config}...")
    print("")

    orchestrator = BuildOrchestrator(
        provider_config=provider_config,
        forge_path=forge_path,
        review=not no_review,
        verbose=verbose,
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

    # forge demo
    demo_parser = subparsers.add_parser("demo", help="Generate demo QR code")
    demo_parser.add_argument("url", nargs="?", help="URL to generate QR for")
    demo_parser.set_defaults(func=cmd_demo)

    # forge publish
    publish_parser = subparsers.add_parser("publish", help="Publish to GitHub")
    publish_parser.set_defaults(func=cmd_publish)

    # forge build
    build_parser = subparsers.add_parser("build", help="Build project using AI agents")
    build_parser.add_argument("--provider", "-p", help="AI provider (anthropic, openai, together, ollama)")
    build_parser.add_argument("--feature", "-f", help="Add a specific feature (incremental build)")
    build_parser.add_argument("--no-review", action="store_true", help="Skip review phase")
    build_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
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
