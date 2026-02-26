"""ADK tool functions for the Forge orchestrator agent.

Each function is an ADK-compatible tool that the orchestrator LLM can call.
Tools make A2A calls to specialized agents and collect results into shared state.

Tool design rules:
- Simple parameter types only (str, int, bool) — ADK converts these to JSON schema
- Docstring is used as the tool description shown to the LLM
- Return a plain string summary that the LLM can reason about
- Side-effect: write files/decisions into the shared BuildArtifacts state
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class BuildArtifacts:
    """Shared state written to by tools, read by orchestrator after run."""
    decisions: Dict = field(default_factory=dict)
    tasks: List = field(default_factory=list)
    files: List[Tuple[str, str]] = field(default_factory=list)  # (path, content)
    errors: List[str] = field(default_factory=list)
    review: Optional[Dict] = None


def make_agent_tools(clients: dict, artifacts: BuildArtifacts, deploy_md: str = "") -> list:
    """Create all ADK tool functions bound to the given A2A clients and shared artifacts.

    Args:
        clients: dict of agent_name → A2AClient
        artifacts: shared BuildArtifacts that tools write into
        deploy_md: contents of .forge/deploy.md (for DeployAgent)

    Returns:
        List of plain Python functions usable as ADK tools
    """
    from ..a2a.types import Task, Message, TextPart

    def _send(agent_name: str, text: str, context: dict = None):
        client = clients.get(agent_name)
        if client is None:
            raise RuntimeError(f"Agent '{agent_name}' not registered")
        task = Task(
            message=Message(role="user", parts=[TextPart(text=text)]),
            context=context or {},
        )
        return client.send_task(task)

    # ── Tools ─────────────────────────────────────────────────────────────────

    def call_planner(spec: str, rules: str) -> str:
        """Analyze the project specification and return a structured build plan.

        Call this FIRST. Returns the tech stack decisions and an ordered list of
        build tasks. You must call this before any other agent.

        Args:
            spec: Full contents of the project spec (.forge/spec.md)
            rules: Full contents of the build rules (.forge/rules.md)
        """
        result = _send(
            "planner",
            f"Analyze this specification and produce a structured build plan.\n\n"
            f"## Spec\n{spec}\n\n## Rules\n{rules}",
        )
        if not result.success:
            artifacts.errors.append(f"Planner failed: {result.error}")
            return f"ERROR: Planner failed — {result.error}"

        plan = result.get_data() or {}
        artifacts.decisions = plan.get("decisions", {})
        artifacts.tasks = plan.get("tasks", [])

        summary = (
            f"Plan ready. {len(artifacts.tasks)} tasks.\n"
            f"Stack: {json.dumps(artifacts.decisions.get('stack', {}))}\n"
            f"Architecture: {artifacts.decisions.get('architecture', '')}"
        )
        return summary

    def call_backend_agent(spec: str, rules: str) -> str:
        """Generate complete backend code: API routes, database models, and service layer.

        Call this after call_planner. Generates all backend source files.

        Args:
            spec: Full contents of the project spec
            rules: Full contents of the build rules
        """
        decisions_str = json.dumps(artifacts.decisions, indent=2)
        result = _send(
            "backend",
            f"Generate backend code (API routes, DB models, service layer).\n\n"
            f"## Spec\n{spec}\n\n## Rules\n{rules}\n\n## Decisions\n{decisions_str}",
            context={"decisions": artifacts.decisions, "spec": spec, "rules": rules},
        )
        if not result.success:
            artifacts.errors.append(f"Backend failed: {result.error}")
            return f"ERROR: Backend failed — {result.error}"

        files = result.get_files()
        artifacts.files.extend(files)
        paths = [f[0] for f in files]
        return f"Backend complete. {len(files)} files: {', '.join(paths[:5])}{'...' if len(paths) > 5 else ''}"

    def call_frontend_agent(spec: str, rules: str) -> str:
        """Generate frontend code: React components, routing, state, and API integration.

        Call this after call_backend_agent so it can match API contracts.

        Args:
            spec: Full contents of the project spec
            rules: Full contents of the build rules
        """
        decisions_str = json.dumps(artifacts.decisions, indent=2)
        backend_paths = [f[0] for f in artifacts.files]
        result = _send(
            "frontend",
            f"Generate frontend code (React components, pages, routing, API integration).\n\n"
            f"## Spec\n{spec}\n\n## Rules\n{rules}\n\n## Decisions\n{decisions_str}",
            context={
                "decisions": artifacts.decisions,
                "spec": spec,
                "rules": rules,
                "backend_files": backend_paths,
            },
        )
        if not result.success:
            artifacts.errors.append(f"Frontend failed: {result.error}")
            return f"ERROR: Frontend failed — {result.error}"

        files = result.get_files()
        artifacts.files.extend(files)
        paths = [f[0] for f in files]
        return f"Frontend complete. {len(files)} files: {', '.join(paths[:5])}{'...' if len(paths) > 5 else ''}"

    def call_security_agent() -> str:
        """Audit all generated code for security issues (OWASP Top 10, secrets, injection).

        Call this after backend and frontend are generated. May return patched files.
        No arguments needed — audits everything generated so far.
        """
        files_dict = {path: content for path, content in artifacts.files}
        result = _send(
            "security",
            "Perform a security audit on the generated code. "
            "Check for OWASP Top 10, hardcoded secrets, and injection flaws.",
            context={"files": files_dict},
        )
        if not result.success:
            artifacts.errors.append(f"Security audit failed: {result.error}")
            return f"ERROR: Security audit failed — {result.error}"

        patched = result.get_files()
        if patched:
            patch_map = {p: c for p, c in patched}
            artifacts.files = [
                (path, patch_map.get(path, content))
                for path, content in artifacts.files
            ]
            existing = {p for p, _ in artifacts.files}
            artifacts.files.extend((p, c) for p, c in patched if p not in existing)
            return f"Security audit complete. {len(patched)} file(s) patched."

        audit_text = result.get_text()
        passed = "PASS" in audit_text.upper() or "no issue" in audit_text.lower()
        return f"Security audit complete. {'No issues found.' if passed else 'Issues found — see audit report.'}"

    def call_ci_agent(spec: str) -> str:
        """Generate CI/CD configuration: GitHub Actions workflows, Dockerfile, docker-compose.

        Call this after call_planner. Independent of backend/frontend output.

        Args:
            spec: Full contents of the project spec
        """
        decisions_str = json.dumps(artifacts.decisions, indent=2)
        result = _send(
            "ci",
            "Generate CI/CD configuration: GitHub Actions workflows, Dockerfile, docker-compose.yml.",
            context={"decisions": artifacts.decisions, "spec": spec},
        )
        if not result.success:
            artifacts.errors.append(f"CI/CD failed: {result.error}")
            return f"ERROR: CI/CD failed — {result.error}"

        files = result.get_files()
        artifacts.files.extend(files)
        paths = [f[0] for f in files]
        return f"CI/CD complete. {len(files)} files: {', '.join(paths)}"

    def call_deploy_agent(spec: str) -> str:
        """Generate deployment configuration for Railway, Render, Vercel, or Fly.io.

        Call this after call_planner. Independent of backend/frontend output.

        Args:
            spec: Full contents of the project spec
        """
        result = _send(
            "deploy",
            "Generate deployment configuration files.",
            context={
                "decisions": artifacts.decisions,
                "spec": spec,
                "deploy_template": deploy_md,
            },
        )
        if not result.success:
            artifacts.errors.append(f"Deploy config failed: {result.error}")
            return f"ERROR: Deploy config failed — {result.error}"

        files = result.get_files()
        artifacts.files.extend(files)
        paths = [f[0] for f in files]
        return f"Deploy config complete. {len(files)} files: {', '.join(paths)}"

    def call_reviewer_agent(spec: str, rules: str) -> str:
        """Review all generated code for correctness, consistency, and security.

        Call this LAST after all other agents have run.

        Args:
            spec: Full contents of the project spec
            rules: Full contents of the build rules
        """
        files_dict = {path: content for path, content in artifacts.files}
        result = _send(
            "reviewer",
            "Review all generated code for correctness, consistency, and completeness.",
            context={"files": files_dict, "spec": spec, "rules": rules},
        )
        if not result.success:
            artifacts.errors.append(f"Review failed: {result.error}")
            return f"ERROR: Review failed — {result.error}"

        review = result.get_data()
        artifacts.review = review or {"text": result.get_text()}

        if review:
            passed = review.get("passed", False)
            n_issues = len(review.get("issues", []))
            return f"Review complete. {'Passed.' if passed else f'{n_issues} issue(s) found.'}"
        return "Review complete."

    def run_parallel_agents(agent_names: str, spec: str, rules: str) -> str:
        """Run multiple independent agents in parallel using a thread pool.

        Use this for agents that do not depend on each other's output.
        Example: backend, ci, and deploy all only need the planner's decisions,
        so they can be launched simultaneously.

        Args:
            agent_names: Comma-separated names of agents to run in parallel.
                         Valid names: backend, frontend, ci, deploy, security
                         Example: "backend,ci,deploy"
            spec: Full contents of the project spec
            rules: Full contents of the build rules
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        _AGENT_DISPATCH = {
            "backend":  lambda: call_backend_agent(spec, rules),
            "frontend": lambda: call_frontend_agent(spec, rules),
            "ci":       lambda: call_ci_agent(spec),
            "deploy":   lambda: call_deploy_agent(spec),
            "security": lambda: call_security_agent(),
        }

        names = [n.strip() for n in agent_names.split(",") if n.strip()]
        unknown = [n for n in names if n not in _AGENT_DISPATCH]
        if unknown:
            return f"ERROR: Unknown agent(s): {', '.join(unknown)}. Valid: {', '.join(_AGENT_DISPATCH)}"

        results: dict[str, str] = {}

        with ThreadPoolExecutor(max_workers=len(names)) as pool:
            future_to_name = {
                pool.submit(_AGENT_DISPATCH[name]): name
                for name in names
            }
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    results[name] = future.result()
                except Exception as exc:
                    err = f"{name} raised an exception: {exc}"
                    artifacts.errors.append(err)
                    results[name] = f"ERROR: {exc}"

        lines = [f"Parallel run complete ({len(names)} agents):"]
        for name in names:
            lines.append(f"  {name}: {results.get(name, 'no result')}")
        return "\n".join(lines)

    return [
        call_planner,
        run_parallel_agents,
        call_backend_agent,
        call_frontend_agent,
        call_security_agent,
        call_ci_agent,
        call_deploy_agent,
        call_reviewer_agent,
    ]
