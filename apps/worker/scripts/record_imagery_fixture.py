"""Record a small offline imagery fixture for fixture mode (one-time, needs network; no keys).

Finds the Sentinel-2 dates through the earth_search_s2 connector (kit), then reads only the fixture extent from
each band's COG through kit/imagery (allowlisted hosts) and saves it as a small GeoTIFF of raw DN values. The
scene evidence is saved with its asset hrefs pointing at those files, so fixture mode runs exactly the same
read_bands → burn maths as live mode, on any area drawn inside the extent.

    uv run python scripts/record_imagery_fixture.py            # Line Fire 2024 (default)
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import numpy as np
import rasterio
from shapely.geometry import box, mapping

from inland_worker.data import DataService
from inland_worker.kit.config import load_providers
from inland_worker.kit.imagery import PROVIDER_ID, _gdal_env, _read_asset, _resampling, aoi_grid, check_href

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "imagery"
BANDS = ("red", "nir", "swir22", "scl")
CASES = {
    # least-cloudy full-coverage dates around the fire (docs/research/line-fire-2024)
    "line_fire_2024": {
        "extent": (-117.205, 34.075, -116.92, 34.235),
        "dates": ["2024-08-20", "2024-10-19"],
    },
    # 2024 Thompson Fire, Oroville (alarm 2024-07-02): cloud-free 0 % scenes either side of the fire
    "thompson_fire_2024": {
        "extent": (-121.60, 39.49, -121.43, 39.60),
        "dates": ["2024-06-22", "2024-07-12"],
    },
}


async def record(case: str) -> None:
    spec = CASES[case]
    out = OUT / case
    out.mkdir(parents=True, exist_ok=True)
    extent = box(*spec["extent"])
    grid = aoi_grid(extent, res=20.0)
    config = load_providers().get(PROVIDER_ID)
    svc = DataService(mode="live")
    scenes_out = []
    for day in spec["dates"]:
        found = await svc.get_evidence(
            PROVIDER_ID,
            area=mapping(extent),
            date_range={"start": day, "end": day},
            params={"cloud_limit": 100},
        )
        if not found.items:
            raise SystemExit(f"no scene found for {day}")
        ev = found.items[0]
        scenes = ev.properties["scenes"]
        assets = {}
        with _gdal_env(config):
            for band in BANDS:
                merged = np.zeros((grid.height, grid.width), dtype=np.uint16)
                for s in scenes:
                    asset = s["assets"][band]
                    check_href(asset["href"], config)
                    raw = _read_asset(asset["href"], grid, 1, _resampling(band, asset, grid.res), np.float32)
                    merged = np.where(merged == 0, np.round(raw).astype(np.uint16), merged)
                name = f"{day}_{band}.tif"
                with rasterio.open(
                    out / name,
                    "w",
                    driver="GTiff",
                    width=grid.width,
                    height=grid.height,
                    count=1,
                    dtype="uint16",
                    crs=grid.crs,
                    transform=grid.transform,
                    nodata=0,
                    compress="deflate",
                    predictor=2,
                ) as dst:
                    dst.write(merged, 1)
                first = scenes[0]["assets"][band]
                assets[band] = {
                    **{k: v for k, v in first.items() if k != "href"},
                    "href": name,  # relative to the fixture folder; satellite/fixtures.py resolves it
                    "spatial_resolution": 20,
                }
        offsets = {s["boa_offset_applied"] for s in scenes}
        if len(offsets) != 1:
            raise SystemExit(f"{day}: scenes disagree on boa_offset_applied")
        merged_scene = {
            "id": "+".join(s["id"] for s in scenes),
            "tile": "+".join(s["tile"] for s in scenes),
            "platform": scenes[0]["platform"],
            "acquired_at": min(s["acquired_at"] for s in scenes),
            "cloud_cover_pct": max(s["cloud_cover_pct"] for s in scenes),
            "processing_baseline": scenes[0]["processing_baseline"],
            "boa_offset_applied": offsets.pop(),
            "assets": assets,
        }
        rec = ev.model_dump(mode="json")
        rec["geometry"] = mapping(extent)
        rec["properties"] = {**rec["properties"], "aoi_coverage": 1.0, "scenes": [merged_scene]}
        rec["quality_flags"] = sorted({*rec["quality_flags"], "fixture"})
        scenes_out.append(rec)
        print(f"{day}: {len(scenes)} tile(s) → {grid.width}x{grid.height} px")
    (out / "scenes.json").write_text(
        json.dumps({"extent": list(spec["extent"]), "crs": grid.crs, "scenes": scenes_out}, indent=2) + "\n"
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("case", nargs="?", default="line_fire_2024", choices=sorted(CASES))
    asyncio.run(record(ap.parse_args().case))
