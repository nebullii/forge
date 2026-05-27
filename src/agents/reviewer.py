"""Reviewer agent -- validates generated code for correctness."""

import json
import re
import yaml

from .base import BaseAgent

ROLE_INSTRUCTION = """\
You are Forge Reviewer, a code review specialist. You check generated code
for correctness, consistency, and completeness.

You look for:
- Missing imports or undefined references
- Inconsistent API contracts (frontend calls endpoint that backend does not define)
- Missing files that are imported or referenced
- Security issues (hardcoded secrets, SQL injection, etc.)
- Missing error handling for critical paths

Output ONLY a single JSON object:
{
  "passed": true,
  "issues": [
    {"file": "path/to/file", "severity": "error", "message": "Description of the issue"}
  ]
}
"""
class ReviewerAgent(BaseAgent):
    name = "reviewer"
    skill_description = (
        "Cross-cutting code review: validates correctness, consistency, "
        "API contracts, imports, and security across all generated files."
    )
    role = (
        "You are Forge Reviewer, a code review specialist. You check generated code "
        "for correctness, consistency, and completeness.\n\n"
        "You look for:\n"
        "- Missing imports\n"
        "- Undefined references between files\n"
        "- Inconsistent API contracts (e.g., frontend calls endpoint that backend doesn't define)\n"
        "- Missing error handling\n"
        "- Security issues (hardcoded secrets, SQL injection, etc.)\n"
        "- Files that reference other files that don't exist\n\n"
        "Be concise. Only report actual issues, not style preferences."
    )

    def review_files(self, files_written: dict[str, str], spec: str,
                     rules: str) -> dict:
        """Review a set of generated files.

        Returns:
            {"passed": True/False, "issues": [{"file": ..., "severity": ..., "message": ...}]}
        """
        files_str = ""
        for fp, content in files_written.items():
            files_str += f"\n### {fp}\n```\n{content}\n```\n"

        prompt = f"""\
## Project Spec
{spec}

## Build Rules
{rules}

## Generated Files
{files_str}

Review these files for correctness. Check for:
1. Missing imports or undefined references
2. Inconsistent API contracts between frontend and backend
3. Missing files that are imported/referenced
4. Security issues (hardcoded secrets, injection vulnerabilities)
5. Missing error handling for critical paths

Output ONLY this JSON object:
{{
  "passed": true,
  "issues": [
    {{"file": "path/to/file", "severity": "error", "message": "Description of the issue"}}
  ]
}}

If no issues found, return:
{{
  "passed": true,
  "issues": []
}}"""

        response = self.invoke_json(prompt)
        return self._parse_review(response)

    def _parse_review(self, response: str) -> dict:
        text = response.strip()

        try:
            result = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            result = None
        if isinstance(result, dict):
            return {
                "passed": result.get("passed", True),
                "issues": result.get("issues", []),
            }

        if text.startswith("```"):
            lines = text.split("\n")
            if lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1])
            else:
                text = "\n".join(lines[1:])

        try:
            result = yaml.safe_load(text)
        except yaml.YAMLError:
            yaml_match = re.search(r'```(?:yaml)?\n(.*?)```', response, re.DOTALL)
            if yaml_match:
                try:
                    result = yaml.safe_load(yaml_match.group(1))
                except yaml.YAMLError:
                    return {"passed": True, "issues": []}
            else:
                return {"passed": True, "issues": []}

        if not isinstance(result, dict):
            return {"passed": True, "issues": []}

        return {
            "passed": result.get("passed", True),
            "issues": result.get("issues", []),
        }
