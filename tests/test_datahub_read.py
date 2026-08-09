"""Reading the graph before deciding.

The parsing tests matter more than they look: an MCP reply echoes the GraphQL
it ran and its variables before the answer, and all three are valid JSON. A
parser that takes the first one returns the VARIABLES — an object with none
of the fields asked for, which is indistinguishable from a graph that holds
nothing. That is the worst possible failure for this module, because the
whole point is telling "I asked and found nothing" apart from "I never asked".
"""

from __future__ import annotations

from entropy_os.datahub_read import Dataset, Field_, GraphContext, _loads


def test_the_answer_is_parsed_not_the_question():
    reply = (
        "query search(\n  $query: String!\n) {\n  searchResults { urn }\n}\n\n"
        'Variables: {"query": "code-engine", "count": 4}\n'
        '{"searchResults": [{"entity": {"urn": "urn:li:dataset:(x,proj_1,PROD)"}}]}'
    )
    got = _loads(reply)
    assert "searchResults" in got, "took the variables instead of the answer"
    assert got["searchResults"][0]["entity"]["urn"].endswith("proj_1,PROD)")


def test_unparseable_text_yields_an_empty_object_not_a_crash():
    assert _loads("no json here at all") == {}


def test_consulted_and_empty_is_not_the_same_as_unreachable():
    """The distinction the whole module exists to preserve. A generator that
    conflates these will happily invent a schema and call it grounded."""
    found_nothing = GraphContext(query="q")
    never_asked = GraphContext(query="q", reason="ConnectError: refused")

    assert found_nothing.consulted is True
    assert never_asked.consulted is False
    assert "holds nothing related" in found_nothing.brief()
    assert "was not consulted" in never_asked.brief()
    assert "refused" in never_asked.brief()


def test_the_brief_carries_real_field_paths_and_types():
    ctx = GraphContext(query="hunter outcome")
    ctx.datasets = [Dataset(
        urn="urn:li:dataset:(urn:li:dataPlatform:veritas,outcome-0,PROD)",
        name="outcome-0", platform="veritas",
        fields=[Field_(path="accepted", type="boolean"),
                Field_(path="accepted_because", type="string")])]
    brief = ctx.brief()
    assert "outcome-0 [veritas]" in brief
    assert "accepted : boolean" in brief
    assert "accepted_because : string" in brief


def test_upstreams_are_named_so_the_generator_sees_provenance():
    urn = "urn:li:dataset:(urn:li:dataPlatform:veritas,outcome-0,PROD)"
    ctx = GraphContext(query="q")
    ctx.datasets = [Dataset(urn=urn, name="outcome-0", platform="veritas")]
    ctx.upstreams[urn] = ["urn:li:dataset:(urn:li:dataPlatform:veritas,run-7,PROD)"]
    assert "fed by run-7" in ctx.brief()
