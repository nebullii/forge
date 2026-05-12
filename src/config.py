"""Configuration for Forge."""

import os
import yaml
from pathlib import Path
from typing import Optional


CONFIG_DIR = Path.home() / ".forge"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

OLLAMA_URL = "http://localhost:11434"

CLOUD_FIRST_CONFIG = """\
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
    profiles:
      fast_local:
        model: llama3.1
        capabilities: [cheap, code, local]
      code_local:
        model: qwen2.5-coder:14b
        capabilities: [code, local, reasoning]
      reason_local:
        model: qwen3:32b
        capabilities: [reasoning, large_context, local]

model_routing:
  planner: ollama:reason_local
  builder: ollama:code_local
  reviewer: ollama:reason_local
  security: ollama:reason_local
"""

# Kept for callers that imported DEFAULT_CONFIG directly.
DEFAULT_CONFIG = CLOUD_FIRST_CONFIG


# Ranked preference of locally-installed models. Earlier patterns win.
_LOCAL_PREFERENCE = (
    "qwen2.5-coder:32b",
    "qwen2.5-coder:14b",
    "qwen2.5-coder:7b",
    "qwen2.5-coder",
    "deepseek-coder",
    "qwen3:32b",
    "qwen3:14b",
    "qwen3",
    "qwen2.5:32b",
    "qwen2.5:14b",
    "qwen2.5",
    "llama3.3",
    "llama3.1:70b",
    "llama3.1",
    "llama3.2",
    "llama3",
    "mistral",
)


def detect_ollama_models(base_url: str = OLLAMA_URL, timeout: float = 1.5) -> list[str]:
    """Return installed Ollama model tags, or [] if Ollama is unreachable."""
    try:
        import requests
        response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []
    names: list[str] = []
    for item in payload.get("models", []) or []:
        name = item.get("model") or item.get("name")
        if name:
            names.append(name)
    return names


def pick_local_model(installed: list[str]) -> Optional[str]:
    """Pick the best-fit model from the installed set."""
    if not installed:
        return None
    lowered = [(m, m.lower()) for m in installed]
    for pref in _LOCAL_PREFERENCE:
        for original, lower in lowered:
            if lower.startswith(pref):
                return original
    return installed[0]


def build_local_first_config(installed: list[str]) -> str:
    """Render an Ollama-first config YAML for the detected models."""
    picked = pick_local_model(installed) or "llama3.1:8b"
    coder = next(
        (m for m in installed if "coder" in m.lower() or "code" in m.lower()),
        picked,
    )
    return f"""\
# Forge Configuration (local-first)
# Detected Ollama on {OLLAMA_URL} — using it as the primary provider.
# Cloud providers remain as fallbacks; set their API keys to enable them.

providers:
  - name: ollama
    base_url: {OLLAMA_URL}
    model: {picked}
    discover: true
    priority: 10
    profiles:
      primary:
        model: {picked}
        capabilities: [code, reasoning, local]
      coder:
        model: {coder}
        capabilities: [code, local]

  - name: anthropic
    api_key: ${{ANTHROPIC_API_KEY}}
    model: claude-sonnet-4-20250514
    priority: 5

  - name: openai
    api_key: ${{OPENAI_API_KEY}}
    model: gpt-4o
    priority: 4

model_routing:
  planner: ollama:primary
  builder: ollama:coder
  reviewer: ollama:primary
  security: ollama:primary
"""


def generate_default_config(detect: bool = True) -> tuple[str, list[str]]:
    """Return ``(yaml_text, installed_local_models)``.

    When *detect* is True and Ollama is running with at least one model
    installed, returns the local-first config. Otherwise returns the cloud
    default.
    """
    if detect:
        installed = detect_ollama_models()
        if installed:
            return build_local_first_config(installed), installed
    return CLOUD_FIRST_CONFIG, []


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
    """Load config, creating default if it doesn't exist.

    First-run path: detect a running Ollama with installed models and write
    a local-first config. Otherwise fall back to the cloud default.
    """
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        yaml_text, installed = generate_default_config(detect=True)
        CONFIG_FILE.write_text(yaml_text)
        print(f"Created config at {CONFIG_FILE}")
        if installed:
            picked = pick_local_model(installed)
            print(f"Detected local Ollama with {len(installed)} model(s) — using '{picked}' by default.")
            print("Cloud providers remain available as fallbacks; set API keys to enable them.")
        else:
            print("Edit it to add your API keys, or set environment variables.")
    return load_config()


def get_provider_config(config: dict, provider_name: Optional[str] = None):
    """Resolve which provider to use. Returns a ProviderConfig."""
    from .router import _provider_config_from_dict

    providers = config.get("providers", [])
    if not providers:
        raise ValueError(
            "No providers configured.\n"
            f"Run 'forge config init' or edit {CONFIG_FILE}"
        )

    if provider_name:
        resolved = _resolve_named_provider(providers, provider_name)
        if resolved is not None:
            return _provider_config_from_dict(resolved)
        raise ValueError(f"Provider '{provider_name}' not found in config.")

    # Find all providers with valid credentials
    valid = []
    for p in providers:
        api_key = p.get("api_key")
        base_url = p.get("base_url")
        if (api_key and api_key.strip()) or base_url:
            valid.append(p)

    if not valid:
        raise ValueError(
            "No provider has valid credentials.\n"
            "Set ANTHROPIC_API_KEY or OPENAI_API_KEY, or edit ~/.forge/config.yaml"
        )

    # One valid provider — use it automatically
    if len(valid) == 1:
        return _provider_config_from_dict(valid[0])

    # Multiple valid providers — ask the user to pick
    print("Multiple AI providers found:\n")
    for i, p in enumerate(valid, 1):
        name = p.get("name", "unknown")
        model = p.get("model", "")
        print(f"  {i}. {name}  ({model})")
    print()

    try:
        while True:
            choice = input(f"Which provider? (1-{len(valid)}): ").strip()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(valid):
                    break
                print(f"  Enter a number between 1 and {len(valid)}")
            except ValueError:
                print("  Enter a number")
    except KeyboardInterrupt:
        print("\nCancelled.")
        import sys
        sys.exit(0)

    chosen = valid[idx]
    return _provider_config_from_dict(chosen)


def _resolve_named_provider(providers: list[dict], provider_name: str) -> Optional[dict]:
    ref = provider_name.lower()
    for provider in providers:
        name = provider.get("name", "").lower()
        if name == ref:
            return provider

        profiles = provider.get("profiles", {})
        if isinstance(profiles, dict):
            for profile_name, profile in profiles.items():
                profile_ref = f"{name}:{profile_name}".lower()
                if ref in {profile_ref, profile_name.lower(), f"{name}/{profile_name}".lower()}:
                    merged = dict(provider)
                    merged.update(profile or {})
                    merged.pop("profiles", None)
                    merged["profile"] = profile_name
                    return merged
    return None


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
