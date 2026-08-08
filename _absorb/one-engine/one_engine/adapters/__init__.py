"""Leaf adapters: one per autonomous engine, each translating the Universal
Engine Contract onto that engine's existing front door. The registry is what
serve.py and the tests use to address them by short name."""

from .research import ResearchAdapter
from .software import SoftwareAdapter
from .university import UniversityAdapter
from .web import WebAdapter

ADAPTERS = {
    "research": ResearchAdapter,
    "software": SoftwareAdapter,
    "university": UniversityAdapter,
    "web": WebAdapter,
}

__all__ = ["ADAPTERS", "ResearchAdapter", "SoftwareAdapter",
           "UniversityAdapter", "WebAdapter"]
