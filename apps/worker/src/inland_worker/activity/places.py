"""Name a place from coordinates (ADR-013): the county + state a point falls in, from the recorded Census
TIGERweb county outlines (config/regions/us_counties.geojson, built by scripts/build_region_seed.py --counties)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from shapely import STRtree
from shapely.geometry import Point, shape

COUNTIES = Path(__file__).resolve().parents[3] / "config" / "regions" / "us_counties.geojson"


@lru_cache
def _index() -> tuple[STRtree, list[dict[str, Any]]]:
    feats = json.loads(COUNTIES.read_text())["features"]
    geoms = [shape(f["geometry"]) for f in feats]
    return STRtree(geoms), [f["properties"] for f in feats]


def place_for(lon: float, lat: float) -> dict[str, str] | None:
    """{"county": "Grant County", "state": "OR"} or None outside every county (e.g. offshore)."""
    tree, props = _index()
    pt = Point(lon, lat)
    for i in tree.query(pt, predicate="intersects"):
        return {"county": props[int(i)]["name"], "state": props[int(i)]["state"]}
    return None


def label(place: dict[str, str] | None, lon: float, lat: float) -> str:
    if place:
        return f"{place['county']}, {place['state']}"
    return f"near {abs(lat):.2f}°{'N' if lat >= 0 else 'S'}, {abs(lon):.2f}°{'W' if lon < 0 else 'E'}"
