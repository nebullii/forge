from pathlib import Path

from src.envfiles import env_target_for_example, materialize_env_files
from src.security.firewall import AgenticFirewall


def test_env_target_for_example_uses_sibling_env_name():
    path = Path("frontend/.env.example")

    assert env_target_for_example(path) == Path("frontend/.env")


def test_materialize_env_files_creates_missing_env_from_example(tmp_path):
    project_root = tmp_path
    example = project_root / "frontend" / ".env.example"
    example.parent.mkdir(parents=True)
    example.write_text("VITE_API_URL=\n")

    created = materialize_env_files(project_root)

    assert created == ["frontend/.env"]
    assert (project_root / "frontend" / ".env").read_text() == "VITE_API_URL=\n"


def test_materialize_env_files_does_not_overwrite_existing_env(tmp_path):
    project_root = tmp_path
    example = project_root / ".env.example"
    example.write_text("API_KEY=\n")
    env_file = project_root / ".env"
    env_file.write_text("API_KEY=real-value\n")

    created = materialize_env_files(project_root)

    assert created == []
    assert env_file.read_text() == "API_KEY=real-value\n"


def test_materialize_env_files_respects_candidate_paths(tmp_path):
    project_root = tmp_path
    frontend_example = project_root / "frontend" / ".env.example"
    backend_example = project_root / "backend" / ".env.example"
    frontend_example.parent.mkdir(parents=True)
    backend_example.parent.mkdir(parents=True)
    frontend_example.write_text("VITE_API_URL=\n")
    backend_example.write_text("DATABASE_URL=\n")

    created = materialize_env_files(project_root, ["frontend/.env.example"])

    assert created == ["frontend/.env"]
    assert (project_root / "frontend" / ".env").exists()
    assert not (project_root / "backend" / ".env").exists()


def test_materialize_env_files_uses_firewall_control_plane_rule(tmp_path):
    project_root = tmp_path
    example = project_root / "frontend" / ".env.example"
    example.parent.mkdir(parents=True)
    example.write_text("VITE_API_URL=\n")
    firewall = AgenticFirewall(audit_log=project_root / "audit.log")

    created = materialize_env_files(project_root, firewall=firewall)

    assert created == ["frontend/.env"]
    assert "CONTROLLED_ENV_MATERIALIZATION" in (project_root / "audit.log").read_text()
