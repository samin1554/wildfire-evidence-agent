"""NIFC WFIGS Interagency Perimeters (current): official perimeters of active fires.

REFERENCE CONNECTOR for the *ArcGIS feature service* pattern. Copy it for CAL FIRE historical, the county
boundary, hazard zones and county layers:
    make new-connector NAME=<id> GROUP=<fire|weather> PATTERN=arcgis

What makes this pattern tricky, and how it's handled here:
- Results are paged: `follow()` asks for the next page while the service reports exceededTransferLimit.
- Dates are epoch milliseconds (`arcgis.epoch_ms`).
- f=geojson already returns GeoJSON in WGS84. Layers queried with f=json (Esri JSON) need
  `arcgis.esri_to_geojson()`; the county boundary is one of those.
Spec: docs/connectors/providers/wfigs.md
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from inland_worker.contracts.models import Evidence, EvidenceType
from inland_worker.kit import arcgis
from inland_worker.kit.connector import BaseConnector, ProviderQuery, ProviderRequest, RawResponse

OUT_FIELDS = [
    "poly_IncidentName",
    "poly_GISAcres",
    "poly_PolygonDateTime",
    "poly_DateCurrent",
    "poly_IRWINID",
    "poly_FeatureCategory",
    "poly_MapMethod",
    "attr_PercentContained",
    "attr_FireDiscoveryDateTime",
    "attr_POOState",
    "attr_UniqueFireIdentifier",
    "attr_IncidentTypeCategory",
    "GlobalID",
]
# a prescribed burn is never reported as a wildfire
INCIDENT_TYPES = {"WF": "wildfire", "RX": "prescribed burn"}


class WfigsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_size: int = Field(default=1000, ge=1, le=2000, description="Layer maxRecordCount is 2000")
    max_offset: float | None = Field(
        default=None,
        gt=0,
        le=0.01,
        description="server-side generalization in degrees (ArcGIS maxAllowableOffset); keeps national pulls small",
    )


class WfigsCurrentConnector(BaseConnector):
    provider_id = "wfigs_current"
    evidence_types = frozenset({EvidenceType.OFFICIAL_PERIMETER})
    Params = WfigsParams

    def build_requests(self, query: ProviderQuery) -> list[ProviderRequest]:
        p: WfigsParams = query.params  # type: ignore[assignment]
        req = arcgis.query_request(bbox=query.get_bbox(), out_fields=OUT_FIELDS, page_size=p.page_size)
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
        observed_at = arcgis.epoch_ms(a.get("poly_PolygonDateTime"))
        updated_at = arcgis.epoch_ms(a.get("poly_DateCurrent"))
        if updated_at is None:
            flags.append("missing_update_time")
        if observed_at is None:
            flags.append("missing_perimeter_time")
            observed_at = updated_at or resp.retrieved_at
        geometry = feature.get("geometry")
        if not geometry:
            flags.append("missing_geometry")
        discovered = arcgis.epoch_ms(a.get("attr_FireDiscoveryDateTime"))
        return self.evidence(
            evidence_type=EvidenceType.OFFICIAL_PERIMETER,
            observed_at=observed_at,
            retrieved_at=resp.retrieved_at,
            geometry=geometry,
            source_record_id=a.get("GlobalID"),
            properties={
                "incident_name": a.get("poly_IncidentName"),
                "gis_acres": a.get("poly_GISAcres"),
                "area_units": "acres",
                "percent_contained": a.get("attr_PercentContained"),
                "feature_category": a.get("poly_FeatureCategory"),
                "map_method": a.get("poly_MapMethod"),
                "irwin_id": a.get("poly_IRWINID"),
                "unique_fire_id": a.get("attr_UniqueFireIdentifier"),
                "origin_state": a.get("attr_POOState"),
                "incident_type_code": a.get("attr_IncidentTypeCategory"),
                "incident_type": INCIDENT_TYPES.get(
                    a.get("attr_IncidentTypeCategory"), a.get("attr_IncidentTypeCategory")
                ),
                "discovered_at": discovered.isoformat() if discovered else None,
                "source_updated_at": updated_at.isoformat() if updated_at else None,  # spec §11.3
            },
            quality_flags=flags,
        )
