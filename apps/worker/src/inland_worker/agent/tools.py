"""The approved tools: the ONLY actions the agent can take (spec §14). Each wraps the data pipeline.

The model picks tools by name and fills in arguments; every name and argument is validated here before
anything runs. Tools never accept URLs or code. Each returns a ToolResult; failures become results, not crashes.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from shapely.geometry import mapping, shape

from inland_worker.contracts.models import DateRange, Evidence, EvidenceType
from inland_worker.data import DataService
from inland_worker.kit.errors import ProviderError
from inland_worker.kit.imagery import aoi_grid, pick_scene, read_bands_async, repair
from inland_worker.kit.runner import data_mode
from inland_worker.satellite import burn

BURN_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "burn_severity"
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


async def burn_severity(ctx: AgentContext, args: BurnSeverityArgs) -> ToolResult:
    """dNBR between the least-cloudy full-coverage Sentinel-2 dates of two windows (ADR-009)."""
    w = default_burn_windows(ctx.date_range)
    w = w.model_copy(update={k: v for k, v in args.model_dump().items() if v is not None})
    if (
        ctx.data.mode or data_mode()
    ) == "fixture":  # pixel reads need the network; replay a recorded calculation
        path = BURN_FIXTURES / "success.json"
        if not path.exists():
            return ToolResult(
                tool="burn_severity", status="missing", note="no recorded burn-severity fixture"
            )
        ev = Evidence.model_validate_json(path.read_text()).with_flag("fixture")
        return ToolResult(
            tool="burn_severity", status="ok", evidence=[ev], note="recorded calculation (fixture mode)"
        )

    scenes = {}
    for label, (start, end) in {
        "before": (w.before_start, w.before_end),
        "after": (w.after_start, w.after_end),
    }.items():
        found = await ctx.data.get_evidence(
            "earth_search_s2",
            area=mapping(ctx.geom),
            job_id=ctx.job_id,
            date_range={"start": start, "end": end},
            params={"cloud_limit": 60},
        )
        scenes[label] = pick_scene(found.items)
        if scenes[label] is None:
            return ToolResult(
                tool="burn_severity",
                status="missing",
                note=f"no cloud-free Sentinel-2 date fully covering the area {start} to {end}",
            )
    grid = aoi_grid(ctx.geom)
    try:
        pre = await read_bands_async(
            scenes["before"], grid, bands=("nir", "swir22"), trace=ctx.data.trace, job_id=ctx.job_id
        )
        post = await read_bands_async(
            scenes["after"], grid, bands=("nir", "swir22"), trace=ctx.data.trace, job_id=ctx.job_id
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
    props = {
        "method": "dNBR (Sentinel-2 L2A, NIR B08 / SWIR2 B12)",
        "before_date": scenes["before"].properties["date"],
        "after_date": scenes["after"].properties["date"],
        "before_scenes": pre.scene_ids,
        "after_scenes": post.scene_ids,
        "dnbr_median": round(float(np.median(vals)), 3),
        "dnbr_p25": round(float(np.percentile(vals, 25)), 3),
        "dnbr_p75": round(float(np.percentile(vals, 75)), 3),
        "class_acres": burn.class_acres(classes, grid.inside, grid.pixel_area_m2),
        "thresholds": list(burn.DNBR_EDGES),
        "threshold_source": "USGS / Key & Benson (2006), forest-calibrated",
        "valid_pixel_pct": valid_pct,
        "resolution_m": grid.res,
        "units": "dNBR (unitless)",
    }
    flags = [] if valid_pct >= 80 else ["low_valid_pixels"]
    ev = Evidence(
        id=Evidence.stable_id(
            "burn_severity", props["before_date"], props["after_date"], json.dumps(mapping(ctx.geom))
        ),
        job_id=ctx.job_id,
        evidence_type=EvidenceType.DETERMINISTIC_CALCULATION,
        source="Inland Resilience worker (Sentinel-2 dNBR)",
        source_record_id=None,
        observed_at=post.acquired_at,
        retrieved_at=datetime.now(UTC),
        geometry=mapping(ctx.geom),
        properties=props,
        quality_flags=flags,
        limitations=[
            "Satellite burn indices indicate vegetation change; they are not ground-verified.",
            "Severity thresholds are forest-calibrated and not yet tuned for chaparral.",
            "Contains modified Copernicus Sentinel data.",
        ],
        source_url="https://element84.com/earth-search/",
    )
    return ToolResult(tool="burn_severity", status="ok", evidence=[ev])


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
