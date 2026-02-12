"""Context management -- assembles project context within token budgets."""

from pathlib import Path
from typing import Optional

CHARS_PER_TOKEN = 4

SKIP_DIRS = {
    ".forge", ".git", "__pycache__", "venv", ".venv",
    "node_modules", "dist", "build", ".next", ".cache",
    "env", ".egg-info",
}

SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".bz2",
    ".db", ".sqlite", ".sqlite3",
    ".lock",
    ".pem", ".key", ".crt", ".cer", ".p12", ".pfx", ".jks", ".keystore",
}

CONFIG_NAMES = {
    "package.json", "requirements.txt", "pyproject.toml", "Cargo.toml",
    "go.mod", "manifest.json", "Dockerfile", "docker-compose.yml",
    ".env.example", "README.md",
}

SENSITIVE_NAMES = {
    ".env", ".env.local", ".env.development", ".env.production",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "credentials", "credential", "secrets", "secret", "token",
    "apikey", "api_key", "password", "passwd", "private",
}


def gather_project_files(project_root: Path) -> list[tuple[Path, str]]:
    """Gather all readable project files as (relative_path, content) pairs."""
    files = []
    for path in sorted(project_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(project_root)

        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts):
            continue
        if path.suffix.lower() in SKIP_EXTENSIONS:
            continue
        name_lower = path.name.lower()
        if name_lower in SENSITIVE_NAMES:
            continue
        if any(marker in name_lower for marker in SENSITIVE_NAMES):
            continue

        try:
            content = path.read_text(errors="replace")
            files.append((rel, content))
        except Exception:
            continue

    return files


def build_context_string(
    project_root: Path,
    max_tokens: int = 4000,
    include_files: Optional[list[str]] = None,
) -> str:
    """Build a context string of project files within a token budget.

    Prioritizes config files, then includes source files by size (small first).
    Truncates large files and lists remaining files if over budget.
    """
    all_files = gather_project_files(project_root)

    if include_files:
        all_files = [(p, c) for p, c in all_files if str(p) in include_files]

    max_chars = max_tokens * CHARS_PER_TOKEN
    parts = []
    used_chars = 0

    def priority(item):
        path, content = item
        is_config = path.name in CONFIG_NAMES
        return (0 if is_config else 1, len(content))

    all_files.sort(key=priority)

    for rel_path, content in all_files:
        header = f"### {rel_path}\n```\n"
        footer = "\n```\n\n"
        overhead = len(header) + len(footer)

        available = max_chars - used_chars - overhead
        if available <= 0:
            parts.append(f"### {rel_path} ({len(content)} chars, skipped)\n")
            continue

        if len(content) <= available:
            parts.append(f"{header}{content}{footer}")
            used_chars += overhead + len(content)
        else:
            truncated = content[:available]
            parts.append(
                f"{header}{truncated}\n... (truncated, {len(content)} chars total){footer}"
            )
            used_chars += overhead + available + 50

    if not parts:
        return "(No project files yet)"

    return "".join(parts)


def build_file_tree(project_root: Path) -> str:
    """Build a simple file tree string for the project."""
    files = gather_project_files(project_root)
    if not files:
        return "(empty project)"

    lines = []
    for rel_path, content in files:
        line_count = content.count("\n") + 1
        lines.append(f"  {rel_path} ({line_count} lines)")

    return "\n".join(lines)
