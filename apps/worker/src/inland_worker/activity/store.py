"""Persist activity snapshots and their history (migrations 0003 + 0004)."""

from __future__ import annotations

import json
from typing import Any

from inland_worker.activity.trends import PERSISTENT_WINDOW_DAYS, History

KEEP_HOURS = 48  # enough to compare with ~24 h ago; the newest snapshot is always kept
COMPARE_HOURS, COMPARE_SLACK_HOURS = 24, 6
CELL_RETENTION_DAYS = 30


def history(pool: Any, clusters: list[dict[str, Any]], generated_at: str) -> tuple[dict[str, History], bool]:
    """Per cluster id: was it seen before the last 24 h, how many detections ~24 h ago, on how many recent days.
    Second value: whether a ~24 h-old snapshot existed (if not, history is still building)."""
    out: dict[str, History] = {}
    with pool.connection() as conn:
        prev = conn.execute(
            """SELECT id FROM activity_snapshots
               WHERE generated_at BETWEEN %(t)s::timestamptz - make_interval(hours => %(h)s + %(s)s)
                                     AND %(t)s::timestamptz - make_interval(hours => %(h)s - %(s)s)
               ORDER BY abs(extract(epoch FROM (generated_at - (%(t)s::timestamptz - make_interval(hours => %(h)s)))))
               LIMIT 1""",
            {"t": generated_at, "h": COMPARE_HOURS, "s": COMPARE_SLACK_HOURS},
        ).fetchone()
        prev_id = prev[0] if prev else None
        any_history = conn.execute("SELECT EXISTS (SELECT 1 FROM activity_cells)").fetchone()[0]
        for c in clusters:
            cells = c["cells"]
            seen, days = conn.execute(
                """SELECT coalesce(bool_or(first_seen < %(t)s::timestamptz - interval '24 hours'), false),
                          coalesce(max(cardinality(array(
                              SELECT d FROM unnest(days) d WHERE d > (%(t)s::timestamptz)::date - %(w)s))), 0)
                   FROM activity_cells
                   WHERE (cell_x::text || '_' || cell_y::text) = ANY(%(cells)s)""",
                {"t": generated_at, "w": PERSISTENT_WINDOW_DAYS, "cells": cells},
            ).fetchone()
            ago = None
            if prev_id is not None:
                ago = conn.execute(
                    "SELECT coalesce(sum(detections), 0) FROM activity_clusters "
                    "WHERE snapshot_id = %s AND cells && %s",
                    (prev_id, cells),
                ).fetchone()[0]
            out[c["id"]] = History(
                seen_before_24h=bool(seen) if any_history else None,
                detections_24h_ago=ago,
                days_seen=int(days),
            )
    return out, prev_id is not None


def update_cells(pool: Any, cells: dict[str, dict[str, Any]], *, now: str | None = None) -> None:
    """Record where heat was seen and on which UTC days (days older than 14 are dropped; idle cells pruned).

    `now` (ISO timestamp) is the clock both windows are measured from; default: the database's clock.
    """
    rows = []
    for key, e in cells.items():
        x, y = (int(v) for v in key.split("_"))
        rows.append((x, y, e["first"], e["last"], sorted(e["days"]), e["count"], now))
    with pool.connection() as conn, conn.transaction():
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO activity_cells (cell_x, cell_y, first_seen, last_seen, days, detections_total)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (cell_x, cell_y) DO UPDATE SET
                     first_seen = least(activity_cells.first_seen, EXCLUDED.first_seen),
                     last_seen = greatest(activity_cells.last_seen, EXCLUDED.last_seen),
                     days = array(SELECT DISTINCT d FROM unnest(activity_cells.days || EXCLUDED.days) d
                                  WHERE d > coalesce(%s::timestamptz, now())::date - 14 ORDER BY d),
                     detections_total = activity_cells.detections_total + EXCLUDED.detections_total""",
                rows,
            )
        conn.execute(
            "DELETE FROM activity_cells WHERE last_seen < coalesce(%s::timestamptz, now()) - make_interval(days => %s)",
            (now, CELL_RETENTION_DAYS),
        )


def save_snapshot(pool: Any, snap: dict[str, Any], *, keep_hours: int = KEEP_HOURS) -> int:
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

        def js(v):
            return json.dumps(v) if v is not None else None

        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO activity_clusters (snapshot_id, id, rank, label, centroid, footprint, suggested_area,
                     detections, high_confidence, max_frp, total_frp, first_seen, last_seen, satellites, official,
                     cells, place, nearest_official, trend, persistent_heat_source, days_seen)
                   VALUES (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                     ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                     %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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
                        js(c["official"]),
                        c.get("cells", []),
                        js(c.get("place")),
                        js(c.get("nearest_official")),
                        js(c.get("trend")),
                        bool(c.get("persistent_heat_source")),
                        int(c.get("days_seen", 0)),
                    )
                    for c in snap["clusters"]
                ],
            )
        conn.execute(
            "DELETE FROM activity_snapshots WHERE generated_at < %s::timestamptz - make_interval(hours => %s) "
            "AND id <> %s",
            (snap["generated_at"], keep_hours, sid),
        )
    return sid
