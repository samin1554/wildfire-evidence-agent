"""Progress events on the Redis `job-events` stream (field `payload` = contracts/job-event.schema.json).

Always published AFTER the database commit that made the change (ADR-004), so a client that misses an event
can always recover the true state from GET /v1/analyses/{id}.
"""

from __future__ import annotations

from typing import Any, Protocol

from inland_worker.contracts.models import JobEvent

EVENTS_STREAM = "job-events"
EVENTS_MAXLEN = 100_000


class EventBus(Protocol):
    async def publish(self, event: JobEvent) -> None: ...


class MemoryEventBus:
    def __init__(self) -> None:
        self.events: list[JobEvent] = []

    async def publish(self, event: JobEvent) -> None:
        self.events.append(event)


class RedisEventBus:
    def __init__(self, redis: Any):  # redis.asyncio.Redis
        self.redis = redis

    async def publish(self, event: JobEvent) -> None:
        await self.redis.xadd(
            EVENTS_STREAM,
            {"payload": event.model_dump_json(exclude_none=True)},
            maxlen=EVENTS_MAXLEN,
            approximate=True,
        )
