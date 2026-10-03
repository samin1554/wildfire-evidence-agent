from inland_worker.connectors.fire.wfigs_history import WfigsHistoryConnector
from inland_worker.kit.testing import ConnectorContract


class TestWfigsHistory(ConnectorContract):
    connector_cls = WfigsHistoryConnector
    query_kwargs = {
        "bbox": (-124.85, 24.39, -66.88, 49.39),
        "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
    }

    def test_query_filters_by_discovery_date_and_size(self):
        c = self.connector()
        (req,) = c.build_requests(
            c.query(**self.query_kwargs, params={"min_acres": 1000, "max_offset": 0.001})
        )
        w = req.params["where"]
        assert "attr_FireDiscoveryDateTime >= TIMESTAMP '2024-01-01 00:00:00'" in w
        assert "attr_FireDiscoveryDateTime < TIMESTAMP '2025-01-01 00:00:00'" in w  # end date inclusive
        assert "poly_GISAcres >= 1000" in w and req.params["maxAllowableOffset"] == "0.001"
        assert "attr_IncidentTypeCategory" in req.params["outFields"]

    def test_no_filters_means_everything(self):
        c = self.connector()
        (req,) = c.build_requests(c.query(bbox=(-110, 35, -100, 45)))
        assert req.params["where"] == "1=1" and "maxAllowableOffset" not in req.params

    async def test_alexander_mountain_fire_is_in_the_recording(self):
        items = (await self.run_fixture("success")).items
        alex = [i for i in items if i.properties["incident_name"] == "Alexander Mountain"]
        assert len(alex) == 1
        p = alex[0].properties
        assert round(p["gis_acres"]) == 9625 and p["incident_type"] == "wildfire"
        assert alex[0].observed_at.date().isoformat() == "2024-07-29"  # discovery date, not the mapping date
        assert any("discovery date" in lim for lim in alex[0].limitations)

    async def test_prescribed_burns_are_labelled(self):
        types = {i.properties["incident_type"] for i in (await self.run_fixture("success")).items}
        assert "wildfire" in types
        assert types <= {"wildfire", "prescribed burn", None}
