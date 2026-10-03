"""Persist activity snapshots (database/migrations/0003_activity) and keep only the newest few."""

from __future__ import annotations

import json
from typing import Any

KEEP = 10


def save_snapshot(pool: Any, snap: dict[str, Any], *, keep: int = KEEP) -> int:
    with pool.connection() as conn, conn.transaction():
        sid = conn.execute(
            """INSERT INTO activity_snapshots (generated_at, data_mode, window_days, detections_considered,
                 sources, limitations, cluster_count)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                snap["generated_at"],
                snap["data_mode"],
                snap["window_days"],
                snap["detections_considered"],
                json.dumps(snap["sources"]),
                snap["limitations"],
                len(snap["clusters"]),
            ),
        ).fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO activity_clusters (snapshot_id, id, rank, label, centroid, footprint, suggested_area,
                     detections, high_confidence, max_frp, total_frp, first_seen, last_seen, satellites, official)
                   VALUES (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                     ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                     %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (
                        sid,
                        c["id"],
                        c["rank"],
                        c["label"],
                        json.dumps(c["centroid"]),
                        json.dumps(c["footprint"]),
                        json.dumps(c["suggested_area"]),
                        c["detections"],
                        c["high_confidence"],
                        c["max_frp"],
                        c["total_frp"],
                        c["first_seen"],
                        c["last_seen"],
                        c["satellites"],
                        json.dumps(c["official"]) if c["official"] else None,
                    )
                    for c in snap["clusters"]
                ],
            )
        conn.execute(
            "DELETE FROM activity_snapshots WHERE id NOT IN "
            "(SELECT id FROM activity_snapshots ORDER BY generated_at DESC, id DESC LIMIT %s)",
            (keep,),
        )
    return sid
