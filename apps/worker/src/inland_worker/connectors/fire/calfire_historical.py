"""CAL FIRE historical fire perimeters (FRAP California_Historic_Fire_Perimeters, layer 2): official perimeters
of past fires, 1950 to the latest season.

Copied from the reference connector fire/wfigs.py (arcgis pattern).
Spec: docs/connectors/providers/calfire-historical.md (note its URL correction: layer 2 of the historic service).

- Queried by envelope and fire year (`YEAR_` between the date range's years); paged like every ArcGIS layer.
- `observed_at` is the alarm (start) date; perimeters are often mapped later, which the limitations say.
- Perimeters can be invalid geometries (the 2024 Line Fire has a self-touching ring): they're kept as published
  and flagged `geometry_repaired` only when repaired downstream; consumers repair before maths (kit/imagery.repair).
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from inland_worker.contracts.models import Evidence, EvidenceType
from inland_worker.kit import arcgis
from inland_worker.kit.connector import BaseConnector, ProviderQuery, ProviderRequest, RawResponse

OUT_FIELDS = [
    "FIRE_NAME",
    "YEAR_",
    "GIS_ACRES",
    "ALARM_DATE",
    "CONT_DATE",
    "CAUSE",
    "AGENCY",
    "UNIT_ID",
    "INC_NUM",
    "IRWINID",
    "OBJECTID",
]


class CalfireParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_year: int = Field(default=2020, ge=1878, le=2100, description="used when no date_range is given")
    page_size: int = Field(default=500, ge=1, le=2000)
    min_acres: float | None = Field(
        default=None, ge=0, description="only fires at least this large (GIS_ACRES)"
    )
    max_offset: float | None = Field(
        default=None,
        gt=0,
        le=0.01,
        description="server-side generalization in degrees (ArcGIS maxAllowableOffset)",
    )


class CalfireHistoricalConnector(BaseConnector):
    provider_id = "calfire_historical"
    evidence_types = frozenset({EvidenceType.OFFICIAL_PERIMETER})
    Params = CalfireParams

    def build_requests(self, query: ProviderQuery) -> list[ProviderRequest]:
        p: CalfireParams = query.params  # type: ignore[assignment]
        if query.date_range is not None:
            where = f"YEAR_ >= {query.date_range.start.year} AND YEAR_ <= {query.date_range.end.year}"
        else:
            where = f"YEAR_ >= {p.min_year}"
        if p.min_acres is not None:
            where += f" AND GIS_ACRES >= {p.min_acres:g}"
        req = arcgis.query_request(
            bbox=query.get_bbox(), out_fields=OUT_FIELDS, where=where, page_size=p.page_size
        )
        req.params["geometryPrecision"] = "6"  # ~0.1 m; full float precision only inflates responses
        if p.max_offset is not None:
            req.params["maxAllowableOffset"] = str(p.max_offset)
        return [req]

    def follow(self, response: RawResponse, query: ProviderQuery) -> list[ProviderRequest]:
        nxt = arcgis.next_page(response)
        return [nxt] if nxt else []

    def parse(self, responses: Sequence[RawResponse], query: ProviderQuery) -> list[Evidence]:
        items: list[Evidence] = []
        for resp in responses:
            payload = resp.json()
            if "error" in payload:  # ArcGIS reports errors with HTTP 200
                raise ValueError(f"ArcGIS error: {payload['error'].get('message', payload['error'])}")
            for feature in payload["features"]:
                items.append(self._feature(feature, resp))
        return items

    def _feature(self, feature: dict, resp: RawResponse) -> Evidence:
        a = feature.get("properties") or {}
        flags: list[str] = []
        alarm = arcgis.epoch_ms(a.get("ALARM_DATE"))
        contained = arcgis.epoch_ms(a.get("CONT_DATE"))
        if alarm is None:
            flags.append("missing_alarm_date")
        if contained is None:
            flags.append("missing_containment_date")
        geometry = feature.get("geometry")
        if not geometry:
            flags.append("missing_geometry")
        record = a.get("IRWINID") or (
            f"{a.get('UNIT_ID')}-{a.get('INC_NUM')}-{a.get('YEAR_')}" if a.get("INC_NUM") else None
        )
        return self.evidence(
            evidence_type=EvidenceType.OFFICIAL_PERIMETER,
            observed_at=alarm or resp.retrieved_at,
            retrieved_at=resp.retrieved_at,
            geometry=geometry,
            source_record_id=record or (str(a["OBJECTID"]) if a.get("OBJECTID") is not None else None),
            properties={
                "incident_name": (a.get("FIRE_NAME") or "").strip().title() or None,
                "fire_name": a.get("FIRE_NAME"),
                "year": a.get("YEAR_"),
                "gis_acres": round(a["GIS_ACRES"], 2)
                if isinstance(a.get("GIS_ACRES"), (int, float))
                else None,
                "area_units": "acres",
                "alarm_date": alarm.date().isoformat() if alarm else None,
                "containment_date": contained.date().isoformat() if contained else None,
                "cause_code": a.get("CAUSE"),
                "agency": a.get("AGENCY"),
                "unit_id": a.get("UNIT_ID"),
                "irwin_id": a.get("IRWINID"),
            },
            quality_flags=flags,
        )
