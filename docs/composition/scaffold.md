# The deterministic scaffold

**The engines propose; the scaffold decides.**

That sentence is Veritas's thesis, and this is the same thesis one level up.
Inside an engine, an LLM proposes an artifact and a gate decides whether it is
acceptable. At the composition boundary, whole *engines* propose stage results
and a gate decides whether the objective may continue.

## Why it had to exist

The first flagship run made the gap concrete. `code-engine` returned:

```
verification_passed: False
known_problems: ["[pytest] tests/test_quiz_service.py: AttributeError… (repair declined)"]
```

…and the pipeline went straight on to generate a public website for that
software. The engine had been *honest*. The composition had simply never
*decided* whether honesty about a red test suite was grounds to stop.

Federation gave the system memory. Temporal gave it durability. Neither gave
it judgment. This is the layer that does.

## What a composition gate is

A pure function from a stage's contract result to a verdict:

```python
class EvidenceFloor(CompositionGate):
    name = "evidence_floor"
    determinism = Determinism.HARD

    def check(self, result: ExecuteResult):
        entities = int(result.outputs.get("entities", 0) or 0)
        claims = int(result.outputs.get("claims", 0) or 0)
        ok = entities >= 1 and claims >= 1
        return ok, f"{entities} entities, {claims} claims (floor: 1/1)", \
               {"entities": entities, "claims": claims}
```

Two properties matter, and both come from *where* gates sit rather than from
how clever they are.

**They read only the contract.** A gate touches `ExecuteResult.outputs`,
`.events`, and `.provenance` — never an engine's internals. That is what keeps
the scaffold composable: an engine that joins later is judged by the same
gates without either side knowing about the other. The test for this is blunt
— every declared gate must reach a verdict from a bare `ExecuteResult` with no
engine object in reach.

**They are almost entirely HARD.** The composition boundary is where
deterministic judgment is *most* available, because the engines already did
the hard part: research ran an evidence gate, code-engine ran ruff and pytest,
design-engine ran its review agents. By the time a result arrives here, the
opinions have already been converted into recorded facts — booleans, counts,
scores. A gate here reads facts; it does not form opinions. No gate in either
pipeline declares `SOFT`, and a test enforces that.

## Determinism, declared honestly

Vocabulary converges deliberately with Veritas (`engine/artifact.py`):

| | Meaning | Consequence when it fails |
| --- | --- | --- |
| `HARD` | a recorded fact — a test result, a count, a score | **block** — stop the run |
| `SOFT` | an opinion (a judge model), never dressed as proof | **proceed** — recorded only |
| `HUMAN` | a person decided | **hold** — wait for a signal |

The gate never chooses its own consequence. It reports a verdict, and the
scaffold maps `(determinism, passed)` onto an action. A gate that could pick
its own consequence would be setting policy, and policy belongs in one place.

The `SOFT → proceed` rule is the load-bearing one: it is what stops an opinion
from quietly becoming a hard gate.

## The human tier, and why verification uses it

`VerificationPassed` is `HUMAN` on purpose, and the split is the point:

- Whether the suite is red is a **hard, deterministic fact**. The gate settles
  that without argument.
- Whether the run may continue *anyway* — because the failure is understood,
  or the site is wanted regardless — is a **judgment call**, and a person
  should make it.

So the gate establishes the fact and hands the consequence to a human. Under
Temporal that is a real pause: the workflow blocks on
`workflow.wait_condition` and resumes on an `approve` / `reject` signal, with
`progress()` reporting which gate is holding.

## Where the decision happens

Inside the **workflow**, not inside an activity. Gates are pure, so they can
run in the deterministic sandbox — and that placement is deliberate: the
decision is the orchestrator's, made from recorded facts, and it lands in
durable workflow history. An activity then *records* the verdict; it never
makes it.

```
stage activity  →  result           (the engine proposes)
workflow        →  stage.judge()    (the scaffold decides)
judgment activity → event + DataHub (the decision is published)
```

## Both orchestrators enforce it

The inline fallback runs the same gates. Inline execution is a degraded
*orchestrator*, never a degraded *scaffold* — a run that loses Temporal must
not thereby lose its decisions.

The one honest difference: inline has no human to ask, so a `hold` cannot be
waited on. It stops, and says exactly that:

```
held by gate(s) verification_passed: verification FAILED: ['pytest: …']
(needs a human decision; the inline orchestrator has no one to ask)
```

## Decisions are published, not logged

A verdict nobody can find later is a log line, not governance. Every judgment
becomes:

- a **`GatesEvaluated` semantic event** carrying each gate's determinism,
  verdict, evidence, and the facts it was decided on; and
- a **DataHub dataset** — `judgment.<objective>.<seq>-<engine>` — whose
  upstream is the stage it judged, so the decision sits downstream of the work
  in the lineage graph with each gate as a queryable property.

"Why was this allowed to continue?" is answerable from the catalog.

## What building this cost, in bugs

Three defects surfaced while wiring the scaffold, and all three were caught by
Temporal's sandbox or by a test rather than by review. Two were the same
mistake wearing different clothes: **convenience defaults constructed inside
the deterministic sandbox.**

**A clock.** `GateVerdict.checked_at` defaulted to `now_iso()`. Gates run in
the workflow, so that was wall-clock access — refused. The fix is also the
better design: a gate is a pure function of facts and has no business reading
a clock, so the timestamp belongs to whatever *records* the verdict.

**A uuid.** `skipped_result()` leaned on `ExecutionRef`'s default factory,
which generates a `uuid4`. Skips are decided in the workflow too. The ref is
now derived — `skipped.2.university` — which is deterministic *and* more
honest than a random id for a stage that never executed. This one had never
fired: no Temporal test exercised a skip, and the one live evolution run had
every stage affected.

**A layering mistake.** `ProducedSomething` reached for `identifying()` from
the federation package, whose `__init__` imports httpx — dragging urllib into
the sandbox. The convention moved to the contract, which is a dependency-free
leaf, and `federation/__init__` now explicitly declines to re-export it. A
test asserts the workflow's import graph stays free of I/O modules, run in a
subprocess so other tests' imports cannot mask the answer.

A fourth was mine, not the architecture's: the workflow resolves pipelines
from the module-level registry while activities may be handed their own, and a
test pipeline made them disagree — surfacing as `KeyError: no stage 3` after
real work had already run. `ObjectiveActivities` now refuses to construct when
its registry disagrees with the workflow's on stage identities.

Chasing that one surfaced a constraint worth stating plainly, because it is
not obvious and it bites silently: **the workflow sandbox re-imports its
modules, so a pipeline registered at runtime is invisible inside a workflow.**
Pipelines must exist at import time. A test fixture that mutated the registry
looked correct, passed its own assertions in the host process, and hung the
workflow forever — the sandbox simply never saw the pipeline. The Temporal
tests now exercise real registered pipelines instead.

## What this does and does not claim

one-engine proves **composability**. Veritas proves **trust**. This layer is
where the second lands in the first: the composite still adds no domain
judgment of its own — it adds the decision about whether the composition may
proceed, from facts its members recorded.

The gates a pipeline declares are part of that pipeline's definition, which
means a second-level system inherits its member's gates by delegating to it,
and declares its own for whatever it composes on top.
