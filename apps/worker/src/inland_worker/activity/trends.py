"""Trends from activity history (ADR-013 amendment). Pure functions: the runner supplies the history.

- trend: `new` when none of the cluster's cells had detections before the last 24 h; otherwise its detections now
  vs. the same cells in the snapshot from ~24 h ago: `growing` (≥ +25 %), `shrinking` (≤ -25 %) or `stable`.
  No snapshot from ~24 h ago yet → `trend: null` (history still building).
- persistent heat source: heat in the same cells on ≥ 5 distinct days of the last 14, and no official perimeter.
  Gas flares, refineries and other industrial sites look like this; a long-burning wildfire with an official
  perimeter never does here. Persistent clusters rank lower (score x 0.3), they are never removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

GROW, SHRINK = 1.25, 0.75
PERSISTENT_DAYS = 5
PERSISTENT_WINDOW_DAYS = 14
DEMOTE = 0.3


@dataclass
class History:
    seen_before_24h: bool | None  # any cell seen before the last 24 h (None: no history recorded at all yet)
    detections_24h_ago: int | None  # detections in the same cells ~24 h ago (None: no snapshot that old yet)
    days_seen: int  # max distinct days with detections among the cluster's cells, last 14 days


def trend(detections: int, h: History) -> dict[str, Any] | None:
    if h.seen_before_24h is None:
        return None  # first refresh ever: nothing can be called new yet
    if not h.seen_before_24h:
        return {"status": "new", "detections_24h_ago": h.detections_24h_ago or 0}
    if h.detections_24h_ago is None:
        return None
    prev = h.detections_24h_ago
    if prev == 0:
        status = "growing"  # seen on earlier days, quiet 24 h ago, active now
    elif detections >= prev * GROW:
        status = "growing"
    elif detections <= prev * SHRINK:
        status = "shrinking"
    else:
        status = "stable"
    return {"status": status, "detections_24h_ago": prev}


def is_persistent(h: History, official: bool) -> bool:
    return not official and h.days_seen >= PERSISTENT_DAYS


def apply(clusters: list[dict[str, Any]], history: dict[str, History]) -> list[dict[str, Any]]:
    """Add trend / persistence to API-shaped clusters (with internal `score`) and re-rank."""
    for c in clusters:
        h = history.get(c["id"], History(False, None, 0))
        c["trend"] = trend(c["detections"], h)
        c["days_seen"] = h.days_seen
        c["persistent_heat_source"] = is_persistent(h, c["official"] is not None)
        if c["persistent_heat_source"]:
            c["score"] = round(c["score"] * DEMOTE, 3)
    clusters.sort(key=lambda c: (-c["score"], -_ts(c["last_seen"]), c["id"]))
    for i, c in enumerate(clusters, start=1):
        c["rank"] = i
    return clusters


def _ts(iso: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(iso).timestamp()
