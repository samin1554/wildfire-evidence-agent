"""The supported region (ADR-011): the California outline and the files generated from it stay in sync."""

import json
import re
from pathlib import Path

from shapely.geometry import Point, shape

from inland_worker.agent.guardrails import REGION_FILE, region

REPO = Path(__file__).resolve().parents[3]


def test_outline_is_california():
    geom = region()
    assert geom.is_valid and geom.geom_type in ("Polygon", "MultiPolygon")
    for lon, lat in [
        (-121.49, 38.58),
        (-118.24, 34.05),
        (-117.29, 34.11),
        (-124.16, 41.75),
    ]:  # Sacramento, LA, SB, Crescent City
        assert geom.contains(Point(lon, lat)), (lon, lat)
    for lon, lat in [
        (-119.81, 39.53),
        (-115.14, 36.17),
        (-114.0, 33.5),
        (-125.0, 37.0),
    ]:  # Reno, Las Vegas, AZ, ocean
        assert not geom.contains(Point(lon, lat)), (lon, lat)
    assert len(REGION_FILE.read_bytes()) < 100_000  # simplified for scope checks


def test_generated_seed_and_web_outline_match_the_committed_outline():
    outline = json.loads(REGION_FILE.read_text())
    sql = (REPO / "database" / "seeds" / "0001_region.sql").read_text()
    seeded = json.loads(re.search(r"ST_GeomFromGeoJSON\('(.+?)'\)", sql).group(1))
    assert shape(seeded).equals(shape(outline["features"][0]["geometry"]))
    assert "ON CONFLICT (id) DO UPDATE" in sql  # idempotent
    web = json.loads((REPO / "apps" / "web" / "public" / "california.geojson").read_text())
    assert web == outline
