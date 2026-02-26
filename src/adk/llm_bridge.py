"""Google ADK LLM bridge -- wraps Forge's BaseProvider as an ADK BaseLlm.

This lets ADK agents (LlmAgent) use any Forge-supported LLM backend
(Anthropic, OpenAI-compat, Ollama) without needing Gemini or Vertex AI.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, AsyncGenerator, Iterable

if TYPE_CHECKING:
    from ..providers.base import BaseProvider


def create_forge_llm(provider: "BaseProvider"):
    """Create a Google ADK BaseLlm that wraps a Forge provider.

    Returns a BaseLlm subclass instance configured for the given provider.
    Requires google-adk to be installed.
    """
    try:
        from google.adk.models.base_llm import BaseLlm
        from google.adk.models.llm_request import LlmRequest
        from google.adk.models.llm_response import LlmResponse
    except ImportError:
        raise ImportError(
            "google-adk is required for ADK integration. "
            "Install with: pip install 'forge-ai[adk]'"
        )

    try:
        from google.genai import types as genai_types
    except ImportError:
        raise ImportError(
            "google-genai is required for ADK integration. "
            "Install with: pip install 'forge-ai[adk]'"
        )

    class ForgeLlmBridge(BaseLlm):
        """ADK BaseLlm implementation backed by a Forge provider."""

        model: str = provider.config.model or "forge-provider"

        @classmethod
        def supported_models(cls) -> Iterable[re.Pattern]:
            # Match any model name -- Forge handles routing
            return [re.compile(r"forge-.*"), re.compile(r".*")]

        async def generate_content_async(
            self,
            llm_request: LlmRequest,
            stream: bool = False,
        ) -> AsyncGenerator[LlmResponse, None]:
            """Translate ADK LlmRequest → Forge messages → LlmResponse."""
            messages = _contents_to_messages(llm_request.contents)

            system = ""
            if llm_request.system_instruction:
                system = _content_to_text(llm_request.system_instruction)

            # Call Forge provider (synchronous) -- run in executor for async
            import asyncio
            loop = asyncio.get_event_loop()
            response_text = await loop.run_in_executor(
                None,
                lambda: provider.chat_with_retry(messages, system=system),
            )

            content = genai_types.Content(
                role="model",
                parts=[genai_types.Part(text=response_text)],
            )
            yield LlmResponse(content=content)

    return ForgeLlmBridge(model=provider.config.model or "forge-provider")


def _contents_to_messages(contents) -> list[dict]:
    """Convert ADK Content list to Forge messages format."""
    messages = []
    for content in contents:
        role = getattr(content, "role", "user")
        # Map ADK roles to OpenAI-style roles
        if role == "model":
            role = "assistant"
        text = _content_to_text(content)
        if text:
            messages.append({"role": role, "content": text})
    return messages


def _content_to_text(content) -> str:
    """Extract text from an ADK Content object."""
    if content is None:
        return ""
    parts = getattr(content, "parts", [])
    texts = []
    for part in parts:
        t = getattr(part, "text", None)
        if t:
            texts.append(t)
    return "\n".join(texts)
