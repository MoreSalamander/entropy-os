"""Visitor counting for the public faces.

The same shape my-AI-stro uses, because it's the right granularity for a
demo people are sent to: every page load POSTs once, deduped by a
per-browser UUID the page generates and keeps in localStorage. A friend who
refreshes five times is one unique visitor with five loads. A curl probe
with no id bumps the load count but never pollutes the unique count.

Storage is one JSON file in the app's data directory (the persistent volume
on the hosted box), written with a temp-file-and-rename so a crash mid-write
can't corrupt the log. A single process serves the site, so one in-process
lock is the whole concurrency story.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


class VisitLog:
    """Total page loads + unique browsers, per page and overall."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def _empty(self) -> dict:
        return {"total": 0, "uniques": {}, "pages": {}}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return self._empty()
        if not isinstance(data, dict) or "uniques" not in data:
            return self._empty()
        data.setdefault("pages", {})
        return data

    def _atomic_save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".visits-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            raise

    def record(self, client_id: str | None, page: str | None = None) -> dict:
        """Count one page load; dedupe uniques by the browser's id."""
        with self._lock:
            data = self._load()
            data["total"] = int(data.get("total", 0)) + 1
            page_key = (page or "").strip() or "/"
            data["pages"][page_key] = int(data["pages"].get(page_key, 0)) + 1
            cid = (client_id or "").strip()
            if cid:
                now = datetime.now(timezone.utc).isoformat()
                entry = data["uniques"].get(cid)
                if entry is None:
                    data["uniques"][cid] = {"first_seen": now, "last_seen": now, "count": 1}
                else:
                    entry["last_seen"] = now
                    entry["count"] = int(entry.get("count", 0)) + 1
            self._atomic_save(data)
            return self._stats(data)

    def stats(self) -> dict:
        with self._lock:
            return self._stats(self._load())

    def _stats(self, data: dict) -> dict:
        return {"total": int(data.get("total", 0)), "unique": len(data.get("uniques", {}))}
