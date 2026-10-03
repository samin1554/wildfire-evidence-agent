"""NASA FIRMS Area API: satellite thermal detections.

REFERENCE CONNECTOR for the *keyed API* pattern (CSV/JSON + API key). Copy it for CIMIS, AirNow, ...
    make new-connector NAME=<id> GROUP=<fire|weather> PATTERN=keyed

What makes this pattern tricky, and how it's handled here:
- The key is a path placeholder `{MAP_KEY}`: the kit fills it from FIRMS_MAP_KEY and redacts it everywhere.
- acq_date + acq_time (HHMM, UTC) become one timezone-aware `observed_at`.
- Confidence differs by sensor, so the raw value is kept plus a normalized one and its scheme.
Spec: docs/connectors/providers/firms.md
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from inland_worker.contracts.models import Evidence, EvidenceType
from inland_worker.kit.connector import BaseConnector, ProviderQuery, ProviderRequest, RawResponse
from inland_worker.kit.errors import ProviderParseError

REQUIRED_COLUMNS = {"latitude", "longitude", "acq_date", "acq_time", "satellite", "instrument", "confidence"}
VIIRS_CONFIDENCE = {"l": "low", "n": "nominal", "h": "high"}


class FirmsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["VIIRS_NOAA21_NRT", "VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT", "LANDSAT_NRT"] = (
        "VIIRS_NOAA21_NRT"
    )
    days: int = Field(default=2, ge=1, le=5, description="FIRMS Area API day range is 1-5")
    date: dt.date | None = Field(
        default=None, description="first day of the range (YYYY-MM-DD); omitted = the most recent `days`"
    )


class FirmsConnector(BaseConnector):
    provider_id = "firms"
    evidence_types = frozenset({EvidenceType.SATELLITE_DETECTION})
    Params = FirmsParams

    # 1. What to ask -------------------------------------------------------------------------------
    def build_requests(self, query: ProviderQuery) -> list[ProviderRequest]:
        p: FirmsParams = query.params  # type: ignore[assignment]
        w, s, e, n = (f"{v:.4f}" for v in query.get_bbox())
        # {MAP_KEY} is replaced by the kit; never put the key in code
        path = f"/{{MAP_KEY}}/{p.source}/{w},{s},{e},{n}/{p.days}"
        if p.date is not None:
            path += f"/{p.date.isoformat()}"  # a past window instead of the last `days`
        return [ProviderRequest(path=path, expect="text")]

    # 2. Translate the answer ------------------------------------------------------------------------
    def parse(self, responses: Sequence[RawResponse], query: ProviderQuery) -> list[Evidence]:
        resp = responses[0]
        text = resp.text().strip()
        if not text:
            return []
        reader = csv.DictReader(io.StringIO(text))
        columns = set(reader.fieldnames or [])
        if not columns >= REQUIRED_COLUMNS:
            # FIRMS reports some errors (e.g. an invalid key) as plain text with HTTP 200
            first_line = text.splitlines()[0][:80]
            raise ProviderParseError(self.provider_id, f"unexpected response, not FIRMS CSV: {first_line!r}")
        return [self._row(row, resp.retrieved_at) for row in reader]

    def _row(self, row: dict[str, str], retrieved_at: datetime) -> Evidence:
        lat, lon = float(row["latitude"]), float(row["longitude"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"coordinates out of range: {lat}, {lon}")
        hhmm = row["acq_time"].strip().zfill(4)
        observed_at = datetime.strptime(f"{row['acq_date']} {hhmm}", "%Y-%m-%d %H%M").replace(tzinfo=UTC)

        raw_conf = row["confidence"].strip()
        instrument = row["instrument"].strip()
        if instrument.upper() == "VIIRS":
            scheme, confidence = "viirs_category", VIIRS_CONFIDENCE.get(raw_conf.lower(), raw_conf)
        else:
            scheme, confidence = "raw", raw_conf

        flags: list[str] = []
        if confidence == "low":
            flags.append("low_confidence")
        frp = float(row["frp"]) if row.get("frp") not in (None, "") else None
        if frp is None:
            flags.append("missing_frp")

        return self.evidence(
            evidence_type=EvidenceType.SATELLITE_DETECTION,
            observed_at=observed_at,
            retrieved_at=retrieved_at,
            geometry={"type": "Point", "coordinates": [lon, lat]},  # GeoJSON is [longitude, latitude]
            source_record_id=f"{row['satellite']}:{observed_at:%Y-%m-%dT%H%MZ}:{lat:.5f},{lon:.5f}",
            properties={
                "satellite": row["satellite"],
                "instrument": instrument,
                "confidence": confidence,
                "confidence_raw": raw_conf,
                "confidence_scheme": scheme,
                "frp": frp,
                "frp_units": "MW",
                "daynight": row.get("daynight") or None,
                "product_version": row.get("version") or None,
            },
            quality_flags=flags,
        )
