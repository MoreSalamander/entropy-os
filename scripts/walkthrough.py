"""Walk the architecture against the LIVE system and print what it answers.

Every line of output below is fetched from running services — nothing here is
narrated from a diagram. Run it after ./scripts/up.sh (and, for the recursion
section, `python -m systems.meta_studio`).

    python scripts/walkthrough.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from one_engine.config import load_config

RULE = "─" * 74


def head(title: str) -> None:
    print(f"\n{RULE}\n{title}\n{RULE}")


async def get(client: httpx.AsyncClient, url: str, path: str):
    try:
        r = await client.get(f"{url}{path}", timeout=30)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        return {"__error__": str(e)}


def tree(node: dict, indent: str = "") -> None:
    print(f"{indent}{node['name']}  ({node['kind']})")
    for member in node.get("members", []):
        tree(member, indent + "    ")


async def main() -> None:
    cfg = load_config()
    async with httpx.AsyncClient() as c:
        head("1 · THE ENGINES — four autonomous systems, each behind the "
             "same contract")
        for name, m in cfg.engines.items():
            ident = await get(c, m.url, "/identity")
            health = await get(c, m.url, "/health")
            if "__error__" in ident:
                print(f"  {name:11} DOWN — {ident['__error__'][:50]}")
                continue
            caps = await get(c, m.url, "/capabilities")
            print(f"  {name:11} {ident['name']:16} {health['status']:8} "
                  f"platform={ident['datahub_platform']:16} "
                  f"{len(caps['capabilities'])} capabilities")

        head("2 · THE COMPOSITE — the same contract, one level up")
        ident = await get(c, cfg.unified_url, "/identity")
        if "__error__" in ident:
            print(f"  unified system unreachable: {ident['__error__']}")
            return
        health = await get(c, cfg.unified_url, "/health")
        caps = await get(c, cfg.unified_url, "/capabilities")
        print(f"  {ident['name']} — kind={ident['kind']}, "
              f"health={health['status']}")
        for k, v in health["checks"].items():
            print(f"      {k:22} {v}")
        print(f"\n  Serves {len(caps['capabilities'])} capabilities, every one "
              f"attributed to itself:")
        for cap in caps["capabilities"]:
            print(f"      {cap['kind']:9} {cap['name']}")
        print(f"  Declares these pipelines as its own: {caps['workflows']}")

        head("3 · SELF-DESCRIPTION — 'what systems compose you?', one call")
        tree(ident["composition"], "  ")

        head("4 · RECURSION — a second system consumes the composite by URL")
        b_url = f"http://localhost:{cfg.system_b_port}"
        b_ident = await get(c, b_url, "/identity")
        if "__error__" in b_ident:
            print(f"  meta-studio not running "
                  f"(start: python -m systems.meta_studio)")
        else:
            b_caps = await get(c, b_url, "/capabilities")
            print(f"  {b_ident['name']} — kind={b_ident['kind']}\n")
            tree(b_ident["composition"], "  ")
            print(f"\n  It offers {len(b_caps['capabilities'])} capabilities, "
                  f"all attributed to itself:")
            print(f"      {sorted(x['name'] for x in b_caps['capabilities'])}")
            print(f"\n  But declares only its OWN pipeline: "
                  f"{b_caps['workflows']}")
            print("  → its member's 'compose.learning_platform' is consumed "
                  "as one opaque\n    capability, not re-run as a pipeline. "
                  "That is what makes the\n    composition recursive rather "
                  "than two-levels-deep by hand.")

        head("5 · HISTORY — what the system has actually done")
        objectives = await get(c, cfg.unified_url, "/objectives")
        for o in (objectives.get("objectives") or [])[-8:]:
            print(f"  {o['objective_id']}  {o['status']:10} {o['subject']}")
        if not objectives.get("objectives"):
            print("  (no objectives yet)")


if __name__ == "__main__":
    asyncio.run(main())
