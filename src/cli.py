"""Forge CLI - AI-agnostic project builder."""

import os
import sys
import argparse
import yaml
from pathlib import Path

from .config import load_config, get_provider
from .builder import Builder
from .deployer import Deployer


FORGE_DIR = ".forge"


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
    (forge_path / "context").mkdir()

    # Create spec.md
    (forge_path / "spec.md").write_text(f"""# Project: {args.name}

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

    # Create rules.md
    (forge_path / "rules.md").write_text("""# Build Rules

## Constraints
- Use free tiers only (no paid services)
- Single deployable unit (no microservices)
- No complex infrastructure (no Kubernetes, no Terraform)
- Prefer SQLite or managed free-tier databases

## Tech Preferences
- Pick boring, proven technology
- Minimize dependencies
- Prioritize simplicity over scalability
- Use environment variables for all secrets

## Code Style
- Clear over clever
- Small files, small functions
- Include basic error handling
- Add comments only where logic isn't obvious
""")

    # Create empty decisions.md
    (forge_path / "decisions.md").write_text("""# Decisions

*AI will write here after analyzing your spec.*

## Tech Stack
[To be determined]

## Architecture
[To be determined]

## Reasoning
[To be determined]
""")

    # Create empty tasks.md
    (forge_path / "tasks.md").write_text("""# Tasks

*AI will break down the build into tasks here.*

## Status
- [ ] Pending

## Task List
[To be generated]
""")

    print(f"✅ Created {args.name}/")
    print(f"")
    print(f"Next steps:")
    print(f"  1. cd {args.name}")
    print(f"  2. Edit .forge/spec.md with your project idea")
    print(f"  3. Run: forge build")


def cmd_build(args):
    """Build the project using AI."""
    forge_path = Path(FORGE_DIR)

    if not forge_path.exists():
        print("Error: No .forge/ directory found. Run 'forge new <name>' first.")
        sys.exit(1)

    config = load_config()
    provider = get_provider(config, args.provider)

    builder = Builder(provider, forge_path, step_mode=args.step)

    print(f"🔨 Building with {provider.name}...")
    print("")

    try:
        builder.run()
        print("")
        print("✅ Build complete!")
        print("   Run 'forge deploy' to ship it.")
    except KeyboardInterrupt:
        print("\n⏸️  Build paused. Run 'forge build' to continue.")
    except Exception as e:
        print(f"\n❌ Build failed: {e}")
        sys.exit(1)


def cmd_deploy(args):
    """Deploy the project to hosting."""
    forge_path = Path(FORGE_DIR)

    if not forge_path.exists():
        print("Error: No .forge/ directory found.")
        sys.exit(1)

    config = load_config()
    deployer = Deployer(config, args.target)

    print(f"🚀 Deploying to {deployer.target}...")

    try:
        url = deployer.run()
        print("")
        print(f"✅ Deployed!")
        print(f"   {url}")
    except Exception as e:
        print(f"\n❌ Deploy failed: {e}")
        sys.exit(1)


def cmd_status(args):
    """Show build status."""
    forge_path = Path(FORGE_DIR)

    if not forge_path.exists():
        print("No .forge/ directory found.")
        return

    tasks_file = forge_path / "tasks.md"
    if not tasks_file.exists():
        print("No tasks yet. Run 'forge build' first.")
        return

    content = tasks_file.read_text()
    print(content)


def cmd_reset(args):
    """Reset build state (keeps spec.md and rules.md)."""
    forge_path = Path(FORGE_DIR)

    if not forge_path.exists():
        print("No .forge/ directory found.")
        return

    # Clear decisions and tasks
    (forge_path / "decisions.md").write_text("# Decisions\n\n*Will be regenerated on next build.*\n")
    (forge_path / "tasks.md").write_text("# Tasks\n\n*Will be regenerated on next build.*\n")

    # Clear context
    context_path = forge_path / "context"
    if context_path.exists():
        for f in context_path.iterdir():
            f.unlink()

    print("✅ Reset complete. spec.md and rules.md preserved.")
    print("   Run 'forge build' to start fresh.")


def main():
    parser = argparse.ArgumentParser(
        prog="forge",
        description="AI-agnostic project builder"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # forge new
    new_parser = subparsers.add_parser("new", help="Create new project")
    new_parser.add_argument("name", help="Project name")
    new_parser.set_defaults(func=cmd_new)

    # forge build
    build_parser = subparsers.add_parser("build", help="Build the project")
    build_parser.add_argument("--provider", "-p", help="AI provider to use")
    build_parser.add_argument("--step", "-s", action="store_true", help="Step through tasks interactively")
    build_parser.set_defaults(func=cmd_build)

    # forge deploy
    deploy_parser = subparsers.add_parser("deploy", help="Deploy the project")
    deploy_parser.add_argument("--target", "-t", help="Deployment target")
    deploy_parser.set_defaults(func=cmd_deploy)

    # forge status
    status_parser = subparsers.add_parser("status", help="Show build status")
    status_parser.set_defaults(func=cmd_status)

    # forge reset
    reset_parser = subparsers.add_parser("reset", help="Reset build state")
    reset_parser.set_defaults(func=cmd_reset)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
