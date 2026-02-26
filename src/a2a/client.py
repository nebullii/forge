"""A2A Client -- sends tasks to A2A-compatible agent HTTP servers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .types import Task, TaskResult, TaskStatus, Message, TextPart, Artifact

if TYPE_CHECKING:
    pass


class A2AClient:
    """Client for communicating with A2A agent servers over HTTP.

    When base_url is None or the agent is provided directly, falls back
    to in-process calls (no HTTP overhead).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        agent=None,  # BaseAgent instance for in-process calls
        timeout: float = 120.0,
    ):
        if base_url is None and agent is None:
            raise ValueError("Either base_url or agent must be provided")
        self.base_url = base_url
        self.agent = agent
        self.timeout = timeout

    def send_task(self, task: Task) -> TaskResult:
        """Send a task to the agent and return the result."""
        if self.agent is not None:
            # In-process call: no HTTP overhead
            return self.agent.handle_a2a_task(task)
        return self._send_http(task)

    def _send_http(self, task: Task) -> TaskResult:
        """Send task via HTTP to a remote A2A server."""
        try:
            import httpx
        except ImportError:
            raise ImportError(
                "httpx is required for remote A2A calls. "
                "Install with: pip install 'forge-ai[adk]'"
            )

        url = f"{self.base_url.rstrip('/')}/tasks/send"
        payload = task.model_dump()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                return TaskResult.model_validate(resp.json())
        except httpx.HTTPStatusError as e:
            return TaskResult(
                id=task.id,
                status=TaskStatus.failed,
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except httpx.RequestError as e:
            return TaskResult(
                id=task.id,
                status=TaskStatus.failed,
                error=f"Connection error to {self.base_url}: {e}",
            )

    @classmethod
    def for_agent(cls, agent) -> "A2AClient":
        """Create an in-process client for a local agent."""
        return cls(agent=agent)

    @classmethod
    def for_url(cls, base_url: str, timeout: float = 120.0) -> "A2AClient":
        """Create an HTTP client for a remote agent server."""
        return cls(base_url=base_url, timeout=timeout)
