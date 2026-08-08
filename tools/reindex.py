#!/usr/bin/env python3
"""Re-index one-engine's DataHub datasets after a search-backend outage.

DataHub keeps two stores: MySQL is the source of truth, the search index is
derived. If the index is down while GMS accepts writes — which it happily
does — the datasets are durable but invisible to search. Everything that
reads DataHub through GraphQL then behaves as though the work never happened,
including the demo's own export tooling. Nothing is lost; it is unfindable,
which is worse than a loud failure because it looks like success.

This reads each dataset back by URN (the MySQL path, which works even with the
index down) and re-ingests it byte-for-byte. The write re-emits the metadata
change log, and the now-healthy index picks it up. No aspect is modified, and
nothing outside one-engine's platforms is touched — deliberately narrower than
DataHub's own RestoreIndices, which would rebuild the whole instance.

    python3 tools/reindex.py [--gms http://localhost:8080] [--dry-run]

URNs come from one-engine's durable event log, so the event log is the
authority on what should exist — which is the same claim the architecture
makes everywhere else.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HEADERS = {"Content-Type": "application/json",
           "X-RestLi-Protocol-Version": "2.0.0"}


def urns_from_event_log(log_path: Path) -> list[str]:
    """Every one-engine-family dataset URN the system says it published."""
    found: set[str] = set()
    if not log_path.exists():
        return []
    with log_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Subjects and payload values carry the URNs the run emitted.
            candidates = [event.get("subject", "")]
            for value in (event.get("payload") or {}).values():
                if isinstance(value, str):
                    candidates.append(value)
            for c in candidates:
                if c.startswith("urn:li:dataset:"):
                    found.add(c)
    return sorted(found)


def fetch(gms: str, urn: str) -> dict | None:
    url = f"{gms}/entities/{urllib.parse.quote(urn, safe='')}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None


def reingest(gms: str, entity: dict, stamp: str) -> tuple[bool, str]:
    """Write the entity back, marked with when it was re-indexed.

    A byte-identical write is a no-op: DataHub suppresses it, emits no
    metadata change log, and the search index never learns anything — which
    is exactly what the first version of this script did, successfully and
    uselessly, for twenty datasets. The write has to actually change
    something, so it records the one true new fact: that this dataset was
    re-indexed, and when. Nothing else is touched.

    GET returns `{"value": {"com.linkedin…DatasetSnapshot": {…}}}`; ingest
    expects that union wrapped one level deeper, as
    `{"entity": {"value": <union>}}`.
    """
    union = entity["value"]
    snapshot = next(iter(union.values()))
    for aspect in snapshot.get("aspects", []):
        props = aspect.get("com.linkedin.dataset.DatasetProperties")
        if props is not None:
            props.setdefault("customProperties", {})["reindexed_at"] = stamp
    body = json.dumps({"entity": {"value": union}}).encode()
    req = urllib.request.Request(f"{gms}/entities?action=ingest",
                                 data=body, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return 200 <= r.status < 300, ""
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read()[:180].decode(errors='replace')}"
    except (urllib.error.URLError, TimeoutError) as e:
        return False, str(e)[:180]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gms", default="http://localhost:8080")
    ap.add_argument("--events", default=str(REPO_ROOT / "storage_data" / "events.jsonl"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    urns = urns_from_event_log(Path(args.events))
    if not urns:
        print(f"no dataset URNs in {args.events}", file=sys.stderr)
        return 1

    print(f"{len(urns)} dataset URNs named by the event log")
    if args.dry_run:
        for u in urns:
            print("  ", u)
        return 0

    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).isoformat()
    touched = missing = failed = 0
    for urn in urns:
        entity = fetch(args.gms, urn)
        if entity is None or not entity.get("value"):
            missing += 1
            print(f"  MISSING  {urn}")
            continue
        ok, why = reingest(args.gms, entity, stamp)
        if ok:
            touched += 1
        else:
            failed += 1
            print(f"  FAILED   {urn}\n           {why}")

    print(f"\nre-ingested {touched} · missing {missing} · failed {failed}")
    print("the search index catches up asynchronously; re-run a search query "
          "in a few seconds to confirm.")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
