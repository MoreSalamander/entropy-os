"""Deterministic source-reliability scoring.

No LLM anywhere in this file on purpose: reliability feeds confidence, and
confidence must be reproducible. Formula:

    reliability = clamp( prior * recency_factor + citation_boost , 0.05 , 0.99 )

  prior           adapter's declared trust level (peer-review > preprint > forum)
  recency_factor  1.0 for fresh material decaying to 0.7 floor over ~5 years —
                  staleness dampens, it never zeroes (old truths stay true)
  citation_boost  log-scaled bump from citations/stars/points when present
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from ..models import RawDoc

_RECENCY_FLOOR = 0.7
_RECENCY_HALFLIFE_DAYS = 3 * 365.0


def _recency_factor(published: datetime | None) -> float:
    if published is None:
        return 0.85  # unknown date: mild penalty, not a death sentence
    age_days = max((datetime.now(UTC) - published).days, 0)
    decay = 0.5 ** (age_days / _RECENCY_HALFLIFE_DAYS)
    return _RECENCY_FLOOR + (1.0 - _RECENCY_FLOOR) * decay


def _citation_boost(doc: RawDoc) -> float:
    count = (doc.extra.get("cited_by", 0) or doc.extra.get("stars", 0)
             or doc.extra.get("points", 0) or doc.extra.get("downloads", 0) or 0)
    if count <= 0:
        return 0.0
    return min(0.15, 0.03 * math.log10(1 + count))  # 10 cites ≈ +0.03, 10k ≈ +0.12


def score_reliability(doc: RawDoc, prior: float) -> float:
    score = prior * _recency_factor(doc.published) + _citation_boost(doc)
    return max(0.05, min(0.99, round(score, 3)))
