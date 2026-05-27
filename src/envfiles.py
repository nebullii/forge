"""Helpers for materializing local env files from .env.example templates."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .security.firewall import AgenticFirewall


def env_target_for_example(example_path: Path) -> Path:
    """Return the sibling .env path for a .env.example file."""
    name = example_path.name
    if name == ".env.example":
        return example_path.with_name(".env")
    if name.endswith(".env.example"):
        return example_path.with_name(name[: -len(".example")])
    return example_path.with_name(".env")


def materialize_env_files(
    project_root: Path,
    candidate_paths: list[str] | None = None,
    firewall: "AgenticFirewall | None" = None,
) -> list[str]:
    """Create local .env files from .env.example templates if they don't exist.

    The copy is one-way and non-destructive: existing .env files are preserved.
    Returns project-relative paths for any files created.
    """
    created: list[str] = []

    if candidate_paths is None:
        examples = sorted(project_root.rglob(".env.example"))
    else:
        examples = []
        seen: set[Path] = set()
        for relative in candidate_paths:
            candidate = project_root / relative
            if candidate.name != ".env.example":
                continue
            resolved = candidate.resolve()
            if resolved in seen or not candidate.exists():
                continue
            seen.add(resolved)
            examples.append(candidate)

    for example in examples:
        target = env_target_for_example(example)
        if target.exists():
            continue
        content = example.read_text()
        if firewall is not None:
            ok, _reason = firewall.validate_materialized_env_write(
                target.relative_to(project_root).as_posix(),
                example.relative_to(project_root).as_posix(),
                content,
            )
            if not ok:
                continue
        target.write_text(content)
        created.append(target.relative_to(project_root).as_posix())

    return created
