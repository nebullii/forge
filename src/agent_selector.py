"""Agent selection — recommends, parses, and displays which agents to run."""

from __future__ import annotations

from typing import Optional

# Ordered by execution phase. Planner and ProjectManager are pipeline
# infrastructure and are not user-selectable.
ALL_AGENTS: list[str] = [
    "backend",
    "frontend",
    "ci",
    "deploy",
    "security",
    "reviewer",
]

AGENT_DESCRIPTIONS: dict[str, str] = {
    "backend":  "API routes, database models, service layer",
    "frontend": "UI components, routing, state, API integration",
    "ci":       "GitHub Actions workflows, Dockerfile, docker-compose",
    "deploy":   "Railway / Render / Vercel / Fly.io deployment configs",
    "security": "OWASP audit, secret detection, code hardening",
    "reviewer": "Cross-cutting review and auto-fix (always last)",
}

# Framework names that imply a CLI tool — no frontend, deploy is optional.
_CLI_FRAMEWORKS = {"click", "typer", "cobra", "clap", "urfave", "argparse"}


class AgentSelector:
    """Recommends and validates the set of agents to run for a given build."""

    def suggest(self, decisions: dict) -> list[str]:
        """Return recommended agent names based on planner decisions.

        Args:
            decisions: The ``decisions`` dict from PlannerAgent, containing
                       at minimum a ``stack`` sub-dict.

        Returns:
            Ordered list of agent names to run, always ending with reviewer.
        """
        stack = decisions.get("stack", {})
        framework = (stack.get("framework") or "").lower()
        frontend  = (stack.get("frontend")  or "").lower()

        is_cli     = any(fw in framework for fw in _CLI_FRAMEWORKS)
        has_frontend = frontend not in ("", "none", "n/a", "-") and not is_cli

        agents: list[str] = ["backend"]

        if has_frontend:
            agents.append("frontend")

        agents.append("ci")

        if not is_cli:
            agents.append("deploy")

        agents.append("security")
        agents.append("reviewer")
        return agents

    def format_suggestion(self, agents: list[str], decisions: dict) -> str:
        """Return a human-readable summary of the agent set.

        Args:
            agents:    Agent names as returned by ``suggest()``.
            decisions: Planner decisions dict (used to show stack context).
        """
        stack = decisions.get("stack", {})
        lines: list[str] = ["Recommended agents for this build:", ""]

        for name in agents:
            desc = AGENT_DESCRIPTIONS.get(name, "")
            lines.append(f"  {name:<10}  {desc}")

        lines.append("")

        stack_parts = [
            v for k, v in stack.items()
            if v and str(v).lower() not in ("none", "n/a", "-", "")
        ]
        if stack_parts:
            lines.append(f"Stack: {' · '.join(str(p) for p in stack_parts)}")

        return "\n".join(lines)

    def parse_flag(self, agents_str: str) -> list[str]:
        """Parse the --agents flag value into a validated list of agent names.

        Args:
            agents_str: One of:
                - ``"auto"`` — returns empty list (caller should use suggest())
                - ``"all"``  — returns all agents in ALL_AGENTS
                - ``"backend,ci,deploy"`` — explicit comma-separated list

        Returns:
            List of validated agent name strings (lowercase).

        Raises:
            ValueError: If any name is not in ALL_AGENTS.
        """
        value = agents_str.strip().lower()

        if value == "auto":
            return []  # sentinel: caller resolves via suggest()

        if value == "all":
            return list(ALL_AGENTS)

        names = [n.strip() for n in value.split(",") if n.strip()]
        unknown = [n for n in names if n not in ALL_AGENTS]
        if unknown:
            raise ValueError(
                f"Unknown agent(s): {', '.join(unknown)}. "
                f"Valid: {', '.join(ALL_AGENTS)}"
            )
        return names
