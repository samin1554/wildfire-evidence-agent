# PRs to bring the lead-owned changes from the demo to `main`

The demo (`demo/full-stack`) stays a reference and is never merged. These four branches carry only lead-owned
material (agent, kit, `providers.yaml`, contracts, ADRs, docs). Merge them in this order; 2 and 4 are stacked, so
GitHub shows each PR's own commits once its base is merged (or set the PR base to the branch below it).
All four were test-merged together on top of `origin/main` (22d20b9): clean merge, 172 worker tests and 28
contract checks pass.

---

## 1. `feat/agent-v1` → `main`: the agent (ADR-010) + fixes

The controlled LangGraph agent, never merged until now, plus what the demo's job runtime needed.

- `run_analysis(…, hooks=Hooks(stage, should_cancel))`: the Milestone 1 job runtime can publish each stage and
  cancel between steps (`Cancelled`).
- The agent's own `agent_inference` evidence has one id per job, so a retried job never stores a duplicate.
- **Bug fix:** in fixture mode `burn_severity` replayed the recorded Line Fire calculation for *any* area and dates.
  It now replays only for the recording's area and dates; anything else is honestly `missing`.
- New dependency: `langgraph` (approved with ADR-010).

Tests: 155 worker tests, including stage order, cancel, stable id, and no replay outside the recording.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

---

## 2. `fix/kit-provider-params` → `main` (after 1): kit/connector parameters

Backward compatible, no fixture changes.

- `firms`: optional `date` (first day of a past window), e.g. to align recordings or look back.
- `wfigs_current`: optional `max_offset` (ArcGIS `maxAllowableOffset`): national pulls otherwise exceed
  `max_response_bytes`. Maps `attr_IncidentTypeCategory` → `incident_type` (`wildfire` / `prescribed burn`) so a
  prescribed burn is never reported as a wildfire.
- Kit config: `kind: reference_layer` for boundary/scope layers that aren't evidence.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

---

## 3. `contract/clarify-errors` → `main` (label `contract-change`): descriptions only, no shape change

Decisions the demo surfaced, so S2/S3/S7 build the same thing.

- `Error.code` lists `INVALID_REQUEST` and `JOB_NOT_COMPLETED` (409 from `/report` for any job not `completed`;
  `details.status` says which).
- `AnalysisJob.error_code` lists the worker's decline codes (`EMERGENCY_REDIRECT`, `UNSUPPORTED_PREDICTION`,
  `DATE_IN_FUTURE`, …) and `TIMEOUT` / `RETRIES_EXHAUSTED`.
- ADR-003 amendment: evidence idempotent on `(job_id, evidence.id)`; a sweep re-enqueues `queued` jobs whose Redis
  message was lost; leases.
- ADR-002 amendment: SSE order on (re)connect.
- S7 guide: Postgres TCP healthcheck, compose `--env-file`, `/artifacts` ownership.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

---

## 4. `contract/national-region-and-activity` → `main` (after 1 and 2; label `contract-change`)

- **ADR-012 accepted:** the region is the 50 states + DC (Census TIGERweb outline in `config/regions/usa.geojson`);
  limits unchanged. Historical perimeters: CAL FIRE in California, NIFC WFIGS history elsewhere (S4 builds both).
- **ADR-013 accepted:** "Active now" feed. `GET /v1/activity` + `ActivitySnapshot` / `ActivityCluster` + example.
  Owners: worker snapshot lead + S7, tables S7, handler S3, UI S1 + S2. Each part has a reference implementation
  on `demo/full-stack`.
- `providers.yaml`: areas `ca/conus/alaska/hawaii_bbox`; `us_states_boundary`, `us_counties_boundary`;
  FIRMS/WFIGS default to `conus_bbox`.
- `scripts/build_region_seed.py`: records outlines; writes the DB seed (`--seed-out`, S7) and web outline
  (`--web-out`, S1) only where their owners choose.
- Agent guardrail uses the US outline. ADR-011 kept as superseded. Data catalog and section-guide pointers updated.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
