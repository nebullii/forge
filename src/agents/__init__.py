"""Forge agents -- specialized AI workers for different build phases.

Classic mode (no ADK required):
    PlannerAgent, CoderAgent, ReviewerAgent, BackendAgent, ...
    Used by BuildOrchestrator in default mode.

ADK mode (requires google-adk):
    create_planner_agent(llm) → LlmAgent
    create_backend_agent(llm) → LlmAgent
    ...
    Each returns a google.adk.agents.LlmAgent wrapped by ADKAgentRunner.
"""

# Classic mode agents (plain Python, no ADK dependency)
from .planner import PlannerAgent
from .coder import CoderAgent
from .reviewer import ReviewerAgent
from .backend import BackendAgent
from .frontend import FrontendAgent
from .security_agent import SecurityAgent
from .ci_cd import CIAgent
from .deploy import DeployAgent

# ADK agent factories (require google-adk at call time, not import time)
from .planner import create_planner_agent
from .backend import create_backend_agent
from .frontend import create_frontend_agent
from .security_agent import create_security_agent
from .ci_cd import create_ci_agent
from .deploy import create_deploy_agent
from .reviewer import create_reviewer_agent

__all__ = [
    # Classic
    "PlannerAgent", "CoderAgent", "ReviewerAgent",
    "BackendAgent", "FrontendAgent", "SecurityAgent", "CIAgent", "DeployAgent",
    # ADK factories
    "create_planner_agent", "create_backend_agent", "create_frontend_agent",
    "create_security_agent", "create_ci_agent", "create_deploy_agent",
    "create_reviewer_agent",
]
