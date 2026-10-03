"""National Weather Service active alerts (watches, warnings, advisories) for a point, e.g. Red Flag Warnings.

Same host and headers as the `nws_forecast` reference (weather/nws_forecast.py); one request, no links to follow:
`GET /alerts/active?point={lat},{lon}` answers with every alert in effect where the area's representative point is.
Owner: Section 5 (demo version by the lead).

- `observed_at` is when the alert was sent; onset/expiry are kept as properties.
- Many alerts are zone-based and carry no polygon (`geometry: null`); the zone list is kept so it's traceable.
- An alert is official weather information, never evacuation guidance from this tool.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from inland_worker.contracts.models import Evidence, EvidenceType
from inland_worker.kit.connector import BaseConnector, ProviderQuery, ProviderRequest, RawResponse

FIRE_WEATHER = {"Red Flag Warning", "Fire Weather Watch", "Extreme Fire Danger", "Fire Warning"}


class NwsAlertsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class NwsAlertsConnector(BaseConnector):
    provider_id = "nws_alerts"
    evidence_types = frozenset({EvidenceType.WEATHER_ALERT})
    Params = NwsAlertsParams

    def build_requests(self, query: ProviderQuery) -> list[ProviderRequest]:
        lon, lat = query.representative_point()
        return [
            ProviderRequest(path="/alerts/active", params={"point": f"{lat:.4f},{lon:.4f}"}, label="alerts")
        ]

    def parse(self, responses: Sequence[RawResponse], query: ProviderQuery) -> list[Evidence]:
        items: list[Evidence] = []
        for resp in responses:
            lat, lon = (float(v) for v in resp.request.params["point"].split(","))
            payload = resp.json()
            if payload.get("type") != "FeatureCollection" or "features" not in payload:
                raise ValueError("NWS alerts response is not a FeatureCollection")
            for f in payload["features"]:
                p = f.get("properties") or {}
                sent = _time(p.get("sent")) or resp.retrieved_at
                event = p.get("event")
                flags = [] if f.get("geometry") else ["zone_based_no_polygon"]
                items.append(
                    self.evidence(
                        evidence_type=EvidenceType.WEATHER_ALERT,
                        observed_at=sent,
                        retrieved_at=resp.retrieved_at,
                        geometry=f.get("geometry"),
                        source_record_id=p.get("id") or f.get("id"),
                        properties={
                            "event": event,
                            "fire_weather": event in FIRE_WEATHER,
                            "severity": p.get("severity"),
                            "certainty": p.get("certainty"),
                            "urgency": p.get("urgency"),
                            "headline": p.get("headline"),
                            "area_desc": p.get("areaDesc"),
                            "onset": p.get("onset"),
                            "ends": p.get("ends") or p.get("expires"),
                            "sender": p.get("senderName"),
                            "zones": [z.rsplit("/", 1)[-1] for z in p.get("affectedZones") or []],
                            # zone-based alerts have no polygon: this is the point they were confirmed for
                            "queried_point": [lon, lat],
                        },
                        quality_flags=flags,
                    )
                )
        return items
