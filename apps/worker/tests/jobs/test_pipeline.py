"""The job pipeline on recorded data with in-memory store/bus: stages, idempotency, cancel, decline, retries."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from inland_worker.contracts.models import AnalysisJobMessage
from inland_worker.contracts.models import JobStatus as S
from inland_worker.data import DataService
from inland_worker.jobs.events import MemoryEventBus
from inland_worker.jobs.pipeline import InjectedFault, PipelineDeps, run_job
from inland_worker.jobs.states import IllegalTransition
from inland_worker.jobs.store import MemoryJobStore

CONTRACTS = Path(__file__).resolve().parents[4] / "contracts"
EVENT_SCHEMA = Draft202012Validator(json.loads((CONTRACTS / "job-event.schema.json").read_text()))
LINE_FIRE = {
    "type": "Polygon",
    "coordinates": [
        [[-117.185, 34.092], [-116.94, 34.092], [-116.94, 34.218], [-117.185, 34.218], [-117.185, 34.092]]
    ],
}
RECENT_AREA = {
    "type": "Polygon",
    "coordinates": [[[-117.5, 34.05], [-117.2, 34.05], [-117.2, 34.2], [-117.5, 34.2], [-117.5, 34.05]]],
}


def message(job_id="11111111-1111-4111-8111-111111111111", area=LINE_FIRE, dates=None, question=None):
    return AnalysisJobMessage(
        job_id=job_id,
        analysis_type="historical_fire_impact",
        question=question or "How badly did the Line Fire burn this area?",
        area=area,
        date_range=dates or {"start": "2024-08-01", "end": "2024-10-31"},
        requested_at=datetime.now(UTC),
    )


@pytest.fixture
def deps(tmp_path):
    return PipelineDeps(
        store=MemoryJobStore(),
        bus=MemoryEventBus(),
        data=DataService(mode="fixture"),
        artifacts_dir=tmp_path,
        today=date(2026, 9, 24),
        lease=timedelta(seconds=0),
    )


def statuses(bus):
    return [e.status for e in bus.events]


async def test_line_fire_job_completes_with_ordered_events_layers_and_report(deps):
    msg = message()
    deps.store.add(msg)
    out = await run_job(msg, deps)
    assert out.status == S.COMPLETED and not out.dead
    assert statuses(deps.bus) == [
        S.VALIDATING,
        S.RETRIEVING_DATA,
        S.PROCESSING_SATELLITE,
        S.VERIFYING_EVIDENCE,
        S.GENERATING_REPORT,
        S.COMPLETED,
    ]
    assert [e.seq for e in deps.bus.events] == list(range(1, 7))
    for e in deps.bus.events:
        assert not list(EVENT_SCHEMA.iter_errors(e.model_dump(mode="json", exclude_none=True)))
    ev = deps.store.evidence[msg.job_id]
    calcs = [e for e in ev.values() if e.evidence_type == "deterministic_calculation"]
    assert {("dnbr_median" in c.properties) or ("ndvi_change_median" in c.properties) for c in calcs} == {
        True
    }
    assert len(calcs) == 2
    layers = deps.store.artifacts[f"layers-{msg.job_id}"]["metadata"]["layers"]
    raster = [la for la in layers if la["kind"] == "raster"]
    assert raster and raster[0]["tile_template"] == f"/v1/tiles/dnbr-{msg.job_id}/{{z}}/{{x}}/{{y}}.png"
    assert list((deps.artifacts_dir / "tiles" / f"dnbr-{msg.job_id}").rglob("*.png"))
    report = deps.store.artifacts[f"report-{msg.job_id}"]["metadata"]
    assert report["job_id"] == msg.job_id and report["limitations"]
    cited = {i for s in report["sections"] for i in s["evidence_ids"]}
    assert cited <= set(ev)


async def test_retry_is_idempotent(deps):
    msg = message()
    deps.store.add(msg)
    await run_job(msg, deps)
    n = len(deps.store.evidence[msg.job_id])
    deps.store.rows[msg.job_id].status = S.GENERATING_REPORT  # as if the worker died before completing
    out = await run_job(msg, deps)
    assert out.status == S.COMPLETED
    assert len(deps.store.evidence[msg.job_id]) == n


async def test_recent_area_has_detections_and_no_satellite_stage(deps):
    msg = message(area=RECENT_AREA, dates={"start": "2026-09-19", "end": "2026-09-24"})
    deps.store.add(msg)
    out = await run_job(msg, deps)
    assert out.status == S.COMPLETED
    assert S.PROCESSING_SATELLITE not in statuses(deps.bus)
    types = {e.evidence_type for e in deps.store.evidence[msg.job_id].values()}
    assert "satellite_detection" in types


async def test_area_without_recorded_imagery_is_insufficient_not_a_substitute(deps):
    far = {
        "type": "Polygon",
        "coordinates": [[[-116.0, 34.5], [-115.9, 34.5], [-115.9, 34.6], [-116.0, 34.6], [-116.0, 34.5]]],
    }
    msg = message(area=far)
    deps.store.add(msg)
    assert (await run_job(msg, deps)).status == S.COMPLETED
    report = deps.store.artifacts[f"report-{msg.job_id}"]["metadata"]
    assert report["confidence"] == "insufficient_evidence"
    assert not any(
        e.evidence_type == "deterministic_calculation" for e in deps.store.evidence[msg.job_id].values()
    )


async def test_emergency_question_is_declined_as_failed(deps):
    msg = message(question="Should I evacuate my house right now?")
    deps.store.add(msg)
    assert (await run_job(msg, deps)).status == S.FAILED
    row = deps.store.rows[msg.job_id]
    assert row.error_code == "EMERGENCY_REDIRECT" and "911" in row.error_message
    assert msg.job_id not in deps.store.evidence


async def test_cancel_between_stages(deps):
    msg = message()
    deps.store.add(msg)
    real = deps.store.transition

    def cancel_after_retrieving(job_id, to, **kw):
        ev = real(job_id, to, **kw)
        if to == S.RETRIEVING_DATA:
            deps.store.rows[job_id].cancel_requested_at = datetime.now(UTC)
        return ev

    deps.store.transition = cancel_after_retrieving
    assert (await run_job(msg, deps)).status == S.CANCELLED
    assert statuses(deps.bus)[-1] == S.CANCELLED


async def test_cancel_before_start(deps):
    msg = message()
    deps.store.add(msg)
    deps.store.rows[msg.job_id].cancel_requested_at = datetime.now(UTC)
    assert (await run_job(msg, deps)).status == S.CANCELLED


async def test_failures_exhaust_retries(deps):
    msg = message()
    deps.store.add(msg)
    deps.fault = "always"
    for _ in range(3):
        with pytest.raises(InjectedFault):
            await run_job(msg, deps)
    out = await run_job(msg, deps)
    assert out.status == S.FAILED and out.dead
    assert deps.store.rows[msg.job_id].error_code == "RETRIES_EXHAUSTED"


async def test_duplicate_while_lease_is_fresh_is_skipped(deps):
    msg = message()
    deps.store.add(msg)
    deps.store.rows[msg.job_id].status = S.RETRIEVING_DATA
    deps.lease = timedelta(minutes=5)
    assert (await run_job(msg, deps)).status is None


async def test_unknown_and_finished_jobs_are_dropped(deps):
    assert (await run_job(message(), deps)).status is None
    msg = message()
    deps.store.add(msg)
    deps.store.rows[msg.job_id].status = S.COMPLETED
    assert (await run_job(msg, deps)).status is None


def test_illegal_transition_raises():
    store = MemoryJobStore()
    msg = message()
    store.add(msg)
    with pytest.raises(IllegalTransition):
        store.transition(msg.job_id, S.COMPLETED)
    store.rows[msg.job_id].status = S.CANCELLED
    with pytest.raises(IllegalTransition):
        store.transition(msg.job_id, S.VALIDATING)
