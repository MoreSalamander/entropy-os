"""Impact analysis — what does new information actually affect?

The evolution loop's hard part is not re-running things; it is knowing what
*needs* re-running. When the system is asked to re-evaluate a subject it has
worked on before, this module answers:

    which prior objectives touched this subject?
    what did each engine produce for it?
    therefore which engines have work to redo, and which do not?

The answers come from the composite's OWN narration — the `StageCompleted`
facts in the durable event log — rather than from each engine's private event
vocabulary. That matters for composability: an engine that joins later becomes
visible to impact analysis by naming its outputs conventionally, with no table
here to update and no knowledge of this module required.

Nothing is inferred: an engine appears in an impact report only if a stage of
its actually completed and produced an identifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..events.bus import EventBus
from .semantics import identifying, slugify

# Ceiling on how much history one analysis reads. The log is append-only and
# a long-lived system accumulates; this keeps analysis bounded and fast while
# still spanning far more objectives than a session will produce.
HISTORY_LIMIT = 100_000


@dataclass
class ImpactReport:
    subject: str
    concept_slug: str
    prior_objectives: list[str] = field(default_factory=list)
    # engine key → the identifying outputs that engine produced for it
    affected: dict[str, dict] = field(default_factory=dict)
    unaffected: list[str] = field(default_factory=list)

    @property
    def is_new_subject(self) -> bool:
        return not self.prior_objectives

    def to_dict(self) -> dict:
        return {"subject": self.subject, "concept_slug": self.concept_slug,
                "prior_objectives": self.prior_objectives,
                "affected": self.affected, "unaffected": self.unaffected,
                "is_new_subject": self.is_new_subject}


def analyze(subject: str, bus: EventBus,
            engines: tuple[str, ...] = ("research", "university", "software",
                                        "web")) -> ImpactReport:
    """Read the system's own history for everything it has done to `subject`.

    Matching is by concept slug, not raw string, so "WebGPU compute shaders"
    and "WebGPU Compute Shaders" resolve to the same subject — the same
    identity rule the federation uses when it publishes a concept.
    """
    slug = slugify(subject)
    report = ImpactReport(subject=subject, concept_slug=slug)
    history = bus.recent(limit=HISTORY_LIMIT)

    objectives = {e.objective_id for e in history
                  if e.kind == "ObjectiveStarted"
                  and slugify(e.subject) == slug}
    report.prior_objectives = sorted(objectives)
    if not objectives:
        report.unaffected = sorted(engines)
        return report

    # Identifying outputs seen since the last StageCompleted, per objective.
    # They are the fallback for history recorded before StageCompleted began
    # carrying `produced`: an append-only log is a durable record, so a
    # consumer that can only read the newest format would quietly lose the
    # system's own past. Harvesting is by CONVENTION (identifying key names),
    # never by a per-engine table, so it stays composable for engines that
    # join later.
    pending: dict[str, dict] = {}

    for event in history:
        if event.objective_id not in objectives:
            continue
        if event.kind != "StageCompleted":
            found = identifying(event.payload)
            if found:
                pending[event.objective_id] = {
                    **pending.get(event.objective_id, {}), **found}
            continue
        if event.payload.get("status") != "completed":
            pending.pop(event.objective_id, None)
            continue

        produced = (event.payload.get("produced")
                    or pending.pop(event.objective_id, {}))
        pending.pop(event.objective_id, None)
        if not produced:
            continue           # a stage that made nothing identifiable
        engine = event.payload.get("engine", "")
        # Later objectives supersede earlier ones for the same engine: the
        # most recent artifact is the one an update would replace.
        report.affected[engine] = {**produced, "at": event.ts,
                                   "objective_id": event.objective_id,
                                   "urn": event.subject}
    report.unaffected = sorted(set(engines) - set(report.affected))
    return report
