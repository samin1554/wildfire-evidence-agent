"""The job state machine (docs/diagrams/job-state.svg, ADR-003, ADR-004). The worker is the only status writer
after Go inserts `queued`; every write goes through a guarded transition that checks the current status."""

from __future__ import annotations

from inland_worker.contracts.models import JobStatus as S

TERMINAL = frozenset({S.COMPLETED, S.FAILED, S.CANCELLED})
ACTIVE = frozenset(set(S) - TERMINAL)

# legal next states. Any active state may restart at `validating` (a retried delivery after a crash) and may end
# `failed` (timeout, retries exhausted) or `cancelled`.
LEGAL: dict[S, frozenset[S]] = {
    S.QUEUED: frozenset({S.VALIDATING}),
    S.VALIDATING: frozenset({S.RETRIEVING_DATA}),
    S.RETRIEVING_DATA: frozenset({S.PROCESSING_SATELLITE, S.VERIFYING_EVIDENCE}),
    S.PROCESSING_SATELLITE: frozenset({S.VERIFYING_EVIDENCE}),
    S.VERIFYING_EVIDENCE: frozenset({S.GENERATING_REPORT}),
    S.GENERATING_REPORT: frozenset({S.COMPLETED}),
}
for _s in ACTIVE:
    LEGAL[_s] = LEGAL[_s] | {S.VALIDATING, S.FAILED, S.CANCELLED}
for _s in TERMINAL:
    LEGAL[_s] = frozenset()

PROGRESS = {
    S.QUEUED: 0,
    S.VALIDATING: 5,
    S.RETRIEVING_DATA: 20,
    S.PROCESSING_SATELLITE: 45,
    S.VERIFYING_EVIDENCE: 75,
    S.GENERATING_REPORT: 90,
    S.COMPLETED: 100,
}
STAGE = {
    S.QUEUED: "Queued",
    S.VALIDATING: "Checking the question, area and dates",
    S.RETRIEVING_DATA: "Retrieving data from approved sources",
    S.PROCESSING_SATELLITE: "Processing satellite imagery",
    S.VERIFYING_EVIDENCE: "Verifying evidence",
    S.GENERATING_REPORT: "Writing the cited report",
    S.COMPLETED: "Completed",
    S.FAILED: "Failed",
    S.CANCELLED: "Cancelled",
}


class IllegalTransition(Exception):
    def __init__(self, job_id: str, to: S, current: str | None):
        super().__init__(f"job {job_id}: cannot move from {current!r} to {to.value!r}")
        self.job_id, self.to, self.current = job_id, to, current


def sources_for(to: S) -> list[str]:
    """Every status that may move to `to`."""
    return sorted(s.value for s, nxt in LEGAL.items() if to in nxt)
