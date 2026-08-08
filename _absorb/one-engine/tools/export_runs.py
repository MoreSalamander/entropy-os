#!/usr/bin/env python3
"""Write one-engine's real runs out as a portable JSON record.

Entropy OS serves this read-only on its hosted face, where none of one-engine's
machinery exists. Run it after a real objective finishes:

    python3 tools/export_runs.py --out ../entropy-os/data/one_engine_runs.json

Exports only what the event log recorded. Stages whose gate verdicts predate
the recorder are marked unrecorded rather than assumed to have passed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from one_engine.config import load_config
from one_engine.export import write_export

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--events", default="",
                    help="event log (default: from config.yaml)")
    ap.add_argument("--out", default=str(REPO_ROOT / "storage_data" / "runs_export.json"))
    args = ap.parse_args()

    events = Path(args.events) if args.events else load_config().events_log_path
    data = write_export(events, Path(args.out))

    t = data["totals"]
    print(f"exported {t['objectives']} objectives "
          f"({t['completed']} completed, {t['failed']} failed) · "
          f"{t['stages']} stages across {len(t['engines'])} engines")
    if t["stages_without_recorded_gates"]:
        print(f"  note: {t['stages_without_recorded_gates']} stage(s) predate "
              f"gate recording and export as unrecorded, not as passing")
    print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
