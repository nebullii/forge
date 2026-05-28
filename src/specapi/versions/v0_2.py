"""Spec API 0.2 implementation.

Version 0.2 is currently forward-compatible with 0.1 and reserved for additive
primitives such as relationships, richer auth policies, jobs/events, and seed
data. Keeping a separate module lets Forge evolve the language without changing
0.1 behavior.
"""

from __future__ import annotations

from ..compiler import compile_task_graph
from ..parser import parse_spec_file, parse_spec_text

__all__ = ["compile_task_graph", "parse_spec_file", "parse_spec_text"]
