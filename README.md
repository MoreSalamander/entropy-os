# Entropy OS

**The front door.** Every dashboard and interview lives here — "what do you
want to build," Mission Control, the layer descent — while the engines live in
[Veritas](https://github.com/MoreSalamander/veritas), imported as a library.

The relationship is the my-AI-script pattern: the front door knows only the
*shape* each engine requires (engine-owned validators imported so drift breaks
loudly at parse time) and never re-implements engine logic. The layers:

**Entropy OS → Opportunity [Agency AI] → Veritas Dynamics (the engine room) →
the agent engines.**

## Status

**The split is complete.** The full front-door surface — Mission Control,
the "what do you want to build" router, runs/memory/collector views, the
Knowledge Graph, the five interactive sessions, the wedge storefront
(`ENTROPY_PUBLIC=1` for hosted mode), the Vending Machine — serves from this
repo at exact route parity with the old in-veritas hub (75 = 75, verified),
against the same data root. Veritas has no web surface anymore.

The judge-facing DataHub hackathon demo is frozen separately at
[entropy-datahub-demo](https://github.com/MoreSalamander/entropy-datahub-demo)
(tag `hackathon-2026`) and does not depend on this repo.

Post-hackathon queue: decompose the monolithic `create_app` into routers +
an AppState, the EngineShape registry for the interview flows, and the
four-layer descent nav.

## Develop

```bash
./dev.sh
.venv/bin/uvicorn entropy_os.app:create_app --factory --port 8100
.venv/bin/pytest -q
```

Data root: `ENTROPY_DATA` env, defaulting to the sibling veritas checkout's
`hub_data/` — the split moves no data files.

---

*Entropy OS, powered by Veritas Dynamics AI — a
[MoreSalamander StudioLabs](https://moresalamander.github.io) Production.*
