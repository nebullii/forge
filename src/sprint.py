"""Sprint management for Sundai Club build days."""

import re
from datetime import datetime
from pathlib import Path

import yaml

FORGE_DIR = ".forge"
SUNDAI_FILE = "sundai.yaml"


def get_sundai_path() -> Path:
    """Get path to sundai.yaml in current project."""
    return Path(FORGE_DIR) / SUNDAI_FILE


def load_sundai_config() -> dict:
    """Load sundai.yaml or return empty dict."""
    path = get_sundai_path()
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_sundai_config(config: dict):
    """Save sundai.yaml."""
    path = get_sundai_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def cmd_sprint_start(args):
    """Start a new sprint."""
    forge_path = Path(FORGE_DIR)

    if not forge_path.exists():
        print("No .forge/ directory found.")
        print("Create a project first: forge new <name>")
        return

    config = load_sundai_config()
    config["sprint_start"] = datetime.now().isoformat()
    config["sprint_date"] = datetime.now().strftime("%Y-%m-%d")
    save_sundai_config(config)

    print("🚀 Sprint started!")
    print("")
    print("Time to ship something.")
    print("")
    print("Next:")
    print("  1. Edit .forge/spec.md")
    print("  2. forge build")
    print("  3. forge dev")
    print("  4. forge deploy")
    print("")


def cmd_sprint_status(args):
    """Show sprint status."""
    forge_path = Path(FORGE_DIR)

    if not forge_path.exists():
        print("No .forge/ directory found.")
        return

    config = load_sundai_config()

    if "sprint_start" not in config:
        print("No active sprint. Run 'forge sprint start' first.")
        return

    # Calculate elapsed time
    start = datetime.fromisoformat(config["sprint_start"])
    elapsed = datetime.now() - start
    hours = int(elapsed.total_seconds() // 3600)
    minutes = int((elapsed.total_seconds() % 3600) // 60)

    print(f"⏱️  Time: {hours}h {minutes}m")
    print("")

    # Count tasks
    tasks_file = forge_path / "tasks.md"
    if tasks_file.exists():
        content = tasks_file.read_text()
        done = len(re.findall(r"- \[x\]", content, re.IGNORECASE))
        pending = len(re.findall(r"- \[ \]", content))
        total = done + pending

        if total > 0:
            print(f"📋 Tasks: {done}/{total} complete")
            progress = int((done / total) * 20)
            bar = "█" * progress + "░" * (20 - progress)
            print(f"   [{bar}]")
            print("")

    # Count files created
    project_root = forge_path.parent
    created_files = []
    for f in project_root.rglob("*"):
        if f.is_file() and ".forge" not in str(f) and "venv" not in str(f):
            if not f.name.startswith("."):
                created_files.append(f)

    if created_files:
        print(f"📁 Files: {len(created_files)}")

        # Count lines of code
        total_lines = 0
        for f in created_files:
            try:
                total_lines += len(f.read_text().splitlines())
            except Exception:
                pass
        if total_lines > 0:
            print(f"📝 Lines: {total_lines}")


def cmd_sprint_wrap(args):
    """Wrap up sprint and generate summary."""
    forge_path = Path(FORGE_DIR)

    if not forge_path.exists():
        print("No .forge/ directory found.")
        return

    config = load_sundai_config()

    if "sprint_start" not in config:
        print("No active sprint to wrap up.")
        return

    # Calculate elapsed time
    start = datetime.fromisoformat(config["sprint_start"])
    elapsed = datetime.now() - start
    hours = int(elapsed.total_seconds() // 3600)
    minutes = int((elapsed.total_seconds() % 3600) // 60)

    # Get project name from spec
    spec_file = forge_path / "spec.md"
    project_name = "Project"
    description = ""
    if spec_file.exists():
        content = spec_file.read_text()
        match = re.search(r"#\s*Project:\s*(.+)", content)
        if match:
            project_name = match.group(1).strip()
        what_match = re.search(r"##\s*What\s*\n(.+?)(?=\n##|\Z)", content, re.DOTALL)
        if what_match:
            description = what_match.group(1).strip().split("\n")[0]

    # Count files and lines
    project_root = forge_path.parent
    created_files = []
    for f in project_root.rglob("*"):
        if f.is_file() and ".forge" not in str(f) and "venv" not in str(f):
            if not f.name.startswith("."):
                created_files.append(f)

    total_lines = 0
    for f in created_files:
        try:
            total_lines += len(f.read_text().splitlines())
        except Exception:
            pass

    # Generate summary
    summary = f"""# Sprint Summary

## {project_name}
{description}

## Stats
- **Time**: {hours}h {minutes}m
- **Files**: {len(created_files)}
- **Lines of code**: {total_lines}

## Files Created
"""
    for f in sorted(created_files)[:20]:
        relative = f.relative_to(project_root)
        summary += f"- {relative}\n"

    if len(created_files) > 20:
        summary += f"- ... and {len(created_files) - 20} more\n"

    # Save summary
    summary_path = forge_path / "sprint-summary.md"
    summary_path.write_text(summary)

    print("🎉 Sprint complete!")
    print("")
    print(f"   Project: {project_name}")
    print(f"   Time: {hours}h {minutes}m")
    print(f"   Files: {len(created_files)}")
    print(f"   Lines: {total_lines}")
    print("")
    print(f"Summary saved to: {summary_path}")
