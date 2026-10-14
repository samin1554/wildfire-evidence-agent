"""Job runtime against real PostgreSQL/PostGIS + Redis (the `make dev` stack).

Skipped unless TEST_DATABASE_URL and TEST_REDIS_URL are set, e.g.
    TEST_DATABASE_URL=postgres://inland:inland@localhost:55432/inland?sslmode=disable \\
    TEST_REDIS_URL=redis://localhost:56379/14 uv run pytest tests/jobs/test_integration.py
Uses its own Redis db so the stack's worker never sees these messages, and deletes its rows afterwards.
"""

import asyncio
import json
import os
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

DSN, REDIS = os.environ.get("TEST_DATABASE_URL"), os.environ.get("TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(not (DSN and REDIS), reason="TEST_DATABASE_URL / TEST_REDIS_URL not set")

LINE_FIRE = {
    "type": "Polygon",
    "coordinates": [[[-117.15, 34.1], [-116.97, 34.1], [-116.97, 34.21], [-117.15, 34.21], [-117.15, 34.1]]],
}
MARK = "[worker-it]"


@pytest.fixture
def pool():
    from psycopg_pool import ConnectionPool

    p = ConnectionPool(DSN, min_size=1, max_size=4, open=True)
    yield p
    with p.connection() as c:
        c.execute("DELETE FROM analysis_jobs WHERE question LIKE %s", (MARK + "%",))
        c.execute("DELETE FROM provider_fetches WHERE provider_id = 'it_provider'")
    p.close()


@pytest.fixture
async def redis():
    import redis.asyncio as aioredis

    r = aioredis.from_url(REDIS, decode_responses=True)
    await r.flushdb()
    yield r
    await r.flushdb()
    await r.aclose()


def insert_job(pool, question="How badly did it burn?", start="2024-08-01", end="2024-10-31"):
    with pool.connection() as c:
        row = c.execute(
            "INSERT INTO analysis_jobs (area, question, analysis_type, date_start, date_end) "
            "VALUES (ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s, 'historical_fire_impact', %s, %s) "
            "RETURNING id::text, created_at",
            (json.dumps(LINE_FIRE), f"{MARK} {question}", start, end),
        ).fetchone()
    return row[0], row[1]


def payload(job_id, requested_at, question="How badly did it burn?"):
    return json.dumps(
        {
            "schema_version": "1",
            "job_id": job_id,
            "analysis_type": "historical_fire_impact",
            "question": f"{MARK} {question}",
            "area": LINE_FIRE,
            "date_range": {"start": "2024-08-01", "end": "2024-10-31"},
            "requested_at": requested_at.isoformat(),
        }
    )


def deps(pool, redis, tmp_path, **kw):
    from inland_worker.data import DataService
    from inland_worker.jobs.events import RedisEventBus
    from inland_worker.jobs.pg_data import PostgresTraceSink
    from inland_worker.jobs.pipeline import PipelineDeps
    from inland_worker.jobs.store import PostgresJobStore

    return PipelineDeps(
        store=PostgresJobStore(pool),
        bus=RedisEventBus(redis),
        data=DataService(mode="fixture", trace=PostgresTraceSink(pool)),
        artifacts_dir=tmp_path,
        today=date(2026, 9, 24),
        **kw,
    )


async def events(redis, job_id):
    out = []
    for _id, f in await redis.xrange("job-events"):
        ev = json.loads(f["payload"])
        if ev["job_id"] == job_id:
            out.append(ev)
    return out


async def test_runtime_runs_a_job_end_to_end(pool, redis, tmp_path):
    from inland_worker.jobs.runtime import Runtime

    job_id, created = insert_job(pool)
    rt = Runtime(redis, deps(pool, redis, tmp_path), consumer="it", block_ms=100)
    await rt.ensure_group()
    await redis.xadd("jobs", {"payload": payload(job_id, created)})
    assert await rt.consume_once() == 1
    evs = await events(redis, job_id)
    assert [e["status"] for e in evs][-1] == "completed"
    assert [e["seq"] for e in evs] == list(range(1, len(evs) + 1))
    with pool.connection() as c:
        status, seq, attempts = c.execute(
            "SELECT status, last_event_seq, attempts FROM analysis_jobs WHERE id = %s", (job_id,)
        ).fetchone()
        n_ev = c.execute("SELECT count(*) FROM evidence_items WHERE job_id = %s", (job_id,)).fetchone()[0]
        kinds = {r[0] for r in c.execute("SELECT artifact_type FROM artifacts WHERE job_id = %s", (job_id,))}
        traces = c.execute("SELECT count(*) FROM tool_executions WHERE job_id = %s", (job_id,)).fetchone()[0]
    assert (status, seq, attempts) == ("completed", len(evs), 1)
    assert n_ev > 0 and {"report", "layer", "tile_layer"} <= kinds and traces > 0
    assert (await redis.xpending("jobs", "workers"))["pending"] == 0  # acked once terminal

    # the same message delivered again is dropped (already completed) and stores nothing new
    await redis.xadd("jobs", {"payload": payload(job_id, created)})
    await rt.consume_once()
    with pool.connection() as c:
        assert (
            c.execute("SELECT count(*) FROM evidence_items WHERE job_id = %s", (job_id,)).fetchone()[0]
            == n_ev
        )


async def test_malformed_message_goes_to_dead_letter(pool, redis, tmp_path):
    from inland_worker.jobs.runtime import Runtime

    rt = Runtime(redis, deps(pool, redis, tmp_path), consumer="it", block_ms=100)
    await rt.ensure_group()
    await redis.xadd("jobs", {"payload": '{"job_id": "x"}'})
    await rt.consume_once()
    dead = await redis.xrange("jobs-dead")
    assert len(dead) == 1 and "reason" in dead[0][1]
    assert (await redis.xpending("jobs", "workers"))["pending"] == 0


async def test_reaper_reclaims_a_dead_consumers_job(pool, redis, tmp_path):
    from inland_worker.jobs.runtime import Runtime

    job_id, created = insert_job(pool, "reclaim")
    rt = Runtime(
        redis, deps(pool, redis, tmp_path, lease=timedelta(0)), consumer="it", idle_ms=1, block_ms=100
    )
    await rt.ensure_group()
    await redis.xadd("jobs", {"payload": payload(job_id, created, "reclaim")})
    await redis.xreadgroup("workers", "ghost", {"jobs": ">"}, count=1)  # taken, never acked
    await asyncio.sleep(0.05)  # let it go idle past idle_ms
    assert await rt.reap_once() == 1
    with pool.connection() as c:
        assert (
            c.execute("SELECT status FROM analysis_jobs WHERE id = %s", (job_id,)).fetchone()[0]
            == "completed"
        )


async def test_sweep_requeues_jobs_whose_message_was_lost(pool, redis, tmp_path):
    from inland_worker.jobs.runtime import Runtime

    job_id, _ = insert_job(pool, "lost message")
    with pool.connection() as c:
        c.execute("UPDATE analysis_jobs SET updated_at = now() - interval '1 hour' WHERE id = %s", (job_id,))
    rt = Runtime(redis, deps(pool, redis, tmp_path), consumer="it", sweep_after=timedelta(minutes=5))
    assert await rt.sweep_once() >= 1
    msgs = [json.loads(f["payload"]) for _id, f in await redis.xrange("jobs")]
    assert any(m["job_id"] == job_id and m["area"]["type"] == "MultiPolygon" for m in msgs)
    assert await rt.sweep_once() == 0  # touched: not re-sent on the next sweep


def test_guarded_transitions_in_postgres(pool):
    from inland_worker.contracts.models import JobStatus as S
    from inland_worker.jobs.states import IllegalTransition
    from inland_worker.jobs.store import PostgresJobStore

    store = PostgresJobStore(pool)
    job_id, _ = insert_job(pool, "guard")
    with pytest.raises(IllegalTransition):
        store.transition(job_id, S.COMPLETED)
    assert store.begin(job_id, lease=timedelta(0)).action == "run"
    ev = store.transition(job_id, S.VALIDATING)
    assert ev.seq == 1 and ev.progress == 5
    store.transition(job_id, S.CANCELLED)
    with pytest.raises(IllegalTransition):
        store.transition(job_id, S.VALIDATING)
    assert store.begin(job_id, lease=timedelta(0)).action == "skip"


def test_postgres_cache_keeps_last_good_snapshot(pool):
    from inland_worker.contracts.models import Evidence
    from inland_worker.data.cache import CacheEntry
    from inland_worker.jobs.pg_data import PostgresCacheStore

    cache = PostgresCacheStore(pool)
    key = f"it_provider:{uuid.uuid4().hex[:8]}"
    assert cache.get(key) is None
    now = datetime.now(UTC)
    ev = Evidence(
        id="e1",
        evidence_type="satellite_detection",
        source="test",
        observed_at=now,
        retrieved_at=now,
        geometry={"type": "Point", "coordinates": [-117, 34]},
        properties={},
        quality_flags=[],
        limitations=["test"],
        source_url="https://example.org",
    )
    for n in (1, 2):
        cache.put(
            CacheEntry(
                provider_id="it_provider",
                cache_key=key,
                items=[ev] * n,
                fetched_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
    got = cache.get(key)
    assert got is not None and len(got.items) == 2 and got.items[0].id == "e1"


async def test_activity_history_trends_and_retention(pool, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from inland_worker.activity import trends
    from inland_worker.activity.snapshot import build_snapshot
    from inland_worker.activity.store import history, save_snapshot, update_cells
    from inland_worker.data import DataService

    # one satellite's recording (NOAA-21, Sep 20-23 2026) so every detection predates the simulated clock, and
    # the simulated snapshots stay older than the stack's real ones (pruning never touches those)
    monkeypatch.setattr("inland_worker.activity.snapshot.SATELLITES", {"VIIRS_NOAA21_NRT": "success"})
    snap = await build_snapshot(DataService(mode="fixture"))
    cells = [c for cl in snap["clusters"] for c in cl["cells"]]
    xs = [(int(k.split("_")[0]), int(k.split("_")[1])) for k in cells]
    with pool.connection() as c:  # start from a clean history for these cells only
        for x, y in xs:
            c.execute("DELETE FROM activity_cells WHERE cell_x = %s AND cell_y = %s", (x, y))
    t0 = datetime(2026, 9, 24, 12, tzinfo=UTC)
    ids = []
    try:
        # first refresh: nothing known yet → every cluster is new, history still building
        s1 = {**snap, "generated_at": t0.isoformat()}
        h1, have = history(pool, s1["clusters"], s1["generated_at"])
        assert not have and all(not h.seen_before_24h for h in h1.values())  # None (empty table) or False
        trends.apply(s1["clusters"], h1)
        statuses = {(cl["trend"] or {}).get("status") for cl in s1["clusters"]}
        assert statuses <= {"new", None}  # never growing/shrinking without history
        ids.append(save_snapshot(pool, s1))
        update_cells(pool, snap["_cells"], now=s1["generated_at"])
        # 24 h later, same detections: seen before, compared with yesterday → stable
        s2 = {**snap, "generated_at": (t0 + timedelta(hours=24)).isoformat()}
        h2, have = history(pool, s2["clusters"], s2["generated_at"])
        assert have and all(h.seen_before_24h for h in h2.values())
        top = s2["clusters"][0]
        assert h2[top["id"]].detections_24h_ago == top["detections"]
        assert trends.trend(top["detections"], h2[top["id"]])["status"] == "stable"
        ids.append(save_snapshot(pool, s2))
        update_cells(pool, snap["_cells"], now=s2["generated_at"])  # same days again: a set, not a counter
        with pool.connection() as c:
            days = c.execute(
                "SELECT max(cardinality(days)) FROM activity_cells WHERE cell_x = %s AND cell_y = %s", xs[0]
            ).fetchone()[0]
        assert days == len(snap["_cells"][cells[0]]["days"])
        # 20 days on, those days fall outside the 14-day window but the cell is kept (retention is 30 days)
        update_cells(
            pool,
            {cells[0]: {**snap["_cells"][cells[0]], "count": 0}},
            now=(t0 + timedelta(days=20)).isoformat(),
        )
        with pool.connection() as c:
            days = c.execute(
                "SELECT cardinality(days) FROM activity_cells WHERE cell_x = %s AND cell_y = %s", xs[0]
            ).fetchone()[0]
        assert days == 0
        # 3 days later: the first snapshot (> 48 h old) is pruned, the newest kept
        ids.append(save_snapshot(pool, {**snap, "generated_at": (t0 + timedelta(hours=72)).isoformat()}))
        with pool.connection() as c:
            kept = {r[0] for r in c.execute("SELECT id FROM activity_snapshots WHERE id = ANY(%s)", (ids,))}
        assert ids[0] not in kept and ids[2] in kept
    finally:
        with pool.connection() as c:
            c.execute("DELETE FROM activity_snapshots WHERE id = ANY(%s)", (ids,))
