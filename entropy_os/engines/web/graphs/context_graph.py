"""Phase 3 — Design Context Graph: the current design problem, live.

Nodes: the project, brand requirements, user-psychology axes (the semantic
traits), analyzed sites, extracted traits, industry notes, tech notes,
required components. Edges connect evidence to the axes it informs. The
graph updates continuously as research workers land results — add_analysis
is called mid-flight, not batch-at-end.

Rollups the synthesis engine reads:
  trait_census()     how often each abstract trait appears across the corpus
  palette_pool()     observed palettes by mode (dark/light)
  section_prior()    which sections the corpus actually uses
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx

from ..models import DesignTrait, ProjectIntent, SiteAnalysis, TraitKind, new_id, now_utc


class DesignContextGraph:
    def __init__(self, project_id: str, intent: ProjectIntent):
        self.project_id = project_id
        self.intent = intent
        self.g = nx.MultiDiGraph()
        self.analyses: dict[str, SiteAnalysis] = {}      # url -> analysis
        self.traits: dict[str, DesignTrait] = {}         # id -> trait
        self.industry_notes: list[dict] = []
        self.tech_notes: list[dict] = []
        self.competitor_discovery_note: str = ""
        self.g.add_node("project", kind="project", label=intent.raw_request[:80])
        for axis in intent.semantic_traits:
            self.g.add_node(f"axis:{axis}", kind="psychology_axis", label=axis)
            self.g.add_edge("project", f"axis:{axis}", key="targets", kind="targets")
        for page in intent.required_pages:
            self.g.add_node(f"page:{page.value}", kind="required_page", label=page.value)
            self.g.add_edge("project", f"page:{page.value}", key="requires", kind="requires")

    # ------------------------------------------------------------------ #
    # live ingestion
    # ------------------------------------------------------------------ #
    def add_analysis(self, worker: str, analysis: SiteAnalysis) -> None:
        self.analyses[analysis.url] = analysis
        site_node = f"site:{analysis.url}"
        self.g.add_node(site_node, kind="site", label=analysis.title[:60] or analysis.url,
                        ok=analysis.ok, worker=worker,
                        category=analysis.seed_category)
        self.g.add_edge("project", site_node, key="researched", kind="researched_by",
                        worker=worker)
        for trait in analysis.traits:
            self.traits[trait.id] = trait
            tnode = f"trait:{trait.kind.value}:{trait.name}"
            if not self.g.has_node(tnode):
                self.g.add_node(tnode, kind="trait", trait_kind=trait.kind.value,
                                label=trait.name)
            self.g.add_edge(site_node, tnode, key=trait.id, kind="exhibits",
                            value=trait.value)

    def add_industry_note(self, worker: str, title: str, text: str, url: str) -> None:
        self.industry_notes.append({"worker": worker, "title": title,
                                    "text": text[:600], "url": url})

    def add_tech_note(self, worker: str, title: str, text: str, url: str,
                      stars: int = 0) -> None:
        self.tech_notes.append({"worker": worker, "title": title,
                                "text": text[:300], "url": url, "stars": stars})

    # ------------------------------------------------------------------ #
    # rollups for synthesis
    # ------------------------------------------------------------------ #
    def trait_census(self, kind: TraitKind | None = None) -> Counter:
        c: Counter = Counter()
        for t in self.traits.values():
            if kind is None or t.kind == kind:
                c[t.name] += 1
        return c

    def palette_pool(self) -> dict[str, list[list[str]]]:
        pool: dict[str, list[list[str]]] = defaultdict(list)
        for a in self.analyses.values():
            if not a.palette:
                continue
            mode = ("dark" if any(t.name == "dark_technical" for t in a.traits)
                    else "light")
            pool[mode].append(a.palette)
        return dict(pool)

    def section_prior(self) -> Counter:
        c: Counter = Counter()
        for a in self.analyses.values():
            for s in a.section_signals:
                c[s] += 1
        return c

    def traits_of_site(self, url: str) -> list[DesignTrait]:
        return [t for t in self.traits.values() if t.site_url == url]

    # ------------------------------------------------------------------ #
    def snapshot(self) -> dict:
        return {
            "project_id": self.project_id,
            "generated_at": now_utc().isoformat(),
            "intent": json.loads(self.intent.model_dump_json()),
            "analyses": [json.loads(a.model_dump_json())
                         for a in self.analyses.values()],
            "industry_notes": self.industry_notes,
            "tech_notes": self.tech_notes,
            "competitor_discovery_note": self.competitor_discovery_note,
            "trait_census": dict(self.trait_census()),
            "section_prior": dict(self.section_prior()),
        }

    def save(self, sessions_dir: Path) -> Path:
        sessions_dir.mkdir(parents=True, exist_ok=True)
        path = sessions_dir / f"{self.project_id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.snapshot(), indent=2, default=str))
        tmp.replace(path)
        return path


def new_project_id() -> str:
    return new_id("project")
