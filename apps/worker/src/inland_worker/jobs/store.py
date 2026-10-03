"""Job persistence: guarded status transitions, evidence, artifacts (spec §10 tables, ADR-003/004).

`PostgresJobStore` is the real one; `MemoryJobStore` has identical semantics for offline tests.
Each transition bumps `last_event_seq` in the same UPDATE, so the event published after the commit carries a
sequence number the API can compare with its DB snapshot (ADR-004: DB first, then the event).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from inland_worker.contracts.models import AnalysisJobMessage, Evidence, JobEvent
from inland_worker.contracts.models import JobStatus as S
from inland_worker.jobs.states import ACTIVE, LEGAL, PROGRESS, STAGE, TERMINAL, IllegalTransition, sources_for

MAX_ATTEMPTS = 3


@dataclass
class Begin:
    """What to do with a delivered job message."""

    action: Literal["run", "skip", "exhausted", "cancelled"]
    reason: str = ""
    events: list[JobEvent] = field(default_factory=list)


class JobStore(Protocol):
    def begin(self, job_id: str, *, lease: timedelta, max_attempts: int = MAX_ATTEMPTS) -> Begin: ...
    def transition(
        self,
        job_id: str,
        to: S,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        message: str | None = None,
    ) -> JobEvent: ...
    def heartbeat(self, job_id: str) -> None: ...
    def cancel_requested(self, job_id: str) -> bool: ...
    def save_evidence(self, job_id: str, items: list[Evidence]) -> int: ...
    def save_artifact(
        self,
        job_id: str,
        artifact_id: str,
        artifact_type: str,
        mime_type: str,
        metadata: dict[str, Any],
        storage_key: str | None = None,
    ) -> None: ...
    def stale_queued(self, older_than: timedelta) -> list[AnalysisJobMessage]: ...


def _event(job_id: str, seq: int, to: S, progress: int, **kw: Any) -> JobEvent:
    return JobEvent(
        job_id=job_id, seq=seq, status=to, progress=progress, stage=STAGE[to], at=datetime.now(UTC), **kw
    )


# --- in-memory (tests) ----------------------------------------------------------------------------------------
@dataclass
class _Row:
    msg: AnalysisJobMessage
    status: S = S.QUEUED
    progress: int = 0
    seq: int = 0
    attempts: int = 0
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    cancel_requested_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class MemoryJobStore:
    def __init__(self) -> None:
        self.rows: dict[str, _Row] = {}
        self.evidence: dict[str, dict[str, Evidence]] = {}
        self.artifacts: dict[str, dict[str, Any]] = {}

    def add(self, msg: AnalysisJobMessage) -> None:
        self.rows[msg.job_id] = _Row(msg=msg)

    def begin(self, job_id: str, *, lease: timedelta, max_attempts: int = MAX_ATTEMPTS) -> Begin:
        row = self.rows.get(job_id)
        if row is None:
            return Begin("skip", "no such job")
        if row.status in TERMINAL:
            return Begin("skip", f"already {row.status.value}")
        if row.cancel_requested_at:
            return Begin("cancelled", events=[self.transition(job_id, S.CANCELLED)])
        if row.status != S.QUEUED and datetime.now(UTC) - row.updated_at < lease:
            return Begin("skip", "another worker holds a fresh lease")
        if row.attempts >= max_attempts:
            ev = self.transition(
                job_id,
                S.FAILED,
                error_code="RETRIES_EXHAUSTED",
                error_message=f"The analysis failed {row.attempts} times and was stopped.",
            )
            return Begin("exhausted", events=[ev])
        row.attempts += 1
        row.updated_at = datetime.now(UTC)
        return Begin("run")

    def transition(self, job_id, to, *, error_code=None, error_message=None, message=None) -> JobEvent:
        row = self.rows.get(job_id)
        if row is None or to not in LEGAL[row.status]:
            raise IllegalTransition(job_id, to, row.status.value if row else None)
        row.status, row.seq = to, row.seq + 1
        row.progress = PROGRESS.get(to, row.progress)
        row.updated_at = datetime.now(UTC)
        row.error_code, row.error_message = error_code, error_message
        return _event(
            job_id, row.seq, to, row.progress, message=message or error_message, error_code=error_code
        )

    def heartbeat(self, job_id: str) -> None:
        if job_id in self.rows:
            self.rows[job_id].updated_at = datetime.now(UTC)

    def cancel_requested(self, job_id: str) -> bool:
        row = self.rows.get(job_id)
        return bool(row and row.cancel_requested_at)

    def save_evidence(self, job_id: str, items: list[Evidence]) -> int:
        stored = self.evidence.setdefault(job_id, {})
        new = [i for i in items if i.id not in stored]
        for i in new:
            stored[i.id] = i
        return len(new)

    def save_artifact(
        self, job_id, artifact_id, artifact_type, mime_type, metadata, storage_key=None
    ) -> None:
        self.artifacts[artifact_id] = {
            "job_id": job_id,
            "artifact_type": artifact_type,
            "mime_type": mime_type,
            "metadata": metadata,
            "storage_key": storage_key,
        }

    def stale_queued(self, older_than: timedelta) -> list[AnalysisJobMessage]:
        cutoff = datetime.now(UTC) - older_than
        out = []
        for row in self.rows.values():
            if row.status == S.QUEUED and row.updated_at < cutoff:
                row.updated_at = datetime.now(UTC)
                out.append(row.msg)
        return out


# --- PostgreSQL ------------------------------------------------------------------------------------------------
class PostgresJobStore:
    def __init__(self, pool: Any):  # psycopg_pool.ConnectionPool
        self.pool = pool

    @classmethod
    def connect(cls, dsn: str) -> PostgresJobStore:
        from psycopg_pool import ConnectionPool

        return cls(ConnectionPool(dsn, min_size=1, max_size=4, open=True))

    def begin(self, job_id: str, *, lease: timedelta, max_attempts: int = MAX_ATTEMPTS) -> Begin:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                "SELECT status, attempts, cancel_requested_at, now() - updated_at FROM analysis_jobs "
                "WHERE id = %s FOR UPDATE",
                (job_id,),
            ).fetchone()
            if row is None:
                return Begin("skip", "no such job")
            status, attempts, cancel_at, age = S(row[0]), row[1], row[2], row[3]
            if status in TERMINAL:
                return Begin("skip", f"already {status.value}")
            if cancel_at is not None:
                return Begin("cancelled", events=[self._transition(conn, job_id, S.CANCELLED)])
            if status != S.QUEUED and age < lease:
                return Begin("skip", "another worker holds a fresh lease")
            if attempts >= max_attempts:
                ev = self._transition(
                    conn,
                    job_id,
                    S.FAILED,
                    error_code="RETRIES_EXHAUSTED",
                    error_message=f"The analysis failed {attempts} times and was stopped.",
                )
                return Begin("exhausted", events=[ev])
            conn.execute(
                "UPDATE analysis_jobs SET attempts = attempts + 1, started_at = coalesce(started_at, now()), "
                "updated_at = now() WHERE id = %s",
                (job_id,),
            )
            return Begin("run")

    def transition(self, job_id, to, *, error_code=None, error_message=None, message=None) -> JobEvent:
        with self.pool.connection() as conn, conn.transaction():
            return self._transition(
                conn, job_id, to, error_code=error_code, error_message=error_message, message=message
            )

    def _transition(self, conn, job_id, to, *, error_code=None, error_message=None, message=None) -> JobEvent:
        progress = PROGRESS.get(to)
        row = conn.execute(
            """UPDATE analysis_jobs SET
                 status = %(to)s,
                 progress = coalesce(%(progress)s, progress),
                 stage = %(stage)s,
                 last_event_seq = last_event_seq + 1,
                 error_code = %(error_code)s,
                 error_message = %(error_message)s,
                 completed_at = CASE WHEN %(terminal)s THEN now() ELSE completed_at END,
                 updated_at = now()
               WHERE id = %(id)s AND status = ANY(%(sources)s)
               RETURNING last_event_seq, progress""",
            {
                "to": to.value,
                "progress": progress,
                "stage": STAGE[to],
                "error_code": error_code,
                "error_message": error_message,
                "terminal": to in TERMINAL,
                "id": job_id,
                "sources": sources_for(to),
            },
        ).fetchone()
        if row is None:
            current = conn.execute("SELECT status FROM analysis_jobs WHERE id = %s", (job_id,)).fetchone()
            raise IllegalTransition(job_id, to, current[0] if current else None)
        return _event(job_id, row[0], to, row[1], message=message or error_message, error_code=error_code)

    def heartbeat(self, job_id: str) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE analysis_jobs SET updated_at = now() WHERE id = %s AND status = ANY(%s)",
                (job_id, [s.value for s in ACTIVE]),
            )

    def cancel_requested(self, job_id: str) -> bool:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT cancel_requested_at IS NOT NULL FROM analysis_jobs WHERE id = %s", (job_id,)
            ).fetchone()
            return bool(row and row[0])

    def save_evidence(self, job_id: str, items: list[Evidence]) -> int:
        if not items:
            return 0
        rows = []
        for ev in items:
            d = ev.model_dump(mode="json")
            rows.append(
                (
                    job_id,
                    d["id"],
                    d["evidence_type"],
                    d["source"],
                    d["source_record_id"],
                    d["observed_at"],
                    d["retrieved_at"],
                    json.dumps(d["geometry"]) if d["geometry"] else None,
                    json.dumps(d["properties"]),
                    d["quality_flags"],
                    d["limitations"],
                    d["source_url"],
                )
            )
        with self.pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO evidence_items (job_id, id, evidence_type, source, source_record_id, observed_at,
                     retrieved_at, geometry, properties, quality_flags, limitations, source_url)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s, %s, %s)
                   ON CONFLICT (job_id, id) DO NOTHING""",
                rows,
            )
            return cur.rowcount if cur.rowcount >= 0 else len(rows)

    def save_artifact(
        self, job_id, artifact_id, artifact_type, mime_type, metadata, storage_key=None
    ) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO artifacts (id, job_id, artifact_type, storage_key, mime_type, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET metadata = EXCLUDED.metadata, storage_key = EXCLUDED.storage_key""",
                (
                    artifact_id,
                    job_id,
                    artifact_type,
                    storage_key,
                    mime_type,
                    json.dumps(metadata, default=str),
                ),
            )

    def stale_queued(self, older_than: timedelta) -> list[AnalysisJobMessage]:
        """Jobs Go inserted but whose `jobs` message never arrived (e.g. Redis was down): re-enqueue them.
        Touching updated_at stops the same job being re-sent on every sweep."""
        with self.pool.connection() as conn, conn.transaction():
            rows = conn.execute(
                """UPDATE analysis_jobs SET updated_at = now()
                   WHERE status = 'queued' AND updated_at < now() - %s
                   RETURNING id::text, analysis_type, question, ST_AsGeoJSON(area)::json, date_start, date_end,
                             created_at""",
                (older_than,),
            ).fetchall()
        return [
            AnalysisJobMessage(
                job_id=r[0],
                analysis_type=r[1],
                question=r[2],
                area=r[3],
                date_range={"start": r[4], "end": r[5]},
                requested_at=r[6],
            )
            for r in rows
        ]
