"""Forge Spec API parsing and task graph compilation."""

from .compiler import TaskGraph
from .models import SpecDocument, SpecDiagnostic, SpecPrimitive
from .parser import parse_spec_file, parse_spec_text
from .versions import compiler_for


def compile_task_graph(doc: SpecDocument) -> TaskGraph:
    """Compile a parsed Spec API document using its declared version."""
    return compiler_for(doc).compile_task_graph(doc)

__all__ = [
    "SpecDiagnostic",
    "SpecDocument",
    "SpecPrimitive",
    "TaskGraph",
    "compile_task_graph",
    "parse_spec_file",
    "parse_spec_text",
]
