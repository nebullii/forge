"""Debug agent — reads crash tracebacks and fixes the failing code.

Called automatically by `forge dev` when the server crashes. Reads the
traceback, identifies the failing file(s), and produces a fix. The dev
server applies the fix and restarts.
"""

import re
from pathlib import Path

from .base import BaseAgent


class DebugAgent(BaseAgent):
    name = "debug"
    skill_description = (
        "Reads a runtime error traceback, identifies the root cause, "
        "and produces a corrected version of the failing file."
    )
    role = (
        "You are Forge Debug, an expert at reading Python and JavaScript "
        "tracebacks and fixing the root cause.\n\n"
        "RULES:\n"
        "- Read the traceback carefully. Identify the EXACT file and line that failed.\n"
        "- Read the current contents of the failing file.\n"
        "- Fix ONLY the bug that caused the crash. Do not refactor or improve other code.\n"
        "- Output the COMPLETE corrected file using:\n\n"
        "```file:path/to/file.ext\n"
        "<complete corrected file>\n"
        "```\n\n"
        "- If the fix requires reading other files (e.g., to check an import path), "
        "the relevant files will be provided in context.\n"
        "- Be precise. One fix per crash.\n"
        "- NEVER add comments to JSON files (package.json, tsconfig.json, etc.) — "
        "JSON does not support comments. This will break the project.\n"
        "- When fixing import errors, check the actual filenames on disk before "
        "writing the fix."
    )

    def diagnose_and_fix(
        self,
        traceback_text: str,
        project_root: Path,
    ) -> list[tuple[str, str]]:
        """Analyze a traceback and return fixed files.

        Args:
            traceback_text: The full stderr/traceback from the crashed process.
            project_root: Root of the project directory.

        Returns:
            List of (filepath, content) tuples for fixed files.
        """
        # Extract files mentioned in the traceback
        failing_files = self._extract_failing_files(traceback_text, project_root)

        # Read contents of failing files + related files
        context_files = {}
        for fp in failing_files:
            full = project_root / fp
            if full.exists():
                try:
                    context_files[fp] = full.read_text()
                except Exception:
                    pass

        # Also try to find files referenced in import errors
        import_targets = self._extract_import_targets(traceback_text, project_root)
        for fp in import_targets:
            if fp not in context_files:
                full = project_root / fp
                if full.exists():
                    try:
                        context_files[fp] = full.read_text()
                    except Exception:
                        pass

        # Build prompt
        files_section = ""
        for fp, content in context_files.items():
            files_section += f"\n### {fp}\n```\n{content}\n```\n"

        # List all project files for import resolution
        all_files = self._list_project_files(project_root)
        file_tree = "\n".join(f"  {f}" for f in all_files[:100])

        prompt = f"""\
The development server crashed with this error:

```
{traceback_text[-3000:]}
```

## Project files involved
{files_section}

## All project files
{file_tree}

Fix the crash. Output the COMPLETE corrected file(s) using:

```file:path/to/file.ext
<complete corrected file contents>
```

Fix ONLY what's needed to resolve this specific crash. Do not change anything else."""

        response = self.invoke(prompt)
        return self.extract_files(response)

    def _extract_failing_files(
        self, traceback_text: str, project_root: Path,
    ) -> list[str]:
        """Extract file paths from a traceback that belong to the project.

        Handles both Python and Node.js traceback formats.
        """
        root_str = str(project_root.resolve())
        files = []

        # Python: File "/path/to/file.py", line 10
        for match in re.finditer(
            r'File "([^"]+)", line \d+',
            traceback_text,
        ):
            path = match.group(1)
            if root_str in path:
                rel = path.replace(root_str + "/", "")
                if rel not in files:
                    files.append(rel)

        # Node.js: at Object.<anonymous> (/path/to/file.js:10:5)
        # Also: at /path/to/file.js:10:5
        for match in re.finditer(
            r'(?:at\s+(?:\S+\s+)?)?\(?([^():\s]+\.[jt]sx?):(\d+):\d+\)?',
            traceback_text,
        ):
            path = match.group(1)
            if root_str in path:
                rel = path.replace(root_str + "/", "")
                if rel not in files:
                    files.append(rel)

        # Node.js: Error: Cannot find module './routes/users'
        for match in re.finditer(
            r"Cannot find module '([^']+)'",
            traceback_text,
        ):
            mod = match.group(1)
            if mod.startswith("."):
                # Relative module — try as file
                for ext in [".js", ".jsx", ".ts", ".tsx", "/index.js"]:
                    candidate = mod.lstrip("./") + ext
                    if (project_root / candidate).exists() and candidate not in files:
                        files.append(candidate)

        return files

    def _extract_import_targets(
        self, traceback_text: str, project_root: Path,
    ) -> list[str]:
        """Try to find files that a failed import was looking for."""
        targets = []

        # ModuleNotFoundError: No module named 'routers.bookmark'
        match = re.search(
            r"No module named '([^']+)'",
            traceback_text,
        )
        if match:
            module_path = match.group(1).replace(".", "/")
            # Try both as directory/__init__.py and as .py file
            for suffix in [".py", "/__init__.py"]:
                candidate = module_path + suffix
                if (project_root / candidate).exists():
                    targets.append(candidate)

            # Also list files in the parent directory to help the LLM
            parent = Path(module_path).parent
            parent_dir = project_root / parent
            if parent_dir.is_dir():
                for f in parent_dir.iterdir():
                    if f.is_file() and f.suffix == ".py":
                        rel = str(f.relative_to(project_root))
                        if rel not in targets:
                            targets.append(rel)

        # ImportError: cannot import name 'x' from 'y'
        match = re.search(
            r"cannot import name '(\w+)' from '([^']+)'",
            traceback_text,
        )
        if match:
            module_path = match.group(2).replace(".", "/") + ".py"
            if (project_root / module_path).exists():
                targets.append(module_path)

        return targets

    def _list_project_files(self, project_root: Path) -> list[str]:
        """List all source files in the project."""
        skip = {".forge", "__pycache__", "node_modules", ".git", "venv", ".venv"}
        files = []
        for p in sorted(project_root.rglob("*")):
            if p.is_file() and not any(s in p.parts for s in skip):
                try:
                    files.append(str(p.relative_to(project_root)))
                except ValueError:
                    pass
        return files
