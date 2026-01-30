"""Local development server with auto-detection."""

import os
import subprocess
import sys
import signal
import time
from pathlib import Path


class DevServer:
    """Auto-detecting development server."""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.process = None

    def detect_project_type(self) -> tuple[str, list[str]]:
        """Detect project type and return (type, command)."""

        # Python with uvicorn (FastAPI/Starlette)
        if (self.project_path / "main.py").exists():
            content = (self.project_path / "main.py").read_text()
            if "fastapi" in content.lower() or "starlette" in content.lower():
                return ("python-uvicorn", ["uvicorn", "main:app", "--reload"])

        # Python with Flask
        if (self.project_path / "app.py").exists():
            content = (self.project_path / "app.py").read_text()
            if "flask" in content.lower():
                return ("python-flask", ["flask", "run", "--reload"])

        # Python generic
        if (self.project_path / "main.py").exists():
            return ("python", ["python", "main.py"])
        if (self.project_path / "app.py").exists():
            return ("python", ["python", "app.py"])

        # Node.js
        package_json = self.project_path / "package.json"
        if package_json.exists():
            import json
            pkg = json.loads(package_json.read_text())
            scripts = pkg.get("scripts", {})
            if "dev" in scripts:
                return ("node", ["npm", "run", "dev"])
            if "start" in scripts:
                return ("node", ["npm", "start"])

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

    def run(self, port: int = 8080):
        """Run the development server."""
        project_type, command = self.detect_project_type()

        if project_type == "unknown":
            print("Could not detect project type.")
            print("Supported: Python (FastAPI/Flask), Node.js, Go, Static HTML")
            return

        # Add port to command where applicable
        if project_type == "python-uvicorn":
            command.extend(["--port", str(port)])
        elif project_type == "python-flask":
            command.extend(["--port", str(port)])
        elif project_type == "static":
            command.append(str(port))
        elif project_type == "node":
            os.environ["PORT"] = str(port)

        print(f"🚀 Starting {project_type} server on port {port}")
        print(f"   http://localhost:{port}")
        print("")
        print("Press Ctrl+C to stop")
        print("")

        def signal_handler(sig, frame):
            if self.process:
                self.process.terminate()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)

        try:
            self.process = subprocess.Popen(
                command,
                cwd=self.project_path,
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            self.process.wait()
        except FileNotFoundError as e:
            print(f"Error: {command[0]} not found")
            if project_type == "python-uvicorn":
                print("Install with: pip install uvicorn")
            elif project_type == "node":
                print("Install Node.js from https://nodejs.org")
        except Exception as e:
            print(f"Error: {e}")


def cmd_dev(args):
    """Run local development server."""
    server = DevServer(Path.cwd())
    server.run(port=getattr(args, 'port', None) or 8080)
