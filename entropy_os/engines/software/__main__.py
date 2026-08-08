"""CLI.

  python -m entropy_os.engines.software build "idea" [--out DIR]
  python -m entropy_os.engines.software impact <project_dir> <component>
  python -m entropy_os.engines.software evolve <project_dir>
  python -m entropy_os.engines.software patterns
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .engine import CodeEngine
from .graphs.context_graph import SoftwareContextGraph
from .impact import analyze_impact, impact_markdown


async def _main() -> int:
    parser = argparse.ArgumentParser(prog="entropy_os.engines.software")
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="idea → researched, generated, verified software")
    b.add_argument("request")
    b.add_argument("--out", type=Path, default=None)

    i = sub.add_parser("impact", help="semantic change-impact analysis")
    i.add_argument("project_dir", type=Path)
    i.add_argument("component")

    e = sub.add_parser("evolve", help="drift/vuln/staleness health check")
    e.add_argument("project_dir", type=Path)

    sub.add_parser("patterns", help="cross-project pattern priors")

    args = parser.parse_args()

    if args.cmd == "impact":
        cg = SoftwareContextGraph.load_sidecar(args.project_dir)
        print(impact_markdown(analyze_impact(cg, args.component)))
        return 0

    engine = CodeEngine()
    try:
        if args.cmd == "build":
            project = await engine.build(args.request, out_dir=args.out)
            print("\n=== generated project ===")
            print(f"id:      {project.project_id}")
            print(f"dir:     {project.out_dir}")
            print(f"files:   {project.files_written}")
            if project.verification:
                for res in project.verification.results:
                    print(f"  {res.check:>12}: {res.status.value}  {res.detail[:70]}")
                for problem in project.verification.known_problems:
                    print(f"  known problem: {problem}")
            print(f"\nrun it:  cd {project.out_dir} && "
                  "pip install -r requirements.txt && uvicorn app.main:app")
        elif args.cmd == "evolve":
            from .evolve import evolve
            findings = await evolve(args.project_dir, engine.llm)
            print(f"\n=== evolution report: {len(findings)} findings ===")
            for f in findings:
                print(f"[{f.severity:>7}] {f.kind:<12} {f.subject}: {f.message[:100]}")
        elif args.cmd == "patterns":
            print(json.dumps(engine.kg.pattern_priors(), indent=2))
    finally:
        await engine.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
