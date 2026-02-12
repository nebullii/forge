"""Provider factory -- lazy imports for optional dependencies."""

from .base import BaseProvider, ProviderConfig


def create_provider(config: ProviderConfig) -> BaseProvider:
    """Create the appropriate provider from config."""
    name = config.name.lower()

    if name == "anthropic":
        from .anthropic import AnthropicProvider
        return AnthropicProvider(config)
    elif name in ("openai", "together", "groq"):
        from .openai_compat import OpenAIProvider
        return OpenAIProvider(config)
    elif name == "ollama":
        from .ollama import OllamaProvider
        return OllamaProvider(config)
    else:
        from .openai_compat import OpenAIProvider
        return OpenAIProvider(config)


__all__ = ["BaseProvider", "ProviderConfig", "create_provider"]
