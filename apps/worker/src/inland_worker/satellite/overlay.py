"""Map overlays: dNBR severity classes rendered to XYZ PNG tiles (web-mercator) for GET /v1/tiles/{layer}/{z}/{x}/{y}.png.

Tiles are written to a directory (the shared `artifacts` volume in Docker); the Go API only serves the files.
Colours follow the severity classes in satellite/burn.py; "Unburned/very low" is left transparent.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

from inland_worker.kit.imagery import AoiGrid
from inland_worker.satellite.burn import CLASS_NAMES

TILE = 256
WEB_MERCATOR_HALF = 20037508.342789244
# RGBA per class index (0 = no data); class 1 (unburned/very low) is transparent on purpose
PALETTE = {
    0: (0, 0, 0, 0),
    1: (0, 0, 0, 0),
    2: (250, 210, 90, 170),
    3: (240, 130, 40, 190),
    4: (180, 30, 20, 210),
}
LEGEND = [
    {"label": CLASS_NAMES[1], "color": "#fad25a"},
    {"label": CLASS_NAMES[2], "color": "#f08228"},
    {"label": CLASS_NAMES[3], "color": "#b41e14"},
]


def _tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    size = 2 * WEB_MERCATOR_HALF / 2**z
    minx = -WEB_MERCATOR_HALF + x * size
    maxy = WEB_MERCATOR_HALF - y * size
    return minx, maxy - size, minx + size, maxy


def _tile_range(bounds_ll: tuple[float, float, float, float], z: int) -> tuple[range, range]:
    w, s, e, n = bounds_ll

    def tx(lon: float) -> int:
        return int((lon + 180) / 360 * 2**z)

    def ty(lat: float) -> int:
        r = math.radians(lat)
        return int((1 - math.asinh(math.tan(r)) / math.pi) / 2 * 2**z)

    return range(tx(w), tx(e) + 1), range(ty(n), ty(s) + 1)


def grid_bounds_ll(grid: AoiGrid) -> tuple[float, float, float, float]:
    to_ll = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True).transform
    t = grid.transform
    xs = [t.c, t.c + t.a * grid.width]
    ys = [t.f, t.f + t.e * grid.height]
    pts = [to_ll(x, y) for x in xs for y in ys]
    return (
        min(p[0] for p in pts),
        min(p[1] for p in pts),
        max(p[0] for p in pts),
        max(p[1] for p in pts),
    )


def render_tiles(classes: np.ndarray, grid: AoiGrid, out_dir: Path, zooms: range = range(10, 15)) -> int:
    """Write {out_dir}/{z}/{x}/{y}.png for every tile touching the grid that has burned pixels. Returns count."""
    bounds = grid_bounds_ll(grid)
    lut = np.zeros((256, 4), dtype=np.uint8)
    for k, rgba in PALETTE.items():
        lut[k] = rgba
    written = 0
    for z in zooms:
        xs, ys = _tile_range(bounds, z)
        for x in xs:
            for y in ys:
                dst = np.zeros((TILE, TILE), dtype=np.uint8)
                reproject(
                    classes,
                    dst,
                    src_transform=grid.transform,
                    src_crs=grid.crs,
                    dst_transform=from_bounds(*_tile_bounds(z, x, y), TILE, TILE),
                    dst_crs="EPSG:3857",
                    resampling=Resampling.nearest,
                    src_nodata=0,
                    dst_nodata=0,
                )
                if not (dst >= 2).any():
                    continue
                rgba = lut[dst].transpose(2, 0, 1)
                path = out_dir / str(z) / str(x) / f"{y}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                with (
                    warnings.catch_warnings(category=NotGeoreferencedWarning, action="ignore"),
                    rasterio.open(
                        path, "w", driver="PNG", width=TILE, height=TILE, count=4, dtype="uint8"
                    ) as f,
                ):
                    f.write(rgba)
                written += 1
    return written
