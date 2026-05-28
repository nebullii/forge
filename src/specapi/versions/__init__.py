"""Version dispatch for Forge Spec API."""

from __future__ import annotations

from ..models import SpecDocument
from . import v0_1, v0_2


PARSERS = {
    "0.1": v0_1,
    "0.2": v0_2,
}


def compiler_for(doc: SpecDocument):
    return PARSERS.get(doc.spec_api_version, v0_1)
