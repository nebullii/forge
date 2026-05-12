"""Ollama local model provider."""

import json
import re
from typing import Generator

from .base import BaseProvider, ProviderConfig, DEFAULT_CONTEXT_WINDOW


# Fallback windows by model family when /api/show parsing fails.
_FAMILY_WINDOWS = {
    "llama3.1": 131072,
    "llama3.2": 131072,
    "llama3.3": 131072,
    "llama3": 8192,
    "qwen2.5": 32768,
    "qwen3": 32768,
    "qwen2.5-coder": 32768,
    "deepseek-coder": 16384,
    "deepseek-r1": 65536,
    "mistral": 32768,
    "mixtral": 32768,
    "gemma2": 8192,
    "phi3": 4096,
}


class OllamaProvider(BaseProvider):

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = (config.base_url or "http://localhost:11434").rstrip("/")

    def _detect_context_window(self) -> int:
        """Probe /api/show for the model's context length, fall back to family map."""
        import requests

        try:
            response = requests.post(
                f"{self.base_url}/api/show",
                json={"name": self.config.model},
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            return self._fallback_window()

        # /api/show exposes parameters as a free-form text block; grep for num_ctx.
        params = data.get("parameters", "") or ""
        match = re.search(r"num_ctx\s+(\d+)", params)
        if match:
            return int(match.group(1))

        # Newer Ollama versions expose model_info with explicit context length.
        info = data.get("model_info", {}) or {}
        for key, value in info.items():
            if "context_length" in key and isinstance(value, (int, float)):
                return int(value)

        return self._fallback_window()

    def _fallback_window(self) -> int:
        model = (self.config.model or "").lower()
        # Try exact family prefix match, longest first
        for family in sorted(_FAMILY_WINDOWS, key=len, reverse=True):
            if model.startswith(family):
                return _FAMILY_WINDOWS[family]
        return DEFAULT_CONTEXT_WINDOW

    def chat(self, messages: list[dict], system: str = "", **options) -> str:
        import requests
        msgs = self._build_messages(messages, system)
        payload = self._build_payload(msgs, stream=False, options=options)

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=300,
            )
            response.raise_for_status()
            data = response.json()
            self._set_last_usage(self._extract_usage(data, endpoint="chat"))
            if "message" in data and "content" in data.get("message", {}):
                return data["message"]["content"]
            if "response" in data:
                return data["response"]
            raise RuntimeError(f"Ollama returned unexpected response: {str(data)[:200]}")
        except requests.HTTPError as exc:
            if getattr(exc.response, "status_code", None) != 404:
                raise
            model_error = self._model_not_found_error(exc.response)
            if model_error:
                raise RuntimeError(model_error) from exc
            return self._chat_via_generate(msgs, options=options)

    def stream(self, messages: list[dict], system: str = "", **options) -> Generator[str, None, None]:
        import requests
        msgs = self._build_messages(messages, system)
        payload = self._build_payload(msgs, stream=True, options=options)

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=300,
            )
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if data.get("done"):
                    self._set_last_usage(self._extract_usage(data, endpoint="chat"))
                if "message" in data:
                    yield data["message"].get("content", "")
                elif "response" in data:
                    yield data["response"]
        except requests.HTTPError as exc:
            if getattr(exc.response, "status_code", None) != 404:
                raise
            model_error = self._model_not_found_error(exc.response)
            if model_error:
                raise RuntimeError(model_error) from exc
            yield from self._stream_via_generate(msgs, options=options)

    def _build_payload(self, msgs: list[dict], *, stream: bool, options: dict) -> dict:
        """Compose the Ollama request body with json mode, keep_alive, num_ctx."""
        payload: dict = {
            "model": self.config.model,
            "messages": msgs,
            "stream": stream,
        }
        if options.get("json_mode"):
            payload["format"] = "json"
        keep_alive = options.get("keep_alive") or self.config.keep_alive
        if keep_alive:
            payload["keep_alive"] = keep_alive

        # num_ctx tells Ollama how much context window to allocate — pinning it
        # to the model's actual window avoids the default 2048-token cap that
        # silently truncates long Forge prompts.
        runtime_opts: dict = dict(options.get("ollama_options") or {})
        if "num_ctx" not in runtime_opts:
            runtime_opts["num_ctx"] = self.get_context_window()
        if runtime_opts:
            payload["options"] = runtime_opts
        return payload

    def _build_messages(self, messages: list[dict], system: str = "") -> list[dict]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        return msgs

    def _chat_via_generate(self, messages: list[dict], options: dict | None = None) -> str:
        import requests

        payload = self._build_generate_payload(messages, stream=False, options=options or {})
        response = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=300,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            model_error = self._model_not_found_error(response)
            if model_error:
                raise RuntimeError(model_error) from exc
            raise
        data = response.json()
        self._set_last_usage(self._extract_usage(data, endpoint="generate"))
        if "response" not in data:
            raise RuntimeError(f"Ollama returned unexpected response: {str(data)[:200]}")
        return data["response"]

    def _stream_via_generate(self, messages: list[dict], options: dict | None = None) -> Generator[str, None, None]:
        import requests

        payload = self._build_generate_payload(messages, stream=True, options=options or {})
        response = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            stream=True,
            timeout=300,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            model_error = self._model_not_found_error(response)
            if model_error:
                raise RuntimeError(model_error) from exc
            raise
        for line in response.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            if data.get("done"):
                self._set_last_usage(self._extract_usage(data, endpoint="generate"))
            if "response" in data:
                yield data["response"]

    def _build_generate_payload(self, messages: list[dict], *, stream: bool, options: dict) -> dict:
        payload: dict = {
            "model": self.config.model,
            "prompt": self._messages_to_prompt(messages),
            "stream": stream,
        }
        if options.get("json_mode"):
            payload["format"] = "json"
        keep_alive = options.get("keep_alive") or self.config.keep_alive
        if keep_alive:
            payload["keep_alive"] = keep_alive
        runtime_opts: dict = dict(options.get("ollama_options") or {})
        if "num_ctx" not in runtime_opts:
            runtime_opts["num_ctx"] = self.get_context_window()
        if runtime_opts:
            payload["options"] = runtime_opts
        return payload

    def _messages_to_prompt(self, messages: list[dict]) -> str:
        prompt_parts: list[str] = []
        for msg in messages:
            role = (msg.get("role") or "user").upper()
            content = msg.get("content", "")
            prompt_parts.append(f"{role}:\n{content}")
        prompt_parts.append("ASSISTANT:")
        return "\n\n".join(prompt_parts)

    def _model_not_found_error(self, response) -> str:
        try:
            payload = response.json()
        except Exception:
            return ""

        message = str(payload.get("error", ""))
        if "not found" not in message.lower() or "model" not in message.lower():
            return ""

        available = self._available_models()
        if available:
            return (
                f"Ollama model '{self.config.model}' is not installed. "
                f"Available models: {', '.join(available)}"
            )
        return f"Ollama model '{self.config.model}' is not installed."

    def _available_models(self) -> list[str]:
        import requests

        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        models = []
        for item in payload.get("models", []):
            name = item.get("model") or item.get("name")
            if name:
                models.append(name)
        return models

    def _extract_usage(self, payload: dict, endpoint: str) -> dict:
        usage = {
            "provider": "ollama",
            "model": self.config.model,
            "endpoint": endpoint,
        }
        scalar_fields = (
            "total_duration",
            "load_duration",
            "prompt_eval_count",
            "prompt_eval_duration",
            "eval_count",
            "eval_duration",
            "context_length",
        )
        for field in scalar_fields:
            value = payload.get(field)
            if value is not None:
                usage[field] = value

        runtime = self._runtime_usage()
        if runtime:
            usage.update(runtime)
        return usage

    def _runtime_usage(self) -> dict:
        import requests

        try:
            response = requests.get(f"{self.base_url}/api/ps", timeout=2)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return {}

        model_entry = None
        for item in payload.get("models", []):
            name = item.get("model") or item.get("name")
            if name == self.config.model:
                model_entry = item
                break
        if model_entry is None:
            return {}

        details = model_entry.get("details", {}) or {}
        usage = {
            "size_bytes": model_entry.get("size"),
            "size_vram_bytes": model_entry.get("size_vram"),
            "processor": model_entry.get("processor"),
            "expires_at": model_entry.get("expires_at"),
            "family": details.get("family"),
            "parameter_size": details.get("parameter_size"),
            "quantization_level": details.get("quantization_level"),
        }
        return {k: v for k, v in usage.items() if v not in (None, "", [])}
