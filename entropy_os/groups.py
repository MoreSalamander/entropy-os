"""The group layers between Entropy OS and the engines — presentation data.

Extracted from veritas orgs/registry.py in the split. A group is data, not an
org: Opportunity [Agency AI] is a real standalone app that arbitrates PRIORITY
across its member engines' already-gated output — it has no verification model
of its own, so it was never an OrgType. The UI renders a group as a wrapper
around its members' cards, with a header that opens the group's own live app.
"""

from __future__ import annotations

from typing import Any

GROUPS: dict[str, dict[str, Any]] = {
    "opportunity": {
        "title": "Opportunity [Agency AI]",
        "description": "Cross-engine arbitration: gathers every member engine's "
        "gate-verified opportunities and allocates the day's mission across them "
        "within one shared time/budget profile. Arbitrates priority, not truth — "
        "every pick already passed its own engine's gate.",
        "members": ["crypto_hunter", "collectible_hunter", "free_money_hunter"],
        "external_url": "http://localhost:8015",
        "launchpad_name": "opportunity-agency-ai",
        "repo_url": "https://github.com/MoreSalamander/opportunity-agency-ai",
        "color": "#e8c468",
    },
}


def validate_groups(registry: dict[str, Any]) -> None:
    """A group member that isn't a registered org would render as an empty card
    and silently break the descent — fail loudly at startup instead. Same
    doctrine as the old import-time guard, new home: this runs against the
    IMPORTED veritas registry when the app is constructed."""
    for gname, group in GROUPS.items():
        for member in group["members"]:
            if member not in registry:
                raise RuntimeError(
                    f"group {gname!r} lists member {member!r}, which is not a registered org"
                )
