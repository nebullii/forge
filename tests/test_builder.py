"""Tests for deterministic bootstrap behavior in the builder."""

from src.agents.builder import BuilderAgent
from src.providers.base import BaseProvider, ProviderConfig


class _ExplodingProvider(BaseProvider):
    def __init__(self):
        super().__init__(ProviderConfig(name="ollama", model="qwen2.5:3b"))

    def chat(self, messages, system=""):
        raise AssertionError("deterministic scaffold should avoid provider calls")

    def stream(self, messages, system=""):
        raise AssertionError("stream should not be used")


class _EchoProvider(BaseProvider):
    def __init__(self):
        super().__init__(ProviderConfig(name="ollama", model="qwen2.5:3b"))

    def chat(self, messages, system=""):
        return "PROVIDER_RESPONSE"

    def stream(self, messages, system=""):
        yield "PROVIDER_RESPONSE"


def test_builder_uses_deterministic_scaffold_for_supported_setup_task(tmp_path):
    builder = BuilderAgent(_ExplodingProvider(), tmp_path)
    task = {
        "name": "Set up supported web app skeleton",
        "description": "Create validated project skeleton",
        "specialization": "setup",
        "files": [
            "README.md",
            ".gitignore",
            "backend/.env.example",
            "backend/main.py",
            "frontend/package.json",
            "frontend/index.html",
            "frontend/vite.config.js",
            "frontend/.env.example",
            "frontend/src/main.jsx",
            "frontend/src/App.jsx",
        ],
    }
    decisions = {
        "template_family": "web-app",
        "stack": {
            "framework": "FastAPI",
            "frontend": "react",
            "styling": "tailwind",
        }
    }

    spec = """# Project: Neighborhood Bakery

## What
A simple marketing website for a neighborhood bakery.

## Users
- Local customers

## Features
- Homepage
- Menu page
- Contact form

## Pages
- `/` - Home
- `/menu` - Menu

## API Endpoints
- `GET /api/menu` - List menu items
- `POST /api/contact` - Send contact request
"""

    response = builder.build_task(task, spec, "rules", decisions)

    assert "```file:.gitignore" in response
    assert "```file:backend/.env.example" in response
    assert "## Overview" in response
    assert "## Initial Scope" in response
    assert "## API Endpoints" in response
    assert "forge dev" in response
    assert "```file:frontend/package.json" in response
    assert "```file:frontend/index.html" in response
    assert "```file:frontend/src/main.jsx" in response
    assert "```file:backend/main.py" in response
    assert "VITE_API_URL=" in response


def test_builder_only_bootstraps_setup_tasks_and_delegates_backend_work(tmp_path):
    builder = BuilderAgent(_EchoProvider(), tmp_path)
    task = {
        "name": "Implement FastAPI backend",
        "description": "Build API",
        "specialization": "backend",
        "files": ["backend/main.py", "backend/routes/api.py"],
    }
    decisions = {
        "template_family": "web-app",
        "stack": {
            "framework": "FastAPI",
            "frontend": "react",
            "styling": "tailwind",
        }
    }

    response = builder.build_task(task, "Neighborhood bakery website", "rules", decisions)

    assert response == "PROVIDER_RESPONSE"
