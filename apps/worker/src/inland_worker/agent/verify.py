"""Evidence verification and the confidence label (spec §15).

BASELINE by the lead so the agent works end to end; Section 8 owns the rules and will extend them
(spatial/temporal matching, calibrated thresholds, claim-source checks). Agent inferences never count.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from inland_worker.agent.tools import ToolResult

Confidence = Literal[
    "unverified_detection", "corroborated_signal", "officially_reported", "insufficient_evidence"
]
BURN_SIGNAL_SHARE = 0.10  # >=10% of the area at moderate/high severity counts as a burn signal
# (a median would under-read burns when the user's area includes unburned land around the fire)


def burned_share(props: dict) -> float:
    acres = props.get("class_acres") or {}
    total = sum(acres.values())
    return (acres.get("Moderate", 0) + acres.get("High", 0)) / total if total else 0.0


class Verification(BaseModel):
    confidence: Confidence
    reasons: list[str]
    signals: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


def verify(results: dict[str, ToolResult]) -> Verification:
    signals, reasons, limitations, gaps = [], [], [], []
    for r in results.values():
        if r.status in ("missing", "error", "not_applicable"):
            gaps.append(f"{r.tool}: {r.note}")
        if r.freshness == "stale":
            limitations.append(f"{r.tool} used the last saved data because the live source failed (stale).")
        for ev in r.evidence:
            limitations.extend(lim for lim in ev.limitations if lim not in limitations)

    detections = results.get("fire_detections")
    if detections and detections.evidence:
        signals.append("satellite_detection")
        reasons.append(f"{len(detections.evidence)} satellite heat detection(s) inside the area")
    burn = results.get("burn_severity")
    if burn and burn.evidence:
        p = burn.evidence[0].properties
        share = burned_share(p)
        if share >= BURN_SIGNAL_SHARE and p["valid_pixel_pct"] >= 50:
            signals.append("burn_severity")
            reasons.append(
                f"measured burn signal: {share:.0%} of the area at moderate/high severity "
                f"({p['before_date']} to {p['after_date']})"
            )
        else:
            reasons.append(f"no strong burn signal: {share:.0%} of the area at moderate/high severity")
    perimeters = results.get("current_perimeters")
    official = bool(perimeters and perimeters.evidence)
    if official:
        reasons.append(f"{len(perimeters.evidence)} official perimeter(s) intersect the area")

    if official:
        confidence: Confidence = "officially_reported"
    elif len(signals) >= 2:
        confidence = "corroborated_signal"
    elif len(signals) == 1:
        confidence = "unverified_detection"
        reasons.append("only one independent evidence type; corroboration needs two")
    else:
        confidence = "insufficient_evidence"
        reasons.append("no usable signal from the available sources")
    if not official and not (perimeters and perimeters.status == "empty"):
        limitations.append(
            "No official fire-perimeter source covered this period, so nothing here is officially "
            "confirmed (historical CAL FIRE perimeters and BAER maps are being connected by Section 4)."
        )
    limitations.extend(f"Not available: {g}" for g in gaps)
    return Verification(
        confidence=confidence, reasons=reasons, signals=signals, limitations=limitations, gaps=gaps
    )
