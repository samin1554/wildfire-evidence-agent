"""Group recent satellite heat detections into clusters and rank them (ADR-013). Deterministic: no model involved.

    detections ──snap to a ~5 km grid──▶ cells ──8-way union-find──▶ clusters ──match──▶ official perimeters
                                                                           └──▶ rank, suggested analysis area

A cluster is a place worth a look, not a fire: it is labelled `unverified_detection` unless an official current
perimeter overlaps it (`officially_reported`), and a prescribed burn is called a prescribed burn.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pyproj import Geod, Transformer
from shapely import affinity
from shapely.geometry import MultiPoint, Point, box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform
from shapely.ops import unary_union

from inland_worker.activity.places import place_for
from inland_worker.contracts.models import Evidence
from inland_worker.kit.imagery import utm_crs_for

CELL_DEG = 0.05  # ~5 km: detections in touching cells belong to one cluster
BUFFER_DEG = 0.03  # ~3 km around the cluster for the suggested analysis area
MAX_AREA_KM2 = 5_000  # same per-job limit as the API (agent/guardrails.py)
_GEOD = Geod(ellps="WGS84")


@dataclass
class Cluster:
    id: str
    detections: list[Evidence]
    footprint: BaseGeometry
    centroid: Point
    suggested_area: BaseGeometry
    high_confidence: int
    max_frp: float
    total_frp: float
    first_seen: datetime
    last_seen: datetime
    satellites: list[str]
    official: dict[str, Any] | None = None
    nearest_official: dict[str, Any] | None = None
    place: dict[str, str] | None = None
    cells: list[tuple[int, int]] = field(default_factory=list)
    rank: int = 0
    score: float = 0.0
    evidence_ids: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return "officially_reported" if self.official else "unverified_detection"


def _cell(ev: Evidence) -> tuple[int, int]:
    lon, lat = ev.geometry.coordinates[:2]  # type: ignore[union-attr]
    return math.floor(lon / CELL_DEG), math.floor(lat / CELL_DEG)


def _groups(cells: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    parent = {c: c for c in cells}

    def find(c):
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c

    for x, y in cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (x + dx, y + dy)
                if n in parent:
                    parent[find(n)] = find((x, y))
    groups: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for c in cells:
        groups.setdefault(find(c), set()).add(c)
    return list(groups.values())


def area_km2(geom: BaseGeometry) -> float:
    return abs(_GEOD.geometry_area_perimeter(geom)[0]) / 1e6


def suggested_area(footprint: BaseGeometry, region: BaseGeometry | None = None) -> BaseGeometry:
    """The cluster's bbox plus ~3 km, shrunk around its centre if over the area limit, then clipped to just
    inside the region (so the API's ST_Within check accepts it even on a coast or a border)."""
    w, s, e, n = footprint.bounds
    area = box(w - BUFFER_DEG, s - BUFFER_DEG, e + BUFFER_DEG, n + BUFFER_DEG)
    size = area_km2(area)
    if size > MAX_AREA_KM2:
        f = math.sqrt(MAX_AREA_KM2 * 0.95 / size)
        area = affinity.scale(area, xfact=f, yfact=f, origin=footprint.centroid)
    if region is not None:
        clipped = area.intersection(region).simplify(0.001, preserve_topology=True)
        polys = [g for g in getattr(clipped, "geoms", [clipped]) if g.geom_type == "Polygon" and g.area > 0]
        if polys:
            area = max(polys, key=lambda g: g.area)  # one polygon: the part that holds the detections
    return area


def _official_match(footprint: BaseGeometry, perimeters: list[Evidence]) -> dict[str, Any] | None:
    hits = []
    for p in perimeters:
        if p.geometry is None:
            continue
        g = shape(p.geometry.model_dump())
        if not g.is_valid:
            g = g.buffer(0)
        if g.intersects(footprint):
            hits.append((g.intersection(footprint).area, p))
    if not hits:
        return None
    _, p = max(hits, key=lambda h: h[0])
    props = p.properties
    return {
        "incident_name": props.get("incident_name"),
        "gis_acres": round(props["gis_acres"]) if isinstance(props.get("gis_acres"), (int, float)) else None,
        "percent_contained": props.get("percent_contained"),
        "incident_type": props.get("incident_type"),
        "source": p.source,
        "evidence_id": p.id,
    }


NEAREST_KM = 50


def _nearest_official(footprint: BaseGeometry, perimeters: list[Evidence]) -> dict[str, Any] | None:
    """Closest current official perimeter within 50 km (context only; it never makes a cluster official)."""
    to_utm = Transformer.from_crs("EPSG:4326", utm_crs_for(footprint), always_xy=True).transform
    fp = shp_transform(to_utm, footprint)
    best = None
    for p in perimeters:
        if p.geometry is None:
            continue
        g = shape(p.geometry.model_dump())
        w, s, e, n = g.bounds
        cx, cy = footprint.centroid.x, footprint.centroid.y
        if cx < w - 1 or cx > e + 1 or cy < s - 1 or cy > n + 1:  # cheap prefilter (~100 km)
            continue
        km = shp_transform(to_utm, g if g.is_valid else g.buffer(0)).distance(fp) / 1000
        if km <= NEAREST_KM and (best is None or km < best[0]):
            best = (km, p)
    if best is None:
        return None
    return {"incident_name": best[1].properties.get("incident_name"), "distance_km": round(best[0], 1)}


def cluster_detections(
    detections: list[Evidence],
    perimeters: list[Evidence] = (),  # type: ignore[assignment]
    *,
    region: BaseGeometry | None = None,
    top: int = 50,
) -> list[Cluster]:
    points = [d for d in detections if d.geometry is not None and d.geometry.type == "Point"]
    inner_region = region.buffer(-0.0005) if region is not None else None  # ~50 m inside the outline
    by_cell: dict[tuple[int, int], list[Evidence]] = {}
    for d in points:
        by_cell.setdefault(_cell(d), []).append(d)
    clusters: list[Cluster] = []
    for cells in _groups(set(by_cell)):
        members = sorted((d for c in cells for d in by_cell[c]), key=lambda d: (d.observed_at, d.id))
        cell_boxes = [
            box(x * CELL_DEG, y * CELL_DEG, (x + 1) * CELL_DEG, (y + 1) * CELL_DEG) for x, y in cells
        ]
        pts = MultiPoint([d.geometry.coordinates[:2] for d in members])  # type: ignore[union-attr]
        footprint = pts.convex_hull.buffer(0.004) if len(members) > 2 else pts.buffer(0.004)  # ~375 m pixel
        frps = [float(d.properties.get("frp") or 0) for d in members]
        first = min(cells)
        c = Cluster(
            id=f"c{first[0]}_{first[1]}",
            detections=members,
            footprint=footprint,
            centroid=pts.centroid,
            suggested_area=suggested_area(unary_union(cell_boxes), inner_region),
            high_confidence=sum(d.properties.get("confidence") == "high" for d in members),
            max_frp=round(max(frps), 1),
            total_frp=round(sum(frps), 1),
            first_seen=members[0].observed_at,
            last_seen=members[-1].observed_at,
            satellites=sorted({str(d.properties.get("satellite")) for d in members}),
            official=_official_match(footprint, list(perimeters)),
            evidence_ids=[d.id for d in members],
            cells=sorted(cells),
        )
        if c.official is None:
            c.nearest_official = _nearest_official(footprint, list(perimeters))
        c.place = place_for(c.centroid.x, c.centroid.y)
        c.score = round(c.high_confidence * 3 + len(members) + math.log1p(c.total_frp), 3)
        clusters.append(c)
    clusters.sort(key=lambda c: (-c.score, -c.last_seen.timestamp(), c.id))
    for i, c in enumerate(clusters[:top], start=1):
        c.rank = i
    return clusters[:top]


def _gj(geom: BaseGeometry) -> dict[str, Any]:
    """GeoJSON with plain lists and ~0.1 m precision (shapely's mapping() uses tuples)."""

    def r(v):
        return round(v, 6) if isinstance(v, float) else [r(x) for x in v]

    g = mapping(geom)
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def to_api(c: Cluster) -> dict[str, Any]:
    """contracts/openapi.yaml#/components/schemas/ActivityCluster"""
    return {
        "id": c.id,
        "rank": c.rank,
        "label": c.label,
        "centroid": _gj(c.centroid),
        "footprint": _gj(c.footprint),
        "suggested_area": _gj(c.suggested_area),
        "detections": len(c.detections),
        "high_confidence": c.high_confidence,
        "max_frp": c.max_frp,
        "total_frp": c.total_frp,
        "frp_units": "MW",
        "first_seen": c.first_seen.isoformat(),
        "last_seen": c.last_seen.isoformat(),
        "satellites": c.satellites,
        "official": c.official,
        "nearest_official": c.nearest_official,
        "place": c.place,
        "trend": None,  # filled from history by activity/trends.py
        "persistent_heat_source": False,
        "days_seen": 0,
        "cells": [cell_key(x) for x in c.cells],  # internal: history matching (not part of the API response)
        "score": c.score,  # internal: re-ranking after trends
    }


def cell_key(cell: tuple[int, int]) -> str:
    return f"{cell[0]}_{cell[1]}"


def cells_by_day(detections: list[Evidence]) -> dict[str, dict[str, Any]]:
    """Per grid cell: the UTC days it had detections, how many, first and last time (for activity_cells)."""
    out: dict[str, dict[str, Any]] = {}
    for d in detections:
        if d.geometry is None:
            continue
        k = cell_key(_cell(d))
        e = out.setdefault(k, {"days": set(), "count": 0, "first": d.observed_at, "last": d.observed_at})
        e["days"].add(d.observed_at.date())
        e["count"] += 1
        e["first"] = min(e["first"], d.observed_at)
        e["last"] = max(e["last"], d.observed_at)
    return out
