"""Local development server with auto-detection and crash auto-fix.

When the server crashes, the DebugAgent reads the traceback, identifies the
failing file, produces a fix, and restarts the server. This loop runs up to
MAX_FIX_ATTEMPTS times before giving up.
"""

import json
import os
import subprocess
import sys
import signal
import time
from pathlib import Path
from typing import Optional

MAX_FIX_ATTEMPTS = 5


class DevServer:
    """Auto-detecting development server with debug agent integration."""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.process = None
        self._provider = None       # cached across fix attempts
        self._provider_config = None

    def detect_project_type(self) -> tuple[str, list[str]]:
        """Detect project type and return (type, command)."""

        # Python with uvicorn (FastAPI/Starlette) — search for main.py/app.py
        # anywhere in the project (up to 3 levels deep)
        python_entry = self._find_python_entry()
        if python_entry:
            return python_entry

        # Python generic
        if (self.project_path / "main.py").exists():
            return ("python", ["python", "main.py"])
        if (self.project_path / "app.py").exists():
            return ("python", ["python", "app.py"])

        # Node.js
        package_json = self.project_path / "package.json"
        if package_json.exists():
            try:
                pkg = json.loads(package_json.read_text())
                scripts = pkg.get("scripts", {})
                if "dev" in scripts:
                    return ("node", ["npm", "run", "dev"])
                if "start" in scripts:
                    return ("node", ["npm", "start"])
            except (json.JSONDecodeError, OSError):
                pass

        # Go
        if (self.project_path / "main.go").exists():
            return ("go", ["go", "run", "."])
        if (self.project_path / "go.mod").exists():
            return ("go", ["go", "run", "."])

        # Static files (index.html)
        if (self.project_path / "index.html").exists():
            return ("static", ["python", "-m", "http.server"])

        # Check for common static directories
        for static_dir in ["public", "dist", "build", "static"]:
            if (self.project_path / static_dir / "index.html").exists():
                return ("static", ["python", "-m", "http.server", "--directory", static_dir])

        return ("unknown", [])

    def _find_python_entry(self) -> Optional[tuple[str, list[str]]]:
        """Search for a FastAPI/Flask entry point up to 3 levels deep."""
        skip = {"node_modules", ".forge", "__pycache__", ".git", "venv", ".venv"}
        # Sort by depth (shallowest first) so backend/main.py wins over backend/app/main.py
        for py_file in sorted(self.project_path.rglob("main.py"), key=lambda p: len(p.parts)):
            if any(s in py_file.parts for s in skip):
                continue
            # Don't go deeper than 3 levels
            try:
                rel = py_file.relative_to(self.project_path)
            except ValueError:
                continue
            if len(rel.parts) > 4:
                continue

            try:
                content = py_file.read_text()[:2000]
            except OSError:
                continue

            if "fastapi" in content.lower() or "starlette" in content.lower():
                # Build uvicorn module path: backend/app/main.py → backend.app.main:app
                module = str(rel.with_suffix("")).replace("/", ".") + ":app"
                return ("python-uvicorn", ["uvicorn", module, "--reload"])
            if "flask" in content.lower():
                return ("python-flask", ["python", str(rel)])

        # Also check app.py
        for py_file in sorted(self.project_path.rglob("app.py"), key=lambda p: len(p.parts)):
            if any(s in py_file.parts for s in skip):
                continue
            try:
                rel = py_file.relative_to(self.project_path)
            except ValueError:
                continue
            if len(rel.parts) > 4:
                continue
            try:
                content = py_file.read_text()[:2000]
            except OSError:
                continue

            if "fastapi" in content.lower() or "starlette" in content.lower():
                module = str(rel.with_suffix("")).replace("/", ".") + ":app"
                return ("python-uvicorn", ["uvicorn", module, "--reload"])
            if "flask" in content.lower():
                return ("python-flask", ["python", str(rel)])

        return None

    def _install_deps(self, project_type: str) -> None:
        """Auto-install project dependencies before starting the server."""
        skip = {"node_modules", ".forge", "__pycache__", ".git", "venv", ".venv"}

        if project_type in ("python-uvicorn", "python-flask", "python"):
            # Find all requirements.txt files
            req_files = [
                f for f in self.project_path.rglob("requirements.txt")
                if not any(s in f.parts for s in skip)
            ]
            for req in req_files:
                print(f"Installing dependencies: {req.relative_to(self.project_path)}")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-q", "-r", str(req)],
                    cwd=self.project_path,
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    print(f"  Warning: pip install failed: {result.stderr[:200]}")

        elif project_type == "node":
            pkg = self.project_path / "package.json"
            nm = self.project_path / "node_modules"
            if pkg.exists() and not nm.exists():
                print("Installing dependencies: npm install")
                result = subprocess.run(
                    ["npm", "install"],
                    cwd=self.project_path,
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    print(f"  Warning: npm install failed: {result.stderr[:200]}")

            # Also check frontend/ subdirectory
            frontend_pkg = self.project_path / "frontend" / "package.json"
            frontend_nm = self.project_path / "frontend" / "node_modules"
            if frontend_pkg.exists() and not frontend_nm.exists():
                print("Installing dependencies: frontend/npm install")
                subprocess.run(
                    ["npm", "install"],
                    cwd=self.project_path / "frontend",
                    capture_output=True, text=True,
                )

    def _detect_frontend(self) -> Optional[tuple[Path, list[str]]]:
        """Detect a frontend subdirectory that needs its own dev server."""
        for name in ["frontend", "client", "web"]:
            pkg = self.project_path / name / "package.json"
            if pkg.exists():
                try:
                    data = json.loads(pkg.read_text())
                    scripts = data.get("scripts", {})
                    if "dev" in scripts:
                        return (self.project_path / name, ["npm", "run", "dev"])
                    if "start" in scripts:
                        return (self.project_path / name, ["npm", "start"])
                except (json.JSONDecodeError, OSError):
                    pass
        return None

    def run(self, port: int = 8080, auto_fix: bool = True):
        """Run the development server with optional crash auto-fix.

        For full-stack projects (backend + frontend), starts both servers.

        Args:
            port: Port number for the server.
            auto_fix: If True, use the DebugAgent to fix crashes and restart.
        """
        project_type, command = self.detect_project_type()

        if project_type == "unknown":
            print("Could not detect project type.")
            print("Supported: Python (FastAPI/Flask), Node.js, Go, Static HTML")
            return

        # Auto-install dependencies before starting
        self._install_deps(project_type)

        # Detect frontend for full-stack projects
        frontend = None
        frontend_process = None
        if project_type in ("python-uvicorn", "python-flask"):
            frontend = self._detect_frontend()
            if frontend:
                frontend_dir, frontend_cmd = frontend
                # Install frontend deps
                if not (frontend_dir / "node_modules").exists():
                    print(f"Installing frontend dependencies...")
                    subprocess.run(
                        ["npm", "install"], cwd=frontend_dir,
                        capture_output=True, text=True,
                    )

        # Add port to command
        if project_type == "python-uvicorn":
            if not auto_fix:
                command.append("--reload")
            command.extend(["--port", str(port)])
        elif project_type == "python-flask":
            command.extend(["--port", str(port)])
        elif project_type == "static":
            command.append(str(port))
        elif project_type == "node":
            os.environ["PORT"] = str(port)

        def signal_handler(sig, frame):
            if self.process:
                self.process.terminate()
            if frontend_process:
                frontend_process.terminate()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)

        # Start frontend in background if detected
        if frontend:
            frontend_dir, frontend_cmd = frontend
            frontend_port = port + 1
            os.environ["PORT"] = str(frontend_port)
            print(f"Starting frontend on port {frontend_port}")
            print(f"   http://localhost:{frontend_port}")
            print()
            frontend_process = subprocess.Popen(
                frontend_cmd, cwd=frontend_dir,
                stdout=sys.stdout, stderr=sys.stderr,
            )

        attempt = 0
        while True:
            print(f"Starting {project_type} server on port {port}")
            print(f"   http://localhost:{port}")
            if auto_fix:
                print(f"   Auto-fix enabled ({MAX_FIX_ATTEMPTS - attempt} attempts remaining)")
            print()

            exit_code, stderr_output = self._run_process(command)

            if exit_code == 0 or exit_code == -2:  # clean exit or Ctrl+C
                break

            # Server crashed
            attempt += 1
            print(f"\n--- Server crashed (exit code {exit_code}) ---\n")

            if not auto_fix or attempt > MAX_FIX_ATTEMPTS:
                if attempt > MAX_FIX_ATTEMPTS:
                    print(f"Gave up after {MAX_FIX_ATTEMPTS} fix attempts.")
                print("Fix the error above and run forge dev again.")
                break

            # Try to auto-fix
            fixed = self._try_auto_fix(stderr_output, attempt)
            if not fixed:
                print("Could not auto-fix. Fix the error above and run forge dev again.")
                break

            print(f"\n--- Restarting server (attempt {attempt}/{MAX_FIX_ATTEMPTS}) ---\n")

        # Clean up frontend process
        if frontend_process and frontend_process.poll() is None:
            frontend_process.terminate()

    def _run_process(self, command: list[str]) -> tuple[int, str]:
        """Run the server process and capture stderr on crash.

        Returns (exit_code, stderr_text).
        """
        try:
            self.process = subprocess.Popen(
                command,
                cwd=self.project_path,
                stdout=sys.stdout,
                stderr=subprocess.PIPE,
            )

            # Read stderr in real-time and capture it
            stderr_lines = []
            for line in self.process.stderr:
                decoded = line.decode("utf-8", errors="replace")
                sys.stderr.write(decoded)
                sys.stderr.flush()
                stderr_lines.append(decoded)

            self.process.wait()
            return self.process.returncode or 0, "".join(stderr_lines)

        except FileNotFoundError:
            msg = f"Error: {command[0]} not found"
            print(msg)
            return 1, msg
        except KeyboardInterrupt:
            if self.process:
                self.process.terminate()
            return -2, ""

    def _try_auto_fix(self, stderr_output: str, attempt: int) -> bool:
        """Use the DebugAgent to fix the crash.

        Returns True if a fix was applied, False if auto-fix isn't available
        or the agent couldn't produce a fix.
        """
        if not stderr_output.strip():
            print("  No error output to diagnose.")
            return False

        # Load provider once, reuse across attempts
        if self._provider is None:
            try:
                from .config import load_config, get_provider_config
                from .providers import create_provider

                config = load_config()
                if not config:
                    print("  No config found — cannot auto-fix.")
                    return False
                self._provider_config = get_provider_config(config)
                self._provider = create_provider(self._provider_config)
            except (ValueError, ImportError, Exception) as e:
                print(f"  Auto-fix unavailable: {e}")
                return False

        from .agents.debug import DebugAgent

        print(f"  Debug agent analyzing crash... ({self._provider_config})")

        agent = DebugAgent(self._provider, self.project_path)

        try:
            fixes = agent.diagnose_and_fix(stderr_output, self.project_path)
        except Exception as e:
            print(f"  Debug agent failed: {e}")
            return False

        if not fixes:
            print("  Debug agent couldn't produce a fix.")
            return False

        # Apply fixes
        for filepath, content in fixes:
            full_path = (self.project_path / filepath).resolve()
            # Safety: don't write outside project root
            try:
                full_path.relative_to(self.project_path.resolve())
            except ValueError:
                print(f"  Skipping {filepath} (outside project root)")
                continue

            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            print(f"  Fixed: {filepath}")

        return True


def cmd_dev(args):
    """Run local development server."""
    server = DevServer(Path.cwd())
    port = getattr(args, 'port', None) or 8080
    no_fix = getattr(args, 'no_fix', False)
    server.run(port=port, auto_fix=not no_fix)
