"""CLI:  python -m entropy_os.engines.web "Create a website for an AI healthcare startup"
Options: --out DIR (default storage_data/sites/<project>), --build (run the
npm/next build gate), --brave-key / --serper-key (widen competitor discovery).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from .engine import DesignEngine


async def _main() -> int:
    parser = argparse.ArgumentParser(prog="entropy_os.engines.web")
    parser.add_argument("request", help="what website to create")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--build", action="store_true",
                        help="run the npm install + next build gate")
    parser.add_argument("--brave-key", default=os.environ.get("BRAVE_SEARCH_API_KEY", ""))
    parser.add_argument("--serper-key", default=os.environ.get("SERPER_API_KEY", ""))
    args = parser.parse_args()

    engine = DesignEngine(brave_key=args.brave_key, serper_key=args.serper_key)
    try:
        site = await engine.generate(args.request, out_dir=args.out,
                                     build_gate=args.build)
    finally:
        await engine.aclose()

    print("\n=== generated site ===")
    print(f"project: {site.project_id}")
    print(f"dir:     {site.out_dir}")
    print(f"files:   {site.files_written}")
    if site.review:
        print("scores:  " + ", ".join(f"{k}={v}" for k, v in site.review.scores.items()))
        print(f"build:   {site.review.build_ok}")
        for f in site.review.findings:
            print(f"  [{f.severity.value:>7}] {f.agent}: {f.message[:90]}")
    print(f"\nrun it:  cd {site.out_dir} && npm install && npm run dev")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
