import json
from datetime import UTC, datetime

import pytest

from inland_worker.connectors.fire.wfigs import WfigsCurrentConnector
from inland_worker.kit.connector import ProviderRequest, RawResponse
from inland_worker.kit.testing import ConnectorContract


class TestWfigsCurrent(ConnectorContract):
    connector_cls = WfigsCurrentConnector
    query_kwargs = {"bbox": (-124.5, 32.5, -114.1, 42.0)}

    def test_query_is_paged_and_ordered(self):
        c = self.connector()
        (req,) = c.build_requests(self.query(c))
        assert req.path == "/query"
        assert req.params["resultOffset"] == "0" and req.params["orderByFields"] == "OBJECTID"
        assert req.params["f"] == "geojson" and req.params["outSR"] == "4326"

    def test_generalization_is_opt_in(self):
        c = self.connector()
        (req,) = c.build_requests(self.query(c))
        assert "maxAllowableOffset" not in req.params
        (req,) = c.build_requests(
            c.query(bbox=(-125, 24, -66, 50), params={"max_offset": 0.001, "page_size": 250})
        )
        assert req.params["maxAllowableOffset"] == "0.001" and req.params["resultRecordCount"] == "250"

    def test_follow_requests_next_page_only_when_exceeded(self):
        c = self.connector()
        (req,) = c.build_requests(self.query(c))

        def resp(payload):
            return RawResponse(
                request=req,
                url="u",
                status=200,
                body=json.dumps(payload).encode(),
                retrieved_at=datetime.now(UTC),
            )

        assert c.follow(resp({"features": []}), self.query(c)) == []
        (nxt,) = c.follow(
            resp({"features": [], "properties": {"exceededTransferLimit": True}}), self.query(c)
        )
        assert nxt.params["resultOffset"] == req.params["resultRecordCount"]

    async def test_source_update_time_kept_on_every_feature(self):
        for item in (await self.run_fixture("success")).items:
            assert item.properties["source_updated_at"] is not None  # spec §11.3
            assert item.properties["area_units"] == "acres"

    def test_arcgis_error_body_is_rejected(self):
        # ArcGIS reports errors with HTTP 200; the runner turns this ValueError into ProviderParseError
        c = self.connector()
        body = json.dumps({"error": {"code": 400, "message": "Invalid query"}}).encode()
        resp = RawResponse(
            request=ProviderRequest(), url="u", status=200, body=body, retrieved_at=datetime.now(UTC)
        )
        with pytest.raises(ValueError, match="ArcGIS error"):
            c.parse([resp], self.query(c))
