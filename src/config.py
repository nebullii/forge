"""Configuration management for Forge."""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


CONFIG_DIR = Path.home() / ".forge"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


@dataclass
class Provider:
    """AI provider configuration."""
    name: str
    api_key: Optional[str]
    model: str
    base_url: Optional[str] = None

    def __str__(self):
        return f"{self.name} ({self.model})"


def load_config() -> dict:
    """Load configuration from ~/.forge/config.yaml."""
    if not CONFIG_FILE.exists():
        create_default_config()

    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)

    # Expand environment variables
    config = _expand_env_vars(config)
    return config


def _expand_env_vars(obj):
    """Recursively expand ${VAR} patterns in config."""
    if isinstance(obj, str):
        if obj.startswith("${") and obj.endswith("}"):
            var_name = obj[2:-1]
            return os.environ.get(var_name, "")
        return obj
    elif isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    return obj


def get_provider(config: dict, provider_name: Optional[str] = None) -> Provider:
    """Get AI provider from config."""
    providers = config.get("providers", [])

    if not providers:
        raise ValueError("No providers configured. Edit ~/.forge/config.yaml")

    # Find requested provider or use first one
    if provider_name:
        for p in providers:
            if p["name"] == provider_name:
                return Provider(**p)
        raise ValueError(f"Provider '{provider_name}' not found in config")

    # Use first provider with a valid API key
    for p in providers:
        if p.get("api_key") or p.get("base_url"):
            return Provider(**p)

    raise ValueError("No configured provider has valid credentials")


def create_default_config():
    """Create default config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    default_config = """# Forge Configuration

# AI Providers (first with valid credentials is used)
providers:
  - name: anthropic
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-sonnet-4-20250514

  - name: openai
    api_key: ${OPENAI_API_KEY}
    model: gpt-4o

  - name: google
    api_key: ${GOOGLE_API_KEY}
    model: gemini-1.5-pro

  - name: ollama
    base_url: http://localhost:11434
    model: llama3.1

  - name: groq
    api_key: ${GROQ_API_KEY}
    model: llama-3.1-70b-versatile

# Deployment targets
deploy:
  default: gcloud

  gcloud:
    project: ${GCLOUD_PROJECT}
    region: us-central1

  vercel:
    token: ${VERCEL_TOKEN}

  railway:
    token: ${RAILWAY_TOKEN}

  render:
    api_key: ${RENDER_API_KEY}
"""

    CONFIG_FILE.write_text(default_config)
    print(f"Created default config at {CONFIG_FILE}")
    print("Edit it to add your API keys.")
