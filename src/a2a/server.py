"""A2A Server -- wraps a Forge agent as an A2A-compatible HTTP server."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .types import AgentCard, Task, TaskResult, TaskStatus

if TYPE_CHECKING:
    pass


def create_a2a_app(agent, host: str = "0.0.0.0", port: int = 8100):
    """Create a FastAPI app that wraps a Forge agent as an A2A server.

    Exposes:
        GET  /.well-known/agent.json  -- AgentCard
        POST /tasks/send              -- process a Task, return TaskResult

    Args:
        agent: A BaseAgent subclass with handle_a2a_task() and agent_card()
        host: Host to bind to
        port: Port to listen on
    """
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import JSONResponse
    except ImportError:
        raise ImportError(
            "fastapi is required for A2A server support. "
            "Install with: pip install 'forge-ai[adk]'"
        )

    app = FastAPI(
        title=f"Forge Agent: {agent.name}",
        description=f"A2A-compatible server for {agent.name}",
        version="0.1.0",
    )

    @app.get("/.well-known/agent.json")
    async def get_agent_card():
        card = agent.get_agent_card(host=host, port=port)
        return JSONResponse(content=card.model_dump())

    @app.post("/tasks/send")
    async def send_task(task: Task) -> TaskResult:
        try:
            result = agent.handle_a2a_task(task)
            return result
        except Exception as e:
            return TaskResult(
                id=task.id,
                status=TaskStatus.failed,
                error=str(e),
            )

    @app.get("/health")
    async def health():
        return {"status": "ok", "agent": agent.name}

    return app


def serve_agent(agent, host: str = "0.0.0.0", port: int = 8100):
    """Start an A2A server for the given agent.

    Blocks until the server is stopped.
    """
    try:
        import uvicorn
    except ImportError:
        raise ImportError(
            "uvicorn is required to serve A2A agents. "
            "Install with: pip install 'forge-ai[adk]'"
        )

    app = create_a2a_app(agent, host=host, port=port)
    print(f"Starting A2A server for '{agent.name}' on http://{host}:{port}")
    print(f"  AgentCard: http://{host}:{port}/.well-known/agent.json")
    uvicorn.run(app, host=host, port=port, log_level="warning")
