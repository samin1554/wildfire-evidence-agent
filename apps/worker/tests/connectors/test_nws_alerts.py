from inland_worker.connectors.weather.nws_alerts import NwsAlertsConnector
from inland_worker.kit.testing import ConnectorContract


class TestNwsAlerts(ConnectorContract):
    connector_cls = NwsAlertsConnector
    query_kwargs = {"bbox": (-96.3, 44.4, -96.2, 44.5)}

    def test_queries_the_area_point(self):
        c = self.connector()
        (req,) = c.build_requests(self.query(c))
        assert req.path == "/alerts/active" and req.params["point"] == "44.4500,-96.2500"

    async def test_recorded_alert_is_mapped(self):
        (item,) = (await self.run_fixture("success")).items
        p = item.properties
        assert p["event"] == "Wind Advisory" and p["fire_weather"] is False
        assert "MNZ071" in p["zones"]  # Lincoln County, MN
        assert item.geometry is None and "zone_based_no_polygon" in item.quality_flags
        assert any("official" in lim or "officials" in lim for lim in item.limitations)

    async def test_no_alerts_is_an_empty_list(self):
        assert (await self.run_fixture("empty")).items == []
