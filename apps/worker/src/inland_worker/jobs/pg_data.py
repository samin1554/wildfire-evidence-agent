"""PostgreSQL implementations of the data layer's CacheStore and TraceSink protocols (ADR-006, spec §10).

They plug into DataService unchanged: `DataService(cache=PostgresCacheStore(pool), trace=PostgresTraceSink(pool))`.
"""

from __future__ import annotations

import json
from typing import Any

from inland_worker.contracts.models import Evidence
from inland_worker.data.cache import CacheEntry
from inland_worker.data.trace import ToolExecution


class PostgresCacheStore:
    def __init__(self, pool: Any):
        self.pool = pool

    def get(self, cache_key: str) -> CacheEntry | None:
        with self.pool.connection() as conn:
            head = conn.execute(
                "SELECT id, provider_id, fetched_at, expires_at FROM provider_fetches "
                "WHERE cache_key = %s AND is_last_good ORDER BY fetched_at DESC LIMIT 1",
                (cache_key,),
            ).fetchone()
            if head is None:
                return None
            rows = conn.execute(
                "SELECT evidence FROM cached_evidence WHERE fetch_id = %s ORDER BY ord", (head[0],)
            ).fetchall()
        return CacheEntry(
            provider_id=head[1],
            cache_key=cache_key,
            items=[Evidence.model_validate(r[0]) for r in rows],
            fetched_at=head[2],
            expires_at=head[3],
        )

    def put(self, entry: CacheEntry) -> None:
        with self.pool.connection() as conn, conn.transaction():
            fetch_id = conn.execute(
                "INSERT INTO provider_fetches (provider_id, cache_key, fetched_at, expires_at, item_count) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (entry.provider_id, entry.cache_key, entry.fetched_at, entry.expires_at, len(entry.items)),
            ).fetchone()[0]
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO cached_evidence (fetch_id, ord, evidence, geometry) "
                    "VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))",
                    [
                        (
                            fetch_id,
                            i,
                            item.model_dump_json(),
                            item.geometry.model_dump_json() if item.geometry else None,
                        )
                        for i, item in enumerate(entry.items)
                    ],
                )
            # keep only the newest snapshot as last-good for this key; older fetches stay for audit
            conn.execute(
                "UPDATE provider_fetches SET is_last_good = false WHERE cache_key = %s AND id <> %s",
                (entry.cache_key, fetch_id),
            )


class PostgresTraceSink:
    def __init__(self, pool: Any):
        self.pool = pool

    def record(self, execution: ToolExecution) -> None:
        d = execution.model_dump(mode="json")
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO tool_executions (job_id, tool_name, input, output_summary, status, error_code, "
                "started_at, completed_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    d["job_id"],
                    d["tool_name"],
                    json.dumps(d["input"], default=str),
                    json.dumps(d["output_summary"], default=str),
                    d["status"],
                    d["error_code"],
                    d["started_at"],
                    d["completed_at"],
                ),
            )
