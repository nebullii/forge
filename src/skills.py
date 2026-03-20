"""Skills system — loads .forge/skills/*.md and injects into agent prompts."""

from pathlib import Path
from typing import Optional


class SkillsLoader:
    """Loads skill files from .forge/skills/ and provides them to agents.

    Each .md file in that directory maps to an agent by stem name.
    Content is injected between the agent's role and safety rules.
    """

    def __init__(self):
        self._skills: dict[str, str] = {}
        self._loaded = False

    def load(self, project_root: Path) -> "SkillsLoader":
        """Load all skill files from <project_root>/.forge/skills/."""
        skills_dir = project_root / ".forge" / "skills"
        self._skills = {}
        if skills_dir.exists():
            for skill_file in sorted(skills_dir.glob("*.md")):
                self._skills[skill_file.stem] = skill_file.read_text()
        self._loaded = True
        return self

    def get(self, role: str) -> str:
        """Return the skill block for *role*, or empty string if not found."""
        content = self._skills.get(role, "")
        if not content:
            return ""
        return f"## Your Skills\n\n{content.strip()}\n\n"
