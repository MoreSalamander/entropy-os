"""DataHub emission — the family pattern applied to learning provenance.

  dataset learn-engine.session.<id>
    ← lineage from learn-engine.agent.<research agent>   (what informed it)
  properties: goal, roadmap size, activities completed, graded items,
  correct rate, mastery distribution — the learning ledger as metadata.
"""

from __future__ import annotations

import httpx

from entropy_os.engines.research.config import DataHubConfig
from entropy_os.engines.research.graphs.datahub_bridge import DataHubBridge

from ..models import LearnerProfile, Roadmap


class LearnDataHubBridge(DataHubBridge):
    def __init__(self, gms_url: str = "http://localhost:8080",
                 enabled: str | bool = "auto"):
        super().__init__(DataHubConfig(enabled=enabled, gms_url=gms_url,
                                       platform="learn-engine", env="PROD"))

    async def emit_session(self, session_id: str, profile: LearnerProfile,
                           roadmap: Roadmap, activities: int,
                           graded: int, correct: int,
                           research_agents: list[str]) -> str:
        if not self.enabled:
            return self.status
        urn = self._dataset_urn(f"session.{session_id}")
        levels: dict[str, int] = {}
        for s in profile.mastery.values():
            levels[s.level.value] = levels.get(s.level.value, 0) + 1
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                upstreams = []
                for agent in research_agents:
                    a_urn = self._dataset_urn(
                        f"agent.{agent.lower().replace(' ', '_')}")
                    await self._ingest_dataset(
                        client, a_urn, f"learn-engine research worker: {agent}",
                        {"agent": agent})
                    upstreams.append(a_urn)
                await self._ingest_dataset(
                    client, urn, f"Learning session: {roadmap.goal}",
                    {"session_id": session_id, "goal": roadmap.goal,
                     "roadmap_concepts": len(roadmap.concepts),
                     "activities": activities, "graded_items": graded,
                     "correct_items": correct,
                     **{f"mastery_{k}": v for k, v in levels.items()}},
                    upstreams=upstreams)
            self.status = f"emitted {urn} with {len(upstreams)} agent lineage upstreams"
        except httpx.HTTPError as e:
            self.status = f"emission failed: {e}"
        return self.status
