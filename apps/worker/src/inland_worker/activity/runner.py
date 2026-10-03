"""`python -m inland_worker activity [--once]`: refresh the activity snapshot on a schedule (ADR-001 ingest mode)."""

from __future__ import annotations

import asyncio
import logging
import os

from inland_worker.activity import trends
from inland_worker.activity.snapshot import build_snapshot, public
from inland_worker.activity.store import history, save_snapshot, update_cells

log = logging.getLogger("inland_worker.activity")
DEFAULT_INTERVAL_S = 1800  # providers.yaml firms.ingestion.schedule is every 30 minutes


HISTORY_NOTE = "History is still building: trends need a snapshot from about 24 hours ago."


async def refresh_once(pool, data) -> dict:
    snap = await build_snapshot(data)
    # history first (what was known before this refresh), then record this refresh's cells
    hist, have_24h = history(pool, snap["clusters"], snap["generated_at"])
    trends.apply(snap["clusters"], hist)
    if not have_24h:
        snap["limitations"].append(HISTORY_NOTE)
    sid = save_snapshot(pool, snap)
    update_cells(pool, snap["_cells"])
    log.info(
        "activity snapshot %s: %d clusters from %d detections (%s)",
        sid,
        len(snap["clusters"]),
        snap["detections_considered"],
        snap["data_mode"],
    )
    return public(snap)


async def serve(once: bool = False) -> None:
    from inland_worker.data import DataService
    from inland_worker.jobs.pg_data import PostgresCacheStore, PostgresTraceSink
    from inland_worker.jobs.store import PostgresJobStore

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        raise SystemExit("DATABASE_URL must be set (see .env.example)")
    pool = PostgresJobStore.connect(dsn).pool
    data = DataService(cache=PostgresCacheStore(pool), trace=PostgresTraceSink(pool))
    interval = int(os.environ.get("ACTIVITY_REFRESH_S", DEFAULT_INTERVAL_S))
    while True:
        try:
            await refresh_once(pool, data)
        except Exception:
            log.exception("activity refresh failed; the previous snapshot stays in place")
        if once:
            return
        await asyncio.sleep(interval)
