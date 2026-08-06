"""Stock the Vending Machine's premade shelf on a fresh data volume.

The /try shelf and the face's vending racks read real org memory
(`org_memory("tutorials")`, `org_memory("academy")`) — on the operator's
machine that memory holds everything the machine has ever dispensed. A fresh
hosted volume holds nothing, which would leave the shelf honestly, uselessly
empty. This script carries the curated stock across: the seed records under
deploy/fly/seed/memory/ are verbatim copies of gate-cleared records from the
operator's store, committed to the repo and baked into the image.

Idempotent by record id: a record already present in the destination store is
never touched, so reboots are no-ops and nothing a live box has accumulated is
ever overwritten. The read side is always the filesystem store (the seeds are
committed .md files); the write side is `default_memory_store`, which follows
VERITAS_MEMORY — SQLite on the hosted box, filesystem elsewhere.

Run: python scripts/seed_shelf.py   (start.sh runs it before the app boots)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from engine.memory import MemoryStore, default_memory_store

SEED_ROOT = Path(__file__).resolve().parent.parent / "deploy" / "fly" / "seed" / "memory"


def seed(data_root: Path) -> dict[str, int]:
    """Copy every seed record its destination org store doesn't already hold.

    Returns {org_name: records_added} for the boot log.
    """
    added: dict[str, int] = {}
    for org_dir in sorted(SEED_ROOT.iterdir()):
        if not org_dir.is_dir():
            continue
        src = MemoryStore(org_dir)
        dst = default_memory_store(data_root / "memory" / org_dir.name)
        have = {rec.id for rec in dst.load_all()}
        count = 0
        for rec in src.load_all():
            if rec.id in have:
                continue
            dst.persist(rec)
            count += 1
        added[org_dir.name] = count
    return added


def main() -> int:
    if not SEED_ROOT.is_dir():
        print(f"seed_shelf: no seed directory at {SEED_ROOT}; nothing to do")
        return 0
    data_root = Path(
        os.environ.get("ENTROPY_DATA") or os.environ.get("VERITAS_DATA") or "hub_data"
    )
    added = seed(data_root)
    total = sum(added.values())
    detail = ", ".join(f"{org}: +{n}" for org, n in sorted(added.items()))
    print(f"seed_shelf: {total} record(s) added into {data_root} ({detail})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
