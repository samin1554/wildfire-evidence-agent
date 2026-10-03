from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from inland_worker.data import DataService, MemoryCacheStore, MemoryTraceSink
from inland_worker.kit import FixtureStore, KitHttpClient, load_providers

WFIGS_BBOX = (-124.5, 32.5, -114.1, 42.0)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 23, 18, 0, tzinfo=UTC)

    def __call__(self):
        return self.now


def recorded_route(router):
    rec = FixtureStore().load("wfigs_current", "success")[0]
    return router.route().mock(return_value=httpx.Response(200, content=rec.body))


@pytest.fixture
def svc():
    clock = Clock()

    def client(connector):
        cfg = connector.config.model_copy(deep=True)
        cfg.retries.backoff_s = 0
        return KitHttpClient(cfg, env={})

    s = DataService(
        registry=load_providers(),
        cache=MemoryCacheStore(),
        trace=MemoryTraceSink(),
        mode="live",
        client_factory=client,
        clock=clock,
    )
    s.test_clock = clock
    return s


async def test_live_then_cache_hit(svc):
    with respx.mock() as router:
        route = recorded_route(router)
        first = await svc.get_evidence("wfigs_current", bbox=WFIGS_BBOX)
        second = await svc.get_evidence("wfigs_current", bbox=WFIGS_BBOX)
    assert (first.origin, second.origin) == ("live", "cache")
    assert route.call_count == 1 and first.freshness.kind == "fresh" and len(first.items) == 9


async def test_expired_cache_refetches(svc):
    with respx.mock() as router:
        route = recorded_route(router)
        await svc.get_evidence("wfigs_current", bbox=WFIGS_BBOX)
        svc.test_clock.now += timedelta(minutes=31)  # ttl is 30m
        again = await svc.get_evidence("wfigs_current", bbox=WFIGS_BBOX)
    assert again.origin == "live" and route.call_count == 2


async def test_provider_down_serves_last_good_snapshot_flagged_stale(svc):
    with respx.mock() as router:
        recorded_route(router)
        await svc.get_evidence("wfigs_current", bbox=WFIGS_BBOX)
    svc.test_clock.now += timedelta(hours=2)
    with respx.mock() as router:
        router.route().mock(return_value=httpx.Response(503))
        stale = await svc.get_evidence("wfigs_current", bbox=WFIGS_BBOX)
    assert stale.origin == "snapshot" and stale.freshness.kind == "stale"
    assert stale.freshness.age_s == 7200 and stale.freshness.reason == "PROVIDER_HTTP_ERROR"
    assert all("stale_snapshot" in i.quality_flags for i in stale.items)


async def test_provider_down_and_no_snapshot_is_missing_not_empty_success(svc):
    with respx.mock() as router:
        router.route().mock(side_effect=httpx.ConnectTimeout("down"))
        result = await svc.get_evidence("wfigs_current", bbox=WFIGS_BBOX)
    assert result.items == [] and result.freshness.kind == "missing" and not result.ok
    assert result.freshness.reason == "PROVIDER_TIMEOUT"


async def test_force_live_bypasses_fresh_cache(svc):
    with respx.mock() as router:
        route = recorded_route(router)
        await svc.get_evidence("wfigs_current", bbox=WFIGS_BBOX)
        await svc.get_evidence("wfigs_current", bbox=WFIGS_BBOX, force_live=True)
    assert route.call_count == 2


async def test_trace_records_every_call_and_job_id_is_attached(svc):
    with respx.mock() as router:
        recorded_route(router)
        result = await svc.get_evidence("wfigs_current", bbox=WFIGS_BBOX, job_id="analysis_1")
    assert all(i.job_id == "analysis_1" for i in result.items)
    (rec,) = svc.trace.records
    assert rec.tool_name == "get_evidence:wfigs_current" and rec.status == "ok" and rec.job_id == "analysis_1"
    assert rec.output_summary["count"] == 9


async def test_default_area_used_when_none_given():
    s = DataService(mode="fixture")
    result = await s.get_evidence("firms")  # providers.yaml: default_area ca_bbox
    assert result.origin == "fixture" and result.items


async def test_unknown_params_rejected_before_any_call():
    with pytest.raises(ValueError):
        await DataService(mode="fixture").get_evidence("firms", params={"dayz": 3})


async def test_reference_layer_is_geojson():
    fc = await DataService(mode="fixture").get_reference_layer("wfigs_current", bbox=WFIGS_BBOX)
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 9
    assert fc["features"][0]["geometry"]["type"] in {"Polygon", "MultiPolygon"}
