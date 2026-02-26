"""Deploy agent -- generates cloud deployment configs for Railway, Render, Vercel, Fly.io."""

from .base import BaseAgent

# ── ADK agent factory ─────────────────────────────────────────────────────────

ADK_INSTRUCTION = """\
You are Forge Deploy, a cloud deployment specialist.

RULES:
- Write COMPLETE files. Never use placeholders like '...' or '# TODO'.
- Default to Railway if no platform is specified (free tier, easiest setup).
- Detect the target platform from the deploy template provided.
- Always include .env.example with every required variable documented.
- Generate a DEPLOY.md with step-by-step deployment instructions.
- Use health check endpoints for deployment verification.
- Never hardcode secrets — always use environment variables.

Generate:
1. Platform config file (railway.toml, render.yaml, vercel.json, or fly.toml)
2. .env.example — all required environment variables with descriptions
3. DEPLOY.md — deployment instructions

Output every file using this exact format:

```file:railway.toml
<complete file contents>
```

Write COMPLETE files.
"""


def create_deploy_agent(llm):
    """Create a Google ADK LlmAgent for the Deploy role.

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
        name="forge-deploy",
        description="Generates deployment configs for Railway, Render, Vercel, Fly.io.",
        model=llm,
        instruction=ADK_INSTRUCTION,
    )


class DeployAgent(BaseAgent):
    name = "deploy"
    skill_description = (
        "Generates deployment configuration files for cloud platforms: "
        "Railway, Render, Vercel, Fly.io, and others."
    )
    role = (
        "You are Forge Deploy, a cloud deployment specialist.\n\n"
        "RULES:\n"
        "- Write COMPLETE files. Never use placeholders like '...' or '# TODO'.\n"
        "- Generate configs for the target platform specified in deploy.md.\n"
        "- Default to Railway if no platform is specified (free tier friendly).\n"
        "- Always include environment variable documentation.\n"
        "- Generate a README section for deployment instructions.\n"
        "- Use health check endpoints for deployment verification.\n"
        "- Never hardcode secrets -- always use environment variables.\n\n"
        "When writing files, use this exact format for EACH file:\n\n"
        "```file:path/to/file.ext\n"
        "<complete file contents here>\n"
        "```\n\n"
        "Write every file in full."
    )

    # Platform-specific config files
    PLATFORM_FILES = {
        "railway": ["railway.toml"],
        "render": ["render.yaml"],
        "vercel": ["vercel.json"],
        "fly": ["fly.toml"],
        "heroku": ["Procfile", "app.json"],
    }

    def generate_deploy(
        self,
        spec: str,
        decisions: dict,
        deploy_template: str = "",
        rules: str = "",
    ) -> str:
        """Generate deployment config files. Returns raw LLM response."""
        import json

        decisions_str = json.dumps(decisions, indent=2) if isinstance(decisions, dict) else str(decisions)

        # Detect target platform from deploy template
        platform_hint = ""
        if deploy_template:
            dl = deploy_template.lower()
            for p in ["railway", "render", "vercel", "fly", "heroku"]:
                if p in dl:
                    platform_hint = f"\nTarget platform: {p.title()}"
                    break

        prompt = f"""\
## Project Specification
{spec}

## Tech Stack Decisions
{decisions_str}
{platform_hint}

## Deploy Template
{deploy_template or "(No deploy template -- use Railway as default)"}

Generate the COMPLETE deployment configuration:
1. Platform-specific config file (railway.toml, render.yaml, vercel.json, or fly.toml)
2. `Procfile` if needed
3. Environment variable documentation (.env.example)
4. Deployment instructions as a section in `DEPLOY.md`

Use this format for each file:

```file:railway.toml
<complete file contents>
```

Match the tech stack and target platform. Include all required environment variables."""

        return self.invoke(prompt)

    def handle_a2a_task(self, task):
        """A2A entry point for deployment config generation."""
        context = task.context or {}
        spec = context.get("spec", "")
        decisions = context.get("decisions", {})
        deploy_template = context.get("deploy_template", "")
        rules = context.get("rules", "")

        prompt_parts = [p.text for p in task.message.parts if hasattr(p, "text")]
        task_text = "\n".join(prompt_parts)

        if spec or decisions:
            response = self.generate_deploy(spec, decisions, deploy_template, rules)
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
                name="deploy_files",
                parts=[FilePart(path=fp, content=c) for fp, c in files],
            ))

        return TaskResult(id=task.id, status=TaskStatus.completed, artifacts=artifacts)
