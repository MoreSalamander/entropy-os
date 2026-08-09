"""The paper renderer, held to the three rules that make it a translation.

A prettier document built from the same evidence is worth having. A prettier
document that quietly gained a fact is worth less than the instrument panel
it replaced, so each rule here is a test rather than a promise in a docstring.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from entropy_os.engines.research.graphs.context_graph import ContextGraph
from entropy_os.engines.research.models import (
    Claim,
    Entity,
    EntityType,
    Evidence,
    Finding,
    ResearchPlan,
    SourceCategory,
)
from entropy_os.engines.research.report.paper import (
    CITE_RE,
    PaperBuilder,
    _title,
    check_citations,
)


def _ev(url: str, title: str = "A Source", rel: float = 0.8) -> Evidence:
    return Evidence(source="academic", category=SourceCategory.ACADEMIC, url=url,
                    title=title, excerpt="…", authors=["Ada Lovelace"],
                    published=datetime(2024, 3, 1, tzinfo=UTC), reliability=rel)


def _graph(topic: str = "US currency") -> ContextGraph:
    cg = ContextGraph("session_test", ResearchPlan(topic=topic))
    dollar = Entity(name="dollar", type=EntityType.CONCEPT,
                    description="the US currency unit")
    fed = Entity(name="Federal Reserve", type=EntityType.ORGANIZATION,
                 description="the US central bank")
    for e in (dollar, fed):
        cg.entities[e.id] = e
    return cg, dollar, fed


def _claim(stmt: str, ents: list[str], evidence: list[Evidence],
           verified: bool = True) -> Claim:
    return Claim(statement=stmt, entity_ids=ents, evidence=evidence,
                 verified=verified, confidence=0.8)


class ScriptedLLM:
    """Returns whatever it was told to, so a test can make the model
    misbehave in exactly the way that matters."""

    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    async def chat_text(self, role, system, user):
        self.calls += 1
        return self.reply


# --------------------------------------------------------------------------- #
# rule 1 — nothing new enters
# --------------------------------------------------------------------------- #

async def test_only_verified_claims_reach_the_paper():
    """An unverified claim did not clear the evidence floor. Prose is exactly
    where that fact would stop being visible, so it never gets there."""
    cg, dollar, _ = _graph()
    cg.claims["c1"] = _claim("The dollar is issued by the Federal Reserve",
                             [dollar.id], [_ev("https://a.test")])
    cg.claims["c2"] = _claim("The dollar will collapse next year",
                             [dollar.id], [_ev("https://b.test")], verified=False)

    paper = await PaperBuilder(llm=None).build(cg, [])
    body = " ".join(t.prose for t in paper.themes)
    assert "issued by the Federal Reserve" in body
    assert "collapse" not in body
    assert paper.claims_verified_total == 1


async def test_a_claim_with_no_evidence_is_not_reported():
    cg, dollar, _ = _graph()
    cg.claims["c1"] = _claim("Unsourced assertion", [dollar.id], [])
    paper = await PaperBuilder(llm=None).build(cg, [])
    assert paper.claims_used == 0


# --------------------------------------------------------------------------- #
# rule 2 — every sentence is traceable
# --------------------------------------------------------------------------- #

def test_an_unresolvable_citation_is_detected():
    assert check_citations("grounded [1] and invented [9]", {1, 2}) == [9]
    assert check_citations("all fine [1] [2]", {1, 2}) == []


async def test_prose_that_cites_a_nonexistent_source_is_discarded():
    """The signature of invention: a model supporting a sentence it made up
    with a reference number that does not exist. The section is dropped
    whole, because deleting the marker would leave the sentence behind."""
    cg, dollar, _ = _graph()
    for i in range(2):
        cg.claims[f"c{i}"] = _claim(f"Verified statement {i} about the dollar",
                                    [dollar.id], [_ev(f"https://s{i}.test")])

    liar = ScriptedLLM("The dollar was abolished in 1912 [42].")
    paper = await PaperBuilder(llm=liar).build(cg, [])
    body = " ".join(t.prose for t in paper.themes)
    assert "abolished" not in body
    assert "Verified statement 0" in body       # fell back to the real claims


async def test_good_prose_is_kept_with_its_citations():
    cg, dollar, _ = _graph()
    for i in range(2):
        cg.claims[f"c{i}"] = _claim(f"Statement {i} about the dollar",
                                    [dollar.id], [_ev(f"https://s{i}.test")])
    good = ScriptedLLM("The dollar is widely used [1]. It is also studied [2].")
    paper = await PaperBuilder(llm=good).build(cg, [])
    assert "widely used [1]" in " ".join(t.prose for t in paper.themes)


async def test_every_reference_number_used_exists_in_the_reference_list():
    cg, dollar, fed = _graph()
    cg.claims["c1"] = _claim("A about the dollar", [dollar.id], [_ev("https://a.test")])
    cg.claims["c2"] = _claim("B about the dollar", [dollar.id], [_ev("https://b.test")])
    cg.claims["c3"] = _claim("C about the Federal Reserve currency",
                             [fed.id], [_ev("https://c.test")])
    paper = await PaperBuilder(llm=None).build(cg, [])
    numbers = {r.n for r in paper.references}
    used = {int(n) for t in paper.themes for n in CITE_RE.findall(t.prose)}
    assert used, "the paper cited nothing at all"
    assert used <= numbers, f"cited {used - numbers} which is not in the references"


async def test_a_source_cited_twice_gets_one_number():
    cg, dollar, _ = _graph()
    shared = "https://same.test"
    cg.claims["c1"] = _claim("First dollar claim", [dollar.id], [_ev(shared)])
    cg.claims["c2"] = _claim("Second dollar claim", [dollar.id], [_ev(shared)])
    paper = await PaperBuilder(llm=None).build(cg, [])
    assert len(paper.references) == 1


# --------------------------------------------------------------------------- #
# rule 3 — off-topic evidence is dropped, and said so
# --------------------------------------------------------------------------- #

async def test_off_topic_claims_are_excluded_and_counted():
    """The real failure this fixes: a session on U.S. currency reporting LHCb
    decay rates. Retrieved, real, and not what was asked."""
    cg, dollar, _ = _graph("US currency")
    physics = Entity(name="LHCb", type=EntityType.ORGANIZATION,
                     description="a particle physics experiment")
    cg.entities[physics.id] = physics
    cg.claims["c1"] = _claim("The dollar is the US currency unit",
                             [dollar.id], [_ev("https://a.test")])
    cg.claims["c2"] = _claim("The decay rate was measured at LHCb",
                             [physics.id], [_ev("https://b.test")])

    paper = await PaperBuilder(llm=None).build(cg, [])
    body = " ".join(t.prose for t in paper.themes)
    assert "decay rate" not in body
    assert paper.excluded_claims == 1
    # …and the reader is told, rather than the number being swallowed.
    assert "set aside as unrelated" in paper.method


async def test_the_filter_never_empties_the_paper():
    """If nothing matched, the filter is wrong — not the evidence. A paper
    with no findings would be a worse lie than one with loose ones."""
    cg, dollar, _ = _graph("zzzq unmatchable topic")
    cg.claims["c1"] = _claim("A real finding", [dollar.id], [_ev("https://a.test")])
    paper = await PaperBuilder(llm=None).build(cg, [])
    assert paper.claims_used == 1
    assert paper.excluded_claims == 0


# --------------------------------------------------------------------------- #
# it reads like a paper
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("asked,expected", [
    ("i would like to learn about U.S. currency", "U.S. currency"),
    ("what is quantitative easing?", "Quantitative easing"),
    ("Tell me about WebGPU", "WebGPU"),
])
def test_the_title_is_a_title_not_the_prompt(asked, expected):
    assert _title(asked) == expected


async def test_the_document_has_the_shape_of_a_paper():
    cg, dollar, fed = _graph()
    for i in range(3):
        cg.claims[f"c{i}"] = _claim(f"Dollar finding {i}", [dollar.id],
                                    [_ev(f"https://s{i}.test")])
    findings = [Finding(agent="Contradiction Agent", kind="contradiction",
                        text="Sources disagree on the 1971 date"),
                Finding(agent="Question Agent", kind="question",
                        text="What drove the 1971 decision?")]
    md = (await PaperBuilder(llm=None).build(cg, findings)).markdown
    for heading in ("## Abstract", "## Contested Points", "## Open Questions",
                    "## Method and Limitations", "## References"):
        assert heading in md
    # No instrument-panel vocabulary leaking into the reader's document.
    assert "confidence 0." not in md
    assert "tasks_spawned" not in md
    assert "https://s0.test" in md          # the sources are actually listed


async def test_a_missing_model_costs_readability_never_grounding():
    """The degraded path is still a paper: plainer sentences, same claims,
    same citations, same references."""
    cg, dollar, _ = _graph()
    for i in range(2):
        cg.claims[f"c{i}"] = _claim(f"Dollar fact {i}", [dollar.id],
                                    [_ev(f"https://s{i}.test")])
    paper = await PaperBuilder(llm=None).build(cg, [])
    assert paper.references
    assert "[1]" in " ".join(t.prose for t in paper.themes)


async def test_the_abstract_names_the_subject_not_the_prompt():
    """The title was cleaned and the abstract was not, so a paper opened with
    "This report examines i would like to learn about U.S. currency" — it had
    published the question someone typed instead of naming its own subject."""
    cg, dollar, _ = _graph("i would like to learn about U.S. currency")
    cg.claims["c1"] = _claim("The dollar is the US currency unit",
                             [dollar.id], [_ev("https://a.test")])
    paper = await PaperBuilder(llm=None).build(cg, [])
    assert "i would like to learn" not in paper.abstract
    assert "U.S. currency" in paper.abstract
    assert paper.title == "U.S. currency"
