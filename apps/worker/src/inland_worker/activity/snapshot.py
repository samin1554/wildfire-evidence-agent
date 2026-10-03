"""Build an activity snapshot: fetch recent detections + current official perimeters through the data layer,
cluster them, and describe the result honestly (ADR-013)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shapely.geometry import Point
from shapely.prepared import prep

from inland_worker.activity.cluster import cells_by_day, cluster_detections, to_api
from inland_worker.agent.guardrails import region
from inland_worker.data import DataService
from inland_worker.kit.runner import data_mode

AREAS = ("conus_bbox", "alaska_bbox", "hawaii_bbox")  # providers.yaml; together they cover the 50 states
# the three VIIRS satellites (~375 m): more passes per day, fewer gaps; recorded fixture case per satellite
SATELLITES = {"VIIRS_NOAA21_NRT": "success", "VIIRS_NOAA20_NRT": "noaa20", "VIIRS_SNPP_NRT": "snpp"}
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
    for source, case in SATELLITES.items():
        for area in AREAS:
            res = await data.get_evidence(
                "firms",
                bbox=data.registry.area_bbox(area),
                params={"days": window_days, "source": source},
                fixture_case=case,
            )
            if not res.ok:
                notes.append(
                    f"NASA FIRMS {source} was unavailable for {area} ({res.freshness.reason}); "
                    "some detections are missing."
                )
            elif res.freshness.kind == "stale":
                notes.append(f"NASA FIRMS {source} for {area} is the last saved copy (live fetch failed).")
            for d in res.items:
                if (
                    d.id not in seen
                    and d.geometry is not None
                    and inside.contains(Point(d.geometry.coordinates[:2]))
                ):
                    seen.add(d.id)
                    detections.append(d)
            if mode == "fixture":
                break  # one recording per satellite serves every area in fixture mode
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
        "_cells": cells_by_day(detections),  # internal: activity_cells upsert (removed before serving)
    }


INTERNAL_CLUSTER_KEYS = ("cells", "score")


def public(snap: dict[str, Any]) -> dict[str, Any]:
    """The snapshot as served (contracts/openapi.yaml ActivitySnapshot): internal keys removed."""
    return {
        **{k: v for k, v in snap.items() if not k.startswith("_")},
        "clusters": [
            {k: v for k, v in c.items() if k not in INTERNAL_CLUSTER_KEYS} for c in snap["clusters"]
        ],
    }
