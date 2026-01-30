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


def cmd_new(args):
    """Create a new project with .forge/ structure."""
    project_path = Path(args.name)

    if project_path.exists():
        print(f"Error: {args.name} already exists")
        sys.exit(1)

    # Create project directory
    project_path.mkdir(parents=True)
    forge_path = project_path / FORGE_DIR
    forge_path.mkdir()

    # Check for template
    template = getattr(args, 'template', None)
    if template:
        template_path = TEMPLATES_DIR / template / ".forge"
        if template_path.exists():
            for f in template_path.iterdir():
                if f.is_file():
                    shutil.copy(f, forge_path / f.name)
            print(f"Created {args.name}/ from '{template}' template")
        else:
            print(f"Warning: Template '{template}' not found, using default")
            _create_default_files(forge_path, args.name)
    else:
        _create_default_files(forge_path, args.name)

    print(f"")
    print(f"Next steps:")
    print(f"  1. cd {args.name}")
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
    new_parser.add_argument("name", help="Project name")
    new_parser.add_argument("--template", "-t", help="Template: web-app, api-only, slack-bot, discord-bot")
    new_parser.set_defaults(func=cmd_new)

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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
