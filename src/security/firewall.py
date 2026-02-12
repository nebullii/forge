"""Agentic Firewall (AFW) - Core security layer for any app."""

import re
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime

DEFAULT_POLICY = {
    "allowed_paths": [
        "src/.*",
        "app/.*",
        "apps/.*",
        "packages/.*",
        "services/.*",
        "lib/.*",
        "libs/.*",
        "components/.*",
        "tests/.*",
        "test/.*",
        "docs/.*",
        "public/.*",
        "static/.*",
        "assets/.*",
        "templates/.*",
        "scripts/.*",
        "config/.*",
        "infra/.*",
        "ops/.*",
        "docker/.*",
        "\\.github/.*",
        "README.md",
        "LICENSE.*",
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "Cargo.toml",
        "go.mod",
        "go.sum",
        "Makefile",
        "Dockerfile",
        "docker-compose\\.ya?ml"
    ],
    "blocked_paths": [
        ".env.*",
        "\\.ssh/.*",
        "\\.aws/.*",
        "\\.gnupg/.*",
        "\\.kube/.*",
        "\\.git/.*",
        "\\.npmrc",
        "\\.pypirc",
        "config/secrets.json",
        "config/credentials.json",
        ".*/\\.bash_history",
        "/etc/.*",
        "/var/.*",
        "/private/.*",
        "/System/.*"
    ],
    "blocked_patterns": [
        "eval\\(",
        "exec\\(",
        "os\\.system\\(",
        "subprocess\\.run\\(",
        "__import__",
        "getattr\\(",
        "setattr\\(",
        "importlib\\."
    ]
}

class AgenticFirewall:
    """Zero-trust middleware for agent tool calls."""

    def __init__(self, policy_path: Optional[Path] = None, audit_log: Optional[Path] = None):
        self.policy = DEFAULT_POLICY
        if policy_path and policy_path.exists():
            with open(policy_path, "r") as f:
                self.policy = json.load(f)
        
        self.audit_log = audit_log or Path("firewall_audit.log")

    def validate_file_write(self, filepath: str, content: str) -> Tuple[bool, str]:
        """Validate if a file write is permitted."""
        
        # Check Blocked Paths
        for pattern in self.policy.get("blocked_paths", []):
            if re.search(pattern, filepath):
                self._log_violation(filepath, "BLOCKED_PATH")
                return False, f"Access to sensitive path '{filepath}' is prohibited by policy."

        # Check Allowed Paths
        is_allowed = False
        for pattern in self.policy.get("allowed_paths", []):
            if re.search(pattern, filepath):
                is_allowed = True
                break
        
        if not is_allowed:
            self._log_violation(filepath, "PATH_NOT_IN_ALLOWLIST")
            return False, f"Path '{filepath}' is not in the allowlist. Only project-related files can be edited."

        # Check for Malicious Patterns in Content
        for pattern in self.policy.get("blocked_patterns", []):
            if re.search(pattern, content):
                self._log_violation(filepath, f"MALICIOUS_CONTENT_PATTERN: {pattern}")
                return False, f"Potentially malicious code pattern detected in '{filepath}'."

        self._log_event(filepath, "PERMITTED")
        return True, "Success"

    def _log_event(self, target: str, action: str, detail: str = ""):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "target": target,
            "action": action,
            "detail": detail
        }
        with open(self.audit_log, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    def _log_violation(self, target: str, violation_type: str):
        print(f"⚠️  SECURITY VIOLATION: {violation_type} on {target}")
        self._log_event(target, "DENIED", violation_type)
