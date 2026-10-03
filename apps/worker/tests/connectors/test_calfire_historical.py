from datetime import date

from inland_worker.connectors.fire.calfire_historical import CalfireHistoricalConnector
from inland_worker.kit.testing import ConnectorContract


class TestCalfireHistorical(ConnectorContract):
    connector_cls = CalfireHistoricalConnector
    query_kwargs = {
        "bbox": (-117.8, 33.8, -114.1, 35.9),
        "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
    }

    def test_query_filters_by_fire_year(self):
        c = self.connector()
        (req,) = c.build_requests(self.query(c))
        assert req.params["where"] == "YEAR_ >= 2024 AND YEAR_ <= 2024"
        assert req.params["f"] == "geojson" and req.params["outSR"] == "4326"

    def test_query_without_dates_uses_min_year(self):
        c = self.connector()
        (req,) = c.build_requests(c.query(bbox=(-117.8, 33.8, -114.1, 35.9), params={"min_year": 2015}))
        assert req.params["where"] == "YEAR_ >= 2015"

    async def test_line_fire_is_in_the_recording(self):
        items = (await self.run_fixture("success")).items
        line = [i for i in items if i.properties["fire_name"] == "LINE"]
        assert len(line) == 1
        p = line[0].properties
        assert p["year"] == 2024 and round(p["gis_acres"]) == 43976 and p["area_units"] == "acres"
        assert line[0].observed_at.date() == date.fromisoformat(p["alarm_date"])
        assert any("alarm" in lim for lim in line[0].limitations)
