"""Build an activity snapshot: fetch recent detections + current official perimeters through the data layer,
cluster them, and describe the result honestly (ADR-013)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shapely.geometry import Point
from shapely.prepared import prep

from inland_worker.activity.cluster import cluster_detections, to_api
from inland_worker.agent.guardrails import region
from inland_worker.data import DataService
from inland_worker.kit.runner import data_mode

AREAS = ("conus_bbox", "alaska_bbox", "hawaii_bbox")  # providers.yaml; together they cover the 50 states
WINDOW_DAYS = 2
LIMITATIONS = [
    "Satellite heat detections are not confirmed fires; they can be industrial heat, flares or prescribed burns.",
    "Detections are ~375 m pixels and arrive a few hours after the satellite passes; clouds and smoke hide fires.",
    "No detection here does not mean nothing is burning.",
    "A cluster is labelled officially reported only when a current official perimeter (NIFC WFIGS) overlaps it.",
]


async def build_snapshot(
    data: DataService, *, window_days: int = WINDOW_DAYS, top: int = 50
) -> dict[str, Any]:
    mode = data.mode or data_mode()
    us = region()
    inside = prep(us.buffer(0.01))
    detections, notes = [], []
    seen: set[str] = set()
    for area in AREAS:
        bbox = data.registry.area_bbox(area)
        res = await data.get_evidence("firms", bbox=bbox, params={"days": window_days})
        if not res.ok:
            notes.append(
                f"NASA FIRMS was unavailable for {area} ({res.freshness.reason}); clusters there are missing."
            )
        elif res.freshness.kind == "stale":
            notes.append(f"NASA FIRMS for {area} is the last saved copy (live fetch failed).")
        for d in res.items:
            if (
                d.id not in seen
                and d.geometry is not None
                and inside.contains(Point(d.geometry.coordinates[:2]))
            ):
                seen.add(d.id)
                detections.append(d)
        if mode == "fixture":
            break  # one recording serves every area in fixture mode; don't count it three times
    # national current perimeters: small pages + ~100 m generalization keep each response well under the size cap
    perims = await data.get_evidence(
        "wfigs_current",
        bbox=data.registry.area_bbox("conus_bbox"),
        params={"page_size": 250, "max_offset": 0.001},
    )
    if not perims.ok:
        notes.append(
            "Current official perimeters (NIFC WFIGS) were unavailable, so no cluster is marked official."
        )
    clusters = cluster_detections(detections, perims.items, region=us, top=top)
    sources = [
        {"source": "NASA FIRMS", "source_url": data.registry.get("firms").source_url},
        {
            "source": data.registry.get("wfigs_current").display_name,
            "source_url": data.registry.get("wfigs_current").source_url,
        },
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "data_mode": mode,
        "window_days": window_days,
        "detections_considered": len(detections),
        "sources": sources,
        "limitations": [*LIMITATIONS, *notes],
        "clusters": [to_api(c) for c in clusters],
    }
