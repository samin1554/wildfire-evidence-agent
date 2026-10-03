"""Satellite maths: hand-checked values, the recorded-imagery path, and overlay tiles."""

import json
from datetime import date
from pathlib import Path

import numpy as np

from inland_worker.agent.tools import AgentContext, BurnSeverityArgs, burn_severity
from inland_worker.contracts.models import DateRange
from inland_worker.data import DataService
from inland_worker.satellite import burn, ndvi
from inland_worker.satellite.overlay import render_tiles

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
LINE_FIRE = {
    "type": "Polygon",
    "coordinates": [
        [[-117.185, 34.092], [-116.94, 34.092], [-116.94, 34.218], [-117.185, 34.218], [-117.185, 34.092]]
    ],
}


def ctx(area, start="2024-08-01", end="2024-10-31"):
    return AgentContext(
        area=area,
        date_range=DateRange(start=start, end=end),
        data=DataService(mode="fixture"),
        today=date(2026, 9, 24),
    )


def test_index_maths_by_hand():
    nir, red, swir = np.array([0.5, 0.0, np.nan]), np.array([0.1, 0.0, 0.2]), np.array([0.3, 0.0, 0.1])
    assert np.allclose(ndvi.ndvi(nir, red)[:1], [0.4 / 0.6])
    assert np.isnan(ndvi.ndvi(nir, red)[1:]).all()  # zero denominator and masked → NaN
    assert np.allclose(burn.nbr(nir, swir)[:1], [0.25])
    assert np.allclose(ndvi.ndvi_change(np.array([0.6]), np.array([0.2])), [-0.4])
    d = np.array([0.05, 0.2, 0.5, 0.9, np.nan], dtype=np.float32)
    assert burn.classify(d).tolist() == [1, 2, 3, 4, 0]
    assert ndvi.summarize(np.array([np.nan]), np.array([True])) is None


async def test_recorded_imagery_matches_the_recorded_line_fire_calculation():
    r = await burn_severity(ctx(LINE_FIRE), BurnSeverityArgs())
    assert r.status == "ok" and "fixture" in r.evidence[0].quality_flags
    got = r.evidence[0].properties
    want = json.loads((FIXTURES / "burn_severity" / "success.json").read_text())["properties"]
    assert (got["before_date"], got["after_date"]) == (want["before_date"], want["after_date"])
    for name, acres in want["class_acres"].items():
        assert abs(got["class_acres"][name] - acres) / acres < 0.05, name
    assert abs(burn_burned(got) - burn_burned(want)) / burn_burned(want) < 0.01
    assert r.evidence[1].properties["ndvi_change_median"] < 0  # vegetation loss after the fire


def burn_burned(p):
    return p["class_acres"]["Moderate"] + p["class_acres"]["High"]


async def test_area_outside_recording_is_missing():
    outside = {
        "type": "Polygon",
        "coordinates": [[[-116.0, 34.5], [-115.9, 34.5], [-115.9, 34.6], [-116.0, 34.6], [-116.0, 34.5]]],
    }
    r = await burn_severity(ctx(outside), BurnSeverityArgs())
    assert r.status == "missing" and not r.evidence and "fixture mode" in r.note


async def test_dates_outside_recording_are_missing():
    r = await burn_severity(ctx(LINE_FIRE, "2023-01-01", "2023-06-30"), BurnSeverityArgs())
    assert r.status == "missing"


async def test_overlay_tiles(tmp_path):
    r = await burn_severity(ctx(LINE_FIRE), BurnSeverityArgs())
    n = render_tiles(r.raster.classes, r.raster.grid, tmp_path, zooms=range(11, 12))
    assert n > 0 and len(list(tmp_path.rglob("*.png"))) == n


def test_no_burned_pixels_writes_no_tiles(tmp_path):
    class Grid:  # minimal stand-in for AoiGrid
        crs = "EPSG:32611"
        transform = __import__("rasterio").transform.from_origin(480000, 3780000, 20, 20)
        width = height = 50

    assert render_tiles(np.ones((50, 50), dtype=np.uint8), Grid, tmp_path, zooms=range(12, 13)) == 0
