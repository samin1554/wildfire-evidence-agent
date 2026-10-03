"""Map layers for GET /v1/analyses/{id}/layers (contracts/openapi.yaml#/components/schemas/Layer).

Vector layers are drawn by the web app from the job's evidence (filtered by `evidence_types`); the raster layer
is the dNBR severity overlay served as tiles. Legends and titles never call a detection a confirmed fire.
"""

from __future__ import annotations

from typing import Any

from shapely.geometry import shape
from shapely.ops import unary_union

from inland_worker.contracts.models import Evidence, EvidenceType

VECTOR_STYLE: dict[str, dict[str, Any]] = {
    EvidenceType.SATELLITE_DETECTION: {
        "title": "Satellite heat detections (unverified)",
        "legend": [
            {"label": "High confidence detection", "color": "#b42318"},
            {"label": "Nominal confidence detection", "color": "#eb6c36"},
            {"label": "Low confidence detection", "color": "#f4b183"},
        ],
    },
    EvidenceType.OFFICIAL_PERIMETER: {
        "title": "Official fire perimeters",
        "legend": [{"label": "Official perimeter", "color": "#7a2e8e"}],
    },
    EvidenceType.WEATHER_FORECAST: {
        "title": "NWS forecast area",
        "legend": [{"label": "Forecast grid cell", "color": "#2f6db5"}],
    },
    EvidenceType.WEATHER_ALERT: {
        "title": "NWS alerts",
        "legend": [{"label": "Alert area", "color": "#c79a00"}],
    },
    EvidenceType.DETERMINISTIC_CALCULATION: {
        "title": "Analysed area (satellite calculations)",
        "legend": [{"label": "Area used for dNBR / NDVI", "color": "#1f7a5c"}],
    },
}


def _bounds(items: list[Evidence]) -> list[float] | None:
    geoms = [shape(i.geometry.model_dump()) for i in items if i.geometry is not None]
    if not geoms:
        return None
    return [round(v, 5) for v in unary_union(geoms).bounds]


def _span(items: list[Evidence]) -> tuple[str | None, str | None]:
    times = sorted(i.observed_at for i in items)
    return (times[0].isoformat(), times[-1].isoformat()) if times else (None, None)


def vector_layers(evidence: list[Evidence]) -> list[dict[str, Any]]:
    out = []
    for etype, style in VECTOR_STYLE.items():
        items = [e for e in evidence if e.evidence_type == etype and e.geometry is not None]
        if not items:
            continue
        start, end = _span(items)
        out.append(
            {
                "id": f"layer_{etype.value}",
                "title": style["title"],
                "kind": "vector",
                "evidence_types": [etype.value],
                "tile_template": None,
                "bounds": _bounds(items),
                "legend": style["legend"],
                "attribution": "; ".join(sorted({i.source for i in items})),
                "observed_from": start,
                "observed_to": end,
                "expires_at": None,
            }
        )
    return out


def raster_layer(
    layer_id: str, bounds: list[float], legend: list[dict[str, str]], calc: Evidence
) -> dict[str, Any]:
    p = calc.properties
    return {
        "id": layer_id,
        "title": f"Burn severity (dNBR) {p.get('before_date')} → {p.get('after_date')}",
        "kind": "raster",
        "evidence_types": [EvidenceType.DETERMINISTIC_CALCULATION.value],
        "tile_template": f"/v1/tiles/{layer_id}/{{z}}/{{x}}/{{y}}.png",
        "bounds": [round(v, 5) for v in bounds],
        "legend": legend,
        "attribution": "Contains modified Copernicus Sentinel data (Earth Search); dNBR by Inland Resilience",
        "observed_from": None,
        "observed_to": calc.observed_at.isoformat(),
        "expires_at": None,
    }
