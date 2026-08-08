"""The six reasoning agents and the full report — content counted, not marker-checked."""

from __future__ import annotations

from entropy_os.engines.research.agents import (AnalystAgent, ContradictionAgent,
                                    DiscoveryAgent, QuestionAgent, TrendAgent,
                                    VerificationAgent)
from entropy_os.engines.research.graphs.context_graph import ContextGraph
from entropy_os.engines.research.llm.client import FakeLLM
from entropy_os.engines.research.models import (Entity, EntityType, ExtractionResult,
                                    Polarity, SourceCategory)
from entropy_os.engines.research.report.builder import ReportBuilder

from .conftest import make_claim, make_evidence


def _cg_with_evidence(plan) -> ContextGraph:
    """A session with: 1 strong claim, 1 corroborated claim, 1 weak claim,
    1 dispute, entities across two source categories."""
    cg = ContextGraph("s_test", plan)
    qc = Entity(name="Quantum Computing", type=EntityType.TECHNOLOGY,
                description="qubit computation")
    ecc = Entity(name="Error Correction", type=EntityType.CONCEPT,
                 description="fixing qubit noise")
    repo = Entity(name="qiskit", type=EntityType.PRODUCT, description="sdk")

    strong = make_claim("Error correction improved in 2026", [ecc.id],
                        [make_evidence(source="pubmed", reliability=0.85, days_old=20)])
    weak = make_claim("QC replaces classical computing", [qc.id],
                      [make_evidence(source="reddit", reliability=0.3)])
    corroborated = make_claim("Qubit counts are rising", [qc.id],
                              [make_evidence(source="arxiv", reliability=0.6, days_old=30),
                               make_evidence(source="gdelt_news", reliability=0.5, days_old=40,
                                             url="https://news/x")])
    dispute = make_claim("QC replaces classical computing is overstated", [qc.id],
                         [make_evidence(source="openalex", reliability=0.8)],
                         polarity=Polarity.DISPUTES)
    code_ev = make_evidence(source="github", reliability=0.55, days_old=15,
                            url="https://github.com/Qiskit/qiskit")
    code_ev.category = SourceCategory.CODE
    code_claim = make_claim("qiskit implements error correction codes",
                            [repo.id, ecc.id], [code_ev])
    # bridges qc↔ecc so a real entity-mediated path exists (qc—bridge—ecc—code_claim—repo);
    # paths through the topic hub are excluded by design
    bridge = make_claim("Error correction is central to quantum computing",
                        [qc.id, ecc.id], [make_evidence(source="openalex",
                                                        reliability=0.75,
                                                        url="https://openalex/b")])

    cg.add_extraction("Academic Research Agent",
                      ExtractionResult(doc_url="https://a", entities=[qc, ecc],
                                       claims=[strong, weak, corroborated, dispute, bridge]))
    cg.add_extraction("Open Source Agent",
                      ExtractionResult(doc_url="https://g", entities=[repo, ecc],
                                       claims=[code_claim]))
    return cg


class TestAgents:
    async def test_verification_gate_policy(self, plan):
        cg = _cg_with_evidence(plan)
        await VerificationAgent(FakeLLM()).analyze(cg)
        by_stmt = {c.statement: c for c in cg.claims.values()}
        assert by_stmt["Error correction improved in 2026"].verified      # strong single source
        assert by_stmt["Qubit counts are rising"].verified                # 2 sources ≥ floor
        assert not by_stmt["QC replaces classical computing"].verified    # weak single source

    async def test_contradiction_agent_confirms_candidates(self, plan):
        cg = _cg_with_evidence(plan)
        assert cg.contradiction_candidates  # deterministic pairing found the dispute
        llm = FakeLLM({"judge": [{"contradicts": True, "explanation": "direct opposition"}]})
        findings = await ContradictionAgent(llm).analyze(cg)
        assert findings and findings[0].kind == "contradiction"
        assert findings[0].evidence_ids  # cites both sides

    async def test_contradiction_agent_never_autoconfirms_without_judge(self, plan):
        cg = _cg_with_evidence(plan)
        findings = await ContradictionAgent(FakeLLM(up=False)).analyze(cg)
        assert findings == []  # fail-closed

    async def test_analyst_summarizes_per_branch(self, plan):
        cg = _cg_with_evidence(plan)
        findings = await AnalystAgent(FakeLLM(text_response="Branch summary.")).analyze(cg)
        kinds = {f.kind for f in findings}
        assert kinds == {"summary"}
        assert len(findings) == 2  # two branches in the fixture
        for f in findings:
            assert f.evidence_ids

    async def test_discovery_finds_cross_category_paths(self, plan):
        cg = _cg_with_evidence(plan)
        findings = await DiscoveryAgent(FakeLLM()).analyze(cg)
        # qc (academic/news) and repo (code) connect via Error Correction
        assert any("qiskit" in f.text or "Quantum" in f.text for f in findings)

    async def test_trend_agent_measures_recent_acceleration(self, plan):
        cg = _cg_with_evidence(plan)
        # add 3 recent evidence items on one entity to cross the threshold
        qc_id = next(eid for eid, e in cg.entities.items()
                     if e.name == "Quantum Computing")
        recent = make_claim("more qc activity", [qc_id],
                            [make_evidence(source="arxiv", days_old=5, url="https://r1"),
                             make_evidence(source="gdelt_news", days_old=8, url="https://r2"),
                             make_evidence(source="hackernews", days_old=12, url="https://r3")])
        cg.add_extraction("News Agent",
                          ExtractionResult(doc_url="https://n", entities=[],
                                           claims=[recent]))
        findings = await TrendAgent(FakeLLM()).analyze(cg)
        assert any("Quantum Computing" in f.text and "Emerging" in f.text
                   for f in findings)

    async def test_question_agent_flags_uncovered_questions(self, plan):
        cg = _cg_with_evidence(plan)
        cg.open_questions.append(
            "What are the cooling requirements for photonic interconnects?")
        await VerificationAgent(FakeLLM()).analyze(cg)
        findings = await QuestionAgent(FakeLLM()).analyze(cg)
        unresolved = [f.text for f in findings if f.text.startswith("Unresolved:")]
        assert any("photonic" in t for t in unresolved)   # uncovered → flagged
        # the fixture's original question IS covered by verified claims
        # (quantum/error/correction all appear) and must NOT be flagged
        assert not any("state of quantum" in t for t in unresolved)


SPEC_SECTIONS = [
    "Executive Summary", "What Changed Recently?", "What Is the Consensus?",
    "What Remains Uncertain?", "What Connections Were Discovered?",
    "Research Map", "Major Entities", "Key Findings", "Evidence Table",
    "Timeline", "Arguments For/Against", "Unknowns", "Future Predictions",
    "Related Discoveries", "Confidence Scores", "Source References",
]


class TestReport:
    async def _build(self, plan, findings=()):
        cg = _cg_with_evidence(plan)
        await VerificationAgent(FakeLLM()).analyze(cg)
        builder = ReportBuilder(FakeLLM(text_response="Executive prose."))
        return cg, await builder.build(
            cg, list(findings), {"docs_extracted": 2},
            [{"source": "arxiv", "category": "academic", "status": "live",
              "detail": "", "reliability_prior": 0.75, "calls": 1, "docs": 2}],
            {"claims_verified": 3, "claims_total": 5}, "datahub off")

    async def test_every_spec_section_present_in_order(self, plan):
        _cg, report = await self._build(plan)
        assert [s.title for s in report.sections] == SPEC_SECTIONS

    async def test_content_counts_match_the_record(self, plan):
        cg, report = await self._build(plan)
        verified = sum(1 for c in cg.claims.values() if c.verified)
        assert report.section("Key Findings").item_count == verified
        distinct_urls = len({ev.url for c in cg.claims.values() for ev in c.evidence})
        assert report.section("Evidence Table").item_count == distinct_urls
        entities_with_claims = len(cg.top_entities(15))
        assert report.section("Major Entities").item_count == entities_with_claims
        # rendered body actually contains the rows it claims to contain
        assert report.section("Major Entities").body_md.count("| ") >= entities_with_claims

    async def test_empty_sections_say_so_instead_of_padding(self, plan):
        _cg, report = await self._build(plan)  # no trend findings passed
        predictions = report.section("Future Predictions")
        assert predictions.item_count == 0
        assert "declining to guess" in predictions.body_md

    async def test_markdown_render_contains_all_sections(self, plan):
        _cg, report = await self._build(plan)
        md = ReportBuilder.to_markdown(report)
        for title in SPEC_SECTIONS:
            assert f"## {title}" in md
