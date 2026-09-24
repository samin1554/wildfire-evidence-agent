"""Guardrails (spec §15): what the agent refuses, and how outside text is kept from steering it.

Go validates requests first (Section 3); these checks are defence in depth inside the worker.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel
from pyproj import Geod
from shapely.geometry import box

from inland_worker.contracts.models import DateRange
from inland_worker.kit.config import load_providers
from inland_worker.kit.imagery import repair

MAX_AREA_KM2 = 5_000  # roughly a quarter of San Bernardino County
MAX_RANGE_DAYS = 3 * 366
REGION_AREA = "sb_county_bbox"  # providers.yaml; the county polygon replaces this once S4's boundary lands
OFFICIAL_HELP = (
    "This tool is for research, not emergencies. For evacuation orders and safety information, call 911 "
    "or follow San Bernardino County Fire, CAL FIRE (fire.ca.gov) and your county's emergency alerts."
)

EMERGENCY = re.compile(
    r"\b(evacuat\w*|escape route|should (i|we) (leave|stay|go)|is it safe|am i in danger|"
    r"shelter in place|emergency|911|where do i go)\b",
    re.I,
)
PREDICTION = re.compile(
    r"\b(predict\w*|forecast where|where will .{0,40}(start|ignite|spread)|next fire|"
    r"will .{0,30}(catch fire|burn next))\b",
    re.I,
)


class ScopeDecision(BaseModel):
    ok: bool
    code: str | None = None
    message: str | None = None


def area_km2(area) -> float:
    return abs(Geod(ellps="WGS84").geometry_area_perimeter(repair(area))[0]) / 1e6


def check_scope(question: str, area: dict, date_range: DateRange, today: date) -> ScopeDecision:
    q = question.strip()
    if not q or len(q) > 2000:
        return ScopeDecision(
            ok=False, code="INVALID_QUESTION", message="Ask a question of up to 2,000 characters."
        )
    if EMERGENCY.search(q):
        return ScopeDecision(ok=False, code="EMERGENCY_REDIRECT", message=OFFICIAL_HELP)
    if PREDICTION.search(q):
        return ScopeDecision(
            ok=False,
            code="UNSUPPORTED_PREDICTION",
            message="This tool analyses what happened; it can't predict where fires will start or "
            "spread. For current fire information, see CAL FIRE (fire.ca.gov).",
        )
    try:
        geom = repair(area)
    except (ValueError, TypeError, KeyError):
        return ScopeDecision(ok=False, code="INVALID_GEOMETRY", message="The area must be a valid polygon.")
    region = box(*load_providers().area_bbox(REGION_AREA))
    if not region.buffer(0.01).contains(geom):
        return ScopeDecision(
            ok=False,
            code="AREA_OUTSIDE_REGION",
            message="The area must be inside San Bernardino County (the supported region).",
        )
    if area_km2(geom) > MAX_AREA_KM2:
        return ScopeDecision(
            ok=False, code="AREA_TOO_LARGE", message=f"Choose an area under {MAX_AREA_KM2:,} km²."
        )
    if date_range.end > today:
        return ScopeDecision(ok=False, code="DATE_IN_FUTURE", message="Dates must not be in the future.")
    if (date_range.end - date_range.start).days > MAX_RANGE_DAYS:
        return ScopeDecision(
            ok=False, code="DATE_RANGE_TOO_LONG", message="Choose a date range of up to 3 years."
        )
    return ScopeDecision(ok=True)


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def untrusted(value: object, limit: int = 400) -> str:
    """Outside text (provider fields, alert descriptions) goes to the model only inside <data> tags, flattened and
    truncated, with no angle brackets, so it can't close the tag or pose as instructions."""
    text = _CONTROL.sub(" ", str(value)).replace("<", "(").replace(">", ")")
    text = re.sub(r"\s+", " ", text).strip()
    return f"<data>{text[:limit]}{'…' if len(text) > limit else ''}</data>"
