"""Coder agent -- generates complete file contents for a given task."""

from .base import BaseAgent


class CoderAgent(BaseAgent):
    name = "coder"
    role = (
        "You are Forge Coder, an expert software developer that writes complete, "
        "production-ready code.\n\n"
        "RULES:\n"
        "- Write COMPLETE files. Never use placeholders like '...' or '# TODO: implement'.\n"
        "- Every file must be fully functional.\n"
        "- Include proper imports, error handling, and comments where logic is non-obvious.\n"
        "- Follow the project's build rules exactly.\n"
        "- Use the structured JSON output format specified in the prompt.\n\n"
        "When writing files, return a single JSON object:\n\n"
        "{\n"
        '  "files": [{"path": "path/to/file.ext", "content": "<complete file contents here>"}]\n'
        "}\n\n"
        "Write every file in full. Do not skip any file."
    )

    def generate_files(self, task: dict, spec: str, rules: str,
                       decisions: str, project_context: str, on_chunk=None) -> str:
        """Generate code for a single task. Returns raw LLM response."""
        prompt = f"""\
## Project Specification
{spec}

## Build Rules
{rules}

## Architecture Decisions
{decisions}

## Current Task
**{task['name']}**
{task['description']}

**Files to produce:** {', '.join(task.get('files', []))}

## Existing Project Context
{project_context}

Write the COMPLETE contents of each file for this task.
Return ONLY this JSON object:
{{
  "files": [
    {{"path": "path/to/filename.ext", "content": "<complete file contents>"}}
  ]
}}

Important:
- Write COMPLETE files, not snippets
- Include all imports
- Include proper error handling
- Follow the build rules exactly
- If modifying an existing file, output the ENTIRE updated file"""

        if on_chunk is not None:
            return self.invoke_streaming(prompt, on_chunk=on_chunk, json_mode=True)
        return self.invoke_json(prompt)

    def fix_file(self, filepath: str, current_content: str, issue: str,
                 spec: str, rules: str) -> str:
        """Fix a specific file based on a review issue."""
        prompt = f"""\
## Build Rules
{rules}

## File to Fix
**{filepath}**

Current content:
```
{current_content}
```

## Issue to Fix
{issue}

Output ONLY this JSON object:
{{
  "files": [
    {{"path": "{filepath}", "content": "<complete corrected file contents>"}}
  ]
}}"""

        return self.invoke_json(prompt)
