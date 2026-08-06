"""How each engine LOOKS and where it OPENS — the front door's knowledge.

Extracted from veritas orgs/registry.py in the split: an org's verification
model is engine truth and stays in the registry; its brand accent, live-app
URL, Launchpad name, and public repo are presentation facts that belong to
the layer doing the presenting. `/api/orgs` merges the registry's truth with
this overlay, so the wire payload — and therefore the UI and its tests —
is unchanged by the extraction.

Orgs without an entry render in the neutral proposal slate: a preset isn't a
separate verification model, just a framing on an existing org's gates.
"""

from __future__ import annotations

from typing import Any

DEFAULT_COLOR = "#8b96ad"  # --proposal slate

PRESENTATION: dict[str, dict[str, Any]] = {
    "software": {"color": "#6ee7ff", "era": "inhouse"},
    "web": {"color": "#a78bfa", "era": "inhouse"},
    "research": {"color": "#f472b6", "era": "inhouse"},
    "production": {"color": "#fb923c", "era": "inhouse"},
    "empirical": {"color": "#34d399", "era": "inhouse"},
    "newsroom": {"color": "#8b96ad", "era": "inhouse"},
    "education": {"color": "#8b96ad", "era": "inhouse"},
    "startup": {"color": "#8b96ad", "era": "inhouse"},
    "game": {"color": "#8b96ad", "era": "inhouse"},
    "crypto_hunter": {
        "era": "datahub",
        "color": "#f0a52c",
        "external_url": "http://localhost:8010",
        "launchpad_name": "crypto-hunter",
        "repo_url": "https://github.com/MoreSalamander/crypto-hunter",
        "site_url": "https://moresalamander.github.io/crypto-hunter/",
        "live_url": "https://crypto-hunter-live.fly.dev",
    },
    "collectible_hunter": {
        "era": "datahub",
        "color": "#d4af37",
        "external_url": "http://localhost:8013",
        "launchpad_name": "collectible-hunter",
        "repo_url": "https://github.com/MoreSalamander/collectible-hunter",
        "site_url": "https://moresalamander.github.io/collectible-hunter/",
    },
    "free_money_hunter": {
        "era": "datahub",
        "color": "#4ade80",
        "external_url": "http://localhost:8014",
        "launchpad_name": "free-money-hunter",
        "repo_url": "https://github.com/MoreSalamander/free-money-hunter",
        "site_url": "https://moresalamander.github.io/free-money-hunter/",
    },
    "hackathon_hunter": {
        "era": "datahub",
        "color": "#e85c5c",
        "external_url": "http://localhost:8016",
        "launchpad_name": "hackathon-hunter",
        "repo_url": "https://github.com/MoreSalamander/hackathon-hunter",
        "site_url": "https://moresalamander.github.io/hackathon-hunter/",
    },
}


def presentation_for(org_name: str) -> dict[str, Any]:
    """The overlay row for one org — always complete, so `/api/orgs` can merge
    without per-field existence checks. Unknown orgs (a new engine registered
    in veritas before this file learns about it) get honest neutral defaults
    rather than a KeyError: the engine still shows up, just unbranded."""
    row = PRESENTATION.get(org_name, {})
    return {
        "color": row.get("color", DEFAULT_COLOR),
        "external_url": row.get("external_url"),
        "launchpad_name": row.get("launchpad_name"),
        "repo_url": row.get("repo_url"),
        # The engine's styled public site (GitHub Pages) — where a visitor who
        # can't reach the live localhost app should land. The showcase, not
        # the source tree.
        "site_url": row.get("site_url"),
        # A real hosted instance of the engine itself (read-only mirror on
        # Fly). When present it outranks site_url for remote visitors: the
        # actual running app beats a page about the app.
        "live_url": row.get("live_url"),
        # Which data plane the engine's truth lives on — the visible wing
        # split on the face. New engines are DataHub-native by policy, but
        # an unlisted org defaults to the in-house wing until stated.
        "era": row.get("era", "inhouse"),
    }
