"""CI/CD agent -- generates GitHub Actions workflows, Dockerfiles, and compose configs."""

from .base import BaseAgent

# ── ADK agent factory ─────────────────────────────────────────────────────────

ADK_INSTRUCTION = """\
You are Forge CI, a DevOps engineer specializing in CI/CD pipelines
and containerization.

RULES:
- Write COMPLETE files. Never use placeholders like '...' or '# TODO'.
- Generate GitHub Actions workflows that lint, test, and build on every PR.
- Use Docker multi-stage builds to minimize image size.
- Use .dockerignore to exclude unnecessary files.
- Pin dependency versions in workflows for reproducibility.
- Use GitHub Secrets for API keys and credentials (never hardcode).
- Match the tech stack decisions exactly.

Generate ALL of the following:
1. .github/workflows/ci.yml — lint and test on every push/PR
2. .github/workflows/deploy.yml — build and deploy on merge to main
3. Dockerfile — production-ready multi-stage build
4. .dockerignore — exclude dev files and secrets
5. docker-compose.yml — local development setup

Output every file using this exact format:

```file:.github/workflows/ci.yml
<complete file contents>
```

Write COMPLETE files.
"""


def create_ci_agent(llm):
    """Create a Google ADK LlmAgent for the CI/CD role.

    Args:
        llm: A google.adk BaseLlm instance (e.g. from create_forge_llm())

    Returns:
        google.adk.agents.LlmAgent
    """
    try:
        from google.adk.agents import LlmAgent
    except ImportError:
        raise ImportError("google-adk required. Install: pip install 'forge-ai[adk]'")

    return LlmAgent(
        name="forge-ci",
        description="Generates CI/CD: GitHub Actions workflows, Dockerfile, docker-compose.",
        model=llm,
        instruction=ADK_INSTRUCTION,
    )


class CIAgent(BaseAgent):
    name = "ci"
    skill_description = (
        "Generates CI/CD configuration: GitHub Actions workflows, "
        "Dockerfile, docker-compose.yml, and build/test pipelines."
    )
    role = (
        "You are Forge CI, a DevOps engineer specializing in CI/CD pipelines "
        "and containerization.\n\n"
        "RULES:\n"
        "- Write COMPLETE files. Never use placeholders like '...' or '# TODO'.\n"
        "- Generate GitHub Actions workflows that: lint, test, and build.\n"
        "- Use Docker multi-stage builds to minimize image size.\n"
        "- Use .dockerignore to exclude unnecessary files.\n"
        "- Pin dependency versions in workflows for reproducibility.\n"
        "- Use secrets for API keys and credentials (never hardcode).\n"
        "- Match the tech stack chosen by the planner exactly.\n\n"
        "When writing files, use this exact format for EACH file:\n\n"
        "```file:path/to/file.ext\n"
        "<complete file contents here>\n"
        "```\n\n"
        "Write every file in full."
    )

    def generate_ci(self, spec: str, decisions: dict, rules: str = "") -> str:
        """Generate CI/CD config files. Returns raw LLM response."""
        import json

        decisions_str = json.dumps(decisions, indent=2) if isinstance(decisions, dict) else str(decisions)

        prompt = f"""\
## Project Specification
{spec}

## Tech Stack Decisions
{decisions_str}

## Build Rules
{rules or "(Use sensible defaults)"}

Generate the COMPLETE CI/CD configuration:
1. `.github/workflows/ci.yml` -- lint + test on every push/PR
2. `.github/workflows/deploy.yml` -- build and deploy on merge to main
3. `Dockerfile` -- production-ready multi-stage build
4. `.dockerignore` -- exclude dev files and secrets
5. `docker-compose.yml` -- local development setup

Use this format for each file:

```file:.github/workflows/ci.yml
<complete file contents>
```

Match the tech stack exactly. Include proper caching for dependencies."""

        return self.invoke(prompt)

    def handle_a2a_task(self, task):
        """A2A entry point for CI/CD generation."""
        context = task.context or {}
        spec = context.get("spec", "")
        decisions = context.get("decisions", {})
        rules = context.get("rules", "")

        prompt_parts = [p.text for p in task.message.parts if hasattr(p, "text")]
        task_text = "\n".join(prompt_parts)

        if spec or decisions:
            response = self.generate_ci(spec, decisions, rules)
        else:
            response = self.invoke(task_text)

        files = self.extract_files(response)

        from ..a2a.types import TaskResult, TaskStatus, Artifact, TextPart, FilePart

        artifacts = [
            Artifact(type="text", name="response", parts=[TextPart(text=response)])
        ]
        if files:
            artifacts.append(Artifact(
                type="files",
                name="ci_files",
                parts=[FilePart(path=fp, content=c) for fp, c in files],
            ))

        return TaskResult(id=task.id, status=TaskStatus.completed, artifacts=artifacts)
