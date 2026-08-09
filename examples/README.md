# Sample outputs — two runs of the same request

Both directories are real runs of the metadata-aware agent against a live
DataHub instance, kept exactly as produced. Nothing was cleaned up for
display, and the first one **failed** — it is here because it is the more
useful of the two.

The request, identical in both:

> a service that records and queries gate outcomes for hunter runs

## What the agent does

1. **Reads DataHub** through DataHub's own MCP server (`mcp-server-datahub`):
   which datasets exist, what fields they actually carry, what feeds them.
2. **Generates** a FastAPI service against those fields.
3. **Gates** the result — the engine's five hard checks (ruff, pytest,
   security, performance, review), plus one more the agent runs on its own
   claim: *did the generated code actually use the schema it was handed?*
4. **Writes back** to DataHub: the project as a dataset, an `UpstreamLineage`
   edge to every dataset that informed it, and each verdict as an assertion
   carrying whether a test produced it or a judge model did.

## The two runs

| | [`01-refused-14pct`](01-refused-14pct/) | [`02-accepted-100pct`](02-accepted-100pct/) |
|---|---|---|
| schema adoption | **1 of 7 (14%)** | **7 of 7 (100%)** |
| engine gates | 5/5 passed | 5/5 passed |
| `agent.schema_fidelity` | **FAILED** | passed |
| outcome | **NOT ACCEPTED** | accepted |
| DataHub URN | `…entropy-agent,generated.proj_54a90c8210,PROD` | `…entropy-agent,generated.proj_fbfdd60377,PROD` |

### Why the first one is here

Every engine gate passed. The linter was clean, the generated test suite ran
green, three static analyses found nothing. By every conventional measure it
was a good build.

And it had ignored the catalog. DataHub said the record contains `accepted`,
`accepted_because`, `confidence`, `created_by`, `retrieved_context`, `type`,
`model_invoked`; the generated model wrote `hunter_run_id`, `gate_outcome`,
`opportunity_type`. One name of seven survived.

That is the failure this project exists to catch: not code that breaks, but
code that passes everything while quietly not being what it claimed. The
agent's own gate refused its own build, so the run is `NOT ACCEPTED` — and
the refusal was published to DataHub alongside the passes.

### What changed between them

Nothing about the prompt. Asking a model to honour field names is a request,
and the measurement is what happened to the request:

```
  0%   the schema reached the intent phase and stopped there
 14%   the schema was added to the architecture prompt
100%   the scaffold parses the catalog and merges the entity itself
```

The model still designs the service — components, endpoints, relationships.
It no longer gets to rename a column that already exists. See
[`entropy_os/engines/software/catalog_entity.py`](../entropy_os/engines/software/catalog_entity.py).

## What is in each directory

- `agent-run.json` — the run as the agent recorded it: what the catalog
  returned, what the generator declared, every verdict with its determinism,
  and the DataHub URN it published to.
- `generated-project/` — the generated FastAPI service, unedited. Caches and
  `__pycache__` removed; nothing else touched.

The clearest single file to read is
[`02-accepted-100pct/generated-project/app/models.py`](02-accepted-100pct/generated-project/app/models.py),
next to the same file in the refused run. One carries DataHub's column names;
the other carries invented ones.

## Reproducing

Requires a DataHub instance (`datahub docker quickstart`) and the engines
running (`./scripts/up.sh`):

```bash
pip install -e ".[datahub]"
python -c "
import asyncio
from entropy_os.datahub_agent import run
r = asyncio.run(run('a service that records and queries gate outcomes for hunter runs'))
print(r.summary())
print(r.published)
"
```

The field names you get depend on what your own catalog holds — which is the
point. An empty catalog produces an honestly ungrounded build that says so,
rather than a confident one that pretends.
