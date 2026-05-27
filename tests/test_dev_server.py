import json

from src.dev_server import DevServer


def test_find_python_entry_returns_uvicorn_command_without_reload(tmp_path):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")

    server = DevServer(tmp_path)
    detected = server._find_python_entry()

    assert detected == ("python-uvicorn", ["uvicorn", "backend.main:app"])


def test_frontend_runtime_command_adds_vite_port_flags(tmp_path):
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "package.json").write_text(json.dumps({
        "scripts": {
            "dev": "vite",
        }
    }))

    server = DevServer(tmp_path)
    command = server._frontend_runtime_command(frontend_dir, ["npm", "run", "dev"], 8080)

    assert command == ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "8080"]


def test_frontend_runtime_command_leaves_non_vite_script_alone(tmp_path):
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "package.json").write_text(json.dumps({
        "scripts": {
            "dev": "next dev",
        }
    }))

    server = DevServer(tmp_path)
    command = server._frontend_runtime_command(frontend_dir, ["npm", "run", "dev"], 8080)

    assert command == ["npm", "run", "dev"]
