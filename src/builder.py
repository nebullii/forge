"""Builder - orchestrates AI to build the project."""

import os
import re
import json
from pathlib import Path
from typing import Optional
from .config import Provider
from .providers import create_adapter, AIAdapter


SYSTEM_PROMPT = """You are Forge, an AI that builds complete software projects from scratch.

You receive a project specification and must:
1. Analyze requirements
2. Make technology decisions
3. Design architecture
4. Write all necessary code
5. Create deployment configuration

RULES:
- Use ONLY free-tier services and simple infrastructure
- Create a single deployable unit (no microservices)
- Write clean, production-ready code
- Include proper error handling
- Use environment variables for secrets
- Keep dependencies minimal

OUTPUT FORMAT:
When writing files, use this exact format:

```file:path/to/file.py
<file contents here>
```

When making decisions, be concise and practical.
When writing code, include the COMPLETE file - no placeholders or "..." shortcuts.
"""


class Builder:
    """Orchestrates the build process."""

    def __init__(self, provider: Provider, forge_path: Path, step_mode: bool = False):
        self.provider = provider
        self.adapter = create_adapter(provider)
        self.forge_path = forge_path
        self.step_mode = step_mode
        self.project_root = forge_path.parent

    def run(self):
        """Run the full build process."""
        # Load inputs
        spec = self._read_file("spec.md")
        rules = self._read_file("rules.md")

        # Phase 1: Analyze and decide
        print("📋 Phase 1: Analyzing spec and making decisions...")
        decisions = self._analyze_and_decide(spec, rules)
        self._write_file("decisions.md", decisions)

        # Phase 2: Plan tasks
        print("📝 Phase 2: Breaking down into tasks...")
        tasks = self._plan_tasks(spec, decisions)
        self._write_file("tasks.md", tasks)

        # Phase 3: Execute tasks
        print("🔨 Phase 3: Building...")
        self._execute_tasks(spec, decisions, tasks)

        # Phase 4: Create deployment config
        print("📦 Phase 4: Creating deployment config...")
        self._create_deploy_config(decisions)

    def _read_file(self, name: str) -> str:
        """Read a file from .forge/"""
        path = self.forge_path / name
        if path.exists():
            return path.read_text()
        return ""

    def _write_file(self, name: str, content: str):
        """Write a file to .forge/"""
        path = self.forge_path / name
        path.write_text(content)

    def _analyze_and_decide(self, spec: str, rules: str) -> str:
        """Have AI analyze spec and make tech decisions."""
        prompt = f"""Analyze this project specification and make technology decisions.

## Specification
{spec}

## Rules/Constraints
{rules}

## Your Task
1. Identify the core features needed
2. Choose a tech stack (language, framework, database, etc.)
3. Design a simple architecture
4. List what files need to be created

Be concise. Pick boring, proven technology. Optimize for simplicity and free deployment.

Output format:
# Decisions

## Tech Stack
- Language: [choice]
- Framework: [choice]
- Database: [choice]
- Hosting: [choice]

## Architecture
[Brief description of how components connect]

## Files to Create
- [file1.py] - [purpose]
- [file2.py] - [purpose]
...

## Reasoning
[1-2 sentences on why these choices]
"""

        response = self.adapter.chat(
            [{"role": "user", "content": prompt}],
            system=SYSTEM_PROMPT
        )
        return response

    def _plan_tasks(self, spec: str, decisions: str) -> str:
        """Break the build into executable tasks."""
        prompt = f"""Based on these decisions, create a task breakdown.

## Specification
{spec}

## Decisions
{decisions}

## Your Task
Create an ordered list of tasks to build this project.
Each task should be small enough to complete in one step.

Output format:
# Tasks

## Status
- [x] Task 1 (completed)
- [ ] Task 2 (pending)
...

## Task Details

### Task 1: [name]
**Goal**: [what this accomplishes]
**Files**: [files to create/modify]
**Dependencies**: [what must exist first]

### Task 2: [name]
...
"""

        response = self.adapter.chat(
            [{"role": "user", "content": prompt}],
            system=SYSTEM_PROMPT
        )
        return response

    def _execute_tasks(self, spec: str, decisions: str, tasks: str):
        """Execute each task by having AI write code."""
        # Parse tasks
        task_blocks = self._parse_tasks(tasks)

        for i, task in enumerate(task_blocks, 1):
            print(f"\n   [{i}/{len(task_blocks)}] {task['name']}")

            if self.step_mode:
                input("   Press Enter to continue...")

            # Get existing context
            context = self._get_project_context()

            prompt = f"""Execute this task by writing the necessary code.

## Project Spec
{spec}

## Decisions
{decisions}

## Current Task
{task['content']}

## Existing Files
{context}

## Instructions
Write the COMPLETE code for all files needed for this task.
Use this format for each file:

```file:path/to/file.py
<complete file contents>
```

Include ALL code - no placeholders, no "..." shortcuts.
Make sure imports and dependencies are correct.
"""

            response = self.adapter.chat(
                [{"role": "user", "content": prompt}],
                system=SYSTEM_PROMPT
            )

            # Extract and write files
            files_written = self._extract_and_write_files(response)
            for f in files_written:
                print(f"      ✓ {f}")

            # Save context for next task
            self._save_context(i, task['name'], response)

    def _parse_tasks(self, tasks_md: str) -> list[dict]:
        """Parse task markdown into structured tasks."""
        tasks = []
        # Find all ### Task N: headings
        pattern = r'### Task \d+: ([^\n]+)\n(.*?)(?=### Task|\Z)'
        matches = re.findall(pattern, tasks_md, re.DOTALL)

        for name, content in matches:
            tasks.append({
                'name': name.strip(),
                'content': content.strip()
            })

        # Fallback: if no structured tasks found, treat whole thing as one task
        if not tasks:
            tasks.append({
                'name': 'Build project',
                'content': tasks_md
            })

        return tasks

    def _get_project_context(self) -> str:
        """Get summary of existing project files."""
        context_parts = []

        for path in self.project_root.rglob("*"):
            if path.is_file():
                rel_path = path.relative_to(self.project_root)

                # Skip .forge, .git, __pycache__, venv, node_modules
                skip_dirs = {'.forge', '.git', '__pycache__', 'venv', 'node_modules', '.venv'}
                if any(part in skip_dirs for part in rel_path.parts):
                    continue

                # Skip binary files
                if path.suffix in {'.pyc', '.png', '.jpg', '.ico', '.woff', '.woff2'}:
                    continue

                try:
                    content = path.read_text()
                    # Truncate large files
                    if len(content) > 2000:
                        content = content[:2000] + "\n... (truncated)"
                    context_parts.append(f"### {rel_path}\n```\n{content}\n```")
                except:
                    pass

        if not context_parts:
            return "(No files yet)"

        return "\n\n".join(context_parts)

    def _extract_and_write_files(self, response: str) -> list[str]:
        """Extract file blocks from response and write them."""
        files_written = []

        # Match ```file:path/to/file.ext or ```path/to/file.ext
        pattern = r'```(?:file:)?([^\n`]+)\n(.*?)```'
        matches = re.findall(pattern, response, re.DOTALL)

        for filepath, content in matches:
            filepath = filepath.strip()

            # Skip if it looks like a language identifier, not a path
            if filepath in {'python', 'javascript', 'typescript', 'json', 'yaml', 'bash', 'sh', 'html', 'css', 'sql', 'markdown', 'md'}:
                continue

            # Clean up path
            if filepath.startswith('/'):
                filepath = filepath[1:]

            full_path = self.project_root / filepath
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content.strip() + '\n')
            files_written.append(filepath)

        return files_written

    def _save_context(self, task_num: int, task_name: str, response: str):
        """Save task execution context for debugging."""
        context_dir = self.forge_path / "context"
        context_dir.mkdir(exist_ok=True)

        safe_name = re.sub(r'[^\w\-]', '_', task_name)[:30]
        context_file = context_dir / f"{task_num:02d}_{safe_name}.md"
        context_file.write_text(f"# Task {task_num}: {task_name}\n\n{response}")

    def _create_deploy_config(self, decisions: str):
        """Create deployment configuration files."""
        # Detect what kind of project this is
        has_requirements = (self.project_root / "requirements.txt").exists()
        has_package_json = (self.project_root / "package.json").exists()
        has_go_mod = (self.project_root / "go.mod").exists()

        if has_requirements:
            self._create_python_deploy()
        elif has_package_json:
            self._create_node_deploy()
        elif has_go_mod:
            self._create_go_deploy()
        else:
            # Ask AI to figure it out
            self._create_generic_deploy(decisions)

    def _create_python_deploy(self):
        """Create Dockerfile and config for Python project."""
        # Check for common entry points
        entry_point = "app.py"
        for candidate in ["app.py", "main.py", "server.py", "api.py"]:
            if (self.project_root / candidate).exists():
                entry_point = candidate
                break

        dockerfile = f"""FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "{entry_point}"]
"""
        (self.project_root / "Dockerfile").write_text(dockerfile)
        print("      ✓ Dockerfile")

        # Cloud Run config
        self._create_cloudrun_config()

    def _create_node_deploy(self):
        """Create Dockerfile for Node.js project."""
        dockerfile = """FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY . .

EXPOSE 8080

CMD ["npm", "start"]
"""
        (self.project_root / "Dockerfile").write_text(dockerfile)
        print("      ✓ Dockerfile")
        self._create_cloudrun_config()

    def _create_go_deploy(self):
        """Create Dockerfile for Go project."""
        dockerfile = """FROM golang:1.21-alpine AS builder

WORKDIR /app
COPY . .
RUN go build -o main .

FROM alpine:latest
WORKDIR /app
COPY --from=builder /app/main .

EXPOSE 8080

CMD ["./main"]
"""
        (self.project_root / "Dockerfile").write_text(dockerfile)
        print("      ✓ Dockerfile")
        self._create_cloudrun_config()

    def _create_generic_deploy(self, decisions: str):
        """Have AI create deployment config."""
        prompt = f"""Create a Dockerfile for this project.

## Decisions
{decisions}

## Existing Files
{self._get_project_context()}

Create a minimal Dockerfile that:
1. Uses an appropriate base image
2. Installs dependencies
3. Copies source code
4. Exposes port 8080
5. Runs the application

Output only the Dockerfile:

```file:Dockerfile
<contents>
```
"""

        response = self.adapter.chat(
            [{"role": "user", "content": prompt}],
            system=SYSTEM_PROMPT
        )
        self._extract_and_write_files(response)
        self._create_cloudrun_config()

    def _create_cloudrun_config(self):
        """Create Cloud Run deployment script."""
        deploy_script = """#!/bin/bash
# Deploy to Google Cloud Run (free tier)

set -e

PROJECT_ID="${GCLOUD_PROJECT:-$(gcloud config get-value project)}"
SERVICE_NAME="${SERVICE_NAME:-$(basename $(pwd))}"
REGION="${REGION:-us-central1}"

echo "🚀 Deploying $SERVICE_NAME to Cloud Run..."

# Build and deploy
gcloud run deploy "$SERVICE_NAME" \\
    --source . \\
    --region "$REGION" \\
    --platform managed \\
    --allow-unauthenticated \\
    --memory 256Mi \\
    --cpu 1 \\
    --min-instances 0 \\
    --max-instances 2

echo ""
echo "✅ Deployed!"
gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)'
"""
        deploy_path = self.project_root / "deploy.sh"
        deploy_path.write_text(deploy_script)
        deploy_path.chmod(0o755)
        print("      ✓ deploy.sh")
