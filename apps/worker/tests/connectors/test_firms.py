from datetime import UTC, datetime

import pytest

from inland_worker.connectors.fire.firms import FirmsConnector
from inland_worker.kit import ProviderParseError
from inland_worker.kit.connector import ProviderRequest, RawResponse
from inland_worker.kit.testing import ConnectorContract


class TestFirms(ConnectorContract):
    connector_cls = FirmsConnector
    query_kwargs = {"bbox": (-117.8, 33.8, -114.1, 35.9), "params": {"source": "VIIRS_NOAA21_NRT", "days": 2}}

    def test_request_uses_key_placeholder_and_bbox(self):
        c = self.connector()
        (req,) = c.build_requests(self.query(c))
        assert req.path == "/{MAP_KEY}/VIIRS_NOAA21_NRT/-117.8000,33.8000,-114.1000,35.9000/2"

    def test_days_outside_1_to_5_rejected_before_any_call(self):
        c = self.connector()
        with pytest.raises(ValueError):
            c.query(bbox=(-117.8, 33.8, -114.1, 35.9), params={"days": 6})

    async def test_rows_map_to_evidence_exactly(self):
        """Every CSV row becomes one item: [lon, lat] order, UTC time from acq_date+acq_time, raw values kept."""
        import csv
        import io

        from inland_worker.kit import FixtureStore

        raw = FixtureStore().load("firms", "success")[0].text()
        rows = list(csv.DictReader(io.StringIO(raw)))
        items = (await self.run_fixture("success")).items
        assert len(items) == len(rows) > 0
        for row, item in zip(rows, items, strict=True):
            assert item.geometry.coordinates == [float(row["longitude"]), float(row["latitude"])]
            hhmm = row["acq_time"].zfill(4)
            assert item.observed_at.strftime("%Y-%m-%d %H%M") == f"{row['acq_date']} {hhmm}"
            assert item.observed_at.utcoffset().total_seconds() == 0
            assert item.properties["confidence_raw"] == row["confidence"]
            assert item.properties["frp_units"] == "MW"

    def test_confidence_and_flag_rules(self):
        c = self.connector()
        header = "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp,daynight\n"
        body = (
            header
            + "34.1,-117.1,2026-09-22,948,N21,VIIRS,l,,N\n34.2,-117.2,2026-09-22,0948,N21,VIIRS,h,12.5,D\n"
        )
        resp = RawResponse(
            request=ProviderRequest(),
            url="x",
            status=200,
            body=body.encode(),
            retrieved_at=datetime(2026, 9, 23, tzinfo=UTC),
        )
        low, high = c.parse([resp], self.query(c))
        assert low.observed_at == datetime(2026, 9, 22, 9, 48, tzinfo=UTC)  # "948" is zero-padded to 09:48
        assert (
            low.properties["confidence"] == "low" and low.properties["confidence_scheme"] == "viirs_category"
        )
        assert {"low_confidence", "missing_frp"} <= set(low.quality_flags)
        assert high.properties["confidence"] == "high" and high.quality_flags == []

    def test_invalid_key_text_is_a_parse_error(self):
        c = self.connector()
        resp = RawResponse(
            request=ProviderRequest(),
            url="x",
            status=200,
            body=b"Invalid MAP_KEY.",
            retrieved_at=datetime.now(UTC),
        )
        with pytest.raises(ProviderParseError):
            c.parse([resp], self.query(c))


def test_past_window_by_date():
    from inland_worker.connectors.fire.firms import FirmsConnector
    from inland_worker.kit.config import load_providers

    c = FirmsConnector(load_providers().get("firms"))
    (req,) = c.build_requests(c.query(bbox=(-118, 34, -117, 35), params={"days": 5, "date": "2026-09-20"}))
    assert req.path.endswith("/-118.0000,34.0000,-117.0000,35.0000/5/2026-09-20")
    (req,) = c.build_requests(c.query(bbox=(-118, 34, -117, 35)))
    assert req.path.endswith("/2")
