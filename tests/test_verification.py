"""Tests for deterministic verification."""

from src.collaboration import ContractRegistry, ApiEndpointContract, UIDataDependency
from src.verification import VerificationContext, VerificationRegistry


def test_verification_registry_runs_python_and_contract_checks(tmp_path):
    registry = ContractRegistry()
    registry.register(ApiEndpointContract(method="GET", path="/users", producer_agent="backend"))
    registry.register(UIDataDependency(view_name="Users", endpoint="GET /users", producer_agent="frontend"))

    context = VerificationContext(
        project_root=tmp_path,
        files={"app/main.py": "def ok():\n    return 1\n"},
        decisions={},
        contracts=registry,
    )
    report = VerificationRegistry().run(context)

    assert report.passed is True
    names = {result.verifier for result in report.results}
    assert "python_syntax" in names
    assert "contract_consistency" in names


def test_verification_report_fails_on_python_syntax_error(tmp_path):
    registry = ContractRegistry()
    context = VerificationContext(
        project_root=tmp_path,
        files={"app/main.py": "def broken(:\n    pass\n"},
        decisions={},
        contracts=registry,
    )
    report = VerificationRegistry().run(context)

    assert report.passed is False
    syntax = next(result for result in report.results if result.verifier == "python_syntax")
    assert syntax.passed is False
    assert "invalid syntax" in syntax.details


def test_supported_stack_structure_verifier_requires_core_fastapi_react_files(tmp_path):
    registry = ContractRegistry()
    context = VerificationContext(
        project_root=tmp_path,
        files={
            "backend/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "frontend/package.json": "{\"name\": \"app\"}",
            "frontend/index.html": "<!doctype html><div id='root'></div>",
        },
        decisions={"stack": {"framework": "fastapi", "frontend": "react"}},
        contracts=registry,
    )

    report = VerificationRegistry().run(context)
    structure = next(result for result in report.results if result.verifier == "supported_stack_structure")
    assert structure.passed is False
    assert "frontend/src/main.jsx|frontend/src/main.js" in structure.details


def test_supported_stack_structure_verifier_infers_frontend_from_generated_files(tmp_path):
    registry = ContractRegistry()
    context = VerificationContext(
        project_root=tmp_path,
        files={
            "backend/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "frontend/App.jsx": "export default function App() { return null }\n",
            "package.json": "{\"name\": \"app\"}",
        },
        decisions={"stack": {"framework": "fastapi", "frontend": "none"}},
        contracts=registry,
    )

    report = VerificationRegistry().run(context)
    structure = next(result for result in report.results if result.verifier == "supported_stack_structure")
    assert structure.passed is False
    assert "frontend/package.json" in structure.details


def test_supported_stack_structure_verifier_requires_frontend_index_html(tmp_path):
    registry = ContractRegistry()
    context = VerificationContext(
        project_root=tmp_path,
        files={
            "backend/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "frontend/package.json": "{\"name\": \"app\"}",
            "frontend/src/main.jsx": "console.log('ok')\n",
        },
        decisions={"stack": {"framework": "fastapi", "frontend": "react"}},
        contracts=registry,
    )

    report = VerificationRegistry().run(context)
    structure = next(result for result in report.results if result.verifier == "supported_stack_structure")
    assert structure.passed is False
    assert "frontend/index.html" in structure.details


def test_frontend_project_verifier_requires_scripts_and_resolvable_imports(tmp_path):
    registry = ContractRegistry()
    context = VerificationContext(
        project_root=tmp_path,
        files={
            "frontend/App.jsx": (
                "import Home from './pages/Home';\n"
                "export default function App() { return <Home />; }\n"
            ),
            "package.json": "{\"name\": \"bakery\", \"scripts\": {\"build\": \"vite build\"}}",
        },
        decisions={},
        contracts=registry,
    )

    report = VerificationRegistry().run(context)
    frontend = next(result for result in report.results if result.verifier == "frontend_project")
    assert frontend.passed is False
    assert "missing 'dev' script" in frontend.details
    assert "missing import target './pages/Home'" in frontend.details


def test_frontend_project_verifier_accepts_parent_directory_imports(tmp_path):
    registry = ContractRegistry()
    context = VerificationContext(
        project_root=tmp_path,
        files={
            "frontend/package.json": "{\"name\": \"bakery\", \"scripts\": {\"dev\": \"vite\", \"build\": \"vite build\"}}",
            "frontend/src/pages/Menu.jsx": "import { api } from '../api/index'\nexport default function Menu() { return null }\n",
            "frontend/src/api/index.js": "export const api = {}\n",
        },
        decisions={},
        contracts=registry,
    )

    report = VerificationRegistry().run(context)
    frontend = next(result for result in report.results if result.verifier == "frontend_project")
    assert frontend.passed is True
