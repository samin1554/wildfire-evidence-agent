"""NIFC WFIGS Interagency Perimeters (all years): official perimeters of past fires across the US, ~2016 onward.

Same service family, fields and parsing as the `wfigs_current` reference (fire/wfigs.py); this layer keeps every
season instead of only active fires. ADR-012 uses it for historical perimeters outside California (inside
California the agent uses `calfire_historical`, which goes back to 1950).

- Filtered by the fire's discovery date (`attr_FireDiscoveryDateTime`) inside the requested range; `observed_at`
  is that discovery time, the perimeter itself was mapped later (said in the limitations).
- `incident_type` keeps WF (wildfire) apart from RX (prescribed burn): a prescribed burn is never a wildfire.
Spec: docs/connectors/providers/wfigs.md (same service family).
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field

from inland_worker.connectors.fire.wfigs import OUT_FIELDS, WfigsCurrentConnector
from inland_worker.contracts.models import Evidence
from inland_worker.kit import arcgis
from inland_worker.kit.connector import ProviderQuery, ProviderRequest, RawResponse

INCIDENT_TYPES = {"WF": "wildfire", "RX": "prescribed burn"}


class WfigsHistoryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_size: int = Field(default=1000, ge=1, le=2000)
    min_acres: float | None = Field(
        default=None, ge=0, description="only fires at least this large (poly_GISAcres)"
    )
    max_offset: float | None = Field(
        default=None,
        gt=0,
        le=0.01,
        description="server-side generalization in degrees (ArcGIS maxAllowableOffset)",
    )


class WfigsHistoryConnector(WfigsCurrentConnector):
    provider_id = "wfigs_history"
    Params = WfigsHistoryParams

    def build_requests(self, query: ProviderQuery) -> list[ProviderRequest]:
        p: WfigsHistoryParams = query.params  # type: ignore[assignment]
        clauses = []
        if query.date_range is not None:
            end = query.date_range.end + timedelta(days=1)
            clauses += [
                f"attr_FireDiscoveryDateTime >= TIMESTAMP '{query.date_range.start} 00:00:00'",
                f"attr_FireDiscoveryDateTime < TIMESTAMP '{end} 00:00:00'",
            ]
        if p.min_acres is not None:
            clauses.append(f"poly_GISAcres >= {p.min_acres:g}")
        req = arcgis.query_request(
            bbox=query.get_bbox(),
            out_fields=[*OUT_FIELDS, "attr_IncidentTypeCategory"],
            where=" AND ".join(clauses) or "1=1",
            page_size=p.page_size,
        )
        req.params["geometryPrecision"] = "6"
        if p.max_offset is not None:
            req.params["maxAllowableOffset"] = str(p.max_offset)
        return [req]

    def _feature(self, feature: dict, resp: RawResponse) -> Evidence:
        ev = super()._feature(feature, resp)
        a = feature.get("properties") or {}
        code = a.get("attr_IncidentTypeCategory")
        discovered = arcgis.epoch_ms(a.get("attr_FireDiscoveryDateTime"))
        flags = list(ev.quality_flags) + ([] if discovered else ["missing_discovery_date"])
        return ev.model_copy(
            update={
                "observed_at": discovered or ev.observed_at,
                "quality_flags": list(dict.fromkeys(flags)),
                "properties": {
                    **ev.properties,
                    "incident_type_code": code,
                    "incident_type": INCIDENT_TYPES.get(code, code),
                },
            }
        )
