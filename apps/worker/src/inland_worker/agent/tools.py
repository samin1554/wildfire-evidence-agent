"""The approved tools: the ONLY actions the agent can take (spec §14). Each wraps the data pipeline.

The model picks tools by name and fills in arguments; every name and argument is validated here before
anything runs. Tools never accept URLs or code. Each returns a ToolResult; failures become results, not crashes.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from shapely.geometry import mapping, shape
from shapely.prepared import prep

from inland_worker.contracts.models import DateRange, Evidence, EvidenceType
from inland_worker.data import DataService
from inland_worker.kit.errors import ProviderError
from inland_worker.kit.imagery import aoi_grid, pick_scene, read_bands_async, repair
from inland_worker.kit.runner import data_mode
from inland_worker.satellite import burn, ndvi
from inland_worker.satellite.fixtures import recorded_scenes

FIRMS_MAX_AGE_DAYS = 5  # the FIRMS Area API only serves the last 1-5 days


@dataclass
class AgentContext:
    area: dict[str, Any]  # GeoJSON Polygon/MultiPolygon (WGS84), already scope-checked
    date_range: DateRange
    data: DataService
    today: date = field(default_factory=lambda: datetime.now(UTC).date())
    job_id: str | None = None

    @property
    def geom(self):
        return repair(self.area)

    def recent(self, days: int) -> bool:
        return self.date_range.end >= self.today - timedelta(days=days)


class ToolResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tool: str
    status: Literal["ok", "empty", "not_applicable", "missing", "error"]
    evidence: list[Evidence] = Field(default_factory=list)
    note: str = ""
    freshness: str = "fresh"
    raster: Any = Field(default=None, exclude=True, repr=False)  # BurnRaster for overlays; not serialized


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FireDetectionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(default=5, ge=1, le=5)


class ScenesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: date | None = None
    end: date | None = None
    cloud_limit: float = Field(default=30, ge=0, le=100)


class BurnSeverityArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before_start: date | None = None
    before_end: date | None = None
    after_start: date | None = None
    after_end: date | None = None


@dataclass
class Tool:
    name: str
    description: str
    Args: type[BaseModel]
    run: Callable[[AgentContext, BaseModel], Awaitable[ToolResult]]

    def spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "args": self.Args.model_json_schema().get("properties", {}),
        }


def _within_area(ctx: AgentContext, items: list[Evidence]) -> list[Evidence]:
    geom = ctx.geom
    return [i for i in items if i.geometry is None or shape(i.geometry.model_dump()).intersects(geom)]


async def _from_provider(ctx: AgentContext, tool: str, provider: str, **kwargs: Any) -> ToolResult:
    result = await ctx.data.get_evidence(provider, job_id=ctx.job_id, **kwargs)
    if not result.ok:
        return ToolResult(
            tool=tool,
            status="missing",
            note=f"{provider} unavailable ({result.freshness.reason})",
            freshness="missing",
        )
    items = _within_area(ctx, result.items)
    return ToolResult(
        tool=tool,
        status="ok" if items else "empty",
        evidence=items,
        freshness=result.freshness.kind,
        note="" if items else "no records inside the area",
    )


# --- tools --------------------------------------------------------------------------------------------------
async def fire_detections(ctx: AgentContext, args: FireDetectionArgs) -> ToolResult:
    if not ctx.recent(FIRMS_MAX_AGE_DAYS):
        return ToolResult(
            tool="fire_detections",
            status="not_applicable",
            note="NASA FIRMS near-real-time detections only cover the last 5 days",
        )
    bbox = tuple(round(v, 4) for v in ctx.geom.bounds)
    return await _from_provider(ctx, "fire_detections", "firms", bbox=bbox, params={"days": args.days})


async def current_perimeters(ctx: AgentContext, args: NoArgs) -> ToolResult:
    if not ctx.recent(1):
        return ToolResult(
            tool="current_perimeters",
            status="not_applicable",
            note="WFIGS holds current perimeters only; historical perimeters need CAL FIRE (Section 4)",
        )
    return await _from_provider(ctx, "current_perimeters", "wfigs_current", bbox=tuple(ctx.geom.bounds))


CALIFORNIA = Path(__file__).resolve().parents[3] / "config" / "regions" / "california.geojson"


@lru_cache
def _california():
    return prep(shape(json.loads(CALIFORNIA.read_text())["features"][0]["geometry"]).buffer(0.01))


def perimeter_source(geom) -> str:
    """One official archive per area, so a fire is never counted twice (ADR-012): CAL FIRE inside California
    (records back to 1950), NIFC WFIGS history elsewhere (about 2016 onward)."""
    return "calfire_historical" if _california().contains(geom) else "wfigs_history"


async def historical_perimeters(ctx: AgentContext, args: NoArgs) -> ToolResult:
    """Official perimeters of fires that started in the requested range and touch the area."""
    provider = perimeter_source(ctx.geom)
    result = await _from_provider(
        ctx,
        "historical_perimeters",
        provider,
        bbox=tuple(round(v, 4) for v in ctx.geom.bounds),
        date_range=ctx.date_range,
    )
    if result.status != "ok":
        return result
    dr = ctx.date_range
    items = [e for e in result.evidence if dr.start <= e.observed_at.date() <= dr.end]
    return result.model_copy(
        update={
            "evidence": items,
            "status": "ok" if items else "empty",
            "note": ""
            if items
            else f"no official perimeter ({provider}) of a fire that started in the range touches the area",
        }
    )


async def weather_forecast(ctx: AgentContext, args: NoArgs) -> ToolResult:
    if not ctx.recent(1):
        return ToolResult(
            tool="weather_forecast",
            status="not_applicable",
            note="NWS forecasts describe current and future weather, not past dates",
        )
    return await _from_provider(ctx, "weather_forecast", "nws_forecast", area=mapping(ctx.geom))


async def satellite_scenes(ctx: AgentContext, args: ScenesArgs) -> ToolResult:
    window = {"start": args.start or ctx.date_range.start, "end": args.end or ctx.date_range.end}
    return await _from_provider(
        ctx,
        "satellite_scenes",
        "earth_search_s2",
        area=mapping(ctx.geom),
        date_range=window,
        params={"cloud_limit": args.cloud_limit},
    )


def default_burn_windows(dr: DateRange) -> BurnSeverityArgs:
    """Without explicit windows: the first and last 30 days of the requested range."""
    span = timedelta(days=min(30, max(1, (dr.end - dr.start).days // 3)))
    return BurnSeverityArgs(
        before_start=dr.start, before_end=dr.start + span, after_start=dr.end - span, after_end=dr.end
    )


@dataclass
class BurnRaster:
    """dNBR classes on the AOI grid, kept for overlay tiles (satellite/overlay.py); never sent to the model."""

    classes: np.ndarray
    grid: Any


async def _scenes_for(ctx: AgentContext, start: date, end: date) -> list[Evidence]:
    if (ctx.data.mode or data_mode()) == "fixture":
        return recorded_scenes(ctx.geom, start, end)  # only what was recorded for this exact area/dates
    found = await ctx.data.get_evidence(
        "earth_search_s2",
        area=mapping(ctx.geom),
        job_id=ctx.job_id,
        date_range={"start": start, "end": end},
        params={"cloud_limit": 60},
    )
    return found.items


async def burn_severity(ctx: AgentContext, args: BurnSeverityArgs) -> ToolResult:
    """dNBR (and NDVI change) between the least-cloudy full-coverage Sentinel-2 dates of two windows (ADR-009).
    In fixture mode the scenes come from recorded imagery (satellite/fixtures.py); the maths is identical."""
    w = default_burn_windows(ctx.date_range)
    w = w.model_copy(update={k: v for k, v in args.model_dump().items() if v is not None})
    fixture = (ctx.data.mode or data_mode()) == "fixture"
    scenes = {}
    for label, (start, end) in {
        "before": (w.before_start, w.before_end),
        "after": (w.after_start, w.after_end),
    }.items():
        scenes[label] = pick_scene(await _scenes_for(ctx, start, end))
        if scenes[label] is None:
            where = (
                "recorded imagery (fixture mode) covering"
                if fixture
                else "cloud-free Sentinel-2 date fully covering"
            )
            return ToolResult(
                tool="burn_severity", status="missing", note=f"no {where} the area {start} to {end}"
            )
    grid = aoi_grid(ctx.geom)
    bands = ("nir", "swir22", "red")
    try:
        pre = await read_bands_async(
            scenes["before"], grid, bands=bands, trace=ctx.data.trace, job_id=ctx.job_id, allow_local=fixture
        )
        post = await read_bands_async(
            scenes["after"], grid, bands=bands, trace=ctx.data.trace, job_id=ctx.job_id, allow_local=fixture
        )
    except ProviderError as exc:
        return ToolResult(tool="burn_severity", status="error", note=f"imagery read failed ({exc.code})")
    d = burn.dnbr(
        burn.nbr(pre.arrays["nir"], pre.arrays["swir22"]), burn.nbr(post.arrays["nir"], post.arrays["swir22"])
    )
    inside = grid.inside & np.isfinite(d)
    if not inside.any():
        return ToolResult(tool="burn_severity", status="missing", note="no cloud-free pixels inside the area")
    vals = d[inside]
    valid_pct = round(100 * float(inside.sum()) / max(int(grid.inside.sum()), 1), 1)
    classes = burn.classify(d)
    common = {
        "before_date": scenes["before"].properties["date"],
        "after_date": scenes["after"].properties["date"],
        "before_scenes": pre.scene_ids,
        "after_scenes": post.scene_ids,
        "valid_pixel_pct": valid_pct,
        "resolution_m": grid.res,
    }
    props = {
        "method": "dNBR (Sentinel-2 L2A, NIR B08 / SWIR2 B12)",
        **common,
        "dnbr_median": round(float(np.median(vals)), 3),
        "dnbr_p25": round(float(np.percentile(vals, 25)), 3),
        "dnbr_p75": round(float(np.percentile(vals, 75)), 3),
        "class_acres": burn.class_acres(classes, grid.inside, grid.pixel_area_m2),
        "thresholds": list(burn.DNBR_EDGES),
        "threshold_source": "USGS / Key & Benson (2006), forest-calibrated",
        "units": "dNBR (unitless)",
    }
    flags = [] if valid_pct >= 80 else ["low_valid_pixels"]
    flags += ["fixture"] if fixture else []
    area_key = json.dumps(mapping(ctx.geom))
    limitations = [
        "Satellite burn indices indicate vegetation change; they are not ground-verified.",
        "Contains modified Copernicus Sentinel data.",
    ]
    base = {
        "job_id": ctx.job_id,
        "evidence_type": EvidenceType.DETERMINISTIC_CALCULATION,
        "source": "Inland Resilience worker (Sentinel-2)",
        "source_record_id": None,
        "observed_at": post.acquired_at,
        "retrieved_at": datetime.now(UTC),
        "geometry": mapping(ctx.geom),
        "quality_flags": flags,
        "source_url": "https://element84.com/earth-search/",
    }
    evidence = [
        Evidence(
            id=Evidence.stable_id("burn_severity", props["before_date"], props["after_date"], area_key),
            properties=props,
            limitations=[
                limitations[0],
                "Severity thresholds are forest-calibrated and not yet tuned for chaparral.",
                limitations[1],
            ],
            **base,
        )
    ]
    change = ndvi.ndvi_change(
        ndvi.ndvi(pre.arrays["nir"], pre.arrays["red"]), ndvi.ndvi(post.arrays["nir"], post.arrays["red"])
    )
    summary = ndvi.summarize(change, grid.inside)
    if summary is not None:
        evidence.append(
            Evidence(
                id=Evidence.stable_id("ndvi_change", props["before_date"], props["after_date"], area_key),
                properties={
                    "method": "NDVI change (Sentinel-2 L2A, NIR B08 / Red B04), after - before",
                    **common,
                    **summary,
                    "loss_threshold": -0.1,
                    "units": "NDVI difference (unitless)",
                },
                limitations=[
                    *limitations,
                    "NDVI also changes with season and drought; a drop is not proof of fire damage on its own.",
                ],
                **base,
            )
        )
    return ToolResult(
        tool="burn_severity",
        status="ok",
        evidence=evidence,
        raster=BurnRaster(classes=np.where(grid.inside, classes, 0).astype(np.uint8), grid=grid),
        note="recorded imagery (fixture mode)" if fixture else "",
    )


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "fire_detections",
            "NASA FIRMS satellite heat detections inside the area. Only the last 1-5 days. "
            "A detection is NOT a confirmed fire.",
            FireDetectionArgs,
            fire_detections,
        ),
        Tool(
            "current_perimeters",
            "Official perimeters of fires burning now (NIFC WFIGS). Current fires only.",
            NoArgs,
            current_perimeters,
        ),
        Tool(
            "historical_perimeters",
            "Official perimeters of past fires (started in the requested range) touching the area: CAL FIRE in "
            "California, NIFC elsewhere in the US.",
            NoArgs,
            historical_perimeters,
        ),
        Tool(
            "weather_forecast",
            "Official NWS forecast for the area. Current/future weather only.",
            NoArgs,
            weather_forecast,
        ),
        Tool(
            "satellite_scenes",
            "Which Sentinel-2 image dates exist for the area and how cloudy they are.",
            ScenesArgs,
            satellite_scenes,
        ),
        Tool(
            "burn_severity",
            "Burn severity (dNBR) from Sentinel-2 images before vs after a fire. Give before and "
            "after date windows (YYYY-MM-DD); defaults to the first/last 30 days of the range.",
            BurnSeverityArgs,
            burn_severity,
        ),
    ]
}
