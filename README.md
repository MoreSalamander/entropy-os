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

Increment 1 of the split from veritas: this repo serves the UI; API routes
are porting over group by group while veritas's hub dual-runs. The migration
plan lives with the maintainers; the judge-facing DataHub hackathon demo is
frozen separately at
[entropy-datahub-demo](https://github.com/MoreSalamander/entropy-datahub-demo)
(tag `hackathon-2026`) and does not depend on this repo.

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
