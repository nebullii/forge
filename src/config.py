"""Configuration for Forge."""

import os
import yaml
from pathlib import Path
from typing import Optional


CONFIG_DIR = Path.home() / ".forge"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

DEFAULT_CONFIG = """\
# Forge Configuration
# The first provider with valid credentials will be used.
# API keys can be set here or as environment variables.

providers:
  - name: anthropic
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-sonnet-4-20250514

  - name: openai
    api_key: ${OPENAI_API_KEY}
    model: gpt-4o

  - name: together
    api_key: ${TOGETHER_API_KEY}
    model: meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo

  - name: ollama
    base_url: http://localhost:11434
    model: llama3.1
"""


def load_config() -> dict:
    """Load user config from ~/.forge/config.yaml."""
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f) or {}
    return _expand_env_vars(config)


def save_config(config: dict):
    """Save config to ~/.forge/config.yaml."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def ensure_config() -> dict:
    """Load config, creating default if it doesn't exist."""
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(DEFAULT_CONFIG)
        print(f"Created config at {CONFIG_FILE}")
        print("Edit it to add your API keys, or set environment variables.")
    return load_config()


def get_provider_config(config: dict, provider_name: Optional[str] = None):
    """Resolve which provider to use. Returns a ProviderConfig."""
    from .providers.base import ProviderConfig

    providers = config.get("providers", [])
    if not providers:
        raise ValueError(
            "No providers configured.\n"
            f"Run 'forge config init' or edit {CONFIG_FILE}"
        )

    if provider_name:
        for p in providers:
            if p["name"].lower() == provider_name.lower():
                return ProviderConfig(**{k: v for k, v in p.items() if v})
        raise ValueError(f"Provider '{provider_name}' not found in config.")

    # Use first provider with valid credentials
    for p in providers:
        api_key = p.get("api_key")
        base_url = p.get("base_url")
        if (api_key and api_key.strip()) or base_url:
            return ProviderConfig(**{k: v for k, v in p.items() if v})

    raise ValueError(
        "No provider has valid credentials.\n"
        "Set ANTHROPIC_API_KEY or OPENAI_API_KEY, or edit ~/.forge/config.yaml"
    )


def _expand_env_vars(obj):
    """Recursively expand ${VAR} in config values."""
    if isinstance(obj, str):
        if obj.startswith("${") and obj.endswith("}"):
            return os.environ.get(obj[2:-1], "")
        return obj
    elif isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    return obj
