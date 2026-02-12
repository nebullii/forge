"""Build orchestrator -- drives the multi-agent build pipeline."""

import sys
import uuid
import yaml
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .providers import create_provider
from .providers.base import ProviderConfig
from .agents import PlannerAgent, CoderAgent, ReviewerAgent
from .security.firewall import AgenticFirewall
from .state import (
    BuildState, TaskState, load_build_state, save_build_state, compute_spec_hash,
)
from .context import build_context_string


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
    ):
        self.forge_path = forge_path
        self.project_root = forge_path.parent
        self.review = review
        self.verbose = verbose

        self.provider = create_provider(provider_config)
        self.planner = PlannerAgent(self.provider, self.project_root)
        self.coder = CoderAgent(self.provider, self.project_root)
        self.reviewer = ReviewerAgent(self.provider, self.project_root) if review else None

        self.firewall = AgenticFirewall(
            policy_path=self.forge_path / "firewall_policy.json",
            audit_log=self.forge_path / "firewall_audit.log"
        )

        self.state = load_build_state(forge_path)
        self.provider_config = provider_config

    def run(self, feature: Optional[str] = None):
        """Run the build (or incremental feature addition)."""
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
        print("Phase 1: Planning...")
        print("")

        existing_context = build_context_string(self.project_root, max_tokens=2000)

        if feature:
            plan = self.planner.plan_incremental(spec, rules, feature, existing_context)
        else:
            plan = self.planner.analyze_and_plan(spec, rules, existing_context)

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

        print(f"   Plan: {len(self.state.tasks)} tasks")
        for t in self.state.tasks:
            print(f"     - {t.name}")
        print("")

    def _phase_build(self, spec: str, rules: str):
        print("Phase 2: Building...")
        print("")
        self._execute_remaining_tasks(spec, rules)

    def _execute_remaining_tasks(self, spec: str, rules: str):
        total = len(self.state.tasks)

        for i in range(self.state.current_task_index, total):
            task = self.state.tasks[i]

            if task.status == "completed":
                continue

            print(f"   [{i+1}/{total}] {task.name}")

            task.status = "in_progress"
            task.started_at = datetime.now().isoformat()
            self.state.current_task_index = i
            self._save_state()

            try:
                project_context = build_context_string(
                    self.project_root, max_tokens=3000
                )

                task_dict = {
                    "name": task.name,
                    "description": task.description,
                    "files": [],
                }

                response = self.coder.generate_files(
                    task_dict, spec, rules,
                    self.state.decisions, project_context
                )

                files = self.coder.extract_files(response)
                
                # Apply Agentic Firewall
                allowed_files = []
                for filepath, content in files:
                    permitted, reason = self.firewall.validate_file_write(filepath, content)
                    if permitted:
                        allowed_files.append((filepath, content))
                    else:
                        print(f"      🚨 FIREWALL BLOCK: {filepath} ({reason})")
                        self.state.errors.append(f"Firewall blocked {filepath}: {reason}")

                written = self.coder.write_files(allowed_files)

                task.files_written = written
                task.status = "completed"
                task.completed_at = datetime.now().isoformat()
                self.state.files_written.extend(written)

                for f in written:
                    print(f"      + {f}")

            except KeyboardInterrupt:
                task.status = "pending"
                self._save_state()
                raise
            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                self.state.errors.append(f"Task '{task.name}': {e}")
                self._save_state()
                print(f"      ERROR: {e}")
                continue

            self._save_state()

        print("")

    def _phase_review(self, spec: str, rules: str):
        print("Phase 3: Reviewing...")

        self.state.status = "reviewing"
        self._save_state()

        files_dict = {}
        for filepath in self.state.files_written:
            full_path = self.project_root / filepath
            if full_path.exists():
                try:
                    files_dict[filepath] = full_path.read_text()
                except Exception:
                    pass

        if not files_dict:
            print("   No files to review.")
            print("")
            return

        review = self.reviewer.review_files(files_dict, spec, rules)

        if review["passed"]:
            print("   Review passed.")
        else:
            issues = review.get("issues", [])
            print(f"   Review found {len(issues)} issue(s):")
            errors = [i for i in issues if i.get("severity") == "error"]
            warnings = [i for i in issues if i.get("severity") == "warning"]

            for issue in errors:
                print(f"      ERROR in {issue.get('file', '?')}: {issue.get('message', '')}")
            for issue in warnings:
                print(f"      WARN  in {issue.get('file', '?')}: {issue.get('message', '')}")

            if errors:
                print("")
                print("   Attempting auto-fix...")
                for issue in errors:
                    filepath = issue.get("file", "")
                    if filepath in files_dict:
                        try:
                            response = self.coder.fix_file(
                                filepath, files_dict[filepath],
                                issue.get("message", ""), spec, rules
                            )
                            fixed_files = self.coder.extract_files(response)
                            written = self.coder.write_files(fixed_files)
                            for f in written:
                                print(f"      ~ {f} (fixed)")
                        except Exception as e:
                            print(f"      Could not fix {filepath}: {e}")

        review_path = self.forge_path / "review.yaml"
        with open(review_path, "w") as f:
            yaml.dump(review, f, default_flow_style=False)

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
            r"\bpost\b",
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
            print(f"WARNING: Suspicious pattern(s) found in .forge/{name}: {unique}")

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

    return "\n".join(parts) if parts else str(decisions)
