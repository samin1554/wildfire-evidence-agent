# Milestone 1: one request, end to end

**Goal (spec §20):** *one request travels through all three apps and produces a visible result, without live providers.*

A user draws an area and asks a question in the browser. Go creates a job and puts it on Redis. The Python worker picks it up, runs, and sends progress back. The browser shows each stage live, then the evidence on the map and in cards. Everything runs on **recorded data** (`INLAND_DATA_MODE=fixture`).

The agent is **not** part of Milestone 1: it comes after (see [what's built](platform-status.md#not-built-yet)). In Milestone 1 the worker returns fixture evidence directly.

![Request lifecycle](diagrams/request-lifecycle.svg)

## Who builds what

| # | Piece | Owner | Builds against (already exists) | Hands to |
|---|---|---|---|---|
| 1 | Draw an area, show evidence on the map | **S1** | `contracts/examples/evidence/*.json` (real FIRMS/WFIGS/NWS examples) | S2 (area), user |
| 2 | Form → `POST /v1/analyses`, live progress over SSE, evidence cards | **S2** | `contracts/openapi.yaml` (+ a mock server), `contracts/job-event.schema.json`, `contracts/examples/job-event/` | user |
| 3 | `POST`/`GET /v1/analyses`, validation, insert `queued` job, `XADD` to `jobs`, SSE from `job-events` | **S3** | `openapi.yaml`, `analysis-job.schema.json`, `job-event.schema.json`, `contracts/examples/invalid/` | worker, S2 |
| 4 | Postgres/PostGIS, Redis, MinIO in compose; `analysis_jobs` + `evidence_items` migrations; `make dev`; CI | **S7** | existing `infrastructure/docker-compose.yml` + `Makefile` (extend them), spec §10 tables + `cancel_requested_at` (ADR-003) | everyone |
| 5 | **Job runtime:** consume `jobs`, move status (only writer), write evidence, publish `job-events`, retries/cancel/timeout | **Lead** | the schemas above, ADR-002/003/004, `get_evidence()` in fixture mode | S3, S2 |
| — | Fixture evidence for the demo area | done | `apps/worker/tests/fixtures/` | worker |

S4, S5, S6 and S8 aren't on the Milestone 1 critical path. Keep building connectors, satellite science and evidence rules on fixtures. They plug into the same flow afterwards.

## The interfaces (so nobody waits)

**Redis streams (ADR-002/003):**

| Stream | Written by | Message | Read by |
|---|---|---|---|
| `jobs` | Go (S3), after inserting the row | field `payload` = JSON matching `analysis-job.schema.json` | worker, consumer group `workers` |
| `job-events` | worker (lead), after each status change | field `payload` = JSON matching `job-event.schema.json` | Go (plain `XREAD`, every instance), forwarded as SSE `id: <seq>` |

> The `payload` field name and group name `workers` are the lead's proposal for Milestone 1. Changing them is a `contract-change` PR.

**Status rules (ADR-004):** Go inserts the job as `queued` and never changes status again (except setting `cancel_requested_at`). The worker makes every later transition (`validating → retrieving_data → … → completed`, or `failed`/`cancelled`), writing the database first, then the event. See the [job state diagram](diagrams/job-state-machine.svg).

**Tables (S7, spec §10):** `analysis_jobs` (plus `cancel_requested_at`), `evidence_items`, `tool_executions`, `artifacts`, `areas_of_interest`, `users`. See the [schema diagram](diagrams/database-schema.svg).

## Build without waiting for each other

| You are | Not ready yet? Use this |
|---|---|
| S1 / S2 | A mock API (MSW) serving `contracts/examples/`; fake SSE events from `contracts/examples/job-event/` |
| S3 | Postgres + Redis in Docker (your own compose snippet until S7's lands); watch your messages with `redis-cli XREAD STREAMS jobs 0` |
| S3 (progress) | Fake worker events: `redis-cli XADD job-events '*' payload '<a job-event example>'` |
| Lead (worker) | Fake jobs: `redis-cli XADD jobs '*' payload "$(cat contracts/examples/analysis-job/line-fire.json)"` |

## Done when (the exit demo)

1. `make dev` starts everything, and all health checks are green (S7).
2. In the browser, draw an area near San Bernardino and submit a question (S1, S2).
3. The API answers straight away with a job ID (S3).
4. The progress list shows each stage as it happens (S3 SSE → S2), ending in `completed`.
5. The evidence appears on the map with a legend and popups, and as cards showing source, times and limitations (S1, S2).
6. Kill the worker mid-job: the job is picked up again and, if it keeps failing, ends `failed` with a clear message. It never stays stuck (lead, ADR-003).
7. Each piece has tests, and the whole flow has one end-to-end test (Playwright or a script).

Also see the [sections index](sections/README.md) for where each section stands, and the [definition of done](guides/start-here.md#5-done-means-done).
