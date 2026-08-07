"""code-engine — AI-native Software Intelligence and Generation Platform.

Third engine on the research-engine substrate:

    User Idea → Software Spec → Parallel Research → Architecture
    → Software Context Graph (the living model) → Multi-Agent Engineering Org
    → Generated Software → Continuous Verification → Impact Analysis
    → Evolution Checks → Software Knowledge Graph (cross-project learning)

Design law (unchanged across the family): LLMs propose through schema gates;
deterministic code decides, renders, and verifies. The Software Context
Graph is built BY CONSTRUCTION during generation — every file knows which
component, feature, and requirement it exists for — then continuously
checked against reality (pytest, ruff, ast-observed structure, OSV, PyPI).
The graph ships inside the generated repo as a sidecar
(.code_engine/graph.json): the software carries its own self-model.
"""

__version__ = "0.1.0"
