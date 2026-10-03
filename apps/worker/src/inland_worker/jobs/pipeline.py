"""One analysis job, start to finish: guarded stage transitions around the agent graph (ADR-003/004, ADR-010).

    queued → validating → retrieving_data → [processing_satellite] → verifying_evidence → generating_report
           → completed          (or failed / cancelled from any active stage)

Every transition is a DB write first, then a `job-events` event. Evidence, the report and layers are stored
idempotently, so a job that is retried after a crash ends with the same rows, never duplicates.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from inland_worker.agent import Cancelled, Hooks, run_analysis
from inland_worker.agent.llm import LLM
from inland_worker.agent.tools import BurnRaster
from inland_worker.contracts.models import AnalysisJobMessage, EvidenceType
from inland_worker.contracts.models import JobStatus as S
from inland_worker.data import DataService
from inland_worker.jobs.events import EventBus
from inland_worker.jobs.layers import raster_layer, vector_layers
from inland_worker.jobs.store import JobStore
from inland_worker.satellite.overlay import LEGEND, grid_bounds_ll, render_tiles

log = logging.getLogger("inland_worker.jobs")


class InjectedFault(RuntimeError):
    """FAULT_INJECT=always makes every attempt fail after `validating` (demo/tests of the retry path only)."""


@dataclass
class PipelineDeps:
    store: JobStore
    bus: EventBus
    data: DataService
    artifacts_dir: Path
    llm: LLM | None = None
    today: date | None = None
    lease: timedelta = timedelta(minutes=5)
    fault: str = ""


@dataclass
class Outcome:
    """`status` is the terminal status reached, or None when the message is dropped (unknown job, already
    finished, or a duplicate while another worker holds the job). `dead` marks retries exhausted."""

    status: S | None
    dead: bool = False


async def run_job(msg: AnalysisJobMessage, deps: PipelineDeps) -> Outcome:
    """Run one delivered job to a terminal state."""
    store, bus, job_id = deps.store, deps.bus, msg.job_id
    begin = store.begin(job_id, lease=deps.lease)
    for ev in begin.events:
        await bus.publish(ev)
    if begin.action == "skip":
        log.info("job %s skipped: %s", job_id, begin.reason)
        return Outcome(None)
    if begin.action == "exhausted":
        return Outcome(S.FAILED, dead=True)
    if begin.action == "cancelled":
        return Outcome(S.CANCELLED)

    async def stage(status: str) -> None:
        if deps.fault == "always" and status == S.RETRIEVING_DATA:
            raise InjectedFault("FAULT_INJECT=always")
        await bus.publish(store.transition(job_id, S(status)))

    async def should_cancel() -> bool:
        store.heartbeat(job_id)
        return store.cancel_requested(job_id)

    try:
        result = await run_analysis(
            msg.question,
            msg.area.model_dump(),
            msg.date_range,
            llm=deps.llm,
            data=deps.data,
            job_id=job_id,
            today=deps.today,
            hooks=Hooks(stage=stage, should_cancel=should_cancel),
        )
    except Cancelled:
        await bus.publish(store.transition(job_id, S.CANCELLED, message="Cancelled at the user's request."))
        return Outcome(S.CANCELLED)

    if result.declined:
        await bus.publish(
            store.transition(job_id, S.FAILED, error_code=result.decline_code, error_message=result.message)
        )
        return Outcome(S.FAILED)

    store.save_evidence(job_id, result.evidence)
    layers = vector_layers(result.evidence)
    burn = result.results.get("burn_severity")
    calc = next(
        (
            e
            for e in result.evidence
            if e.evidence_type == EvidenceType.DETERMINISTIC_CALCULATION and "dnbr_median" in e.properties
        ),
        None,
    )
    if burn is not None and isinstance(burn.raster, BurnRaster) and calc is not None:
        layer_id = f"dnbr-{job_id}"
        out = deps.artifacts_dir / "tiles" / layer_id
        shutil.rmtree(out, ignore_errors=True)  # a retry re-renders identical tiles
        count = render_tiles(burn.raster.classes, burn.raster.grid, out)
        if count:
            layer = raster_layer(layer_id, list(grid_bounds_ll(burn.raster.grid)), LEGEND, calc)
            layers.append(layer)
            store.save_artifact(
                job_id,
                layer_id,
                "tile_layer",
                "image/png",
                {**layer, "tile_count": count},
                storage_key=f"tiles/{layer_id}",
            )
    store.save_artifact(job_id, f"layers-{job_id}", "layer", "application/json", {"layers": layers})
    report = result.report.model_dump(mode="json")
    report["job_id"] = job_id
    store.save_artifact(
        job_id,
        f"report-{job_id}",
        "report",
        "application/json",
        {
            **report,
            "trace": {
                "plan": result.plan,
                "plan_source": result.plan_source,
                "explanation_source": result.explanation_source,
                "models_used": result.models_used,
                "steps": result.steps,
            },
        },
    )
    await bus.publish(store.transition(job_id, S.COMPLETED))
    return Outcome(S.COMPLETED)


def deps_from_env(store: JobStore, bus: EventBus, data: DataService, llm: LLM | None) -> PipelineDeps:
    fixture_today = os.environ.get("INLAND_FIXTURE_TODAY", "").strip()
    return PipelineDeps(
        store=store,
        bus=bus,
        data=data,
        llm=llm,
        artifacts_dir=Path(os.environ.get("ARTIFACTS_DIR", "/artifacts")),
        today=date.fromisoformat(fixture_today) if fixture_today else None,
        lease=timedelta(milliseconds=int(os.environ.get("REAPER_IDLE_MS", "600000")) // 2),
        fault=os.environ.get("FAULT_INJECT", "").strip().lower(),
    )
