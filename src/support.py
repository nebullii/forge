"""Declared support matrix for Forge."""

SUPPORTED_TEMPLATES = {
    "web-app",
    "api-only",
    "ai-app",
}

SUPPORTED_PROVIDERS = {
    "anthropic",
    "openai",
    "ollama",
}

SUPPORTED_FRAMEWORKS = {
    "fastapi",
    "react",
    "vite",
}

RECOMMENDED_OLLAMA_MODELS = {
    "gpt-oss:20b",
    "gemma3:12b",
    "qwen3:latest",
    "llama3.2:3b",
    "llama3.1:8b",
}


def is_supported_provider(name: str) -> bool:
    return (name or "").strip().lower() in SUPPORTED_PROVIDERS


def is_recommended_ollama_model(name: str) -> bool:
    return (name or "").strip().lower() in {item.lower() for item in RECOMMENDED_OLLAMA_MODELS}
