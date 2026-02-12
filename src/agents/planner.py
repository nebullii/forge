"""Planner agent -- analyzes spec and produces a structured build plan."""

import re
import yaml
from pathlib import Path

from .base import BaseAgent


class PlannerAgent(BaseAgent):
    name = "planner"
    role = (
        "You are Forge Planner, a software architect that analyzes project "
        "specifications and creates structured build plans.\n\n"
        "You make practical technology decisions, preferring boring/proven technology. "
        "You optimize for simplicity, free-tier deployment, and fast iteration.\n\n"
        "When outputting a plan, you MUST use the exact YAML format specified in the "
        "prompt. Do not wrap the YAML in markdown code fences unless asked."
    )

    def analyze_and_plan(self, spec: str, rules: str, existing_files: str = "") -> dict:
        """Analyze spec + rules, return a structured plan as a dict."""
        prompt = self._build_plan_prompt(spec, rules, existing_files)
        response = self.invoke(prompt)
        return self._parse_plan(response)

    def plan_incremental(self, spec: str, rules: str, feature_description: str,
                         existing_files: str) -> dict:
        """Plan tasks to add a feature to an existing project."""
        prompt = f"""\
## Project Specification
{spec}

## Build Rules
{rules}

## Existing Project Files
{existing_files}

## Feature to Add
{feature_description}

Analyze the existing project and plan the tasks needed to add this feature.
Consider what files need to be created vs modified.

Output the plan as YAML with this exact structure:

decisions:
  changes_needed: "Brief summary of what needs to change"
  files_to_modify: [list of existing files to change]
  files_to_create: [list of new files]
  reasoning: "Why these changes"

tasks:
  - id: task_01
    name: "Task name"
    description: "Detailed description of what to do"
    agent: coder
    files: [files this task touches]
  - id: task_02
    name: "..."
    description: "..."
    agent: coder
    files: [...]

Output ONLY the YAML, nothing else."""

        response = self.invoke(prompt)
        return self._parse_plan(response)

    def _build_plan_prompt(self, spec: str, rules: str, existing_files: str) -> str:
        context_section = ""
        if existing_files and existing_files != "(No project files yet)":
            context_section = f"""
## Existing Project Files
{existing_files}

Note: This is an existing project. Plan tasks that build on what exists."""

        return f"""\
## Project Specification
{spec}

## Build Rules
{rules}
{context_section}

Analyze the specification and rules. Then output a structured build plan as YAML.

Requirements for the plan:
- Break the build into 3-8 focused tasks
- Each task should produce 1-4 files
- Order tasks so dependencies come first (data models before routes, etc.)
- First task should always be project setup (config files, dependencies)
- Last task should be integration / wiring everything together
- Keep tasks small enough that the AI can write complete files in one pass

Output the plan as YAML with this exact structure:

decisions:
  stack:
    language: "..."
    framework: "..."
    database: "..."
    styling: "..."
  architecture: "Brief description of how components connect"
  reasoning: "1-2 sentences on why these choices"

tasks:
  - id: task_01
    name: "Set up project structure and dependencies"
    description: "Create the project skeleton with package manifests and config files"
    agent: coder
    files: [requirements.txt, main.py]
  - id: task_02
    name: "..."
    description: "..."
    agent: coder
    files: [...]

Output ONLY the YAML, nothing else."""

    def _parse_plan(self, response: str) -> dict:
        """Parse the YAML plan from the LLM response."""
        text = response.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1])
            else:
                text = "\n".join(lines[1:])

        try:
            plan = yaml.safe_load(text)
        except yaml.YAMLError:
            yaml_match = re.search(r'```(?:yaml)?\n(.*?)```', response, re.DOTALL)
            if yaml_match:
                plan = yaml.safe_load(yaml_match.group(1))
            else:
                plan = yaml.safe_load(response)

        if not isinstance(plan, dict) or "tasks" not in plan:
            raise ValueError("Planner did not return a valid plan with tasks.")

        return plan
