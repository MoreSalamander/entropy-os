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
an AppState and the EngineShape registry for the interview flows.

## Run it on your Mac

Zero-install path: the hosted face at
**[entropy-os-live.fly.dev](https://entropy-os-live.fly.dev)** — nothing to
set up, the Vending Machine demo included.

To run your own:

**Prerequisites**

- macOS with **Python 3.11+** (3.12 recommended) and git.
- A model brain, one of:
  - **Claude API** (simplest): an Anthropic API key.
  - **Local** (free, heavier): [Ollama](https://ollama.com) with the default
    model pulled — `ollama pull gemma4:12b`.
- Optional: **Docker Desktop** — the Vending Machine's code slot runs
  untrusted code only inside throwaway containers; without Docker running it
  refuses honestly instead of running unisolated.

**Setup**

```bash
git clone https://github.com/MoreSalamander/entropy-os
cd entropy-os
./dev.sh
```

`dev.sh` creates `.venv`, installs the veritas engine (editable from a
sibling `../veritas` checkout when present, else the declared git dependency),
this app with dev extras, and the Chromium build the web slot's render gate
drives.

**Pick the brain**

```bash
# Claude API:
export ANTHROPIC_API_KEY=sk-ant-...   # your key
export VERITAS_MODEL=sonnet
# — or local: have Ollama running with gemma4:12b pulled (the default,
#   no env vars needed).
```

**Run**

```bash
.venv/bin/uvicorn entropy_os.app:app --port 8101
```

Open **http://localhost:8101** — the face; the Vending Machine is at
`/try`. Tests: `.venv/bin/pytest -q` (158). Pre-deploy boot check:
`./dev.sh smoke`.

Data root: `ENTROPY_DATA` env; the default is the sibling veritas checkout's
`hub_data/` (the split moved no data files) — with no sibling checkout, set
`ENTROPY_DATA` to any directory you like and it starts empty.

---

*Entropy OS, powered by Veritas Dynamics AI — a
[MoreSalamander StudioLabs](https://moresalamander.github.io) Production.*
