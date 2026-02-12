"""Base agent with shared prompt construction and file extraction."""

import re
from pathlib import Path

from ..providers.base import BaseProvider


class BaseAgent:
    """Base class for all Forge agents.

    Each agent has a role (system prompt), can construct prompts from context,
    and can extract file blocks from LLM responses.
    """

    role: str = "You are a helpful AI assistant."
    name: str = "base"

    def __init__(self, provider: BaseProvider, project_root: Path):
        self.provider = provider
        self.project_root = project_root

    def invoke(self, prompt: str) -> str:
        """Send a prompt to the LLM with this agent's system role."""
        messages = [{"role": "user", "content": prompt}]
        return self.provider.chat_with_retry(messages, system=self.role)

    def invoke_with_history(self, messages: list[dict]) -> str:
        """Send a multi-turn conversation."""
        return self.provider.chat_with_retry(messages, system=self.role)

    def extract_files(self, response: str) -> list[tuple[str, str]]:
        """Extract file blocks from LLM response.

        Recognizes:
          ```file:path/to/file.ext
          <content>
          ```

        and:
          ```path/to/file.ext
          <content>
          ```

        Returns list of (filepath, content) tuples.
        """
        files = []

        # Match ```file:path or ```language:path or ```path patterns
        # The key is the path must contain a / or end with a known extension
        pattern = r'```(?:file:)([^\n`]+)\n(.*?)```'
        for match in re.finditer(pattern, response, re.DOTALL):
            filepath = match.group(1).strip()
            content = match.group(2)
            filepath = filepath.lstrip("/")
            files.append((filepath, content.rstrip() + "\n"))

        if files:
            return files

        # Fallback: try to match ```path/to/file.ext patterns (path must have /)
        pattern2 = r'```([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)\n(.*?)```'
        for match in re.finditer(pattern2, response, re.DOTALL):
            filepath = match.group(1).strip()
            # Must look like a path (has / or at least a dot-extension)
            if "/" in filepath:
                filepath = filepath.lstrip("/")
                content = match.group(2)
                files.append((filepath, content.rstrip() + "\n"))

        if files:
            return files

        # Last resort: --- path/to/file.ext --- format
        pattern3 = r'---\s+([^\n]+\.[\w]+)\s+---\n(.*?)(?:---\s+end\s+---|(?=---\s+\S+\.[\w]+\s+---)|\Z)'
        for match in re.finditer(pattern3, response, re.DOTALL):
            filepath = match.group(1).strip().lstrip("/")
            content = match.group(2)
            files.append((filepath, content.rstrip() + "\n"))

        return files

    def write_files(self, files: list[tuple[str, str]]) -> list[str]:
        """Write extracted files to disk. Returns list of paths written."""
        written = []
        for filepath, content in files:
            full_path = self.project_root / filepath
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            written.append(filepath)
        return written
