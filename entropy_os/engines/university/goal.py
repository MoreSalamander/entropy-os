"""Phase 1 — Learning Goal Analysis (Curriculum Agent, planning half).

Goal → roadmap DAG through a schema gate, then deterministic validation:

  * concepts deduped by normalized name; depth assigned from the edge
    structure (goal concepts depth 0, prerequisites deeper)
  * only relations from the EduRelation vocabulary survive
  * the `requires` subgraph must be a DAG — cycles are broken at the
    weakest link (the edge closing the cycle) with a validation note,
    because a curriculum with circular prerequisites is unteachable
  * learning_order = topological sort of `requires`, prerequisites first,
    deterministic tie-break (depth, then name)
  * LLM down → a minimal one-concept roadmap still works, labeled
"""

from __future__ import annotations

from collections import defaultdict

from entropy_os.engines.research.llm.client import LLMClient, LLMUnavailable
from entropy_os.engines.research.models import normalize_name

from .models import Concept, EduRelation, Roadmap

_ROADMAP_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "concepts": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "summary": {"type": "string"}},
            "required": ["name", "summary"]}},
        "edges": {"type": "array", "items": {"type": "object", "properties": {
            "src": {"type": "string"},
            "relation": {"type": "string",
                         "enum": [r.value for r in EduRelation]},
            "dst": {"type": "string"}},
            "required": ["src", "relation", "dst"]}},
        "goal_concepts": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["subject", "concepts", "edges", "goal_concepts"],
}

_SYSTEM = """You are the curriculum-planning module of an education platform.
Given a learning goal, produce a prerequisite roadmap as JSON:
- subject: the field this goal belongs to
- concepts: 8-16 concepts spanning the goal itself AND its prerequisites
  (each with a one-sentence summary)
- edges: relations between concept names. "X requires Y" means Y must be
  learned BEFORE X. Also use builds_upon/related_to/applied_in where true.
- goal_concepts: which of your concepts are the goal itself (not prerequisites)
Prerequisites should be genuinely necessary, not encyclopedic. No filler."""


class GoalAnalyzer:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def analyze(self, goal: str) -> Roadmap:
        notes: list[str] = []
        try:
            proposal = await self.llm.chat_json(
                "plan", _SYSTEM, f"Learning goal: {goal}", _ROADMAP_SCHEMA)
        except LLMUnavailable:
            proposal = {}
            notes.append("LLM unavailable — minimal fallback roadmap")

        # ---- concepts, deduped -----------------------------------------
        by_norm: dict[str, Concept] = {}
        for c in proposal.get("concepts") or []:
            if not isinstance(c, dict) or not str(c.get("name", "")).strip():
                continue
            name = str(c["name"]).strip()[:80]
            key = normalize_name(name)
            if key not in by_norm:
                by_norm[key] = Concept(name=name,
                                       summary=str(c.get("summary", ""))[:250])
        if not by_norm:
            root = Concept(name=goal[:80], summary=f"Direct study of: {goal}")
            by_norm[normalize_name(root.name)] = root
            notes.append("no concepts proposed; goal itself is the sole concept")

        # ---- edges, validated -------------------------------------------
        edges: list[tuple[str, str, str]] = []
        for e in proposal.get("edges") or []:
            if not isinstance(e, dict):
                continue
            src = by_norm.get(normalize_name(str(e.get("src", ""))))
            dst = by_norm.get(normalize_name(str(e.get("dst", ""))))
            try:
                rel = EduRelation(e.get("relation", ""))
            except ValueError:
                continue
            if src and dst and src.name != dst.name:
                edges.append((src.name, rel.value, dst.name))

        # ---- requires-DAG enforcement -----------------------------------
        requires = [(s, d) for s, r, d in edges if r == "requires"]
        adjacency: dict[str, set[str]] = defaultdict(set)
        for s, d in requires:
            adjacency[s].add(d)     # s requires d → d before s

        def _find_cycle() -> list[str] | None:
            WHITE, GRAY, BLACK = 0, 1, 2
            color = {c.name: WHITE for c in by_norm.values()}
            stack: list[str] = []

            def dfs(node: str) -> list[str] | None:
                color[node] = GRAY
                stack.append(node)
                for nxt in adjacency.get(node, ()):  # noqa: B007
                    if color.get(nxt, 0) == 1:
                        return stack[stack.index(nxt):] + [nxt]
                    if color.get(nxt, 0) == 0:
                        found = dfs(nxt)
                        if found:
                            return found
                stack.pop()
                color[node] = BLACK
                return None

            for name in list(color):
                if color[name] == WHITE:
                    found = dfs(name)
                    if found:
                        return found
            return None

        while True:
            cycle = _find_cycle()
            if not cycle:
                break
            # break the edge that closes the cycle
            s, d = cycle[-2], cycle[-1]
            adjacency[s].discard(d)
            edges = [e for e in edges if not (e[0] == s and e[1] == "requires"
                                              and e[2] == d)]
            notes.append(f"broke circular prerequisite: {s} → {d}")

        # ---- depths + topological learning order ------------------------
        goal_names = {by_norm[normalize_name(g)].name
                      for g in proposal.get("goal_concepts") or []
                      if normalize_name(g) in by_norm}
        if not goal_names:
            # concepts nothing requires FROM are the top of the tree
            required_by_someone = {d for _s, d in
                                   ((s, d) for s, r, d in edges if r == "requires")}
            goal_names = ({c.name for c in by_norm.values()}
                          - required_by_someone) or {next(iter(by_norm.values())).name}

        depth: dict[str, int] = {g: 0 for g in goal_names}
        frontier = list(goal_names)
        while frontier:
            node = frontier.pop()
            for pre in adjacency.get(node, ()):
                if depth.get(pre, -1) < depth[node] + 1:
                    depth[pre] = depth[node] + 1
                    frontier.append(pre)
        for c in by_norm.values():
            c.depth = depth.get(c.name, 0)

        # Kahn's algorithm on (prerequisite → dependent) direction
        indeg: dict[str, int] = {c.name: 0 for c in by_norm.values()}
        dependents: dict[str, set[str]] = defaultdict(set)
        for s, d in ((s, d) for s, r, d in edges if r == "requires"):
            dependents[d].add(s)
            indeg[s] += 1
        ready = sorted((n for n, deg in indeg.items() if deg == 0),
                       key=lambda n: (-depth.get(n, 0), n))
        order: list[str] = []
        while ready:
            node = ready.pop(0)
            order.append(node)
            for dep in sorted(dependents.get(node, ())):
                indeg[dep] -= 1
                if indeg[dep] == 0:
                    ready.append(dep)
            ready.sort(key=lambda n: (-depth.get(n, 0), n))
        for name in sorted(indeg, key=lambda n: (-depth.get(n, 0), n)):
            if name not in order:   # unreachable safety net
                order.append(name)

        return Roadmap(goal=goal,
                       subject=str(proposal.get("subject") or "general")[:60],
                       concepts=list(by_norm.values()), edges=edges,
                       validation_notes=notes, learning_order=order)
