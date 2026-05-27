"""Capability-based model routing and local Ollama discovery."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .providers.base import ProviderConfig


ROLE_CAPABILITIES = {
    "planner": ("reasoning", "large_context"),
    "builder": ("code", "reasoning"),
    "reviewer": ("reasoning", "review", "large_context"),
    "security": ("reasoning", "review", "security"),
    "verifier": (),
    "backend": ("code", "reasoning"),
    "frontend": ("code", "reasoning"),
    "tester": ("code", "review"),
    "test": ("code", "review"),
    "coder": ("cheap", "code"),
    "ci": ("cheap", "code"),
    "deploy": ("cheap", "code"),
    "debug": ("reasoning", "code"),
    "orchestrator": ("reasoning", "large_context"),
}


@dataclass(frozen=True)
class RouteDecision:
    """A routed provider plus the reason it was selected."""

    provider_config: ProviderConfig
    reason: str
    rank: int = 0


@dataclass
class ModelRouter:
    """Routes tasks to provider/model profiles based on role and policy."""

    config: dict
    default_provider: ProviderConfig
    provider_scope: Optional[str] = None
    route_overrides: dict[str, object] = field(default_factory=dict)
    _candidates: list[ProviderConfig] = field(default_factory=list)
    _outcomes: dict[tuple[str, str, str, str], list[bool]] = field(default_factory=dict)
    quality_snapshot: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.route_overrides:
            self.route_overrides = self.config.get("model_routing", {})
        if not self._candidates:
            self._candidates = self._load_candidates()

    def route_chain(self, role: str, attempt: int = 1) -> list[RouteDecision]:
        """Return ordered provider candidates for the given role."""
        role = role or "coder"
        capabilities = ROLE_CAPABILITIES.get(role, ("code",))
        explicit = self._explicit_chain(role)
        ranked: list[RouteDecision] = list(explicit)
        seen: set[tuple[str, str, str]] = set()
        for item in explicit:
            cfg = item.provider_config
            seen.add((cfg.name, cfg.profile, cfg.model))
        for candidate in self._candidates:
            score = self._candidate_score(candidate, capabilities)
            history = self._outcomes.get((role, candidate.name, candidate.profile, candidate.model), [])
            if history:
                failures = len([item for item in history if not item])
                successes = len(history) - failures
                score += successes * 2
                score -= failures * 15
            quality = self.quality_snapshot.get(self._quality_key(role, candidate))
            if quality:
                attempts = max(1, int(quality.get("attempts", 0)))
                eval_count = max(1, int(quality.get("eval_count", 0)))
                score += int((int(quality.get("successes", 0)) / attempts) * 35)
                score += int((int(quality.get("eval_score_total", 0)) / eval_count) / 5)
                score -= int((int(quality.get("failures", 0)) / attempts) * 10)
            reason = f"matched capabilities {', '.join(capabilities)}"
            key = (candidate.name, candidate.profile, candidate.model)
            if key in seen:
                continue
            seen.add(key)
            ranked.append(RouteDecision(candidate, reason=reason, rank=score))

        ranked.sort(key=lambda item: item.rank, reverse=True)
        if not ranked:
            return [RouteDecision(self.default_provider, reason="default provider fallback", rank=0)]
        return ranked

    def record_outcome(self, role: str, config: ProviderConfig, success: bool) -> None:
        """Track recent routed outcomes so weak candidates get demoted."""
        key = (role, config.name, config.profile, config.model)
        history = self._outcomes.setdefault(key, [])
        history.append(bool(success))
        # Recent history matters most; keep the window small and cheap.
        if len(history) > 20:
            del history[:-20]

    def _quality_key(self, role: str, config: ProviderConfig) -> str:
        return "|".join([role, config.name, config.profile or "", config.model])

    def discover_ollama_models(self, provider_name: str = "ollama") -> list[ProviderConfig]:
        """Public helper for tests or diagnostics."""
        providers = self.config.get("providers", [])
        for provider in providers:
            if provider.get("name", "").lower() == provider_name.lower():
                return self._discover_ollama_models(provider)
        return []

    def _load_candidates(self) -> list[ProviderConfig]:
        providers = self.config.get("providers", [])
        candidates: list[ProviderConfig] = []
        for provider in providers:
            if not isinstance(provider, dict):
                continue
            provider_name = provider.get("name", "")
            profiles = provider.get("profiles")
            if profiles and isinstance(profiles, dict):
                for profile_name, profile_data in profiles.items():
                    if not self._scope_allows(provider_name, profile_name=profile_name):
                        continue
                    merged = dict(provider)
                    merged.update(profile_data or {})
                    merged.pop("profiles", None)
                    merged["profile"] = profile_name
                    candidates.append(_provider_config_from_dict(merged))
            else:
                if self._scope_allows(provider_name, model_name=provider.get("model", "")):
                    candidates.append(_provider_config_from_dict(provider))

            if provider.get("name", "").lower() == "ollama" and provider.get("discover", False):
                discovered = [
                    cfg for cfg in self._discover_ollama_models(provider)
                    if self._scope_allows(cfg.name, profile_name=cfg.profile, model_name=cfg.model)
                ]
                candidates.extend(discovered)

        if not candidates:
            candidates.append(self.default_provider)
        return candidates

    def _scope_allows(
        self,
        provider_name: str,
        *,
        profile_name: str = "",
        model_name: str = "",
    ) -> bool:
        scope = (self.provider_scope or "").strip().lower()
        if not scope:
            return True

        provider = (provider_name or "").strip().lower()
        profile = (profile_name or "").strip().lower()
        model = (model_name or "").strip().lower()

        if scope == provider:
            return True

        refs = {provider}
        if profile:
            refs.add(profile)
            if not profile.startswith(f"{provider}:") and not profile.startswith(f"{provider}/"):
                refs.add(f"{provider}:{profile}")
                refs.add(f"{provider}/{profile}")
        if model:
            refs.add(f"{provider}:{model}")

        return scope in refs

    def _discover_ollama_models(self, provider: dict) -> list[ProviderConfig]:
        try:
            import requests
        except ImportError:
            return []

        base_url = (provider.get("base_url") or "http://localhost:11434").rstrip("/")
        try:
            response = requests.get(f"{base_url}/api/tags", timeout=5)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        discovered: list[ProviderConfig] = []
        for item in payload.get("models", []):
            model_name = item.get("model") or item.get("name")
            if not model_name:
                continue
            profile = f"ollama:{model_name}"
            metadata = {
                "family": item.get("details", {}).get("family", ""),
                "parameter_size": item.get("details", {}).get("parameter_size", ""),
                "quantization_level": item.get("details", {}).get("quantization_level", ""),
                "size": item.get("size", 0),
            }
            capabilities = tuple(sorted(_infer_capabilities("ollama", model_name, metadata)))
            discovered.append(ProviderConfig(
                name="ollama",
                base_url=base_url,
                model=model_name,
                profile=profile,
                capabilities=capabilities,
                priority=provider.get("priority", 0),
                metadata=metadata,
            ))
        return discovered

    def _explicit_chain(self, role: str) -> list[RouteDecision]:
        route = self.route_overrides.get(role)
        if route is None:
            return []

        names = route if isinstance(route, list) else [route]
        matched: list[RouteDecision] = []
        for idx, name in enumerate(names):
            candidate = self._find_candidate(str(name))
            if candidate is not None:
                matched.append(RouteDecision(
                    provider_config=candidate,
                    reason=f"explicit route for {role}",
                    rank=10_000 - idx,
                ))
        return matched

    def _find_candidate(self, ref: str) -> Optional[ProviderConfig]:
        ref = ref.strip().lower()
        for candidate in self._candidates:
            if candidate.profile and candidate.profile.lower() == ref:
                return candidate
            if f"{candidate.name}:{candidate.profile}".lower() == ref:
                return candidate
            if f"{candidate.name}/{candidate.profile}".lower() == ref:
                return candidate
            if f"{candidate.name}:{candidate.model}".lower() == ref:
                return candidate
            if candidate.model.lower() == ref:
                return candidate
            if candidate.name.lower() == ref and not candidate.profile:
                return candidate
        return None

    def _candidate_score(self, candidate: ProviderConfig, required: Iterable[str]) -> int:
        score = candidate.priority * 10
        caps = set(candidate.capabilities)
        for capability in required:
            if capability in caps:
                score += 30
        if "local" in caps:
            score += 15
        if "cheap" in caps:
            score += 5
        return score


def _provider_config_from_dict(data: dict) -> ProviderConfig:
    allowed = {
        "name",
        "api_key",
        "model",
        "base_url",
        "max_tokens",
        "profile",
        "capabilities",
        "priority",
        "metadata",
    }
    payload = {k: v for k, v in data.items() if k in allowed and v is not None}
    capabilities = payload.get("capabilities")
    if capabilities is None:
        payload["capabilities"] = tuple(sorted(_infer_capabilities(
            payload.get("name", ""),
            payload.get("model", ""),
            payload.get("metadata", {}),
        )))
    else:
        payload["capabilities"] = tuple(capabilities)
    payload.setdefault("metadata", {})
    return ProviderConfig(**payload)


def _infer_capabilities(provider_name: str, model_name: str, metadata: Optional[dict] = None) -> set[str]:
    provider = provider_name.lower()
    model = (model_name or "").lower()
    metadata = metadata or {}

    caps = {"general"}
    if provider == "ollama":
        caps.add("local")

    if any(token in model for token in ("coder", "code", "devstral", "qwen2.5-coder", "deepseek-coder")):
        caps.add("code")
    if any(token in model for token in ("claude", "gpt", "sonnet", "reason", "r1", "opus")):
        caps.add("reasoning")
    if any(token in model for token in ("mini", "small", "3b", "7b")):
        caps.add("cheap")
    if any(token in model for token in ("70b", "72b", "110b", "405b", "large")):
        caps.add("large_context")
        caps.add("reasoning")

    param_size = str(metadata.get("parameter_size", "")).lower()
    match = re.search(r"(\d+(\.\d+)?)b", param_size)
    if match:
        size = float(match.group(1))
        if size <= 8:
            caps.add("cheap")
        if size >= 30:
            caps.add("large_context")
            caps.add("reasoning")
        if size >= 14:
            caps.add("code")

    if not {"code", "reasoning"} & caps:
        caps.add("code")
    return caps
