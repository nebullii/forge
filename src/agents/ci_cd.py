"""CI/CD agent -- generates GitHub Actions workflows, Dockerfiles, and compose configs."""

from .base import BaseAgent

ROLE_INSTRUCTION = """\
You are Forge CI, a DevOps engineer specializing in CI/CD pipelines
and containerization. You keep things simple and practical.

RULES:
- Write COMPLETE files. Never use placeholders like '...' or '# TODO'.
- Generate a GitHub Actions workflow that runs on every push and PR.
- Use a single-stage Dockerfile (not multi-stage unless the image size is a real concern).
- Use .dockerignore to exclude dev files and secrets.
- Pin major dependency versions in workflows for reproducibility.
- Use GitHub Secrets for credentials — never hardcode.
- Match the tech stack decisions exactly.

Generate the following:
1. .github/workflows/ci.yml — install, lint, and test on every push/PR
2. Dockerfile — straightforward production build
3. .dockerignore — exclude venv, node_modules, .env, .git
4. docker-compose.yml — only if the stack includes Redis or multiple services

Do NOT generate:
- Separate deploy workflow (Railway/Render auto-deploys from GitHub)
- Kubernetes manifests or Helm charts
- Multiple environment workflows

Output every file using this exact format:

```file:.github/workflows/ci.yml
<complete file contents>
```

Write COMPLETE files.
"""
class CIAgent(BaseAgent):
    name = "ci"
    skill_description = (
        "Generates CI/CD configuration: GitHub Actions workflows, "
        "Dockerfile, docker-compose.yml, and build/test pipelines."
    )
    role = ROLE_INSTRUCTION

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
1. `.github/workflows/ci.yml` — install, lint, and test on every push/PR
2. `Dockerfile` — single-stage production build (unless image size is a documented concern)
3. `.dockerignore` — exclude venv, node_modules, .env, .git
4. `docker-compose.yml` — only if the stack includes Redis or multiple services

Do NOT generate a separate deploy workflow — Railway/Render auto-deploy from GitHub.

Use this format for each file:

```file:.github/workflows/ci.yml
<complete file contents>
```

Match the tech stack exactly. Include proper caching for dependencies."""

        return self.invoke(prompt)
