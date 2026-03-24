"""ADK tool functions for the Forge orchestrator agent.

Each function is an ADK-compatible tool that the orchestrator LLM can call.
Tools route tasks to specialized agents via A2A and publish results into the
shared ArtifactBus / ContractRegistry — replacing the old tuple-list approach
with typed, thread-safe artifact exchange.

Tool design rules:
- Simple parameter types only (str, int, bool) — ADK converts these to JSON schema
- Docstring is used as the tool description shown to the LLM
- Return a plain string summary that the LLM can reason about
- Side-effect: publish artifacts into the shared BuildContext
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..collaboration import (
    ArtifactBus,
    ContractRegistry,
    CodeArtifact,
    DecisionArtifact,
    ReviewArtifact,
    BuildLogArtifact,
    extract_contracts_from_response,
)


class PipelineAbortError(RuntimeError):
    """Raised when a critical pipeline stage fails and execution cannot continue."""


@dataclass
class BuildContext:
    """Shared state for a single build run.

    Wraps an ``ArtifactBus`` (source of truth for all generated content) and a
    ``ContractRegistry`` (structured API / model contracts).  Orchestrator-level
    bookkeeping (task list, abort flag) lives here directly.
    """

    bus: ArtifactBus = field(default_factory=ArtifactBus)
    registry: ContractRegistry = field(default_factory=ContractRegistry)
    decisions: Dict = field(default_factory=dict)
    tasks: List = field(default_factory=list)
    aborted: bool = False
    # PM-enriched per-task prompts (populated by call_project_manager)
    task_prompts: Dict = field(default_factory=dict)   # task_id → prompt str
    task_agents: Dict = field(default_factory=dict)     # task_id → agent name

    # -- Convenience accessors used by orchestrator_agent.py ---------------

    @property
    def files(self) -> List[tuple]:
        return self.bus.export_files_list()

    @property
    def errors(self) -> List[str]:
        return self.bus.get_errors()

    @property
    def review(self) -> Optional[Dict]:
        return self.bus.get_review()


def make_agent_tools(
    clients: dict,
    context: BuildContext,
    deploy_md: str = "",
) -> list:
    """Create all ADK tool functions bound to the given A2A clients and shared context.

    Args:
        clients:   dict of agent_name → A2AClient
        context:   shared BuildContext that tools publish into
        deploy_md: contents of .forge/deploy.md (for DeployAgent)

    Returns:
        List of plain Python functions usable as ADK tools
    """
    from ..a2a.types import Task, Message, TextPart

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send(agent_name: str, text: str, ctx: dict = None):
        client = clients.get(agent_name)
        if client is None:
            raise RuntimeError(f"Agent '{agent_name}' not registered")
        task = Task(
            message=Message(role="user", parts=[TextPart(text=text)]),
            context=ctx or {},
        )
        return client.send_task(task)

    def _log_error(msg: str, agent: str = "orchestrator"):
        context.bus.publish(BuildLogArtifact(
            message=msg, producer_agent=agent, level="error",
        ))

    def _get_pm_prompts(agent_name: str) -> str:
        """Collect PM-enriched prompts for tasks assigned to *agent_name*."""
        prompts = [
            context.task_prompts[tid]
            for tid, agent in context.task_agents.items()
            if agent == agent_name and context.task_prompts.get(tid)
        ]
        if not prompts:
            return ""
        return (
            "\n\n## Task Instructions (from Project Manager)\n"
            + "\n---\n".join(prompts)
        )

    def _publish_files(
        files: list[tuple[str, str]],
        agent_name: str,
        task_id: str = "",
    ):
        """Publish generated files as CodeArtifacts to the bus."""
        for path, content in files:
            context.bus.publish(CodeArtifact(
                path=path,
                content=content,
                producer_agent=agent_name,
                task_id=task_id,
            ))

    # ── Tools ─────────────────────────────────────────────────────────────

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
            context.aborted = True
            msg = f"Planner failed: {result.error}"
            _log_error(msg, "planner")
            raise PipelineAbortError(msg)

        plan = result.get_data() or {}
        context.decisions = plan.get("decisions", {})
        context.tasks = plan.get("tasks", [])

        # Publish decisions to the bus
        for key, value in context.decisions.items():
            context.bus.publish(DecisionArtifact(
                key=key, value=value, producer_agent="planner",
            ))

        summary = (
            f"Plan ready. {len(context.tasks)} tasks.\n"
            f"Stack: {json.dumps(context.decisions.get('stack', {}))}\n"
            f"Architecture: {context.decisions.get('architecture', '')}"
        )
        return summary

    def call_project_manager(spec: str, rules: str) -> str:
        """Enrich the build plan: assign each task to the right agent and generate
        a targeted, self-contained prompt per task.

        Call this AFTER call_planner and BEFORE any other agent.

        Args:
            spec: Full contents of the project spec
            rules: Full contents of the build rules
        """
        result = _send(
            "project_manager",
            "Enrich this build plan with agent assignments and per-task prompts.",
            ctx={
                "plan": {"decisions": context.decisions, "tasks": context.tasks},
                "spec": spec,
                "rules": rules,
            },
        )
        if not result.success:
            context.aborted = True
            msg = f"Project Manager failed: {result.error}"
            _log_error(msg, "project_manager")
            raise PipelineAbortError(msg)

        enriched = result.get_data() or {}
        enriched_tasks = enriched.get("tasks", [])
        if enriched_tasks:
            context.tasks = enriched_tasks
            # Store PM-enriched prompts for use by downstream tools
            for t in enriched_tasks:
                tid = t.get("id", "")
                if tid:
                    context.task_prompts[tid] = t.get("prompt", "")
                    context.task_agents[tid] = t.get("agent", "coder")

        assignments = ", ".join(
            f"{t.get('id', '?')}→{t.get('agent', '?')}"
            for t in enriched_tasks[:5]
        )
        return f"Tasks enriched. {len(enriched_tasks)} tasks assigned. {assignments}"

    def call_backend_agent(spec: str, rules: str) -> str:
        """Generate complete backend code: API routes, database models, and service layer.

        Call this after call_planner. Generates all backend source files.

        Args:
            spec: Full contents of the project spec
            rules: Full contents of the build rules
        """
        decisions_str = json.dumps(context.decisions, indent=2)
        pm_block = _get_pm_prompts("backend")
        result = _send(
            "backend",
            f"Generate backend code (API routes, DB models, service layer).\n\n"
            f"## Spec\n{spec}\n\n## Rules\n{rules}\n\n## Decisions\n{decisions_str}"
            f"{pm_block}",
            ctx={"decisions": context.decisions, "spec": spec, "rules": rules},
        )
        if not result.success:
            _log_error(f"Backend failed: {result.error}", "backend")
            return f"ERROR: Backend failed — {result.error}"

        files = result.get_files()
        _publish_files(files, "backend")

        # Extract and register structured contracts
        response_text = result.get_text()
        contracts = extract_contracts_from_response(response_text, producer_agent="backend")
        context.registry.register_many(contracts.get("api", []))
        context.registry.register_many(contracts.get("models", []))
        context.registry.register_many(contracts.get("events", []))

        paths = [f[0] for f in files]
        n_contracts = sum(len(contracts.get(k, [])) for k in ("api", "models", "events"))
        return (
            f"Backend complete. {len(files)} files: "
            f"{', '.join(paths[:5])}{'...' if len(paths) > 5 else ''}. "
            f"{n_contracts} contract(s) registered."
        )

    def call_frontend_agent(spec: str, rules: str) -> str:
        """Generate frontend code: React components, routing, state, and API integration.

        Call this after call_backend_agent so it can match API contracts.

        Args:
            spec: Full contents of the project spec
            rules: Full contents of the build rules
        """
        decisions_str = json.dumps(context.decisions, indent=2)

        # Give the frontend agent actual backend contracts + relevant code
        contracts_text = context.registry.format_for_prompt()
        all_code = context.bus.export_files_dict()
        backend_code = {
            p: c for p, c in all_code.items()
            if any(kw in p.lower() for kw in (
                "route", "api", "schema", "model", "main", "endpoint",
            ))
        }

        pm_block = _get_pm_prompts("frontend")
        result = _send(
            "frontend",
            f"Generate frontend code (React components, pages, routing, API integration).\n\n"
            f"## Spec\n{spec}\n\n## Rules\n{rules}\n\n## Decisions\n{decisions_str}\n\n"
            f"## Backend API Contracts (match these exactly)\n{contracts_text}"
            f"{pm_block}",
            ctx={
                "decisions": context.decisions,
                "spec": spec,
                "rules": rules,
                "contracts": contracts_text,
                "backend_code": backend_code,
            },
        )
        if not result.success:
            _log_error(f"Frontend failed: {result.error}", "frontend")
            return f"ERROR: Frontend failed — {result.error}"

        files = result.get_files()
        _publish_files(files, "frontend")

        paths = [f[0] for f in files]
        return (
            f"Frontend complete. {len(files)} files: "
            f"{', '.join(paths[:5])}{'...' if len(paths) > 5 else ''}"
        )

    def call_security_agent() -> str:
        """Audit all generated code for security issues (OWASP Top 10, secrets, injection).

        Call this after backend and frontend are generated. May return patched files.
        No arguments needed — audits everything generated so far.
        """
        # Pass ALL code content from the bus — not just filenames
        all_code = context.bus.export_files_dict()
        contracts_text = context.registry.format_for_prompt()
        security_notes = context.registry.validate_security_coverage()

        pre_check_lines = []
        if not security_notes["passed"]:
            pre_check_lines.append("Auth coverage issues found:")
            for issue in security_notes.get("issues", []):
                pre_check_lines.append(f"  - {issue}")
        pre_check = "\n".join(pre_check_lines) if pre_check_lines else "Pre-check passed."

        result = _send(
            "security",
            f"Perform a security audit on the generated code. "
            f"Check for OWASP Top 10, hardcoded secrets, and injection flaws.\n\n"
            f"## Security Pre-Check\n{pre_check}",
            ctx={"files": all_code, "contracts": contracts_text},
        )
        if not result.success:
            _log_error(f"Security audit failed: {result.error}", "security")
            return f"ERROR: Security audit failed — {result.error}"

        # Publish patched files (security fixes) as new versions
        patched = result.get_files()
        if patched:
            for path, content in patched:
                existing = context.bus.latest(path)
                version = (existing.version + 1) if existing else 1
                context.bus.publish(CodeArtifact(
                    path=path,
                    content=content,
                    producer_agent="security",
                    version=version,
                ))
            return f"Security audit complete. {len(patched)} file(s) patched."

        audit_text = result.get_text()
        passed = "PASS" in audit_text.upper() or "no issue" in audit_text.lower()
        return (
            f"Security audit complete. "
            f"{'No issues found.' if passed else 'Issues found — see audit report.'}"
        )

    def call_ci_agent(spec: str) -> str:
        """Generate CI/CD configuration: GitHub Actions workflows, Dockerfile, docker-compose.

        Call this after call_planner. Independent of backend/frontend output.

        Args:
            spec: Full contents of the project spec
        """
        pm_block = _get_pm_prompts("ci")
        result = _send(
            "ci",
            f"Generate CI/CD configuration: GitHub Actions workflows, Dockerfile, docker-compose.yml."
            f"{pm_block}",
            ctx={"decisions": context.decisions, "spec": spec},
        )
        if not result.success:
            _log_error(f"CI/CD failed: {result.error}", "ci")
            return f"ERROR: CI/CD failed — {result.error}"

        files = result.get_files()
        _publish_files(files, "ci")

        paths = [f[0] for f in files]
        return f"CI/CD complete. {len(files)} files: {', '.join(paths)}"

    def call_deploy_agent(spec: str) -> str:
        """Generate deployment configuration for Railway, Render, Vercel, or Fly.io.

        Call this after call_planner. Independent of backend/frontend output.

        Args:
            spec: Full contents of the project spec
        """
        pm_block = _get_pm_prompts("deploy")
        result = _send(
            "deploy",
            f"Generate deployment configuration files.{pm_block}",
            ctx={
                "decisions": context.decisions,
                "spec": spec,
                "deploy_template": deploy_md,
            },
        )
        if not result.success:
            _log_error(f"Deploy config failed: {result.error}", "deploy")
            return f"ERROR: Deploy config failed — {result.error}"

        files = result.get_files()
        _publish_files(files, "deploy")

        paths = [f[0] for f in files]
        return f"Deploy config complete. {len(files)} files: {', '.join(paths)}"

    def call_reviewer_agent(spec: str, rules: str) -> str:
        """Review all generated code for correctness, consistency, and security.

        Call this LAST after all other agents have run.

        Args:
            spec: Full contents of the project spec
            rules: Full contents of the build rules
        """
        # Give the reviewer ALL generated code + contracts
        all_code = context.bus.export_files_dict()
        contracts_text = context.registry.format_for_prompt()

        # Run structural contract validation
        contract_check = context.registry.validate_frontend_against_backend()
        validation_note = ""
        if not contract_check["passed"]:
            validation_note = (
                "\n\n## Contract Validation Issues\n"
                + "\n".join(f"- {i}" for i in contract_check["issues"])
            )

        result = _send(
            "reviewer",
            f"Review all generated code for correctness, consistency, and completeness."
            f"{validation_note}",
            ctx={
                "files": all_code,
                "spec": spec,
                "rules": rules,
                "contracts": contracts_text,
            },
        )
        if not result.success:
            _log_error(f"Review failed: {result.error}", "reviewer")
            return f"ERROR: Review failed — {result.error}"

        review = result.get_data()
        review_data = review or {"text": result.get_text()}

        # Publish review to bus
        issues = review_data.get("issues", []) if isinstance(review_data, dict) else []
        context.bus.publish(ReviewArtifact(
            target_path="",
            producer_agent="reviewer",
            passed=review_data.get("passed", True) if isinstance(review_data, dict) else True,
            issues=tuple(
                i if isinstance(i, dict) else {"message": str(i)} for i in issues
            ),
        ))

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
            return (
                f"ERROR: Unknown agent(s): {', '.join(unknown)}. "
                f"Valid: {', '.join(_AGENT_DISPATCH)}"
            )

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
                    _log_error(err, name)
                    results[name] = f"ERROR: {exc}"

        lines = [f"Parallel run complete ({len(names)} agents):"]
        for name in names:
            lines.append(f"  {name}: {results.get(name, 'no result')}")
        return "\n".join(lines)

    def rework_file(agent_name: str, filepath: str, issue: str, spec: str, rules: str) -> str:
        """Send a file back to its original agent for rework based on a reviewer issue.

        Use this after call_reviewer_agent if the review found error-severity issues.
        One rework attempt per file — do NOT call this more than once for the same file.

        Args:
            agent_name: The agent that originally produced the file
                        (e.g. "backend", "frontend", "ci", "deploy")
            filepath:   Path of the file to rework (e.g. "app/routes/users.py")
            issue:      Description of the issue to fix
            spec:       Full contents of the project spec
            rules:      Full contents of the build rules
        """
        from ..collaboration import ReworkRequestArtifact

        existing = context.bus.latest(filepath)
        if existing is None:
            return f"ERROR: No file '{filepath}' found in the artifact bus."

        current_content = existing.content

        result = _send(
            agent_name,
            f"Fix this issue in {filepath}:\n\n"
            f"## Issue\n{issue}\n\n"
            f"## Current File Contents\n```\n{current_content}\n```\n\n"
            f"## Spec\n{spec}\n\n## Rules\n{rules}\n\n"
            f"Output the complete corrected file using:\n"
            f"```file:{filepath}\n<complete corrected file>\n```",
            ctx={"spec": spec, "rules": rules},
        )
        if not result.success:
            _log_error(f"Rework failed for {filepath}: {result.error}", agent_name)
            return f"ERROR: Rework of {filepath} failed — {result.error}"

        files = result.get_files()
        if files:
            for path, content in files:
                old = context.bus.latest(path)
                version = (old.version + 1) if old else 1
                context.bus.publish(CodeArtifact(
                    path=path, content=content,
                    producer_agent=agent_name, version=version,
                ))

        # Record the rework request for traceability
        context.bus.publish(ReworkRequestArtifact(
            target_path=filepath,
            original_agent=agent_name,
            issue=issue,
            producer_agent="reviewer",
        ))

        return f"Reworked {filepath} via {agent_name}. {len(files)} file(s) updated."

    return [
        call_planner,
        call_project_manager,
        run_parallel_agents,
        call_backend_agent,
        call_frontend_agent,
        call_security_agent,
        call_ci_agent,
        call_deploy_agent,
        call_reviewer_agent,
        rework_file,
    ]
