"""Build orchestrator -- drives the multi-agent build pipeline."""

import logging
import sys
import threading
import uuid
import json
import yaml
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

TASK_LANE_ORDER = {
    "setup": 0,
    "backend": 1,
    "ci": 2,
    "deploy": 3,
    "frontend": 4,
    "integration": 5,
    "security": 6,
    "coder": 7,
}


HIGH_SIGNAL_SUSPICIOUS_PATTERNS = (
    r"\bexfiltrat(e|ion|ing)\b",
    r"\bleak\b",
    r"\bupload\b",
    r"\btransfer\b",
    r"\bsend to\b",
    r"\bhttp(s)?://\b",
    r"\bcurl\b",
    r"\bwget\b",
    r"\bpastebin\b",
    r"\bgist\b",
    r"\bdrive\.google\b",
    r"\bdropbox\b",
)

SENSITIVE_TERMS = (
    r"\bsecret(s)?\b",
    r"\btoken(s)?\b",
    r"\bapi[- _]?key(s)?\b",
    r"\bpassword(s)?\b",
    r"\bprivate key\b",
    r"\bssh\b",
    r"\bcredential(s)?\b",
)

from .providers import create_provider
from .providers.base import ProviderConfig
from .agents import PlannerAgent, BuilderAgent, CoderAgent, ReviewerAgent
from .agents import BackendAgent, FrontendAgent, SecurityAgent, CIAgent, DeployAgent
from .config import load_config
from .audit import BuildAuditLogger
from .policy import load_build_policy
from .router import ModelRouter, RouteDecision
from .envfiles import materialize_env_files
from .security.firewall import AgenticFirewall
from .state import (
    BuildState, TaskState, load_build_state, save_build_state, compute_spec_hash,
)
from .context import build_context_string
from .skills import SkillsLoader
from .collaboration import (
    ArtifactBus,
    ArtifactStore,
    ContractRegistry,
    CodeArtifact,
    DecisionArtifact,
    TaskPlanArtifact,
    BuildOutputArtifact,
    BuildLogArtifact,
    ReviewArtifact,
    ReviewFindingArtifact,
    VerificationArtifact,
    ReworkRequestArtifact,
    extract_contracts_from_response,
    validate_agent_output,
)
from .verification import VerificationContext, VerificationRegistry
from .verification.html_behavior import HTMLBehaviorVerifier
from .verification.javascript import JavaScriptVerifier
from .support import is_supported_provider
from .ui import format_usage_summary

if TYPE_CHECKING:
    from .ui import BuildUI


class BuildOrchestrator:
    """Orchestrates the full build pipeline.

    Pipeline phases:
      1. PLANNING   -- PlannerAgent analyzes spec, produces task list
      2. BUILDING   -- BuilderAgent executes planned implementation tasks
      3. REVIEWING  -- ReviewerAgent validates the output (optional)
      4. VERIFYING  -- Deterministic verifiers validate the generated project

    State is persisted after each task, enabling resume on failure.
    """

    # Max times the builder re-attempts a task after executable verifiers
    # surface fixable errors. Counts attempts AFTER the initial generation.
    MAX_REFEED_ATTEMPTS = 2

    # Verifiers that run inline after each task, before disk write. Cheap +
    # local (no LLM call), so we run them on every build regardless of phase.
    _INLINE_VERIFIERS = (JavaScriptVerifier, HTMLBehaviorVerifier)

    def __init__(
        self,
        provider_config: ProviderConfig,
        forge_path: Path,
        review: bool = True,
        verbose: bool = False,
        approval_mode: Optional[str] = None,
        provider_scope: Optional[str] = None,
        config_dict: Optional[dict] = None,
        ui: Optional["BuildUI"] = None,
    ):
        self.forge_path = forge_path
        self.project_root = forge_path.parent
        self.verbose = verbose
        self.ui = ui
        self.policy = load_build_policy(forge_path)
        if approval_mode:
            self.policy.approval_mode = approval_mode
        self.review = review or self.policy.require_review

        self.config = config_dict or load_config() or {
            "providers": [{
                "name": provider_config.name,
                "api_key": provider_config.api_key,
                "model": provider_config.model,
                "base_url": provider_config.base_url,
                "max_tokens": provider_config.max_tokens,
            }]
        }
        self.model_router = ModelRouter(self.config, provider_config, provider_scope=provider_scope)
        self.provider = create_provider(provider_config)

        # Load skills for this project
        skills = SkillsLoader().load(self.project_root)

        self.planner = PlannerAgent(self.provider, self.project_root, skills_loader=skills)
        self.builder = BuilderAgent(self.provider, self.project_root, skills_loader=skills)
        self.coder = CoderAgent(self.provider, self.project_root, skills_loader=skills)
        self.reviewer = ReviewerAgent(self.provider, self.project_root, skills_loader=skills) if self.review else None
        self.verification_registry = VerificationRegistry()
        self._verification_report = None

        self._classic_agents: dict = {}  # lazy: agent_name → agent instance
        self._skills = skills

        # Collaboration layer — shared artifact bus and contract registry
        # Load existing contracts for incremental builds (forge build --feature)
        contracts_path = self.forge_path / "contracts.json"
        self.bus = ArtifactBus()
        self.artifact_store = ArtifactStore(self.forge_path)
        for artifact in self.artifact_store.load_all():
            self.bus.publish(artifact)
        self.registry = (
            ContractRegistry.load(contracts_path)
            if contracts_path.exists()
            else ContractRegistry()
        )

        self.firewall = AgenticFirewall(
            policy_path=self.forge_path / "firewall_policy.json",
            audit_log=self.forge_path / "firewall_audit.log"
        )
        self.audit = BuildAuditLogger(self.forge_path)

        self.state = load_build_state(forge_path)
        self.provider_config = provider_config
        self._build_start_time: Optional[float] = None
        self._state_lock = threading.Lock()  # protects state mutations in parallel mode

    def run(self, feature: Optional[str] = None):
        """Run the build (or incremental feature addition)."""
        self._build_start_time = time.monotonic()
        self.audit.log(
            "build_started",
            build_id=self.state.build_id or "",
            provider=self.provider_config.name,
            model=self.provider_config.model,
            approval_mode=self.policy.approval_mode,
        )
        try:
            spec = self._read_forge_file("spec.md")
            rules = self._read_forge_file("rules.md")
            self._warn_suspicious(spec, "spec.md")
            self._warn_suspicious(rules, "rules.md")

            if not spec:
                print("Error: .forge/spec.md is empty or missing.")
                print("Edit it with your project description first.")
                sys.exit(1)

            if self._can_resume(spec):
                print("Resuming previous build...")
                print("")
                self._execute_remaining_tasks(spec, rules)
            else:
                self._init_state(spec)
                self._phase_plan(spec, rules, feature)
                self._phase_build(spec, rules)

            if self.review and self.reviewer:
                self._phase_review(spec, rules)
            if self.policy.require_verification:
                self._phase_verify()

            self.state.status = "completed"
            self.state.completed_at = datetime.now().isoformat()
            self._save_state()

            # Persist contracts for incremental builds
            self.registry.save(self.forge_path / "contracts.json")
            if self.policy.auto_export_openapi and len(self.registry) > 0:
                self.registry.export_openapi(
                    self.forge_path / "openapi.json",
                    title=self.policy.openapi_title,
                )
            self.audit.log(
                "build_completed",
                build_id=self.state.build_id,
                files_written=len(self.state.files_written),
                errors=len(self.state.errors),
                contracts=len(self.registry),
            )
            self._write_audit_report()

            if self.ui:
                self.ui.build_summary(
                    files=self.state.files_written,
                    errors=self.state.errors,
                    start_time=self._build_start_time,
                )
        except Exception as exc:
            self.state.status = "failed"
            self.state.completed_at = datetime.now().isoformat()
            if str(exc):
                self.state.errors.append(str(exc))
            self._save_state()
            self.audit.log(
                "build_failed",
                build_id=self.state.build_id,
                error=str(exc),
            )
            self._write_audit_report()
            raise

    def _can_resume(self, spec: str) -> bool:
        if self.state.status in ("not_started", "completed"):
            return False
        current_hash = compute_spec_hash(self.forge_path)
        if self.state.spec_hash != current_hash:
            return False
        pending = [t for t in self.state.tasks if t.status in ("pending", "in_progress")]
        return len(pending) > 0

    def _init_state(self, spec: str):
        self.bus = ArtifactBus()
        self.artifact_store.reset()
        self._verification_report = None
        self.state = BuildState(
            build_id=uuid.uuid4().hex[:8],
            status="planning",
            started_at=datetime.now().isoformat(),
            provider=self.provider_config.name,
            model=self.provider_config.model,
            spec_hash=compute_spec_hash(self.forge_path),
        )
        self._save_state()
        self.audit.log(
            "state_initialized",
            build_id=self.state.build_id,
            spec_hash=self.state.spec_hash,
        )

    def _phase_plan(self, spec: str, rules: str, feature: Optional[str]):
        if self.ui:
            self.ui.phase_start("Phase 1: Planning")
        else:
            print("Phase 1: Planning...")
            print("")

        existing_context = build_context_string(self.project_root, max_tokens=2000)

        plan, planner_usage = self._run_planner_with_routing(spec, rules, feature, existing_context)

        if self.ui:
            self.ui.stream_stop()
            self.ui.spinner_stop()

        decisions = plan.get("decisions", {})
        self.state.decisions = _format_decisions(decisions)
        for key in ("stack", "architecture", "reasoning", "directory_structure"):
            value = decisions.get(key)
            if value:
                self._publish_artifact(DecisionArtifact(
                    key=key, value=value, producer_agent="planner",
                ))

        decisions_path = self.forge_path / "decisions.md"
        decisions_path.write_text(f"# Build Decisions\n\n{self.state.decisions}\n")

        self.state.tasks = []
        for i, task_data in enumerate(plan.get("tasks", [])):
            planned_files = _normalize_planned_files(task_data.get("files", []))
            description = task_data.get("description", "")
            if planned_files != task_data.get("files", []):
                description = (
                    f"{description.rstrip()} "
                    "Document required variables in `.env.example` files only; do not create real `.env` files."
                ).strip()
            task = TaskState(
                id=task_data.get("id", f"task_{i+1:02d}"),
                name=task_data.get("name", "Unnamed task"),
                description=description,
                agent="builder",
                specialization=task_data.get("specialization") or task_data.get("agent", "coder"),
                planned_files=planned_files,
            )
            self.state.tasks.append(task)
            self._publish_artifact(TaskPlanArtifact(
                task_id=task.id,
                name=task.name,
                description=task.description,
                specialization=task.specialization or "coder",
                planned_files=tuple(task.planned_files),
            ))

        self.state.tasks.sort(
            key=lambda task: (
                TASK_LANE_ORDER.get(self._task_lane(task), 99),
                task.id,
            )
        )

        self.state.status = "building"
        self.state.current_task_index = 0
        self._save_state()
        self.audit.log(
            "plan_created",
            build_id=self.state.build_id,
            task_count=len(self.state.tasks),
            stack=decisions.get("stack", {}),
        )
        if planner_usage:
            self.audit.log(
                "model_usage",
                build_id=self.state.build_id,
                role="planner",
                phase="planning",
                usage=planner_usage,
            )
        self._validate_policy(decisions.get("stack", {}), [t.agent for t in self.state.tasks])
        self._approval_gate(
            "plan",
            f"Planner selected stack {decisions.get('stack', {})} with {len(self.state.tasks)} tasks.",
        )

        if self.ui:
            if planner_usage:
                self.ui.note(f"planner usage: {_format_usage_for_output(planner_usage)}")
            self.ui.phase_end(f"  {len(self.state.tasks)} tasks planned")
            self.ui.set_tasks([t.name for t in self.state.tasks])
        else:
            print(f"   Plan: {len(self.state.tasks)} tasks")
            if planner_usage:
                print(f"     usage: {_format_usage_for_output(planner_usage)}")
            for t in self.state.tasks:
                print(f"     - {t.name}")
            print("")

    def _get_classic_agent(self, agent_name: str, provider_config: Optional[ProviderConfig] = None):
        """Return (or lazily create) a classic-mode agent for the given role and provider."""
        cls_map = {
            "planner": PlannerAgent,
            "builder": BuilderAgent,
            "backend": BackendAgent,
            "frontend": FrontendAgent,
            "ci": CIAgent,
            "deploy": DeployAgent,
            "security": SecurityAgent,
            "reviewer": ReviewerAgent,
            "coder": CoderAgent,
        }
        cfg = provider_config or self.provider_config
        key = (agent_name, cfg.name, cfg.profile, cfg.model)
        if key not in self._classic_agents:
            cls = cls_map.get(agent_name, CoderAgent)
            provider = create_provider(cfg)
            self._classic_agents[key] = cls(
                provider, self.project_root, skills_loader=self._skills
            )
        return self._classic_agents[key]

    def _log_route_selection(self, role: str, decision: RouteDecision, mode: str, attempt: int) -> None:
        self.audit.log(
            "model_route_selected",
            build_id=self.state.build_id or "",
            role=role,
            provider=decision.provider_config.name,
            profile=decision.provider_config.profile,
            model=decision.provider_config.model,
            reason=decision.reason,
            mode=mode,
            attempt=attempt,
        )

    def _notify_route_fallback(self, role: str, failed: RouteDecision, reason: str, next_attempt: int) -> None:
        """Tell the user we're walking to the next model in the chain."""
        short_reason = reason.splitlines()[0][:120] if reason else "unknown failure"
        msg = (
            f"{role} model {failed.provider_config} failed ({short_reason}); "
            f"trying next candidate (#{next_attempt})..."
        )
        if self.ui:
            self.ui.note(msg)
        else:
            print(f"   ! {msg}")

    def _should_skip_remaining_chain(
        self, decision: RouteDecision, exc: Exception, remaining: list[RouteDecision]
    ) -> bool:
        """Decide whether to abort the chain entirely after a failure.

        Returns True only when the failure is an auth error and every remaining
        candidate would hit the same auth context. OOM and context-overflow
        failures continue the chain — a different model often succeeds.
        """
        err = str(exc).lower()
        if not ("api key" in err or "unauthorized" in err or "authentication" in err):
            return False
        same_auth = all(
            d.provider_config.name == decision.provider_config.name
            and (d.provider_config.api_key or "") == (decision.provider_config.api_key or "")
            for d in remaining
        )
        return same_auth

    def _run_planner_with_routing(
        self,
        spec: str,
        rules: str,
        feature: Optional[str],
        existing_context: str,
    ) -> tuple[dict, dict]:
        errors = []
        chain = self.model_router.route_chain("planner")
        for idx, decision in enumerate(chain):
            attempt = idx + 1
            self._log_route_selection("planner", decision, "plan", attempt)
            agent = self._get_classic_agent("planner", decision.provider_config)
            failure: Optional[Exception] = None
            try:
                if feature:
                    plan = agent.plan_incremental(spec, rules, feature, existing_context)
                else:
                    on_chunk = None
                    if self.ui:
                        # Show a live token counter while the planner streams.
                        # New chain attempt → reset counter to start at 0.
                        label = (
                            "    Planning"
                            if attempt == 1
                            else f"    Planning (fallback #{attempt})"
                        )
                        self.ui.stream_stop()
                        self.ui.stream_start(label)
                        on_chunk = self.ui.stream_chunk
                    try:
                        plan = agent.analyze_and_plan(
                            spec, rules, existing_context, on_chunk=on_chunk
                        )
                    finally:
                        if self.ui:
                            self.ui.stream_stop()
                if isinstance(plan, dict) and plan.get("tasks"):
                    return plan, agent.provider.get_last_usage()
                reason = "planner produced no tasks"
                failure = RuntimeError(reason)
            except Exception as exc:
                reason = str(exc)
                failure = exc
            errors.append(f"{decision.provider_config}: {reason}")
            self.audit.log(
                "model_route_failed",
                build_id=self.state.build_id or "",
                role="planner",
                provider=decision.provider_config.name,
                profile=decision.provider_config.profile,
                model=decision.provider_config.model,
                attempt=attempt,
                error=reason,
            )
            remaining = chain[idx + 1:]
            if not remaining:
                break
            if self._should_skip_remaining_chain(decision, failure, remaining):
                self.audit.log(
                    "model_route_aborted",
                    build_id=self.state.build_id or "",
                    role="planner",
                    reason="auth failure on shared provider — skipping remaining chain",
                )
                break
            self._notify_route_fallback("planner", decision, reason, attempt + 1)
        raise RuntimeError(f"Planner failed across all routed models: {'; '.join(errors)}")

    def _run_reviewer_with_routing(self, files_dict: dict[str, str], spec: str, rules: str) -> tuple[dict, dict]:
        errors = []
        chain = self.model_router.route_chain("reviewer")
        for idx, decision in enumerate(chain):
            attempt = idx + 1
            self._log_route_selection("reviewer", decision, "review", attempt)
            agent = self._get_classic_agent("reviewer", decision.provider_config)
            failure: Optional[Exception] = None
            try:
                review = agent.review_files(files_dict, spec, rules)
                if isinstance(review, dict) and "passed" in review:
                    return review, agent.provider.get_last_usage()
                reason = "reviewer produced invalid review"
                failure = RuntimeError(reason)
            except Exception as exc:
                reason = str(exc)
                failure = exc
            errors.append(f"{decision.provider_config}: {reason}")
            self.audit.log(
                "model_route_failed",
                build_id=self.state.build_id or "",
                role="reviewer",
                provider=decision.provider_config.name,
                profile=decision.provider_config.profile,
                model=decision.provider_config.model,
                attempt=attempt,
                error=reason,
            )
            remaining = chain[idx + 1:]
            if not remaining:
                break
            if self._should_skip_remaining_chain(decision, failure, remaining):
                break
            self._notify_route_fallback("reviewer", decision, reason, attempt + 1)
        raise RuntimeError(f"Reviewer failed across all routed models: {'; '.join(errors)}")

    def _generate_with_routing(
        self,
        agent_name: str,
        prompt_to_use: str,
        fallback_task: Optional[dict] = None,
        spec: str = "",
        rules: str = "",
        decisions: str = "",
        project_context: str = "",
    ) -> tuple[str, list[tuple[str, str]], ProviderConfig, dict]:
        errors = []
        role = agent_name or "coder"
        chain = self.model_router.route_chain(role)
        for idx, decision in enumerate(chain):
            attempt = idx + 1
            self._log_route_selection(role, decision, "build", attempt)
            failure: Optional[Exception] = None
            try:
                if role == "builder":
                    agent = self._get_classic_agent("builder", decision.provider_config)
                    response = agent.build_task(
                        fallback_task or {"name": "Task", "description": "", "files": []},
                        spec,
                        rules,
                        decisions,
                        project_context=project_context,
                        backend_files=(fallback_task or {}).get("backend_files", []),
                        deploy_template=(fallback_task or {}).get("deploy_template", ""),
                    )
                elif prompt_to_use:
                    agent = self._get_classic_agent(role, decision.provider_config)
                    response = agent.invoke(prompt_to_use)
                else:
                    agent = self._get_classic_agent("coder", decision.provider_config)
                    response = agent.generate_files(
                        fallback_task or {"name": "Task", "description": "", "files": []},
                        spec,
                        rules,
                        decisions,
                        project_context,
                    )

                files = agent.extract_files(response)
                validation = validate_agent_output(role, response, files)
                if validation.valid:
                    return response, files, decision.provider_config, agent.provider.get_last_usage()
                reason = validation.reason
                failure = RuntimeError(reason)
            except Exception as exc:
                reason = str(exc)
                failure = exc

            errors.append(f"{decision.provider_config}: {reason}")
            self.audit.log(
                "model_route_failed",
                build_id=self.state.build_id or "",
                role=role,
                provider=decision.provider_config.name,
                profile=decision.provider_config.profile,
                model=decision.provider_config.model,
                attempt=attempt,
                error=reason,
            )
            remaining = chain[idx + 1:]
            if not remaining:
                break
            if self._should_skip_remaining_chain(decision, failure, remaining):
                break
            self._notify_route_fallback(role, decision, reason, attempt + 1)
        raise RuntimeError(f"{role} failed across all routed models: {'; '.join(errors)}")

    def _fix_with_routing(
        self,
        producer: str,
        filepath: str,
        current_content: str,
        issue: str,
        spec: str,
        rules: str,
    ) -> tuple[list[tuple[str, str]], ProviderConfig, dict]:
        prompt = (
            f"Fix this issue in {filepath}:\n"
            f"Issue: {issue}\n\n"
            f"Current file contents:\n```\n{current_content}\n```\n\n"
            f"## Spec\n{spec}\n\n## Rules\n{rules}\n\n"
            f"Output the complete corrected file using:\n"
            f"```file:{filepath}\n<complete corrected file>\n```"
        )
        response, files, cfg, usage = self._generate_with_routing(producer, prompt_to_use=prompt)
        return files, cfg, usage

    def _phase_build(self, spec: str, rules: str):
        if self.ui:
            self.ui.phase_start("Phase 2: Building")
        else:
            print("Phase 2: Building...")
            print("")

        lanes_used = {self._task_lane(task) for task in self.state.tasks}
        self._approval_gate(
            "build",
            f"Build phase will run {len(self.state.tasks)} tasks across {sorted(lanes_used)}.",
        )
        interactive_gates = self.policy.approval_mode == "interactive" and self.policy.approval_gates
        if len(lanes_used) > 1 and not interactive_gates:
            self._execute_tasks_parallel(spec, rules)
        else:
            self._execute_tasks_sequential(spec, rules)

        failed_tasks = [task for task in self.state.tasks if task.status == "failed"]
        if failed_tasks:
            names = ", ".join(task.name for task in failed_tasks[:3])
            suffix = "" if len(failed_tasks) <= 3 else f" (+{len(failed_tasks) - 3} more)"
            raise RuntimeError(
                f"Build phase failed: {len(failed_tasks)} task(s) failed: {names}{suffix}"
            )

        if self.ui:
            self.ui.phase_end("  Build phase complete")

    # -- Single-task execution (shared by sequential and parallel paths) ----

    def _run_single_task(self, task_id: str, spec: str, rules: str) -> None:
        """Execute one task: invoke agent, firewall, write files, publish to bus.

        Thread-safe — uses ``_state_lock`` for shared-state mutations.
        Raises on failure so the scheduler can track it.
        """
        task = self._task_by_id(task_id)
        if task is None or task.status == "completed":
            return

        total = len(self.state.tasks)
        idx = next(
            (i for i, t in enumerate(self.state.tasks) if t.id == task_id), 0
        )

        if self.ui:
            self.ui.task_start(task.name)
        else:
            with self._state_lock:
                print(f"   [{idx + 1}/{total}] {task.name}")

        task.status = "in_progress"
        task.started_at = datetime.now().isoformat()
        with self._state_lock:
            self._save_state()

        project_context = build_context_string(self.project_root, max_tokens=3000)

        agent_name = task.agent or "builder"
        specialization = task.specialization or "coder"
        self.audit.log(
            "task_started",
            build_id=self.state.build_id,
            task_id=task.id,
            task_name=task.name,
            agent=agent_name,
        )

        # Inject contract context for frontend tasks
        prompt_to_use = task.prompt
        if specialization == "frontend" and prompt_to_use and len(self.registry) > 0:
            contracts_block = self.registry.format_for_prompt()
            backend_code = self.bus.export_files_dict()
            backend_relevant = {
                p: c for p, c in backend_code.items()
                if any(kw in p.lower() for kw in (
                    "route", "api", "schema", "model", "main", "endpoint",
                ))
            }
            extra = f"\n\n## Backend API Contracts (match these exactly)\n{contracts_block}"
            if backend_relevant:
                extra += "\n\n## Backend Code Reference"
                for fp, content in backend_relevant.items():
                    extra += f"\n### {fp}\n```\n{content}\n```"
            prompt_to_use = prompt_to_use + extra

        task_dict = {
            "name": task.name,
            "description": task.description,
            "files": task.planned_files,
            "specialization": specialization,
            "backend_files": [
                path for path in self.bus.export_files_dict()
                if any(token in path.lower() for token in ("api", "route", "schema", "model", "main"))
            ],
            "deploy_template": self._read_forge_file("deploy.md"),
        }
        response, files, used_provider, usage = self._generate_with_routing(
            agent_name="builder",
            prompt_to_use=prompt_to_use or "",
            fallback_task=task_dict,
            spec=spec,
            rules=rules,
            decisions=self.bus.get_decisions(),
            project_context=project_context,
        )

        # Normalize paths against the plan — local models routinely add
        # spurious 'frontend/', 'src/', or 'app/' prefixes the planner didn't ask for.
        from .agents.base import normalize_paths_against_plan
        original_paths = [p for p, _ in files]
        files = normalize_paths_against_plan(files, task.planned_files)
        normalized_paths = [p for p, _ in files]
        path_fixes = [
            (orig, new) for orig, new in zip(original_paths, normalized_paths)
            if orig != new
        ]
        if path_fixes:
            for orig, new in path_fixes:
                msg = f"path corrected: {orig} -> {new} (matched planned file)"
                if self.ui:
                    self.ui.note(msg)
                else:
                    with self._state_lock:
                        print(f"      ! {msg}")
            self.audit.log(
                "task_path_normalized",
                build_id=self.state.build_id,
                task_id=task.id,
                corrections=[{"from": o, "to": n} for o, n in path_fixes],
            )

        # Validate-and-refeed loop: run executable verifiers in-memory against
        # the candidate files. On failure, build a fix prompt with the verifier
        # output and re-invoke the builder. Bounded by MAX_REFEED_ATTEMPTS so
        # a model that can't fix the bug doesn't loop forever.
        files, refeed_history = self._refeed_until_clean(
            task=task, files=files, spec=spec, rules=rules,
        )
        if refeed_history:
            self.audit.log(
                "task_refeed_summary",
                build_id=self.state.build_id,
                task_id=task.id,
                attempts=len(refeed_history),
                final_errors=refeed_history[-1].get("remaining_errors", 0),
            )

        writer_agent = self._get_classic_agent("builder", used_provider)
        self.audit.log(
            "task_model_used",
            build_id=self.state.build_id,
            task_id=task.id,
            agent="builder",
            provider=used_provider.name,
            profile=used_provider.profile,
            model=used_provider.model,
        )
        if usage:
            self.audit.log(
                "model_usage",
                build_id=self.state.build_id,
                role="builder",
                task_id=task.id,
                phase="build",
                usage=usage,
            )

        # Apply Agentic Firewall
        allowed_files = []
        blocked_files = []
        for filepath, content in files:
            permitted, reason = self.firewall.validate_file_write(filepath, content)
            if permitted:
                allowed_files.append((filepath, content))
            else:
                blocked_files.append((filepath, reason))
                if not self.ui:
                    with self._state_lock:
                        print(f"      FIREWALL BLOCK: {filepath} ({reason})")
                self.state.errors.append(f"Firewall blocked {filepath}: {reason}")
                self._publish_artifact(BuildLogArtifact(
                    message=f"Firewall blocked {filepath}: {reason}",
                    producer_agent="firewall",
                    level="error",
                    task_id=task.id,
                ))
                self.audit.log(
                    "firewall_blocked",
                    build_id=self.state.build_id,
                    task_id=task.id,
                    path=filepath,
                    reason=reason,
                )

        if blocked_files:
            blocked_summary = ", ".join(path for path, _ in blocked_files[:3])
            if len(blocked_files) > 3:
                blocked_summary += f" (+{len(blocked_files) - 3} more)"
            raise RuntimeError(f"Firewall blocked task outputs: {blocked_summary}")

        self._approval_gate(
            "task_write",
            f"Task '{task.name}' ({agent_name}) is ready to write {len(allowed_files)} files.",
        )
        written = writer_agent.write_files(allowed_files)
        created_env_files = materialize_env_files(self.project_root, written, firewall=self.firewall)
        if created_env_files:
            written = list(written) + created_env_files

        # Publish to artifact bus (thread-safe)
        for filepath, content in allowed_files:
            self._publish_artifact(CodeArtifact(
                path=filepath, content=content,
                producer_agent=specialization, task_id=task.id,
            ))

        # Extract contracts from backend agent responses
        if specialization == "backend":
            contracts = extract_contracts_from_response(
                response, producer_agent="backend",
            )
            self.registry.register_many(contracts.get("api", []))
            self.registry.register_many(contracts.get("models", []))
            self.registry.register_many(contracts.get("events", []))
            contract_types = tuple(
                name
                for name, items in (
                    ("api", contracts.get("api", [])),
                    ("model", contracts.get("models", [])),
                    ("event", contracts.get("events", [])),
                )
                if items
            )
        else:
            contract_types = ()

        task.files_written = written
        task.status = "completed"
        task.completed_at = datetime.now().isoformat()

        with self._state_lock:
            self.state.files_written.extend(written)
            self._save_state()
        for path in written:
            self.audit.log(
                "file_written",
                build_id=self.state.build_id,
                task_id=task.id,
                path=path,
                agent="builder",
            )
        for path in created_env_files:
            self.audit.log(
                "env_materialized",
                build_id=self.state.build_id,
                task_id=task.id,
                path=path,
            )
        self.audit.log(
            "task_completed",
            build_id=self.state.build_id,
            task_id=task.id,
            task_name=task.name,
            files_written=len(written),
        )
        self._publish_artifact(BuildOutputArtifact(
            task_id=task.id,
            specialization=specialization,
            planned_files=tuple(task.planned_files),
            files_written=tuple(written),
            contract_types=contract_types,
        ))

        if self.ui:
            self.ui.task_done(task.name, written, usage=usage)
        else:
            if usage:
                with self._state_lock:
                    print(f"      usage: {_format_usage_for_output(usage)}")
            with self._state_lock:
                for f in written:
                    print(f"      + {f}")

    def _refeed_until_clean(
        self,
        task: TaskState,
        files: list[tuple[str, str]],
        spec: str,
        rules: str,
    ) -> tuple[list[tuple[str, str]], list[dict]]:
        """Run executable verifiers; if they find issues, ask the model to fix.

        Returns the (possibly-corrected) files list and a list of per-attempt
        records for audit logging. Never raises — if the model can't fix the
        issues, we surface them and let the caller proceed (firewall + Phase
        4 verification will still gate the build).
        """
        from .agents.base import normalize_paths_against_plan

        history: list[dict] = []
        for attempt in range(self.MAX_REFEED_ATTEMPTS + 1):
            failures = self._run_inline_verifiers(files)
            if not failures:
                if attempt > 0:
                    msg = f"refeed: issues resolved after {attempt} attempt(s)"
                    if self.ui:
                        self.ui.note(msg)
                    else:
                        with self._state_lock:
                            print(f"      ! {msg}")
                return files, history

            history.append({
                "attempt": attempt,
                "remaining_errors": sum(len(r.logs) for r in failures),
            })
            if attempt >= self.MAX_REFEED_ATTEMPTS:
                # Out of attempts — surface and let firewall/Phase 4 handle it
                msg = (
                    f"refeed: {sum(len(r.logs) for r in failures)} issue(s) remain "
                    f"after {attempt} refeed(s); proceeding to firewall + verification"
                )
                if self.ui:
                    self.ui.note(msg)
                else:
                    with self._state_lock:
                        print(f"      ! {msg}")
                return files, history

            fix_prompt = self._build_refeed_prompt(task, files, failures)
            msg = f"refeed #{attempt + 1}: fixing {sum(len(r.logs) for r in failures)} issue(s)..."
            if self.ui:
                self.ui.note(msg)
            else:
                with self._state_lock:
                    print(f"      ! {msg}")

            try:
                _resp, new_files, _cfg, _usage = self._generate_with_routing(
                    agent_name=task.agent or "builder",
                    prompt_to_use=fix_prompt,
                    spec=spec, rules=rules,
                )
            except Exception as exc:
                # If the fix attempt itself fails, log and stop refeeding
                self.audit.log(
                    "task_refeed_failed",
                    build_id=self.state.build_id,
                    task_id=task.id,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                return files, history

            new_files = normalize_paths_against_plan(new_files, task.planned_files)
            if not new_files:
                # Model returned nothing — give up rather than loop on empty
                return files, history

            # Merge: keep prior files not touched in this attempt, replace those that were
            merged: dict[str, str] = {p: c for p, c in files}
            for path, content in new_files:
                merged[path] = content
            files = list(merged.items())
        return files, history

    def _run_inline_verifiers(self, files: list[tuple[str, str]]):
        """Run executable verifiers against candidate files plus prior bus state."""
        bus_files = self.bus.export_files_dict()
        combined = dict(bus_files)
        for path, content in files:
            combined[path] = content
        context = VerificationContext(
            project_root=self.project_root,
            files=combined,
            decisions=self.bus.get_decisions(),
            contracts=self.registry,
        )
        failures = []
        for verifier_cls in self._INLINE_VERIFIERS:
            verifier = verifier_cls()
            if not verifier.applies_to(context):
                continue
            result = verifier.run(context)
            if (not result.passed) and result.severity == "error" and result.retryable:
                failures.append(result)
        return failures

    def _build_refeed_prompt(
        self, task: TaskState, files: list[tuple[str, str]], failures
    ) -> str:
        """Compose a fix-only prompt the model can act on without redesigning."""
        file_blocks = []
        for path, content in files:
            file_blocks.append(f"```file:{path}\n{content.rstrip()}\n```")

        issue_lines: list[str] = []
        for result in failures:
            issue_lines.append(f"## {result.verifier}")
            for log in result.logs:
                issue_lines.append(f"- {log}")

        files_section = "\n\n".join(file_blocks) if file_blocks else "(no files yet)"
        issues_section = "\n".join(issue_lines)

        return (
            f"You generated the following files for task '{task.name}':\n\n"
            f"{files_section}\n\n"
            f"Static analysis surfaced these issues that must be fixed:\n\n"
            f"{issues_section}\n\n"
            "Rules:\n"
            "1. Fix ONLY the issues listed above.\n"
            "2. Do not rename files or change paths.\n"
            "3. Do not introduce new external network URLs.\n"
            "4. If a function is reported as undefined, either define it or "
            "remove the call.\n"
            "5. Return the COMPLETE corrected file(s) using the exact same "
            "`````file:path` format. Only include files that needed changes."
        )

    def _task_by_id(self, task_id: str):
        """Look up a TaskState by id."""
        for t in self.state.tasks:
            if t.id == task_id:
                return t
        return None

    def _execute_remaining_tasks(self, spec: str, rules: str):
        """Backward-compat entry point used by the resume path."""
        lanes_used = {self._task_lane(task) for task in self.state.tasks}
        if len(lanes_used) > 1:
            self._execute_tasks_parallel(spec, rules)
        else:
            self._execute_tasks_sequential(spec, rules)

    # -- Sequential execution (fallback / single-agent plans) ---------------

    def _execute_tasks_sequential(self, spec: str, rules: str):
        """Run tasks one at a time (original behaviour)."""
        for task in self.state.tasks:
            if task.status == "completed":
                continue
            try:
                self._run_single_task(task.id, spec, rules)
            except KeyboardInterrupt:
                if self.ui:
                    self.ui.spinner_stop()
                task.status = "pending"
                self._save_state()
                raise
            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                self.state.errors.append(f"Task '{task.name}': {e}")
                self.audit.log(
                    "task_failed",
                    build_id=self.state.build_id,
                    task_id=task.id,
                    task_name=task.name,
                    error=str(e),
                )
                self._save_state()
                if self.ui:
                    self.ui.task_error(task.name, str(e))
                else:
                    print(f"      ERROR: {e}")
                continue
        if not self.ui:
            print("")

    # -- Parallel execution (multi-agent plans) -----------------------------

    def _execute_tasks_parallel(self, spec: str, rules: str):
        """Run tasks respecting dependency graph, parallelising where possible."""
        from .scheduler import build_dependency_graph, ParallelScheduler

        pending = [t for t in self.state.tasks if t.status != "completed"]
        if not pending:
            return

        graph = build_dependency_graph(pending)
        scheduler = ParallelScheduler(max_workers=4)

        if not self.ui:
            lanes = {n.agent for n in graph}
            print(f"   Parallel scheduler: {len(graph)} tasks across {lanes}")
            print("")

        def _run(task_id: str):
            self._run_single_task(task_id, spec, rules)

        failed_ids = scheduler.execute(graph, _run)

        # Mark skipped tasks
        for tid in failed_ids:
            task = self._task_by_id(tid)
            if task and task.status != "failed":
                task.status = "failed"
                task.error = "Skipped: upstream dependency failed"
                self.state.errors.append(
                    f"Task '{task.name}': skipped (dependency failed)"
                )

        self._save_state()
        if not self.ui:
            print("")

    def _phase_review(self, spec: str, rules: str):
        if self.ui:
            self.ui.phase_start("Phase 3: Reviewing")
            self.ui.spinner_start("    Reviewing generated files")
        else:
            print("Phase 3: Reviewing...")

        self.state.status = "reviewing"
        self._save_state()
        self._approval_gate(
            "review",
            f"Reviewer is about to inspect {len(self.state.files_written)} generated files.",
        )

        # Prefer bus contents (source of truth) over disk reads
        files_dict = self.bus.export_files_dict()
        if not files_dict:
            # Fallback: read from disk (pre-bus compat or resumed builds)
            for filepath in self.state.files_written:
                full_path = self.project_root / filepath
                if full_path.exists():
                    try:
                        files_dict[filepath] = full_path.read_text()
                    except Exception:
                        pass

        if not files_dict:
            if self.ui:
                self.ui.spinner_stop()
                self.ui.phase_end("  No files to review")
            else:
                print("   No files to review.")
                print("")
            return

        # Inject contract validation results into the review
        contracts_note = ""
        if len(self.registry) > 0:
            contracts_note = f"\n\n## Registered API Contracts\n{self.registry.format_for_prompt()}"
            contract_check = self.registry.validate_frontend_against_backend()
            if not contract_check["passed"]:
                contracts_note += "\n\n## Contract Validation Issues\n"
                contracts_note += "\n".join(f"- {i}" for i in contract_check["issues"])
            sec_check = self.registry.validate_security_coverage()
            if not sec_check["passed"]:
                contracts_note += "\n\n## Auth Coverage Issues\n"
                contracts_note += "\n".join(f"- {i}" for i in sec_check["issues"])

        review, review_usage = self._run_reviewer_with_routing(files_dict, spec, rules + contracts_note)
        issues = tuple(review.get("issues", []))
        self._publish_artifact(ReviewArtifact(
            target_path="",
            producer_agent="reviewer",
            passed=review.get("passed", False),
            issues=issues,
        ))

        if self.ui:
            self.ui.spinner_stop()

        fixes_applied = 0
        if review["passed"]:
            if not self.ui:
                print("   Review passed.")
        else:
            issues = review.get("issues", [])
            errors = [i for i in issues if i.get("severity") == "error"]
            warnings = [i for i in issues if i.get("severity") == "warning"]

            for issue in issues:
                filepath = issue.get("file", "")
                self._publish_artifact(ReviewFindingArtifact(
                    target_path=filepath,
                    message=issue.get("message", ""),
                    severity=issue.get("severity", "warning"),
                    producer_agent="reviewer",
                    issue_type=issue.get("type", "review"),
                    retryable=issue.get("severity") == "error",
                ))

            if not self.ui:
                print(f"   Review found {len(issues)} issue(s):")
                for issue in errors:
                    print(f"      ERROR in {issue.get('file', '?')}: {issue.get('message', '')}")
                for issue in warnings:
                    print(f"      WARN  in {issue.get('file', '?')}: {issue.get('message', '')}")

            if errors:
                if not self.ui:
                    print("")
                    print("   Attempting auto-fix...")
                for issue in errors:
                    filepath = issue.get("file", "")
                    if filepath in files_dict:
                        try:
                            # Route fixes to the original agent that produced the file
                            code_art = self.bus.latest(filepath)
                            producer = code_art.producer_agent if code_art else "coder"
                            self._publish_artifact(ReworkRequestArtifact(
                                target_path=filepath,
                                original_agent=producer,
                                issue=issue.get('message', ''),
                                producer_agent="reviewer",
                            ))
                            fixed_files, used_provider, fix_usage = self._fix_with_routing(
                                producer=producer,
                                filepath=filepath,
                                current_content=files_dict[filepath],
                                issue=issue.get('message', ''),
                                spec=spec,
                                rules=rules,
                            )
                            fix_agent = self._get_classic_agent(producer, used_provider)
                            written = fix_agent.write_files(fixed_files)

                            # Update bus with fixed versions
                            for fp, content in fixed_files:
                                existing = self.bus.latest(fp)
                                version = (existing.version + 1) if existing else 1
                                self._publish_artifact(CodeArtifact(
                                    path=fp,
                                    content=content,
                                    producer_agent=producer,
                                    version=version,
                                ))

                            fixes_applied += len(written)
                            self.audit.log(
                                "task_model_used",
                                build_id=self.state.build_id,
                                task_id=f"fix:{filepath}",
                                agent=producer,
                                provider=used_provider.name,
                                profile=used_provider.profile,
                                model=used_provider.model,
                            )
                            if fix_usage:
                                self.audit.log(
                                    "model_usage",
                                    build_id=self.state.build_id,
                                    role=producer,
                                    task_id=f"fix:{filepath}",
                                    phase="fix",
                                    usage=fix_usage,
                                )
                            if not self.ui:
                                for f in written:
                                    print(f"      ~ {f} (fixed by {producer})")
                        except Exception as e:
                            if not self.ui:
                                print(f"      Could not fix {filepath}: {e}")

        review_path = self.forge_path / "review.yaml"
        with open(review_path, "w") as f:
            yaml.dump(review, f, default_flow_style=False)
        self.audit.log(
            "review_completed",
            build_id=self.state.build_id,
            passed=review.get("passed", False),
            issue_count=len(review.get("issues", [])),
            fixes_applied=fixes_applied,
        )
        if review_usage:
            self.audit.log(
                "model_usage",
                build_id=self.state.build_id,
                role="reviewer",
                phase="review",
                usage=review_usage,
            )

        if self.ui:
            if review_usage:
                self.ui.note(f"reviewer usage: {_format_usage_for_output(review_usage)}")
            fix_note = f", {fixes_applied} auto-fix(es) applied" if fixes_applied else ""
            status = "passed" if review["passed"] else f"{len(review.get('issues', []))} issue(s)"
            self.ui.phase_end(f"  Review {status}{fix_note}")
        else:
            if review_usage:
                print(f"   usage: {_format_usage_for_output(review_usage)}")
            print("")

    def _phase_verify(self):
        if self.ui:
            self.ui.phase_start("Phase 4: Verifying")
        else:
            print("Phase 4: Verifying...")

        files_dict = self.bus.export_files_dict()
        if not files_dict:
            for filepath in self.state.files_written:
                full_path = self.project_root / filepath
                if full_path.exists():
                    try:
                        files_dict[filepath] = full_path.read_text()
                    except Exception:
                        pass

        context = VerificationContext(
            project_root=self.project_root,
            files=files_dict,
            decisions=self.bus.get_decisions(),
            contracts=self.registry,
        )
        report = self.verification_registry.run(context)
        self._verification_report = report

        verification_path = self.forge_path / "verification.json"
        verification_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n")

        for result in report.results:
            self._publish_artifact(VerificationArtifact(
                verifier=result.verifier,
                category=result.category,
                passed=result.passed,
                severity=result.severity,
                summary=result.summary,
                details=result.details,
                files=result.files,
                retryable=result.retryable,
            ))
            self.audit.log(
                "verification_result",
                build_id=self.state.build_id,
                verifier=result.verifier,
                category=result.category,
                passed=result.passed,
                severity=result.severity,
                summary=result.summary,
            )

        warning_failures = [
            result for result in report.results
            if (not result.passed)
            and result.severity == "warning"
            and result.category.lower() in self.policy.normalized_warning_categories()
        ]
        if warning_failures:
            failed = warning_failures[0]
            raise RuntimeError(
                f"Verification warning promoted to failure: {failed.verifier}: "
                f"{failed.details or failed.summary}"
            )

        if not report.passed:
            failed = report.failed_results()[0]
            raise RuntimeError(
                f"Verification failed: {failed.verifier}: {failed.details or failed.summary}"
            )

        if self.ui:
            self.ui.phase_end(f"  Verification passed ({len(report.results)} checks)")
        else:
            print(f"   Verification passed ({len(report.results)} checks)")
            print("")

    def _read_forge_file(self, name: str) -> str:
        path = self.forge_path / name
        if path.exists():
            return path.read_text()
        return ""

    def _warn_suspicious(self, text: str, name: str) -> None:
        hits = find_suspicious_patterns(text)

        if hits:
            unique = ", ".join(sorted(set(hits)))
            logger.warning("Suspicious pattern(s) found in .forge/%s: %s", name, unique)
            self.audit.log(
                "suspicious_input",
                build_id=self.state.build_id or "",
                source=name,
                patterns=sorted(set(hits)),
            )

    def _save_state(self):
        save_build_state(self.forge_path, self.state)
        self.artifact_store.write_snapshot(self.bus.snapshot())

    def _task_lane(self, task: TaskState) -> str:
        return (task.specialization or task.agent or "setup").strip().lower()

    def _publish_artifact(self, artifact) -> None:
        self.bus.publish(artifact)
        self.artifact_store.append(artifact)
        self.artifact_store.write_snapshot(self.bus.snapshot())

    def _validate_policy(self, stack: dict, agents: list[str]) -> None:
        errors = self.policy.validate_plan(stack, agents, provider=self.provider_config.name)
        if self.policy.support_tier == "supported" and not is_supported_provider(self.provider_config.name):
            errors.append(
                f"Support tier 'supported' does not include provider '{self.provider_config.name}'."
            )
        if errors:
            for error in errors:
                self.audit.log("policy_violation", build_id=self.state.build_id, message=error)
            raise RuntimeError(errors[0])

    def _approval_gate(self, gate: str, summary: str) -> None:
        if not self.policy.should_gate(gate):
            return

        mode = (self.policy.approval_mode or "off").lower()
        if mode == "off":
            return
        if mode != "interactive":
            raise RuntimeError(f"Unsupported approval mode: {self.policy.approval_mode}")

        print(f"Approval required [{gate}]: {summary}")
        response = input("Proceed? [y/N]: ").strip().lower()
        if response not in {"y", "yes"}:
            self.audit.log(
                "approval_denied",
                build_id=self.state.build_id,
                gate=gate,
                summary=summary,
            )
            raise RuntimeError(f"Approval denied for gate '{gate}'.")

        self.audit.log(
            "approval_granted",
            build_id=self.state.build_id,
            gate=gate,
            summary=summary,
        )

    def _write_audit_report(self) -> None:
        task_counts = {}
        for task in self.state.tasks:
            task_counts[task.status] = task_counts.get(task.status, 0) + 1

        report = {
            "build_id": self.state.build_id,
            "status": self.state.status,
            "provider": self.state.provider,
            "model": self.state.model,
            "started_at": self.state.started_at,
            "completed_at": self.state.completed_at,
            "policy": {
                "mode": self.policy.mode,
                "support_tier": self.policy.support_tier,
                "approval_mode": self.policy.approval_mode,
                "approval_gates": self.policy.approval_gates,
                "require_review": self.policy.require_review,
                "require_verification": self.policy.require_verification,
                "fail_on_warning_categories": self.policy.fail_on_warning_categories,
            },
            "tasks": task_counts,
            "files_written": self.state.files_written,
            "errors": self.state.errors,
            "contract_counts": {
                "api": len(self.registry.get_api_contracts()),
                "models": len(self.registry.get_model_contracts()),
                "events": len(self.registry.get_event_contracts()),
            },
            "verification": (
                self._verification_report.to_dict()
                if self._verification_report is not None
                else None
            ),
        }
        self.audit.write_report(report)

def find_suspicious_patterns(text: str) -> list[str]:
    """Return high-signal suspicious input matches.

    Sensitive terms alone are common in build rules. To reduce false positives,
    only report them when they appear alongside an exfiltration or outbound-transfer
    indicator in the same input.
    """
    if not text:
        return []

    hits = []
    lowered = text.lower()
    high_signal_hit = False

    for pat in HIGH_SIGNAL_SUSPICIOUS_PATTERNS:
        if re.search(pat, lowered, re.IGNORECASE):
            high_signal_hit = True
            hits.append(pat.strip("\\b").replace("\\", ""))

    if high_signal_hit:
        for pat in SENSITIVE_TERMS:
            if re.search(pat, lowered, re.IGNORECASE):
                hits.append(pat.strip("\\b").replace("\\", ""))

    return sorted(set(hits))


def _format_decisions(decisions: dict) -> str:
    """Format decisions dict as readable markdown."""
    parts = []

    stack = decisions.get("stack", {})
    if stack:
        parts.append("## Tech Stack")
        for k, v in stack.items():
            parts.append(f"- **{k.title()}**: {v}")

    arch = decisions.get("architecture", "")
    if arch:
        parts.append(f"\n## Architecture\n{arch}")

    reasoning = decisions.get("reasoning", "")
    if reasoning:
        parts.append(f"\n## Reasoning\n{reasoning}")

    changes = decisions.get("changes_needed", "")
    if changes:
        parts.append(f"\n## Changes Needed\n{changes}")

    dir_structure = decisions.get("directory_structure", "")
    if dir_structure:
        parts.append(f"\n## Directory Structure (all agents must follow this)\n{dir_structure}")

    return "\n".join(parts) if parts else str(decisions)


def _format_usage_for_output(usage: dict) -> str:
    return format_usage_summary(usage)


def _normalize_planned_files(files: list[str]) -> list[str]:
    """Rewrite unsafe env-file plans into documentation files and normalize paths."""
    normalized: list[str] = []
    seen: set[str] = set()

    for raw_path in files or []:
        path = str(raw_path or "").strip()
        if not path:
            continue
        while path.startswith("./"):
            path = path[2:]
        if _is_blocked_env_path(path):
            parent = str(Path(path).parent)
            path = ".env.example" if parent in {"", "."} else f"{parent}/.env.example"
        if path not in seen:
            normalized.append(path)
            seen.add(path)
    return normalized


def _is_blocked_env_path(path: str) -> bool:
    lowered = path.strip().lower()
    if not lowered:
        return False
    return lowered.endswith("/.env") or lowered in {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
    } or lowered.endswith((
        "/.env.local",
        "/.env.production",
        "/.env.development",
    ))
