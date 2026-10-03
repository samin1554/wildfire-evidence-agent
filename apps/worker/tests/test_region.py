"""The supported region (ADR-012): the US outline and the files generated from it stay in sync."""

import json
import re
from pathlib import Path

from shapely.geometry import Point, shape

from inland_worker.agent.guardrails import REGION_FILE, region

REPO = Path(__file__).resolve().parents[3]
INSIDE = {
    "Sacramento": (-121.49, 38.58),
    "Denver": (-104.99, 39.74),
    "Anchorage": (-149.9, 61.22),
    "Honolulu": (-157.86, 21.31),
    "Miami": (-80.19, 25.76),
    "Washington DC": (-77.04, 38.9),
    "Reno": (-119.81, 39.53),
}
OUTSIDE = {
    "Tijuana": (-117.02, 32.51),
    "Vancouver": (-123.12, 49.28),
    "Toronto": (-79.38, 43.65),
    "Gulf of Mexico": (-90.0, 26.0),
    "San Juan PR (territories out of scope)": (-66.1, 18.47),
}


def test_outline_is_the_50_states_and_dc():
    geom = region()
    assert geom.is_valid and geom.geom_type == "MultiPolygon"
    for name, pt in INSIDE.items():
        assert geom.contains(Point(pt)), name
    for name, pt in OUTSIDE.items():
        assert not geom.contains(Point(pt)), name
    props = json.loads(REGION_FILE.read_text())["features"][0]["properties"]
    assert len(props["states"]) == 51 and "DC" in props["states"] and "PR" not in props["states"]
    assert len(REGION_FILE.read_bytes()) < 1_000_000  # simplified for scope checks


def test_california_outline_is_kept_for_routing():
    ca = shape(json.loads((REGION_FILE.parent / "california.geojson").read_text())["features"][0]["geometry"])
    assert ca.contains(Point(INSIDE["Sacramento"])) and not ca.contains(Point(INSIDE["Reno"]))


def test_generated_seed_and_web_outline_match_the_committed_outline():
    outline = json.loads(REGION_FILE.read_text())
    sql = (REPO / "database" / "seeds" / "0001_region.sql").read_text()
    seeded = json.loads(re.search(r"ST_GeomFromGeoJSON\('(.+?)'\)", sql).group(1))
    assert shape(seeded).equals(shape(outline["features"][0]["geometry"]))
    assert "ON CONFLICT (id) DO UPDATE" in sql  # idempotent
    web = json.loads((REPO / "apps" / "web" / "public" / "region.geojson").read_text())
    assert web == outline
