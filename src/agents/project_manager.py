"""Project Manager agent -- enriches build plans with role-specific agent prompts."""

import re
import yaml

from .base import BaseAgent


# ── ADK agent factory ─────────────────────────────────────────────────────────

ADK_INSTRUCTION = """\
You are Forge Project Manager, a technical lead that takes a build plan and
enriches it by assigning each task to the right specialized agent and writing
a detailed, self-contained prompt that agent can execute without needing the
full project spec.

AGENT ROLES:
- backend  — API routes, DB models, services, auth, business logic
- frontend — React components, pages, routing, state, API integration
- coder    — project setup, config files, utilities, scripts, glue code
- ci       — GitHub Actions workflows, Dockerfile, docker-compose
- deploy   — Railway/Render/Vercel/Fly.io deployment configs
- security — security audits (assign only if task is explicitly a security review)

RULES FOR ENRICHED PROMPTS:
- Each prompt must be SELF-CONTAINED: include stack, architecture, and file list
- Backend tasks: list the API endpoints/contracts this task exposes
- Frontend tasks: list the backend contracts this task consumes
- CI/Deploy tasks: include the stack so the agent knows what runtime to target
- Coder tasks: list exact files and what each should contain

Output ONLY YAML in this exact format — no markdown fences:

tasks:
  - id: task_01
    name: "..."
    agent: coder
    prompt: |
      <full self-contained prompt for the assigned agent>
    contracts: ""
  - id: task_02
    name: "..."
    agent: backend
    prompt: |
      <full self-contained prompt for the assigned agent>
    contracts: |
      POST /some/endpoint → {field: type}
"""


def create_project_manager_agent(llm):
    """Create a Google ADK LlmAgent for the Project Manager role."""
    try:
        from google.adk.agents import LlmAgent
    except ImportError:
        raise ImportError("google-adk required. Install: pip install 'forge-ai[adk]'")

    return LlmAgent(
        name="forge-project-manager",
        description=(
            "Enriches build plans: assigns each task to the right specialized agent "
            "and generates a targeted, self-contained prompt per task."
        ),
        model=llm,
        instruction=ADK_INSTRUCTION,
    )


# ── Classic mode agent ─────────────────────────────────────────────────────────

_VALID_AGENTS = {"backend", "frontend", "coder", "ci", "deploy", "security"}


class ProjectManagerAgent(BaseAgent):
    name = "project_manager"
    skill_description = (
        "Enriches build plans by assigning each task to the right specialized agent "
        "and generating a detailed, self-contained prompt per task."
    )
    role = (
        "You are Forge Project Manager, a technical lead that takes a build plan and "
        "enriches it by assigning each task to the right specialized agent and writing "
        "a detailed, self-contained prompt for that agent.\n\n"
        "AGENT ROLES:\n"
        "- backend  — API routes, DB models, services, auth, business logic\n"
        "- frontend — React components, pages, routing, state, API integration\n"
        "- coder    — project setup, config files, utilities, scripts, glue code\n"
        "- ci       — GitHub Actions workflows, Dockerfile, docker-compose\n"
        "- deploy   — Railway/Render/Vercel/Fly.io deployment configs\n"
        "- security — security audits (only if task is explicitly a security review)\n\n"
        "Each prompt must be SELF-CONTAINED and include stack, architecture, file list, "
        "and any API contracts to expose or consume.\n\n"
        "Output ONLY YAML, no markdown fences."
    )

    def enrich_plan(self, plan: dict, spec: str, rules: str) -> dict:
        """Enrich a build plan with agent assignments and per-task prompts.

        Makes a single LLM call with all tasks at once.

        Args:
            plan: Dict with 'decisions' and 'tasks' keys (from PlannerAgent)
            spec: Full project spec text
            rules: Full build rules text

        Returns:
            Dict with 'tasks' list where each task has 'agent', 'prompt', 'contracts'
        """
        prompt = self._build_enrich_prompt(plan, spec, rules)
        response = self.invoke(prompt)
        return self._parse_enriched_plan(response, plan)

    def _build_enrich_prompt(self, plan: dict, spec: str, rules: str) -> str:
        decisions = plan.get("decisions", {})
        tasks = plan.get("tasks", [])

        tasks_yaml = yaml.dump(tasks, default_flow_style=False, sort_keys=False)

        stack = decisions.get("stack", {})
        arch = decisions.get("architecture", "")

        stack_lines = "\n".join(f"  {k}: {v}" for k, v in stack.items()) if stack else "  (see spec)"

        return f"""\
## Project Specification
{spec}

## Build Rules
{rules}

## Tech Stack Decisions
{stack_lines}

## Architecture
{arch or "(see spec)"}

## Tasks from Planner
{tasks_yaml}

For each task above, output:
1. The correct agent assignment (backend / frontend / coder / ci / deploy / security)
2. A self-contained prompt that agent can execute without needing the full spec
3. API contracts this task exposes (empty string if none)

Rules for prompts:
- Backend tasks: describe endpoints to create, DB schema, auth requirements
- Frontend tasks: describe pages/components + list backend contracts to consume
- CI tasks: include the full stack so the agent knows which runtime/language
- Deploy tasks: include stack + target platform from spec
- Coder tasks: list exact files and their purpose

Output ONLY YAML in this exact format:

tasks:
  - id: task_01
    name: "..."
    agent: coder
    prompt: |
      <full self-contained instructions>
    contracts: ""
  - id: task_02
    name: "..."
    agent: backend
    prompt: |
      <full self-contained instructions>
    contracts: |
      POST /endpoint → {{field: type}}

Output ONLY the YAML, nothing else."""

    def _parse_enriched_plan(self, response: str, original_plan: dict) -> dict:
        """Parse the enriched plan YAML, falling back to original tasks on error."""
        text = response.strip()

        # Strip markdown fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            end = next((i for i in range(len(lines) - 1, 0, -1) if lines[i].strip() == "```"), -1)
            if end > 0:
                text = "\n".join(lines[1:end])
            else:
                text = "\n".join(lines[1:])

        try:
            parsed = yaml.safe_load(text)
        except yaml.YAMLError:
            yaml_match = re.search(r'```(?:yaml)?\n(.*?)```', response, re.DOTALL)
            if yaml_match:
                parsed = yaml.safe_load(yaml_match.group(1))
            else:
                return {"tasks": original_plan.get("tasks", [])}

        if not isinstance(parsed, dict) or "tasks" not in parsed:
            return {"tasks": original_plan.get("tasks", [])}

        # Validate and sanitize agent fields
        for task in parsed["tasks"]:
            agent = task.get("agent", "coder")
            if agent not in _VALID_AGENTS:
                task["agent"] = "coder"

        return parsed

    def handle_a2a_task(self, task):
        """A2A entry point: receives plan + spec/rules in context, returns enriched plan."""
        from ..a2a.types import TaskResult, TaskStatus, Artifact, TextPart

        context = task.context or {}
        plan = context.get("plan", {})
        spec = context.get("spec", "")
        rules = context.get("rules", "")

        if not plan:
            # Try to extract from message text
            parts = [p.text for p in task.message.parts if hasattr(p, "text")]
            spec = "\n".join(parts)

        try:
            enriched = self.enrich_plan(plan, spec, rules)
            summary = f"Enriched {len(enriched.get('tasks', []))} tasks with agent assignments.\n"
            for t in enriched.get("tasks", []):
                summary += f"  → {t.get('id', '?')} '{t.get('name', '')}' → {t.get('agent', '?')}\n"

            return TaskResult(
                id=task.id,
                status=TaskStatus.completed,
                artifacts=[
                    Artifact(
                        type="plan",
                        name="enriched_plan",
                        parts=[TextPart(text=summary)],
                        data=enriched,
                    )
                ],
            )
        except Exception as e:
            return TaskResult(id=task.id, status=TaskStatus.failed, error=str(e))
