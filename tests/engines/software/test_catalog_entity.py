"""The catalog decides its own column names.

Measured before this existed: handed seven real field names, the generator
adopted one. Every fix that keeps the decision with the model is the same
request in a louder voice, so the decision moves to something that cannot
hallucinate.
"""

from __future__ import annotations

from entropy_os.engines.software.catalog_entity import merge, parse
from entropy_os.engines.software.models import EntityField, EntityModel

BRIEF = """outcome-0 [veritas]
    accepted : boolean
    accepted_because : string
    confidence : string
    id : string
opportunity-1 [veritas]
    type : string
"""


def test_fields_are_taken_verbatim():
    [outcome, opportunity] = parse(BRIEF)
    assert [f.name for f in outcome.fields] == [
        "accepted", "accepted_because", "confidence"]
    assert [f.name for f in opportunity.fields] == ["type"]


def test_catalog_types_become_python_types():
    outcome = parse(BRIEF)[0]
    kinds = {f.name: f.type for f in outcome.fields}
    assert kinds["accepted"] == "bool"
    assert kinds["accepted_because"] == "str"


def test_an_unknown_type_degrades_to_str():
    """Safe direction: a string holding a number is inconvenient; the reverse
    breaks at insert time."""
    ent = parse("thing [x]\n    weird : someexotictype\n")[0]
    assert ent.fields[0].type == "str"


def test_boilerplate_columns_are_not_forced_in():
    """Every generated model already has an id. Forcing the catalog's would
    collide with the scaffolding rather than describe the data."""
    outcome = parse(BRIEF)[0]
    assert "id" not in [f.name for f in outcome.fields]


def test_a_proposed_entity_of_the_same_name_is_replaced_not_blended():
    """Keeping the model's invented columns beside the real ones is how a
    schema quietly becomes approximate."""
    catalog = parse(BRIEF)
    proposed = [EntityModel(name="Outcome0",
                            fields=[EntityField(name="invented_column", type="str")])]
    merged = merge(proposed, catalog)
    outcome = next(e for e in merged if e.name == "Outcome0")
    assert "invented_column" not in [f.name for f in outcome.fields]
    assert "accepted" in [f.name for f in outcome.fields]


def test_entities_the_model_invented_for_itself_survive():
    """The catalog says nothing about them, so it gets no vote on them."""
    merged = merge([EntityModel(name="HunterRun",
                                fields=[EntityField(name="run_id", type="str")])],
                   parse(BRIEF))
    assert "HunterRun" in [e.name for e in merged]


def test_no_catalog_leaves_the_architecture_untouched():
    proposed = [EntityModel(name="Thing", fields=[EntityField(name="a", type="str")])]
    assert merge(proposed, parse("")) == proposed


def test_a_dataset_name_becomes_a_pascal_class_name():
    assert parse("hunter-demo-outcome [veritas]\n    x : string\n")[0].name \
        == "HunterDemoOutcome"
