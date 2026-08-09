"""CLI entry point.

    python -m entropy_os.engines.research "topic to research" [--max-per-source N] [--variants N]

Runs the full pipeline in the foreground with live progress lines, writes
the markdown report to storage_data/reports/, prints its path and the
section content-counts (the fidelity check, visible every run).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .config import load_config
from .engine import Engine
from .models import ProgressEvent


async def _main() -> int:
    parser = argparse.ArgumentParser(prog="entropy_os.engines.research")
    parser.add_argument("topic", help="research topic / question / domain")
    parser.add_argument("--max-per-source", type=int, default=None,
                        help="override orchestrator.max_results_per_source")
    parser.add_argument("--variants", type=int, default=None,
                        help="override orchestrator.query_variants")
    args = parser.parse_args()

    cfg = load_config()
    if args.max_per_source is not None:
        cfg.orchestrator.max_results_per_source = args.max_per_source
    if args.variants is not None:
        cfg.orchestrator.query_variants = args.variants

    engine = Engine(cfg)

    async def progress(ev: ProgressEvent) -> None:
        extras = " ".join(f"{k}={v}" for k, v in ev.data.items())
        print(f"[{ev.phase.value:>13}] {ev.message} {extras}".rstrip(), flush=True)

    try:
        report, _cg = await engine.research(args.topic, progress)
    finally:
        await engine.aclose()

    out_dir = cfg.resolve_path(cfg.report.output_dir)
    print("\n=== report sections (item counts — content fidelity) ===")
    for s in report.sections:
        print(f"  {s.item_count:>4}  {s.title}")
    print(f"\nreport: {out_dir / (report.session_id + '.md')}")
    print(f"session file: {report.stats.get('session_file')}")
    print(f"datahub: {report.stats.get('datahub')}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
