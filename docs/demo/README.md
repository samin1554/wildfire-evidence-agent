# Running the full stack

The whole product end to end: web → Go API → Redis → worker (agent + satellite maths) → SSE → map,
evidence cards and a cited report. It runs **offline on recorded data** by default.

## Run it

Needs Docker Desktop only (no Go, Node or Python on your machine).

```bash
make dev        # postgres/postgis, redis, minio, migrations, seed, api, worker, web; waits for health
```

Open **http://localhost:5173**. Pick a demo area (or draw your own anywhere inside the dashed US outline), then run.

```bash
make e2e        # end-to-end acceptance (Milestone 1 "Done when", plus satellite, report, crash/retry/cancel)
make test       # unit tests: worker (pytest), api (go test in Docker), web (vitest)
make e2e-ui     # browser test (Playwright; first run: cd apps/web && npx playwright install chromium)
make down       # stop (V=1 also deletes data)
```

## Region: the United States ([ADR-012](../adr/ADR-012-national-region.md), proposed)

Scope is the 50 states + DC, decided by the Census TIGERweb outline that `apps/worker/scripts/build_region_seed.py`
generates into the DB seed (API), the worker guardrail and the map. Areas over Mexico, Canada or open ocean get
`AREA_OUTSIDE_REGION`; territories and areas crossing the antimeridian aren't supported yet. Per-job limits
(5,000 km², 3 years) are unchanged.

Official historical perimeters come from CAL FIRE inside California (1950+) and NIFC WFIGS everywhere else
(~2016+); FIRMS, Sentinel-2, NWS and WFIGS current already cover the whole country.

## "Active now": follow the data ([ADR-013](../adr/ADR-013-activity-feed.md), proposed)

The app opens on **Active now**: recent NASA FIRMS heat detections across the US, grouped into clusters, ranked,
and matched to current official perimeters (NIFC WFIGS). Click a cluster (in the list or on the map), then
**Analyse this area**: the area, question and last-4-days dates are filled in and the normal analysis runs.
The `worker-activity` service rebuilds the feed every 30 minutes; the API only serves the latest snapshot
(`GET /v1/activity`). A cluster is a place worth a look, not a confirmed fire.

Each cluster shows its county and state, which satellites saw it (NOAA-21, NOAA-20, Suomi-NPP), a trend once there
is a day of history (New / Growing / Steady / Shrinking), the nearest official incident when none overlaps, and a
"likely persistent heat source" note for places that glow on 5+ of the last 14 days without an official perimeter
(hidden by default). Filter by state, official only or size, sort, and share the address bar: `?cluster=…` opens a
cluster, `?job=…` reopens an analysis.

Analyses mask water out of burn severity (a reservoir level change no longer reads as "burned") and cite NWS
watches/warnings in effect (e.g. Red Flag Warnings) for current questions.

## Demo areas

| Button | Area / dates | What runs | Expected confidence |
|---|---|---|---|
| **Line Fire 2024** | Highland / Running Springs, 2024-08-01 → 2024-10-31 | CAL FIRE historical perimeter + Sentinel-2 **dNBR** burn severity + **NDVI** change on recorded imagery, overlay tiles on the map | `officially_reported` (the CAL FIRE perimeter), with the measured burn alongside |
| **Alexander Mountain Fire 2024** | Loveland / Masonville, Colorado, 2024-07-01 → 2024-08-31 | NIFC WFIGS perimeter + dNBR/NDVI on recorded imagery (4 Jul → 28 Aug) | `officially_reported`; ~7,250 acres moderate/high measured vs NIFC's 9,625 |
| **Thompson Fire 2024** | Oroville, 2024-06-20 → 2024-07-15 | CAL FIRE perimeter + dNBR/NDVI on recorded imagery (22 Jun → 12 Jul) | `officially_reported`; the measured burn (~3,150 acres moderate/high) agrees with CAL FIRE's 3,782 acres |
| **Recent detections** | Victorville / Apple Valley, 2026-09-19 → 24 | NASA FIRMS heat detections, NIFC current perimeters, NWS forecast (recorded Sep 2026) | `unverified_detection` |

Any other area works too. Data is clipped to your polygon; an area or date range the recordings don't cover
honestly reports **insufficient evidence** (with the gaps listed), never someone else's result.

## What happens when you click "Run analysis"

| Step | Where | Code |
|---|---|---|
| 1. Client checks (inside county, < 5,000 km², no crossing edges) | web | `apps/web/src/map/region.ts` |
| 2. `POST /v1/analyses`: strict JSON, type, dates ≤ 3 years, then PostGIS: valid / `ST_Within` region / area | api | `apps/api/internal/httpapi/{validate,analyses}.go` |
| 3. Insert `queued` (the API's only status write), `XADD jobs` | api | `internal/store`, `internal/queue` |
| 4. `XREADGROUP workers`, guarded transitions, DB first then `XADD job-events` | worker | `apps/worker/src/inland_worker/jobs/` |
| 5. Agent: scope check → plan → approved tools → verify → cited report (rule-based without an LLM key) | worker | `inland_worker/agent/` |
| 6. dNBR/NDVI on the user's area grid; overlay tiles rendered to the shared volume | worker | `inland_worker/satellite/` |
| 7. SSE: missed history, DB snapshot, live events; closes at a terminal status | api | `internal/httpapi/events.go` |
| 8. Evidence (paged), layers, report → map + cards + report panel | web | `apps/web/src/{analysis,map}/` |

**Reliability (ADR-003):** a heartbeat keeps a running job's lease; a reaper `XAUTOCLAIM`s messages from a dead
worker; after 3 attempts the job ends `failed` / `RETRIES_EXHAUSTED` and the message goes to `jobs-dead`; a
10-minute wall clock ends `failed` / `TIMEOUT`; cancel is checked between every step. A sweep re-enqueues
`queued` jobs whose Redis message was lost, so the API never has to write status (ADR-004).

## Fixture vs live

| | Fixture (default) | Live |
|---|---|---|
| Switch | `INLAND_DATA_MODE=fixture` | `INLAND_DATA_MODE=live` in `.env`, then `make dev` |
| Keys | none | `FIRMS_MAP_KEY` (FIRMS); Earth Search, WFIGS, NWS need none |
| "Today" | `INLAND_FIXTURE_TODAY=2026-09-24` (when the data was recorded) | the real date |
| Imagery | `apps/worker/tests/fixtures/imagery/line_fire_2024/` (recorded once by `scripts/record_imagery_fixture.py`) | Sentinel-2 COGs read through `kit/imagery` |
| Cache | not used | `provider_fetches` / `cached_evidence` (PostgresCacheStore) |

**LLM:** without `OPENROUTER_API_KEY` the agent uses its rule-based planner and wording (fully deterministic).
With a key it plans and explains through OpenRouter, still validated, cited and never calculating (ADR-007/010).

## Where to look in the code

| Area | Code |
|---|---|
| Map | `apps/web/src/map/MapView.tsx` (Terra Draw, layers, legend, popups), `region.ts` |
| Analysis UI | `apps/web/src/analysis/` (`useAnalysis.ts` SSE flow, `progress.ts` reducer, cards, report) |
| Go API | `apps/api/` (all `openapi.yaml` routes, SSE, PostGIS validation, rate limit) |
| Connectors | `connectors/fire/calfire_historical.py` (an ArcGIS copy of `wfigs`), called through `get_evidence()` |
| Satellite | `apps/worker/src/inland_worker/satellite/` (`burn.py`, `ndvi.py`, `overlay.py`, `fixtures.py`) |
| Platform | `infrastructure/docker-compose.yml`, `database/`, `Makefile`, `.github/workflows/ci.yml` |
| Evidence | `agent/verify.py` (baseline labels), `jobs/layers.py`, the report sections |

## Open design questions

Each has a working answer in the code today; none changes a contract.

1. **`/report` for failed or declined jobs** returns 409 `JOB_NOT_COMPLETED`, but the contract describes 409 as
   "hasn't finished yet". A failed job *has* finished. Add a distinct code?
2. **Decline codes** (`EMERGENCY_REDIRECT`, `UNSUPPORTED_PREDICTION`, `DATE_IN_FUTURE`) appear as the job's
   `error_code` but aren't listed in `Error.code`. Generic request errors use `INVALID_REQUEST`, also unlisted.
3. **Evidence idempotency key:** ADR-003 says `(job_id, source, source_record_id)`; computed evidence has no
   record id, so the code keys on `(job_id, id)` (the deterministic evidence id).
4. **SSE order:** the contract says the DB state is sent "first". The API sends missed history first, then the
   DB state, so `seq` always increases. Clients see the same final state either way.
5. **dNBR-only label:** a measured burn alone is `unverified_detection` (baseline `verify.py`); a calibrated rule is future work.
6. **Fixture data inside product code:** fixture mode reads `apps/worker/tests/fixtures/` at runtime. It works
   (the image ships them) but a proper fixture store location is worth deciding.
7. **`calfire_historical` is a minimal connector**: it queries layer 2 of the historic
   service by envelope and fire year, recorded for 2024 fires in the county box.
