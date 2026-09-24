"""Real calls to real providers. Not part of the normal test run.

    make test-live        (reads keys from the repo's .env)

Each test proves the full live path works today: allowlisted HTTP → parse → schema-valid evidence.
"""

import os

import pytest

from inland_worker.connectors.registry import get_connector
from inland_worker.kit import fetch
from inland_worker.kit.testing import assert_valid_evidence

pytestmark = pytest.mark.live

CALIFORNIA = (-124.5, 32.5, -114.1, 42.0)
SB_COUNTY = (-117.8, 33.8, -114.1, 35.9)


@pytest.fixture(autouse=True)
def _real_user_agent(monkeypatch):
    # conftest sets a test UA; live calls should identify the project properly
    ua = (
        os.environ.get("LIVE_NWS_USER_AGENT")
        or "inland-resilience-agent/0.1 (+https://github.com/samin1554/inland-resilience)"
    )
    monkeypatch.setenv("NWS_USER_AGENT", ua)


async def test_wfigs_current_live():
    c = get_connector("wfigs_current")
    result = await fetch(c, c.query(bbox=CALIFORNIA), mode="live")
    assert_valid_evidence(result.items)
    print(f"\nWFIGS: {len(result.items)} current perimeters in California")


async def test_nws_forecast_live():
    c = get_connector("nws_forecast")
    result = await fetch(c, c.query(bbox=(-117.2998, 34.0983, -117.2798, 34.1183)), mode="live")
    assert len(result.items) == 1
    assert_valid_evidence(result.items)
    print(f"\nNWS: {len(result.items[0].properties['periods'])} forecast periods for San Bernardino")


@pytest.mark.skipif(not os.environ.get("FIRMS_MAP_KEY"), reason="FIRMS_MAP_KEY not set in .env")
async def test_firms_live():
    c = get_connector("firms")
    result = await fetch(c, c.query(bbox=SB_COUNTY, params={"days": 5}), mode="live")
    assert_valid_evidence(result.items)
    assert all(os.environ["FIRMS_MAP_KEY"] not in r.url for r in result.responses)
    print(f"\nFIRMS: {len(result.items)} detections in the SB County box (last 5 days)")


async def test_earth_search_scenes_and_kit_imagery_live():
    """Scene search → pick → windowed reads through the kit: burned area shows a strong dNBR, unburned doesn't."""
    import numpy as np
    from shapely.geometry import box, mapping

    from inland_worker.kit.imagery import aoi_grid, pick_scene, read_bands

    c = get_connector("earth_search_s2")

    async def ndbr_median(area):
        grid = aoi_grid(area)
        nbrs = []
        for day in ("2024-08-20", "2024-10-19"):  # before / after the 2024 Line Fire
            q = c.query(area=area, date_range={"start": day, "end": day}, params={"cloud_limit": 100})
            scene = pick_scene((await fetch(c, q, mode="live")).items)
            s = read_bands(scene, grid, bands=("nir", "swir22"))
            nbrs.append((s.arrays["nir"] - s.arrays["swir22"]) / (s.arrays["nir"] + s.arrays["swir22"]))
        return float(np.nanmedian((nbrs[0] - nbrs[1])[grid.inside]))

    burned = await ndbr_median(mapping(box(-117.10, 34.15, -117.08, 34.17)))  # inside the Line Fire
    unburned = await ndbr_median(mapping(box(-116.90, 34.12, -116.88, 34.14)))  # east of the perimeter
    print(f"\nEarth Search + kit/imagery: dNBR median burned {burned:.2f}, unburned {unburned:.2f}")
    assert burned > 0.3 and abs(unburned) < 0.15


@pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY not set in .env")
async def test_agent_with_a_real_free_model():
    """Real OpenRouter model, recorded data: the model's plan and wording still pass every check."""
    from datetime import date

    from inland_worker.agent import OpenRouterLLM, run_analysis
    from inland_worker.data import DataService

    area = {
        "type": "Polygon",
        "coordinates": [
            [[-117.185, 34.092], [-116.94, 34.092], [-116.94, 34.218], [-117.185, 34.218], [-117.185, 34.092]]
        ],
    }
    result = await run_analysis(
        "How badly did the 2024 Line Fire burn?",
        area,
        {"start": "2024-08-01", "end": "2024-10-31"},
        llm=OpenRouterLLM(),
        data=DataService(mode="fixture"),
        today=date(2026, 9, 24),
    )
    ids = {e.id for e in result.evidence}
    assert result.report and all(set(s.evidence_ids) <= ids for s in result.report.sections)
    assert "burn_severity" in [s["name"] for s in result.plan]
    print(
        f"\nAgent (models {result.models_used}): plan={result.plan_source} explanation={result.explanation_source} "
        f"confidence={result.report.confidence}"
    )
