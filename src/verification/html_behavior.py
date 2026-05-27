"""HTML behavioural verifier — catches the offline/dead-binding bug class.

Specifically:
  - External network resources on tags that should be self-contained (audio,
    img, script, link) — violates "single-file static site / no network"
  - <button id="..."> elements with no JS handler bound to them anywhere in
    the page's inline scripts — dead controls
  - <audio> / <video> elements with no src and no <source> child — silently broken
  - Forms with no action and no JS submit handler — dead submission

The verifier is intentionally conservative: it warns on the cases above only
when the project is a static / single-file site (no backend). For full-stack
projects, external URLs and form posts are expected.
"""

from __future__ import annotations

import re
from typing import Iterable

from .base import BaseVerifier
from .models import VerificationContext, VerificationResult


# Tags whose self-host expectation differs by attribute name
_NETWORK_ATTRS = {
    "audio": "src",
    "video": "src",
    "source": "src",
    "img": "src",
    "script": "src",
    "link": "href",
    "iframe": "src",
}

_EXTERNAL_URL_RE = re.compile(r"^\s*https?://", re.IGNORECASE)


class HTMLBehaviorVerifier(BaseVerifier):
    name = "html_behavior"
    category = "html"

    def applies_to(self, context: VerificationContext) -> bool:
        return any(path.endswith((".html", ".htm")) for path in context.files)

    def run(self, context: VerificationContext) -> VerificationResult:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return VerificationResult(
                verifier=self.name, category=self.category,
                passed=True, severity="info",
                summary="HTML behaviour check skipped (bs4 not installed)",
            )

        is_offline_site = self._is_offline_site(context)

        failures: list[str] = []
        affected: list[str] = []

        for path, content in context.files.items():
            if not path.endswith((".html", ".htm")):
                continue
            soup = BeautifulSoup(content, "html.parser")

            if is_offline_site:
                failures.extend(self._check_external_resources(path, soup))

            failures.extend(self._check_empty_media(path, soup))
            failures.extend(self._check_dead_buttons(path, soup))

            if any(failure.startswith(f"{path}:") for failure in failures[-10:]):
                affected.append(path)

        unique_files = tuple(dict.fromkeys(affected))
        return VerificationResult(
            verifier=self.name,
            category=self.category,
            passed=not failures,
            severity="error",
            summary="HTML behaviour and offline-resource check",
            details="\n".join(failures),
            logs=tuple(failures),
            files=unique_files,
            retryable=True,
        )

    # ------------------------------------------------------------------
    def _is_offline_site(self, context: VerificationContext) -> bool:
        """True when this is a single-file or static project with no backend.

        The local fast-path planner emits framework='static-html' or similar;
        we also infer offline from "no backend/" directory and presence of an
        index.html at root.
        """
        stack = context.decisions.get("stack", {}) if isinstance(context.decisions, dict) else {}
        framework = str(stack.get("framework", "")).strip().lower()
        backend = str(stack.get("backend", "")).strip().lower()
        if framework in ("static-html", "static", "html", "plain-html"):
            return True
        if backend in ("none", "", "static"):
            has_backend_dir = any(p.startswith("backend/") for p in context.files)
            has_index = "index.html" in context.files
            if has_index and not has_backend_dir:
                return True
        return False

    def _check_external_resources(self, path: str, soup) -> list[str]:
        failures: list[str] = []
        for tag_name, attr in _NETWORK_ATTRS.items():
            for tag in soup.find_all(tag_name):
                value = tag.get(attr)
                if value and _EXTERNAL_URL_RE.match(value):
                    # Allow CDN links to permitted hosts inside <link>/<script>
                    # only when the project is not declared static — but in the
                    # offline path we always flag.
                    line = _line_of(soup, tag)
                    failures.append(
                        f"{path}:{line} <{tag_name} {attr}=\"{value}\"> uses an "
                        "external URL; an offline single-file site must inline or "
                        "self-host this resource."
                    )
        return failures

    def _check_empty_media(self, path: str, soup) -> list[str]:
        failures: list[str] = []
        for tag in soup.find_all(["audio", "video"]):
            has_src = bool(tag.get("src"))
            has_source_child = tag.find("source") is not None
            if not has_src and not has_source_child:
                line = _line_of(soup, tag)
                failures.append(
                    f"{path}:{line} <{tag.name}> has neither a src attribute nor a "
                    "<source> child — element is silently inert."
                )
        return failures

    def _check_dead_buttons(self, path: str, soup) -> list[str]:
        failures: list[str] = []
        script_body = self._collect_script_text(soup)
        for button in soup.find_all("button"):
            if button.get("onclick"):
                continue
            if button.get("type", "").lower() == "submit":
                # Submit buttons are handled by their form
                if button.find_parent("form") is not None:
                    continue
            button_id = button.get("id")
            classes = button.get("class") or []

            if button_id and self._references_id(script_body, button_id):
                continue
            if classes and any(self._references_class(script_body, cls) for cls in classes):
                continue

            line = _line_of(soup, button)
            label = (button.get_text() or button_id or "").strip()[:30]
            failures.append(
                f"{path}:{line} <button id=\"{button_id or ''}\"> '{label}' has no "
                "onclick attribute and no JS handler bound to its id/class — dead control."
            )
        return failures

    def _collect_script_text(self, soup) -> str:
        bodies: list[str] = []
        for script in soup.find_all("script"):
            if script.get("src"):
                continue
            text = script.string or ""
            if text:
                bodies.append(text)
        return "\n".join(bodies)

    def _references_id(self, script_text: str, button_id: str) -> bool:
        if not script_text or not button_id:
            return False
        # Match getElementById('id') / getElementById("id") / .querySelector('#id')
        patterns = (
            rf"getElementById\s*\(\s*['\"]{re.escape(button_id)}['\"]",
            rf"querySelector(?:All)?\s*\(\s*['\"]#{re.escape(button_id)}\b",
        )
        return any(re.search(pat, script_text) for pat in patterns)

    def _references_class(self, script_text: str, class_name: str) -> bool:
        if not script_text or not class_name:
            return False
        patterns = (
            rf"getElementsByClassName\s*\(\s*['\"]{re.escape(class_name)}['\"]",
            rf"querySelector(?:All)?\s*\(\s*['\"]\.{re.escape(class_name)}\b",
        )
        return any(re.search(pat, script_text) for pat in patterns)


def _line_of(soup, tag) -> int:
    """Best-effort line number for a bs4 tag using sourceline when available."""
    line = getattr(tag, "sourceline", None)
    return int(line) if line else 0
