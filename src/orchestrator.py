"""Build orchestrator -- drives the multi-agent build pipeline."""

import logging
import sys
import threading
import uuid
import yaml
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

from .providers import create_provider
from .providers.base import ProviderConfig
from .agents import PlannerAgent, CoderAgent, ReviewerAgent
from .agents import BackendAgent, FrontendAgent, SecurityAgent, CIAgent, DeployAgent
from .agents import ProjectManagerAgent
from .security.firewall import AgenticFirewall
from .state import (
    BuildState, TaskState, load_build_state, save_build_state, compute_spec_hash,
)
from .context import build_context_string
from .skills import SkillsLoader
from .collaboration import (
    ArtifactBus,
    ContractRegistry,
    CodeArtifact,
    DecisionArtifact,
    BuildLogArtifact,
    extract_contracts_from_response,
)

if TYPE_CHECKING:
    from .ui import BuildUI


class BuildOrchestrator:
    """Orchestrates the full build pipeline.

    Pipeline phases:
      1. PLANNING   -- PlannerAgent analyzes spec, produces task list
      2. BUILDING   -- CoderAgent executes each task sequentially
      3. REVIEWING  -- ReviewerAgent validates the output (optional)

    State is persisted after each task, enabling resume on failure.
    """

    def __init__(
        self,
        provider_config: ProviderConfig,
        forge_path: Path,
        review: bool = True,
        verbose: bool = False,
        use_adk: bool = False,
        ui: Optional["BuildUI"] = None,
    ):
        self.forge_path = forge_path
        self.project_root = forge_path.parent
        self.review = review
        self.verbose = verbose
        self.use_adk = use_adk
        self.ui = ui

        self.provider = create_provider(provider_config)

        # Load skills for this project
        skills = SkillsLoader().load(self.project_root)

        self.planner = PlannerAgent(self.provider, self.project_root, skills_loader=skills)
        self.coder = CoderAgent(self.provider, self.project_root, skills_loader=skills)
        self.reviewer = ReviewerAgent(self.provider, self.project_root, skills_loader=skills) if review else None
        self.project_manager = ProjectManagerAgent(self.provider, self.project_root, skills_loader=skills)

        # ADK specialized agents (initialized lazily in ADK mode)
        self._adk_agents = None
        self._classic_agents: dict = {}  # lazy: agent_name → agent instance
        self._skills = skills

        # Collaboration layer — shared artifact bus and contract registry
        # Load existing contracts for incremental builds (forge build --feature)
        contracts_path = self.forge_path / "contracts.json"
        self.bus = ArtifactBus()
        self.registry = (
            ContractRegistry.load(contracts_path)
            if contracts_path.exists()
            else ContractRegistry()
        )

        self.firewall = AgenticFirewall(
            policy_path=self.forge_path / "firewall_policy.json",
            audit_log=self.forge_path / "firewall_audit.log"
        )

        self.state = load_build_state(forge_path)
        self.provider_config = provider_config
        self._build_start_time: Optional[float] = None
        self._state_lock = threading.Lock()  # protects state mutations in parallel mode

    def _init_adk_agents(self) -> dict:
        """Initialize all specialized agents as ADK LlmAgent + ADKAgentRunner instances."""
        if self._adk_agents is not None:
            return self._adk_agents

        from .adk.llm_bridge import create_forge_llm
        from .adk.agent_runner import ADKAgentRunner
        from .agents import (
            create_planner_agent, create_backend_agent, create_frontend_agent,
            create_security_agent, create_ci_agent, create_deploy_agent,
            create_reviewer_agent, create_project_manager_agent,
        )

        llm = create_forge_llm(self.provider)

        self._adk_agents = {
            "planner": ADKAgentRunner(
                create_planner_agent(llm), name="planner",
                skill_description="Analyzes spec and produces a structured build plan.",
            ),
            "backend": ADKAgentRunner(
                create_backend_agent(llm), name="backend",
                skill_description="Generates FastAPI backend: routes, models, services.",
            ),
            "frontend": ADKAgentRunner(
                create_frontend_agent(llm), name="frontend",
                skill_description="Generates React/TypeScript frontend with API integration.",
            ),
            "security": ADKAgentRunner(
                create_security_agent(llm), name="security",
                skill_description="OWASP security audit and code hardening.",
            ),
            "ci": ADKAgentRunner(
                create_ci_agent(llm), name="ci",
                skill_description="Generates GitHub Actions workflows, Dockerfile, docker-compose.",
            ),
            "deploy": ADKAgentRunner(
                create_deploy_agent(llm), name="deploy",
                skill_description="Generates deployment configs for Railway, Render, Vercel, Fly.io.",
            ),
            "reviewer": ADKAgentRunner(
                create_reviewer_agent(llm), name="reviewer",
                skill_description="Reviews all generated code for correctness and consistency.",
            ),
            "project_manager": ADKAgentRunner(
                create_project_manager_agent(llm), name="project_manager",
                skill_description="Assigns tasks to specialized agents with targeted prompts.",
            ),
        }
        return self._adk_agents

    def run(self, feature: Optional[str] = None):
        """Run the build (or incremental feature addition)."""
        self._build_start_time = time.monotonic()

        spec = self._read_forge_file("spec.md")
        rules = self._read_forge_file("rules.md")
        self._warn_suspicious(spec, "spec.md")
        self._warn_suspicious(rules, "rules.md")

        if not spec:
            print("Error: .forge/spec.md is empty or missing.")
            print("Edit it with your project description first.")
            sys.exit(1)

        if self.use_adk:
            self._run_adk(spec, rules)
            return

        if self._can_resume(spec):
            print("Resuming previous build...")
            print("")
            self._execute_remaining_tasks(spec, rules)
        else:
            self._init_state(spec)
            self._phase_plan(spec, rules, feature)
            self._phase_manage(spec, rules)
            self._phase_build(spec, rules)

        if self.review and self.reviewer:
            self._phase_review(spec, rules)

        self.state.status = "completed"
        self.state.completed_at = datetime.now().isoformat()
        self._save_state()

        # Persist contracts for incremental builds
        self.registry.save(self.forge_path / "contracts.json")

        if self.ui:
            self.ui.build_summary(
                files=self.state.files_written,
                errors=self.state.errors,
                start_time=self._build_start_time,
            )
    def _run_adk(self, spec: str, rules: str):
        """Run the build using the ADK + A2A multi-agent pipeline."""
        from .adk.orchestrator_agent import ForgeADKOrchestrator

        self._init_state(spec)
        self.state.status = "building"
        self._save_state()

        print("Phase 1-7: ADK Multi-Agent Pipeline")
        print("  PlannerAgent → BackendAgent → FrontendAgent →")
        print("  SecurityAgent → CIAgent → DeployAgent → ReviewerAgent")
        print("")

        agents = self._init_adk_agents()
        orchestrator = ForgeADKOrchestrator(
            provider=self.provider,
            forge_path=self.forge_path,
            agents=agents,
        )

        result = orchestrator.run(spec, rules, verbose=self.verbose)

        # Surface agent errors before writing anything
        errors = result.get("errors", [])
        for err in errors:
            logger.warning("ADK agent error: %s", err)

        # Abort if planning itself failed — nothing useful to write
        if errors and not result.get("files_written"):
            self.state.status = "failed"
            self.state.completed_at = datetime.now().isoformat()
            self._save_state()
            raise RuntimeError(f"ADK build failed: {errors[0]}")

        # Write all generated files through the firewall
        all_files = result.get("files_written", [])
        written = []
        for filepath, content in all_files:
            permitted, reason = self.firewall.validate_file_write(filepath, content)
            if permitted:
                try:
                    self.coder.write_files([(filepath, content)])
                    written.append(filepath)
                    print(f"   + {filepath}")
                except Exception as e:
                    print(f"   ERROR writing {filepath}: {e}")
                    self.state.errors.append(f"Write error {filepath}: {e}")
            else:
                print(f"   FIREWALL BLOCK: {filepath} ({reason})")
                self.state.errors.append(f"Firewall blocked {filepath}: {reason}")

        self.state.files_written.extend(written)

        # Print review summary if available
        review = result.get("review")
        if review and isinstance(review, dict):
            passed = review.get("passed")
            issues = review.get("issues", [])
            if passed is True:
                print("\nReview: passed")
            elif issues:
                print(f"\nReview: {len(issues)} issue(s) found")
            print("")

        self.state.status = "completed"
        self.state.completed_at = datetime.now().isoformat()
        self._save_state()

    def _can_resume(self, spec: str) -> bool:
        if self.state.status in ("not_started", "completed"):
            return False
        current_hash = compute_spec_hash(self.forge_path)
        if self.state.spec_hash != current_hash:
            return False
        pending = [t for t in self.state.tasks if t.status in ("pending", "in_progress")]
        return len(pending) > 0

    def _init_state(self, spec: str):
        self.state = BuildState(
            build_id=uuid.uuid4().hex[:8],
            status="planning",
            started_at=datetime.now().isoformat(),
            provider=self.provider_config.name,
            model=self.provider_config.model,
            spec_hash=compute_spec_hash(self.forge_path),
        )
        self._save_state()

    def _phase_plan(self, spec: str, rules: str, feature: Optional[str]):
        if self.ui:
            self.ui.phase_start("Phase 1: Planning")
            self.ui.spinner_start("    Analyzing spec")
        else:
            print("Phase 1: Planning...")
            print("")

        existing_context = build_context_string(self.project_root, max_tokens=2000)

        if feature:
            plan = self.planner.plan_incremental(spec, rules, feature, existing_context)
        else:
            plan = self.planner.analyze_and_plan(spec, rules, existing_context)

        if self.ui:
            self.ui.spinner_stop()

        decisions = plan.get("decisions", {})
        self.state.decisions = _format_decisions(decisions)

        decisions_path = self.forge_path / "decisions.md"
        decisions_path.write_text(f"# Build Decisions\n\n{self.state.decisions}\n")

        self.state.tasks = []
        for i, task_data in enumerate(plan.get("tasks", [])):
            task = TaskState(
                id=task_data.get("id", f"task_{i+1:02d}"),
                name=task_data.get("name", "Unnamed task"),
                description=task_data.get("description", ""),
                agent=task_data.get("agent", "coder"),
            )
            self.state.tasks.append(task)

        self.state.status = "building"
        self.state.current_task_index = 0
        self._save_state()

        if self.ui:
            self.ui.phase_end(f"  {len(self.state.tasks)} tasks planned")
            self.ui.set_tasks([t.name for t in self.state.tasks])
        else:
            print(f"   Plan: {len(self.state.tasks)} tasks")
            for t in self.state.tasks:
                print(f"     - {t.name}")
            print("")

    def _phase_manage(self, spec: str, rules: str):
        """Phase 1b: Project Manager enriches tasks with agent assignments + prompts."""
        if self.ui:
            self.ui.spinner_start("    Project Manager distributing tasks")
        else:
            print("Phase 1b: Project Manager...")
            print("")

        tasks_as_dicts = [
            {"id": t.id, "name": t.name, "description": t.description, "agent": t.agent}
            for t in self.state.tasks
        ]
        plan = {"decisions": {}, "tasks": tasks_as_dicts}

        # Recover decisions from decisions.md if present
        decisions_path = self.forge_path / "decisions.md"
        if decisions_path.exists():
            plan["decisions"] = {"raw": decisions_path.read_text()}

        try:
            enriched = self.project_manager.enrich_plan(plan, spec, rules)
        except Exception as e:
            if self.ui:
                self.ui.spinner_stop()
            else:
                print(f"   WARNING: Project Manager failed ({e}), using original plan")
                print("")
            return

        if self.ui:
            self.ui.spinner_stop()

        enriched_tasks = enriched.get("tasks", [])
        enriched_by_id = {t.get("id"): t for t in enriched_tasks}

        for task_state in self.state.tasks:
            enriched_task = enriched_by_id.get(task_state.id)
            if enriched_task:
                task_state.agent = enriched_task.get("agent", task_state.agent or "coder")
                task_state.prompt = enriched_task.get("prompt", "")
                task_state.contracts = enriched_task.get("contracts", "")

        self._save_state()

        if not self.ui:
            for t in self.state.tasks:
                pad = " " * max(0, 40 - len(t.name))
                print(f"     {t.name}{pad}→ {t.agent}")
            print("")

    def _get_classic_agent(self, agent_name: str):
        """Return (or lazily create) the classic-mode agent instance for the given role."""
        if agent_name not in self._classic_agents:
            cls_map = {
                "backend":  BackendAgent,
                "frontend": FrontendAgent,
                "ci":       CIAgent,
                "deploy":   DeployAgent,
                "security": SecurityAgent,
                "coder":    CoderAgent,
            }
            cls = cls_map.get(agent_name, CoderAgent)
            self._classic_agents[agent_name] = cls(
                self.provider, self.project_root, skills_loader=self._skills
            )
        return self._classic_agents[agent_name]

    def _phase_build(self, spec: str, rules: str):
        if self.ui:
            self.ui.phase_start("Phase 2: Building")
        else:
            print("Phase 2: Building...")
            print("")

        # Check if we can parallelise: tasks must span multiple agent types
        agents_used = {(t.agent or "coder") for t in self.state.tasks}
        if len(agents_used) > 1:
            self._execute_tasks_parallel(spec, rules)
        else:
            self._execute_tasks_sequential(spec, rules)

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

        agent_name = task.agent or "coder"
        agent = self._get_classic_agent(agent_name)

        # Inject contract context for frontend tasks
        prompt_to_use = task.prompt
        if agent_name == "frontend" and prompt_to_use and len(self.registry) > 0:
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

        if prompt_to_use:
            response = agent.invoke(prompt_to_use)
        else:
            task_dict = {
                "name": task.name,
                "description": task.description,
                "files": [],
            }
            response = self.coder.generate_files(
                task_dict, spec, rules,
                self.state.decisions, project_context,
            )

        files = agent.extract_files(response)

        # Apply Agentic Firewall
        allowed_files = []
        for filepath, content in files:
            permitted, reason = self.firewall.validate_file_write(filepath, content)
            if permitted:
                allowed_files.append((filepath, content))
            else:
                if not self.ui:
                    with self._state_lock:
                        print(f"      FIREWALL BLOCK: {filepath} ({reason})")
                self.state.errors.append(f"Firewall blocked {filepath}: {reason}")

        written = agent.write_files(allowed_files)

        # Publish to artifact bus (thread-safe)
        for filepath, content in allowed_files:
            self.bus.publish(CodeArtifact(
                path=filepath, content=content,
                producer_agent=agent_name, task_id=task.id,
            ))

        # Extract contracts from backend agent responses
        if agent_name == "backend":
            contracts = extract_contracts_from_response(
                response, producer_agent="backend",
            )
            self.registry.register_many(contracts.get("api", []))
            self.registry.register_many(contracts.get("models", []))
            self.registry.register_many(contracts.get("events", []))

        task.files_written = written
        task.status = "completed"
        task.completed_at = datetime.now().isoformat()

        with self._state_lock:
            self.state.files_written.extend(written)
            self._save_state()

        if self.ui:
            self.ui.task_done(task.name, written)
        else:
            with self._state_lock:
                for f in written:
                    print(f"      + {f}")

    def _task_by_id(self, task_id: str):
        """Look up a TaskState by id."""
        for t in self.state.tasks:
            if t.id == task_id:
                return t
        return None

    def _execute_remaining_tasks(self, spec: str, rules: str):
        """Backward-compat entry point used by the resume path."""
        agents_used = {(t.agent or "coder") for t in self.state.tasks}
        if len(agents_used) > 1:
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
            agents = {n.agent for n in graph}
            print(f"   Parallel scheduler: {len(graph)} tasks across {agents}")
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

        review = self.reviewer.review_files(files_dict, spec, rules + contracts_note)

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
                            fix_agent = self._get_classic_agent(producer)

                            response = fix_agent.invoke(
                                f"Fix this issue in {filepath}:\n"
                                f"Issue: {issue.get('message', '')}\n\n"
                                f"Current file contents:\n```\n{files_dict[filepath]}\n```\n\n"
                                f"## Spec\n{spec}\n\n## Rules\n{rules}\n\n"
                                f"Output the complete corrected file using:\n"
                                f"```file:{filepath}\n<complete corrected file>\n```"
                            )
                            fixed_files = fix_agent.extract_files(response)
                            written = fix_agent.write_files(fixed_files)

                            # Update bus with fixed versions
                            for fp, content in fixed_files:
                                existing = self.bus.latest(fp)
                                version = (existing.version + 1) if existing else 1
                                self.bus.publish(CodeArtifact(
                                    path=fp,
                                    content=content,
                                    producer_agent=producer,
                                    version=version,
                                ))

                            fixes_applied += len(written)
                            if not self.ui:
                                for f in written:
                                    print(f"      ~ {f} (fixed by {producer})")
                        except Exception as e:
                            if not self.ui:
                                print(f"      Could not fix {filepath}: {e}")

        review_path = self.forge_path / "review.yaml"
        with open(review_path, "w") as f:
            yaml.dump(review, f, default_flow_style=False)

        if self.ui:
            fix_note = f", {fixes_applied} auto-fix(es) applied" if fixes_applied else ""
            status = "passed" if review["passed"] else f"{len(review.get('issues', []))} issue(s)"
            self.ui.phase_end(f"  Review {status}{fix_note}")
        else:
            print("")

    def _read_forge_file(self, name: str) -> str:
        path = self.forge_path / name
        if path.exists():
            return path.read_text()
        return ""

    def _warn_suspicious(self, text: str, name: str) -> None:
        if not text:
            return

        patterns = [
            r"\bexfiltrat(e|ion|ing)\b",
            r"\bleak\b",
            r"\bsecret(s)?\b",
            r"\btoken(s)?\b",
            r"\bapi[- _]?key(s)?\b",
            r"\bpassword(s)?\b",
            r"\bprivate key\b",
            r"\bssh\b",
            r"\bcredential(s)?\b",
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
        ]

        hits = []
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                hits.append(pat.strip("\\b").replace("\\", ""))

        if hits:
            unique = ", ".join(sorted(set(hits)))
            logger.warning("Suspicious pattern(s) found in .forge/%s: %s", name, unique)

    def _save_state(self):
        save_build_state(self.forge_path, self.state)


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
