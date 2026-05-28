"""Forge CLI - Project scaffolding for LLM-assisted development."""

import os
import sys
import shutil
import argparse
import subprocess
import json
from pathlib import Path

import yaml

from .policy import write_default_policy
from .support import is_recommended_ollama_model, is_supported_provider
from .evals import run_eval
from .quality import QualityTracker


FORGE_DIR = ".forge"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Template descriptions for the templates command and interactive mode
TEMPLATES = {
    "web-app":    "Full-stack web app (React + FastAPI + SQLite)",
    "api-only":   "REST API backend (FastAPI + SQLite)",
    "ai-app":     "AI/LLM application (OpenAI/Anthropic + chat UI)",
    "chrome-ext": "Chrome browser extension (Manifest V3)",
    "cli-tool":   "Command-line tool (Click/Typer + packaging)",
    "data-viz":   "Dashboard/visualization (Streamlit or React + charts)",
    "slack-bot":  "Slack bot (slack-bolt)",
    "discord-bot":"Discord bot (discord.py)",
}

# Detailed stack info shown during interactive spec building
TEMPLATE_STACKS = {
    "web-app":    "React · FastAPI · SQLite · Tailwind · Railway",
    "api-only":   "FastAPI · Pydantic · SQLite · Railway",
    "ai-app":     "React · FastAPI · OpenAI/Anthropic · Railway",
    "chrome-ext": "Manifest V3 · JavaScript/React · Chrome Storage",
    "cli-tool":   "Python · Click/Typer · Rich · PyPI",
    "data-viz":   "Streamlit or React · Plotly/Recharts · Railway",
    "slack-bot":  "Python · slack-bolt · Railway",
    "discord-bot":"Python · discord.py · Railway",
}


def _merge_setup_provider(existing: dict, new_entry: dict) -> dict:
    """Persist one active provider while preserving unrelated config keys."""
    merged = dict(existing or {})
    merged["providers"] = [new_entry]
    return merged


def _interactive_new(default_name=None):
    """Interactive project creation: template picker + spec builder."""
    template_list = list(TEMPLATES.keys())
    divider = "─" * 50

    # ── Step 1: Pick template ──────────────────────────────
    print()
    print("What kind of project are you building?\n")
    for i, (name, desc) in enumerate(TEMPLATES.items(), 1):
        stack = TEMPLATE_STACKS.get(name, "")
        print(f"  {i}. {name:12}  {desc}")
        print(f"     {'':12}  Stack: {stack}")
        print()
    print(f"  {len(TEMPLATES) + 1}. (blank)       Start from scratch")
    print()

    while True:
        try:
            choice = input(f"Choose a template (1-{len(TEMPLATES) + 1}): ").strip()
            choice_num = int(choice)
            if 1 <= choice_num <= len(TEMPLATES):
                template = template_list[choice_num - 1]
                break
            elif choice_num == len(TEMPLATES) + 1:
                template = None
                break
            else:
                print(f"  Please enter a number between 1 and {len(TEMPLATES) + 1}.")
        except (ValueError, KeyboardInterrupt):
            print("\nCancelled.")
            sys.exit(0)

    # ── Step 2: Project name ───────────────────────────────
    print()
    if template:
        stack = TEMPLATE_STACKS.get(template, "")
        print(f"  Template : {template}")
        print(f"  Stack    : {stack}")
        print()

    if default_name:
        project_name = default_name
        print(f"Project name: {project_name}")
    else:
        while True:
            try:
                project_name = input("Project name: ").strip()
                if project_name:
                    break
                print("  Project name cannot be empty.")
            except KeyboardInterrupt:
                print("\nCancelled.")
                sys.exit(0)

    # ── Step 3: Describe your idea ──────────────────────────
    print()
    print(divider)
    if template:
        stack = TEMPLATE_STACKS.get(template, "")
        print(f"  Building with: {stack}")
    print(divider)
    print()

    try:
        print("Describe your idea in a few sentences.")
        print("What does the app do? Who is it for? What are the key features?\n")
        idea = input("> ").strip()
        if not idea:
            print("No description provided. You can edit .forge/spec.md later.")
            return template, project_name, None
        print()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)

    # ── Step 4: AI generates structured spec ──────────────
    spec_md = _ai_generate_spec(project_name, idea, template)

    if spec_md:
        print(divider)
        print("  Here's what I understood:")
        print(divider)
        print()
        print(spec_md)
        print()
        print(divider)
        print()

        try:
            confirm = input("Looks good? [Y/n/edit]: ").strip().lower()
            if confirm in ("n", "no"):
                print("Cancelled.")
                sys.exit(0)
            if confirm in ("e", "edit"):
                print("\nYou can refine the spec after the project is created.")
                print("Run: nano .forge/spec.md\n")
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(0)

        return template, project_name, {"_raw_spec": spec_md}
    else:
        # AI not available — fall back to manual input
        print("  (AI spec generation not available — no API key configured)")
        print("  You can edit .forge/spec.md after creation.\n")

        try:
            confirm = input("Create project with default spec? [Y/n]: ").strip().lower()
            if confirm in ("n", "no"):
                print("Cancelled.")
                sys.exit(0)
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(0)

        return template, project_name, None


def _ai_generate_spec(project_name: str, idea: str, template: str = None) -> str:
    """Use the LLM to turn a freeform idea into a structured spec.md.

    Returns the spec markdown string, or empty string if no provider is available.
    """
    try:
        from .config import load_config, get_provider_config
        from .providers import create_provider

        config = load_config()
        if not config:
            return ""
        provider_config = get_provider_config(config)
        provider = create_provider(provider_config)
    except (ValueError, ImportError, Exception):
        return ""

    stack_hint = ""
    if template:
        stack = TEMPLATE_STACKS.get(template, "")
        if stack:
            stack_hint = f"\nPreferred stack: {stack}"

    prompt = f"""\
Turn this project idea into a structured project specification.
Output ONLY the markdown — no explanation, no fences.

Project name: {project_name}{stack_hint}

User's idea:
{idea}

Use this exact format:

# Project: {project_name}

## What
[1-2 sentence description of what the app does]

## Users
[Who will use this — one line]

## Features
- [Feature 1]
- [Feature 2]
- [Feature 3]
(list 4-8 concrete features based on the idea)

## Non-goals
- [Thing this app does NOT do]
(list 2-3 non-goals to keep scope focused)

## Stack
[Technology choices, or "Let Forge decide" if no preference]
"""

    try:
        messages = [{"role": "user", "content": prompt}]
        response = provider.chat(messages)
        # Strip markdown fences if present
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1])
            else:
                text = "\n".join(lines[1:])
        return text.strip()
    except Exception:
        return ""


def cmd_new(args):
    """Create a new project with .forge/ structure."""
    interactive = getattr(args, 'interactive', False)
    template = getattr(args, 'template', None)
    project_name = getattr(args, 'name', None)
    spec_answers = None

    if interactive:
        template, project_name, spec_answers = _interactive_new(project_name)

    if not project_name:
        print("Error: Project name is required")
        sys.exit(1)

    project_path = Path(project_name)

    if project_path.exists():
        print(f"Error: {project_name} already exists")
        sys.exit(1)

    # Create project directory
    project_path.mkdir(parents=True)
    forge_path = project_path / FORGE_DIR
    forge_path.mkdir()

    if template:
        template_path = TEMPLATES_DIR / template / ".forge"
        if template_path.exists():
            for f in template_path.iterdir():
                if f.is_file():
                    shutil.copy(f, forge_path / f.name)
        else:
            print(f"Warning: Template '{template}' not found, using default")
            _create_default_files(forge_path, project_name)
    else:
        _create_default_files(forge_path, project_name)

    # Overwrite spec.md with interactive answers if provided
    if spec_answers:
        _write_spec(forge_path, project_name, spec_answers, template)

    # Copy firewall policy
    policy_src = TEMPLATES_DIR / "common" / "firewall_policy.json"
    if policy_src.exists():
        shutil.copy(policy_src, forge_path / "firewall_policy.json")
    governance_src = TEMPLATES_DIR / "common" / "policy.yaml"
    if governance_src.exists():
        shutil.copy(governance_src, forge_path / "policy.yaml")
    else:
        write_default_policy(forge_path / "policy.yaml")

    # Copy skill files
    skills_src = TEMPLATES_DIR / "common" / "skills"
    if skills_src.exists():
        skills_dst = forge_path / "skills"
        skills_dst.mkdir(exist_ok=True)
        count = 0
        for skill_file in skills_src.glob("*.md"):
            shutil.copy(skill_file, skills_dst / skill_file.name)
            count += 1

    print(f"Created {project_name}/")
    print(f"  .forge/spec.md    ✓")
    print(f"  .forge/rules.md   ✓")
    print(f"  .forge/policy.yaml ✓")
    if (forge_path / "deploy.md").exists():
        print(f"  .forge/deploy.md  ✓")
    if skills_src.exists():
        print(f"  .forge/skills/    ✓  ({count} skill files)")
    print()
    print(f"Next steps:")
    print(f"  cd {project_name}")
    print(f"  nano .forge/spec.md     # edit your project spec")
    print(f"  forge build")


def _write_spec(forge_path: Path, project_name: str, answers: dict, template: str = None):
    """Write spec.md from interactive answers or AI-generated spec."""
    # AI-generated raw spec — write directly
    if "_raw_spec" in answers:
        (forge_path / "spec.md").write_text(answers["_raw_spec"] + "\n")
        return

    # Legacy manual answers format
    lines = [f"# Project: {project_name}", ""]

    if template:
        stack = TEMPLATE_STACKS.get(template, "")
        lines += [f"## Stack", f"{stack}", ""]

    what = answers.get("what", "").strip()
    lines += ["## What", what if what else "[Describe what you're building]", ""]

    users = answers.get("users", "").strip()
    lines += ["## Users", f"- {users}" if users else "- [Who will use this?]", ""]

    features = answers.get("features") or []
    lines.append("## Features")
    if features:
        for f in features:
            lines.append(f"- {f}")
    else:
        lines.append("- [Feature 1]")
    lines.append("")

    vibe = answers.get("vibe", "").strip()
    if vibe:
        lines += ["## Vibe", vibe, ""]

    (forge_path / "spec.md").write_text("\n".join(lines))


def _create_default_files(forge_path: Path, project_name: str):
    """Create default spec.md and rules.md."""
    (forge_path / "spec.md").write_text(f"""# Project: {project_name}

## What
[Describe what you're building in 1-2 sentences]

## Users
- [Who will use this?]

## Features
- [Feature 1]
- [Feature 2]
- [Feature 3]

## Vibe
[What should it feel like? Fast? Minimal? Fun?]
""")

    (forge_path / "rules.md").write_text("""# Build Rules

## Stack Defaults
- Backend:  FastAPI + sqlite3 (raw SQL, no ORM)
- Frontend: React + Vite + plain JavaScript (not TypeScript)
- Styling:  Tailwind CSS
- Deploy:   Railway (single service, free tier)

## Constraints
- Free tiers only — no paid services or credit card required
- Single deployable unit — no microservices
- SQLite for all persistence — no Postgres, Redis, or external DBs
- Environment variables for all secrets — never hardcode

## What NOT to use
- ORMs (SQLAlchemy, Prisma) — use sqlite3 directly
- TypeScript — use plain JavaScript/JSX
- Redux, Zustand, React Query — use useState/useEffect + fetch()
- Celery or message queues
- GraphQL — use REST
- Complex auth (OAuth2, social login) — use simple JWT if needed

## Use when appropriate
- Redis — for caching high-read data or improving page load
- Docker + docker-compose — when stack has multiple services (e.g. app + Redis)

## Code Style
- Clear over clever
- Small files, small functions
- Basic error handling at boundaries
- No premature abstraction
""")

    print(f"Created {project_name}/")


def cmd_init(args):
    """Initialize .forge/ in current directory."""
    forge_path = Path(FORGE_DIR)

    if forge_path.exists():
        print(".forge/ already exists")
        return

    forge_path.mkdir()
    project_name = Path.cwd().name
    _create_default_files(forge_path, project_name)

    # Copy skill files
    skills_src = TEMPLATES_DIR / "common" / "skills"
    if skills_src.exists():
        skills_dst = forge_path / "skills"
        skills_dst.mkdir(exist_ok=True)
        count = 0
        for skill_file in skills_src.glob("*.md"):
            shutil.copy(skill_file, skills_dst / skill_file.name)
            count += 1
        print(f"  .forge/skills/    ✓  ({count} skill files)")

    governance_src = TEMPLATES_DIR / "common" / "policy.yaml"
    if governance_src.exists():
        shutil.copy(governance_src, forge_path / "policy.yaml")
    else:
        write_default_policy(forge_path / "policy.yaml")
    print(f"  .forge/policy.yaml ✓")

    print("")
    print("Next: nano .forge/spec.md    # edit your project spec")


def cmd_fix(args):
    """Fix errors by analyzing a traceback and patching the failing files."""
    from .config import load_config, get_provider_config
    from .providers import create_provider
    from .agents.debug import DebugAgent

    project_root = Path.cwd()

    # Get the error text
    error_text = getattr(args, 'error', None) or ""
    if not error_text:
        print("Paste the error/traceback below (empty line to finish):\n")
        lines = []
        try:
            while True:
                line = input()
                if not line and lines:
                    break
                lines.append(line)
        except (KeyboardInterrupt, EOFError):
            pass
        error_text = "\n".join(lines)

    if not error_text.strip():
        print("No error provided.")
        return

    # Load provider
    try:
        config = load_config()
        provider_config = get_provider_config(config)
        provider = create_provider(provider_config)
    except (ValueError, Exception) as e:
        print(f"Error: {e}")
        print("Run 'forge setup' to configure an API key.")
        return

    print(f"\nAnalyzing error and generating a targeted fix... ({provider_config})\n")

    agent = DebugAgent(provider, project_root)
    try:
        fixes = agent.diagnose_and_fix(error_text, project_root)
    except Exception as e:
        print(f"Fix command failed: {e}")
        return

    if not fixes:
        print("No fix could be produced for that error.")
        return

    for filepath, content in fixes:
        full_path = (project_root / filepath).resolve()
        try:
            full_path.relative_to(project_root.resolve())
        except ValueError:
            print(f"  Skipping {filepath} (outside project root)")
            continue
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        print(f"  Fixed: {filepath}")

    print(f"\n{len(fixes)} file(s) updated. Restart your server to test.")


def cmd_dev(args):
    """Run local development server with auto-fix on crash."""
    from .dev_server import DevServer

    server = DevServer(Path.cwd())
    port = getattr(args, 'port', None) or 8080
    no_fix = getattr(args, 'no_fix', False)
    server.run(port=port, auto_fix=not no_fix)


def cmd_sprint(args):
    """Sprint management commands."""
    from .sprint import cmd_sprint_start, cmd_sprint_status, cmd_sprint_wrap

    if args.sprint_cmd == "start":
        cmd_sprint_start(args)
    elif args.sprint_cmd == "status":
        cmd_sprint_status(args)
    elif args.sprint_cmd == "wrap":
        cmd_sprint_wrap(args)
    else:
        print("Usage: forge sprint <start|status|wrap>")



def cmd_templates(args):
    """List available project templates."""
    print("\nAvailable templates:\n")
    for name, desc in TEMPLATES.items():
        print(f"  {name:12} - {desc}")
    print()
    print("Usage: forge new my-project --template <template-name>")
    print("   or: forge new --interactive")
    print()


def _validate_api_key_format(provider: str, key: str) -> tuple[bool, str]:
    """Check that an API key has the expected prefix and minimum length."""
    key = key.strip()
    if not key:
        return False, "API key cannot be empty"

    checks = {
        "anthropic": ("sk-ant-", 40),
        "openai":    ("sk-",    40),
        "together":  ("",       32),
    }

    if provider in checks:
        prefix, min_len = checks[provider]
        if prefix and not key.startswith(prefix):
            return False, f"Expected key starting with '{prefix}'"
        if len(key) < min_len:
            return False, f"Key looks too short (expected ≥{min_len} chars)"

    return True, ""


def _list_ollama_models(base_url: str = "http://localhost:11434") -> list[dict]:
    """Return Ollama model metadata from the local server."""
    import requests

    resp = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=5)
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("models", [])


def _select_ollama_model(default_model: str, base_url: str = "http://localhost:11434") -> tuple[str, str]:
    """Pick an installed local Ollama model, preferring the requested default."""
    models = _list_ollama_models(base_url)
    names = [m.get("model") or m.get("name") for m in models if (m.get("model") or m.get("name"))]
    if default_model in names:
        return default_model, ""

    local_names = [
        (m.get("model") or m.get("name"))
        for m in models
        if (m.get("model") or m.get("name")) and not m.get("remote_host")
    ]
    if local_names:
        chosen = local_names[0]
        note = f"Using installed Ollama model '{chosen}' instead of missing default '{default_model}'."
        return chosen, note

    return default_model, ""


def _provider_preflight(provider_config) -> tuple[bool, str]:
    """Run a lightweight readiness check for the selected provider."""
    if provider_config.name == "ollama":
        return _test_provider_connection(provider_config.name, provider_config.api_key or "", provider_config.model)
    return True, ""


def _apply_model_override(provider_config, config: dict, provider_name: str | None, model: str | None):
    """Override the selected provider model for a single command."""
    if not model:
        return provider_config, config, provider_name

    overridden = type(provider_config)(
        name=provider_config.name,
        api_key=provider_config.api_key,
        model=model,
        base_url=provider_config.base_url,
        max_tokens=provider_config.max_tokens,
        profile="",
        capabilities=provider_config.capabilities,
        priority=provider_config.priority,
        metadata=dict(provider_config.metadata),
    )

    effective_provider = provider_name or provider_config.name
    effective_scope = f"{provider_config.name}:{model}"
    return overridden, config, effective_scope


def _test_provider_connection(provider: str, api_key: str, model: str) -> tuple[bool, str]:
    """Make a minimal API call to verify the key works."""
    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            client.messages.create(
                model=model,
                max_tokens=10,
                messages=[{"role": "user", "content": "hi"}],
            )
        elif provider in ("openai", "together"):
            import openai
            base_url = "https://api.together.xyz/v1" if provider == "together" else None
            client = openai.OpenAI(api_key=api_key, base_url=base_url)
            client.chat.completions.create(
                model=model,
                max_tokens=10,
                messages=[{"role": "user", "content": "hi"}],
            )
        elif provider == "ollama":
            import requests
            available = _list_ollama_models("http://localhost:11434")
            available_names = [
                item.get("model") or item.get("name")
                for item in available
                if (item.get("model") or item.get("name"))
            ]
            if available_names and model not in available_names:
                return False, (
                    f"Model '{model}' is not installed in Ollama. "
                    f"Available models: {', '.join(available_names)}"
                )
            last_error = ""
            for timeout_seconds in (30, 60):
                try:
                    resp = requests.post(
                        "http://localhost:11434/api/chat",
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": "hi"}],
                            "stream": False,
                            "options": {"num_predict": 1},
                        },
                        timeout=timeout_seconds,
                    )
                    if resp.status_code == 404:
                        resp = requests.post(
                            "http://localhost:11434/api/generate",
                            json={
                                "model": model,
                                "prompt": "hi",
                                "stream": False,
                                "options": {"num_predict": 1},
                            },
                            timeout=timeout_seconds,
                        )
                    resp.raise_for_status()
                    break
                except Exception as exc:
                    last_error = str(exc)
            else:
                return False, last_error
        else:
            return True, "Unknown provider — skipping connection test"
        return True, ""
    except Exception as e:
        return False, str(e)


def cmd_setup(args):
    """Interactive setup wizard: pick provider, enter API key, validate, save."""
    from .config import CONFIG_DIR, CONFIG_FILE, load_config, save_config

    divider = "─" * 50

    print()
    print(divider)
    print("  Forge Setup Wizard")
    print(divider)
    print()

    providers = [
        ("anthropic", "Anthropic Claude", "claude-sonnet-4-20250514", "https://console.anthropic.com/settings/keys"),
        ("openai",    "OpenAI GPT",       "gpt-4o",                  "https://platform.openai.com/api-keys"),
        ("together",  "Together AI",      "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", "https://api.together.ai/settings/api-keys"),
        ("ollama",    "Ollama (local)",   "llama3.1",                 ""),
    ]

    print("Choose your AI provider:\n")
    for i, (_, label, model, _url) in enumerate(providers, 1):
        print(f"  {i}. {label}  ({model})")
    print()

    try:
        while True:
            choice = input(f"Provider (1-{len(providers)}): ").strip()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(providers):
                    break
                print(f"  Enter a number between 1 and {len(providers)}")
            except ValueError:
                print("  Enter a number")
    except KeyboardInterrupt:
        print("\nCancelled.")
        return

    provider_id, provider_label, default_model, key_url = providers[idx]
    selected_model = default_model

    # Ollama needs no API key
    api_key = ""
    if provider_id != "ollama":
        print()
        if key_url:
            print(f"  Get your API key at: {key_url}")
        try:
            while True:
                api_key = input(f"  {provider_label} API key: ").strip()
                ok, msg = _validate_api_key_format(provider_id, api_key)
                if ok:
                    break
                print(f"  Invalid format: {msg}")
        except KeyboardInterrupt:
            print("\nCancelled.")
            return
    else:
        try:
            selected_model, model_note = _select_ollama_model(default_model)
            if model_note:
                print(f"  {model_note}")
        except Exception:
            selected_model = default_model

    # Test connection
    print()
    print("  Testing connection...", end="", flush=True)
    ok, err = _test_provider_connection(provider_id, api_key, selected_model)
    if ok:
        print(" OK")
    else:
        print(f" FAILED\n  Error: {err}")
        try:
            cont = input("  Save anyway? [y/N]: ").strip().lower()
            if cont != "y":
                print("  Setup cancelled.")
                return
        except KeyboardInterrupt:
            print("\nCancelled.")
            return

    # Build and save config
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_config() if CONFIG_FILE.exists() else {}

    new_entry: dict = {"name": provider_id, "model": selected_model}
    if provider_id == "ollama":
        new_entry["base_url"] = "http://localhost:11434"
    else:
        new_entry["api_key"] = api_key

    config_to_save = _merge_setup_provider(existing, new_entry)
    save_config(config_to_save)

    print()
    print(f"  Config saved to {CONFIG_FILE}")
    print(divider)
    print()


def cmd_build(args):
    """Build the project using AI agents."""
    forge_path = Path(FORGE_DIR)

    if not forge_path.exists():
        print("No .forge/ directory found.")
        print("Run 'forge new <name>' or 'forge init' first.")
        sys.exit(1)

    from .config import ensure_config, get_provider_config
    from .orchestrator import BuildOrchestrator
    from .ui import BuildUI

    config = ensure_config()

    try:
        provider_config = get_provider_config(config, getattr(args, 'provider', None))
    except ValueError:
        print("No API key configured. Running setup wizard...\n")
        cmd_setup(args)
        # Re-load config after setup
        config = ensure_config()
        try:
            provider_config = get_provider_config(config, getattr(args, 'provider', None))
        except ValueError as e2:
            print(f"Error: {e2}")
            sys.exit(1)

    provider_config, config, provider_scope = _apply_model_override(
        provider_config,
        config,
        getattr(args, 'provider', None),
        getattr(args, 'model', None),
    )

    feature = getattr(args, 'feature', None)
    no_review = getattr(args, 'no_review', False)
    verbose = getattr(args, 'verbose', False)
    approval_mode = getattr(args, 'approval_mode', None)

    ok, err = _provider_preflight(provider_config)
    if not ok:
        print(f"Provider preflight failed for {provider_config}:")
        print(f"  {err}")
        if provider_config.name == "ollama":
            print("  Run 'forge doctor -p ollama' for local model diagnostics.")
        sys.exit(1)

    ui = BuildUI(verbose=verbose)

    print(f"Building with {provider_config}...")
    print("")

    orchestrator = BuildOrchestrator(
        provider_config=provider_config,
        forge_path=forge_path,
        review=not no_review,
        verbose=verbose,
        approval_mode=approval_mode,
        provider_scope=provider_scope,
        config_dict=config,
        ui=ui,
    )

    try:
        orchestrator.run(feature=feature)
    except KeyboardInterrupt:
        print("")
        print("Build paused. Run 'forge build' to resume.")
    except Exception as e:
        print(f"Build failed: {e}")
        sys.exit(1)


def cmd_spec(args):
    """Validate or compile Forge Spec API directives."""
    from .specapi import compile_task_graph, parse_spec_file

    forge_path = Path(FORGE_DIR)
    spec_path = Path(getattr(args, "path", "") or forge_path / "spec.md")
    if not spec_path.exists():
        print(f"Spec file not found: {spec_path}")
        sys.exit(1)

    doc = parse_spec_file(spec_path)
    spec_cmd = getattr(args, "spec_cmd", "validate")

    if spec_cmd == "validate":
        for diagnostic in doc.diagnostics:
            print(f"{diagnostic.severity.upper()} line {diagnostic.line}: {diagnostic.message}")
        if doc.valid:
            print(f"Spec API valid: {len(doc.primitives)} primitive(s)")
            return
        sys.exit(1)

    if spec_cmd == "compile":
        graph = compile_task_graph(doc)
        output = {
            "spec": doc.to_dict(),
            "task_graph": graph.to_dict(),
        }
        rendered = json.dumps(output, indent=2, sort_keys=True)
        output_path = getattr(args, "output", None)
        if output_path:
            Path(output_path).write_text(rendered + "\n")
            print(f"Wrote compiled spec to {output_path}")
        else:
            print(rendered)
        if not doc.valid:
            sys.exit(1)


def cmd_serve(args):
    """Run the local Forge REST control plane."""
    from .control_plane import run_control_plane

    run_control_plane(
        host=getattr(args, "host", "127.0.0.1"),
        port=getattr(args, "port", 4123),
        project_root=Path.cwd(),
        ui=bool(getattr(args, "ui", False)),
    )


def cmd_worker(args):
    """Run queued REST control-plane jobs."""
    from .control_plane import run_worker

    run_worker(
        project_root=Path.cwd(),
        once=bool(getattr(args, "once", False)),
        poll_interval=float(getattr(args, "poll_interval", 1.0)),
    )


def cmd_doctor(args):
    """Check project and provider readiness before running a build."""
    from .config import CONFIG_FILE, load_config, get_provider_config

    provider_name = getattr(args, "provider", None)
    forge_path = Path(FORGE_DIR)

    print("Forge doctor")
    print("")

    if forge_path.exists():
        print(f"[ok] project: {forge_path.resolve()}")
    else:
        print("[warn] project: no .forge/ directory in the current working directory")

    if CONFIG_FILE.exists():
        print(f"[ok] config: {CONFIG_FILE}")
    else:
        print(f"[warn] config: missing {CONFIG_FILE}")
        return

    config = load_config()
    try:
        provider_config = get_provider_config(config, provider_name)
    except Exception as exc:
        print(f"[fail] provider resolution: {exc}")
        return

    provider_config, config, _provider_scope = _apply_model_override(
        provider_config,
        config,
        provider_name,
        getattr(args, "model", None),
    )

    print(f"[ok] provider: {provider_config}")
    if is_supported_provider(provider_config.name):
        print("[ok] support tier: provider is in the supported matrix")
    else:
        print("[warn] support tier: provider is outside the supported matrix")

    if provider_config.name == "ollama":
        try:
            models = _list_ollama_models(provider_config.base_url or "http://localhost:11434")
            installed = [
                (m.get("model") or m.get("name"))
                for m in models
                if (m.get("model") or m.get("name"))
            ]
            print(f"[ok] ollama tags: {len(installed)} model(s) visible")
            if installed:
                print(f"      installed: {', '.join(installed)}")
            if is_recommended_ollama_model(provider_config.model):
                print("[ok] ollama model: selected model is in the recommended local set")
            else:
                print("[warn] ollama model: selected model is not in the recommended local set")
        except Exception as exc:
            print(f"[fail] ollama tags: {exc}")
            return

    ok, err = _provider_preflight(provider_config)
    if ok:
        print("[ok] provider preflight: generation path is reachable")
    else:
        print(f"[fail] provider preflight: {err}")

    if forge_path.exists():
        tracker = QualityTracker(forge_path)
        summaries = tracker.model_summary(provider_config.name, provider_config.model)
        if summaries:
            print("[ok] model quality: historical build data found")
            for item in summaries[:3]:
                attempts = item.get("attempts", 0)
                successes = item.get("successes", 0)
                eval_count = max(1, item.get("eval_count", 0))
                eval_avg = int(item.get("eval_score_total", 0)) / eval_count
                print(
                    f"      {item.get('role')}: {successes}/{attempts} success, "
                    f"avg eval {eval_avg:.1f}"
                )
        else:
            print("[warn] model quality: no historical data yet for selected model")


def cmd_contracts(args):
    """Export persisted contracts in various formats."""
    forge_path = Path(FORGE_DIR)
    contracts_path = forge_path / "contracts.json"
    if not contracts_path.exists():
        print("No persisted contracts found. Run 'forge build' first.")
        sys.exit(1)

    from .collaboration import ContractRegistry

    registry = ContractRegistry.load(contracts_path)
    contracts_cmd = getattr(args, "contracts_cmd", "export")
    if contracts_cmd != "export":
        print("Usage: forge contracts export")
        sys.exit(1)

    output_format = getattr(args, "format", "openapi")
    output = Path(getattr(args, "output", ""))

    if output_format == "openapi":
        target = output or (forge_path / "openapi.json")
        registry.export_openapi(target)
        print(f"Exported OpenAPI spec to {target}")
        return

    if output_format == "json":
        target = output or (forge_path / "contracts-export.json")
        target.write_text(registry.format_as_json() + "\n")
        print(f"Exported contracts to {target}")
        return

    print(f"Unsupported format: {output_format}")
    sys.exit(1)


def cmd_eval(args):
    """Evaluate a captured agent response."""
    if getattr(args, "kind", "") == "smoke":
        from .evals import run_smoke_eval

        name = getattr(args, "scenario", "")
        if not name:
            print("Error: forge eval smoke requires --scenario")
            sys.exit(1)
        result = run_smoke_eval(name, output_dir=Path(getattr(args, "output_dir", "") or ".forge/evals"))
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.kind} score={result.score} {result.summary}")
        if not result.passed:
            sys.exit(1)
        return

    input_path = Path(getattr(args, "input", ""))
    if not str(input_path):
        print("Error: --input is required for planner, reviewer, and backend evals")
        sys.exit(1)
    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        sys.exit(1)
    if input_path.is_dir():
        failures = 0
        for file_path in sorted(p for p in input_path.iterdir() if p.is_file()):
            stem = file_path.stem.split("-", 1)[0].lower()
            result = run_eval(stem, file_path.read_text())
            status = "PASS" if result.passed else "FAIL"
            print(f"{status} {file_path.name} score={result.score} {result.summary}")
            if not result.passed:
                failures += 1
        if failures:
            sys.exit(1)
        return

    result = run_eval(getattr(args, "kind"), input_path.read_text())
    status = "PASS" if result.passed else "FAIL"
    print(f"{status} {result.kind} score={result.score} {result.summary}")
    if not result.passed:
        sys.exit(1)



def cmd_config(args):
    """Manage Forge configuration."""
    from .config import CONFIG_FILE, ensure_config, detect_ollama_models, pick_local_model

    config_cmd = getattr(args, 'config_cmd', 'show')

    if config_cmd == "show":
        if CONFIG_FILE.exists():
            print(CONFIG_FILE.read_text())
        else:
            print(f"No config found at {CONFIG_FILE}")
            print("Run 'forge config init' to create one.")
    elif config_cmd == "init":
        # Show the user what we detected before creating the config
        if not CONFIG_FILE.exists():
            installed = detect_ollama_models()
            if installed:
                picked = pick_local_model(installed)
                print(f"Detected Ollama with {len(installed)} model(s) installed.")
                print(f"  Picked: {picked}")
                print(f"  Available: {', '.join(installed[:6])}{' ...' if len(installed) > 6 else ''}")
                print("Writing a local-first config (cloud providers remain as fallbacks).")
                print("")
            else:
                print("No local Ollama detected — writing a cloud-first config.")
                print("Start Ollama and re-run 'forge config init' to switch to local-first.")
                print("")
        ensure_config()
        print(f"Config at: {CONFIG_FILE}")
    elif config_cmd == "path":
        print(CONFIG_FILE)


def cmd_status(args):
    """Show current build status."""
    forge_path = Path(FORGE_DIR)
    if not forge_path.exists():
        print("No .forge/ directory found.")
        return

    from .state import load_build_state

    state = load_build_state(forge_path)

    if state.status == "not_started":
        print("No build started yet. Run 'forge build'.")
        return

    print(f"Build: {state.build_id}")
    print(f"Status: {state.status}")
    print(f"Provider: {state.provider} ({state.model})")
    print(f"Started: {state.started_at}")
    if state.completed_at:
        print(f"Completed: {state.completed_at}")
    print("")

    if state.tasks:
        completed = sum(1 for t in state.tasks if t.status == "completed")
        total = len(state.tasks)
        print(f"Tasks: {completed}/{total}")
        for t in state.tasks:
            icons = {"completed": "+", "failed": "X", "in_progress": ">", "pending": " "}
            print(f"  [{icons.get(t.status, '?')}] {t.name}")
            if t.error:
                print(f"      Error: {t.error}")
        print("")

    if state.files_written:
        print(f"Files written: {len(state.files_written)}")
        for f in state.files_written:
            print(f"  {f}")


def cmd_publish(args):
    """Publish project to GitHub."""
    if not shutil.which("gh"):
        print("Requires GitHub CLI: https://cli.github.com")
        sys.exit(1)

    project_name = Path.cwd().name

    # Initialize git if needed
    if not Path(".git").exists():
        subprocess.run(["git", "init"], check=True)
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], check=True)

    print(f"Creating GitHub repo: {project_name}")
    result = subprocess.run(
        ["gh", "repo", "create", project_name, "--public", "--source=.", "--push"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print("Published!")
        for line in result.stdout.splitlines():
            if "github.com" in line:
                print(f"  {line.strip()}")
                break
    else:
        # Try pushing to existing repo
        subprocess.run(["git", "push", "-u", "origin", "main"], check=True)
        print("Pushed to existing repo")


def main():
    parser = argparse.ArgumentParser(
        prog="forge",
        description="Project scaffolding for LLM-assisted development"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # forge new
    new_parser = subparsers.add_parser("new", help="Create new project")
    new_parser.add_argument("name", nargs="?", help="Project name")
    new_parser.add_argument("--template", "-t", help="Template name (use 'forge templates' to list)")
    new_parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode with template picker")
    new_parser.set_defaults(func=cmd_new)

    # forge templates
    templates_parser = subparsers.add_parser("templates", help="List available templates")
    templates_parser.set_defaults(func=cmd_templates)

    # forge init
    init_parser = subparsers.add_parser("init", help="Initialize .forge/ in current directory")
    init_parser.set_defaults(func=cmd_init)

    # forge dev
    dev_parser = subparsers.add_parser("dev", help="Run local dev server (auto-fixes crashes)")
    dev_parser.add_argument("--port", type=int, default=8080, help="Port number")
    dev_parser.add_argument("--no-fix", action="store_true", help="Disable auto-fix on crash")
    dev_parser.set_defaults(func=cmd_dev)

    # forge fix
    fix_parser = subparsers.add_parser("fix", help="Fix errors by analyzing a traceback and patching the failing files")
    fix_parser.add_argument("error", nargs="?", help="Error message (or omit to paste interactively)")
    fix_parser.set_defaults(func=cmd_fix)

    # forge sprint
    sprint_parser = subparsers.add_parser("sprint", help="Sprint timer")
    sprint_parser.add_argument("sprint_cmd", choices=["start", "status", "wrap"], help="Sprint command")
    sprint_parser.set_defaults(func=cmd_sprint)

    # forge publish
    publish_parser = subparsers.add_parser("publish", help="Publish to GitHub")
    publish_parser.set_defaults(func=cmd_publish)

    # forge build
    build_parser = subparsers.add_parser("build", help="Build project using AI agents")
    build_parser.add_argument("--provider", "-p", help="AI provider (anthropic, openai, together, ollama)")
    build_parser.add_argument("--model", "-m", help="Override the provider model for this run")
    build_parser.add_argument("--feature", "-f", help="Add a specific feature (incremental build)")
    build_parser.add_argument("--no-review", action="store_true", help="Skip review phase")
    build_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    build_parser.add_argument("--approval-mode", choices=["off", "interactive"],
                              help="Override .forge/policy.yaml approval mode for this build")
    build_parser.set_defaults(func=cmd_build)

    # forge spec
    spec_parser = subparsers.add_parser("spec", help="Validate or compile Forge Spec API directives")
    spec_subparsers = spec_parser.add_subparsers(dest="spec_cmd", required=True)
    spec_validate_parser = spec_subparsers.add_parser("validate", help="Validate .forge/spec.md")
    spec_validate_parser.add_argument("--path", default=str(Path(FORGE_DIR) / "spec.md"), help="Spec file path")
    spec_validate_parser.set_defaults(func=cmd_spec)
    spec_compile_parser = spec_subparsers.add_parser("compile", help="Compile .forge/spec.md to a task graph")
    spec_compile_parser.add_argument("--path", default=str(Path(FORGE_DIR) / "spec.md"), help="Spec file path")
    spec_compile_parser.add_argument("--output", "-o", help="Write compiled JSON to a file")
    spec_compile_parser.set_defaults(func=cmd_spec)

    # forge serve
    serve_parser = subparsers.add_parser("serve", help="Run local Forge REST control plane")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    serve_parser.add_argument("--port", type=int, default=4123, help="Bind port")
    serve_parser.add_argument("--ui", action="store_true", help="Serve the local dashboard at /dashboard")
    serve_parser.set_defaults(func=cmd_serve)

    # forge worker
    worker_parser = subparsers.add_parser("worker", help="Run queued REST control-plane jobs")
    worker_parser.add_argument("--once", action="store_true", help="Process at most one queued job")
    worker_parser.add_argument("--poll-interval", type=float, default=1.0, help="Seconds between queue polls")
    worker_parser.set_defaults(func=cmd_worker)

    # forge doctor
    doctor_parser = subparsers.add_parser("doctor", help="Check project and provider readiness")
    doctor_parser.add_argument("--provider", "-p", help="Provider to check (anthropic, openai, together, ollama)")
    doctor_parser.add_argument("--model", "-m", help="Override the provider model for this check")
    doctor_parser.set_defaults(func=cmd_doctor)

    # forge setup
    setup_parser = subparsers.add_parser("setup", help="Interactive setup wizard (API key + provider)")
    setup_parser.set_defaults(func=cmd_setup)

    # forge config
    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_parser.add_argument("config_cmd", nargs="?", default="show",
                               choices=["show", "init", "path"],
                               help="Config subcommand")
    config_parser.set_defaults(func=cmd_config)

    # forge status
    status_parser = subparsers.add_parser("status", help="Show build status")
    status_parser.set_defaults(func=cmd_status)

    # forge contracts
    contracts_parser = subparsers.add_parser("contracts", help="Export persisted contracts")
    contracts_subparsers = contracts_parser.add_subparsers(dest="contracts_cmd", required=True)
    contracts_export_parser = contracts_subparsers.add_parser("export", help="Export contracts to OpenAPI or JSON")
    contracts_export_parser.add_argument("--format", choices=["openapi", "json"], default="openapi",
                                         help="Export format")
    contracts_export_parser.add_argument("--output", "-o", help="Output path")
    contracts_export_parser.set_defaults(func=cmd_contracts)

    # forge eval
    eval_parser = subparsers.add_parser("eval", help="Evaluate a captured planner/reviewer/backend response")
    eval_parser.add_argument("kind", choices=["planner", "reviewer", "backend", "smoke"], help="Response kind to evaluate")
    eval_parser.add_argument("--input", "-i", help="Path to the response text file")
    eval_parser.add_argument("--scenario", choices=["crm-basic", "api-only-crud", "frontend-contracts"],
                             help="Smoke scenario for `forge eval smoke`")
    eval_parser.add_argument("--output-dir", default=".forge/evals", help="Directory for smoke eval artifacts")
    eval_parser.set_defaults(func=cmd_eval)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
