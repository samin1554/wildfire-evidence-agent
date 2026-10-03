"""The job runtime: consume the Redis `jobs` stream and run each analysis (Milestone 1, ADR-003/004).

- XREADGROUP in group `workers`; XACK only once the job is terminal (or the message is unusable).
- While a job runs, a heartbeat keeps its message "fresh" (XCLAIM to self) and its DB lease (updated_at) alive.
- A reaper XAUTOCLAIMs messages idle longer than REAPER_IDLE_MS (a crashed worker) and runs them again; after
  MAX_ATTEMPTS the job ends `failed` / RETRIES_EXHAUSTED and the message moves to `jobs-dead`.
- A sweep re-enqueues `queued` jobs whose message never reached Redis, so Go never has to write status.
- Each job has a wall clock (JOB_TIMEOUT_S, default 600 s); past it the job ends `failed` / TIMEOUT.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
from datetime import timedelta
from typing import Any

from pydantic import ValidationError

from inland_worker.contracts.models import AnalysisJobMessage
from inland_worker.contracts.models import JobStatus as S
from inland_worker.jobs.pipeline import PipelineDeps, run_job
from inland_worker.jobs.states import IllegalTransition

log = logging.getLogger("inland_worker.jobs")

JOBS_STREAM = "jobs"
DEAD_STREAM = "jobs-dead"
GROUP = "workers"


class Runtime:
    def __init__(
        self,
        redis: Any,  # redis.asyncio.Redis (decode_responses=True)
        deps: PipelineDeps,
        *,
        consumer: str | None = None,
        idle_ms: int = 600_000,
        job_timeout_s: float = 600,
        sweep_after: timedelta = timedelta(minutes=5),
        block_ms: int = 2000,
    ):
        self.redis, self.deps = redis, deps
        self.consumer = consumer or f"{socket.gethostname()}-{os.getpid()}"
        self.idle_ms, self.job_timeout_s, self.sweep_after, self.block_ms = (
            idle_ms,
            job_timeout_s,
            sweep_after,
            block_ms,
        )
        self.running: set[str] = set()  # message ids in flight here
        self._stop = asyncio.Event()

    @classmethod
    def from_env(cls, redis: Any, deps: PipelineDeps) -> Runtime:
        return cls(
            redis,
            deps,
            idle_ms=int(os.environ.get("REAPER_IDLE_MS", "600000")),
            job_timeout_s=float(os.environ.get("JOB_TIMEOUT_S", "600")),
            sweep_after=timedelta(seconds=int(os.environ.get("QUEUED_SWEEP_S", "300"))),
        )

    async def ensure_group(self) -> None:
        try:
            await self.redis.xgroup_create(JOBS_STREAM, GROUP, id="0", mkstream=True)
        except Exception as exc:  # BUSYGROUP: already exists
            if "BUSYGROUP" not in str(exc):
                raise

    def stop(self) -> None:
        self._stop.set()

    # --- one message --------------------------------------------------------------------------------------
    async def handle(self, msg_id: str, fields: dict[str, str]) -> None:
        try:
            msg = AnalysisJobMessage.model_validate_json(fields.get("payload", ""))
        except ValidationError as exc:
            log.warning("message %s is not a valid analysis job; moving to %s", msg_id, DEAD_STREAM)
            await self.redis.xadd(
                DEAD_STREAM,
                {"payload": fields.get("payload", ""), "reason": str(exc)[:500], "msg_id": msg_id},
            )
            await self.redis.xack(JOBS_STREAM, GROUP, msg_id)
            return
        self.running.add(msg_id)
        beat = asyncio.create_task(self._heartbeat(msg_id, msg.job_id))
        try:
            outcome = await asyncio.wait_for(run_job(msg, self.deps), timeout=self.job_timeout_s)
            if outcome.dead:
                await self.redis.xadd(
                    DEAD_STREAM, {**fields, "reason": "RETRIES_EXHAUSTED", "msg_id": msg_id}
                )
            await self.redis.xack(JOBS_STREAM, GROUP, msg_id)
            log.info("job %s → %s", msg.job_id, outcome.status.value if outcome.status else "dropped")
        except TimeoutError:
            with contextlib.suppress(IllegalTransition):
                await self.deps.bus.publish(
                    self.deps.store.transition(
                        msg.job_id,
                        S.FAILED,
                        error_code="TIMEOUT",
                        error_message=f"The analysis took longer than {int(self.job_timeout_s)} s and was stopped.",
                    )
                )
            await self.redis.xack(JOBS_STREAM, GROUP, msg_id)
        except Exception:
            # leave the message pending: the reaper retries it after REAPER_IDLE_MS (begin() counts attempts)
            log.exception("job %s attempt failed; it will be retried", msg.job_id)
        finally:
            beat.cancel()
            self.running.discard(msg_id)

    async def _heartbeat(self, msg_id: str, job_id: str) -> None:
        every = max(self.idle_ms / 3000, 0.5)
        while True:
            await asyncio.sleep(every)
            with contextlib.suppress(Exception):
                await self.redis.xclaim(JOBS_STREAM, GROUP, self.consumer, 0, [msg_id], justid=True)
                self.deps.store.heartbeat(job_id)

    # --- loops ----------------------------------------------------------------------------------------------
    async def consume_once(self) -> int:
        reply = await self.redis.xreadgroup(
            GROUP, self.consumer, {JOBS_STREAM: ">"}, count=1, block=self.block_ms
        )
        n = 0
        for _stream, messages in reply or []:
            for msg_id, fields in messages:
                await self.handle(msg_id, fields)
                n += 1
        return n

    async def reap_once(self) -> int:
        _next, claimed, *_ = await self.redis.xautoclaim(
            JOBS_STREAM, GROUP, self.consumer, min_idle_time=self.idle_ms, start_id="0-0", count=10
        )
        n = 0
        for msg_id, fields in claimed:
            if msg_id in self.running or fields is None:
                continue
            log.info("reclaimed %s after %d ms idle", msg_id, self.idle_ms)
            await self.handle(msg_id, fields)
            n += 1
        return n

    async def sweep_once(self) -> int:
        stale = self.deps.store.stale_queued(self.sweep_after)
        for msg in stale:
            log.info("re-enqueuing job %s (queued but never delivered)", msg.job_id)
            await self.redis.xadd(JOBS_STREAM, {"payload": msg.model_dump_json()})
        return len(stale)

    async def run(self) -> None:
        await self.ensure_group()
        log.info(
            "worker %s consuming %s/%s (reaper idle %d ms)", self.consumer, JOBS_STREAM, GROUP, self.idle_ms
        )
        reap_every = max(self.idle_ms / 2000, 1.0)
        last_reap = last_sweep = 0.0
        loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            try:
                await self.consume_once()
                now = loop.time()
                if now - last_reap >= reap_every:
                    await self.reap_once()
                    last_reap = now
                if now - last_sweep >= 30:
                    await self.sweep_once()
                    last_sweep = now
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("runtime loop error; retrying in 2 s")
                await asyncio.sleep(2)


async def serve() -> None:
    """Entry point for `python -m inland_worker jobs`."""
    import redis.asyncio as aioredis

    from inland_worker.agent import OpenRouterLLM
    from inland_worker.data import DataService
    from inland_worker.jobs.events import RedisEventBus
    from inland_worker.jobs.pg_data import PostgresCacheStore, PostgresTraceSink
    from inland_worker.jobs.pipeline import deps_from_env
    from inland_worker.jobs.store import PostgresJobStore

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    dsn, redis_url = os.environ.get("DATABASE_URL", ""), os.environ.get("REDIS_URL", "")
    if not dsn or not redis_url:
        raise SystemExit("DATABASE_URL and REDIS_URL must be set (see .env.example)")
    store = PostgresJobStore.connect(dsn)
    data = DataService(cache=PostgresCacheStore(store.pool), trace=PostgresTraceSink(store.pool))
    llm = OpenRouterLLM() if os.environ.get("OPENROUTER_API_KEY") else None
    log.info(
        "data mode: %s · LLM: %s",
        os.environ.get("INLAND_DATA_MODE", "live"),
        "OpenRouter" if llm else "none (rule-based planner and wording)",
    )
    r = aioredis.from_url(redis_url, decode_responses=True)
    deps = deps_from_env(store, RedisEventBus(r), data, llm)
    await Runtime.from_env(r, deps).run()
