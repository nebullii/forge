"""Knowledge base for Forge — stores and retrieves user feedback across builds.

Learnings are stored in ~/.forge/knowledge.md as human-readable markdown.
Agents read this file before planning so past feedback improves future builds.
"""

from datetime import datetime
from pathlib import Path

KNOWLEDGE_FILE = Path.home() / ".forge" / "knowledge.md"


def load() -> str:
    """Return the full knowledge base as a string, or empty string if none."""
    if KNOWLEDGE_FILE.exists():
        return KNOWLEDGE_FILE.read_text().strip()
    return ""


def add(feedback: str, template: str = "") -> None:
    """Append a feedback entry to the knowledge base.

    Args:
        feedback: Free-form feedback text from the user
        template: Template name used for this build (e.g. 'web-app')
    """
    date = datetime.now().strftime("%Y-%m-%d")
    header = f"{date} | {template}" if template else date
    entry = f"\n## {header}\n\n{feedback.strip()}\n\n---\n"

    KNOWLEDGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KNOWLEDGE_FILE, "a") as f:
        f.write(entry)


def collect_feedback(template: str = "") -> bool:
    """Prompt the user for build feedback interactively.

    Returns True if feedback was saved, False if skipped.
    """
    print()
    print("Any feedback on this build? (press Enter to skip)")
    print("This helps agents make better decisions on future builds.")
    print()

    lines = []
    try:
        while True:
            line = input("> ").rstrip()
            if not line:
                break
            lines.append(line)
    except (KeyboardInterrupt, EOFError):
        print()
        return False

    feedback = "\n".join(lines).strip()
    if not feedback:
        return False

    add(feedback, template)
    print("Saved to ~/.forge/knowledge.md")
    return True
