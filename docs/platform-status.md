# What's already built (and how to use it)

The lead has built the **core data layer** that every section plugs into. This page covers each piece: what it is, where it lives, how to use it today, what it guarantees, and what **you** are expected to do with it.

> Last updated Sep 24, 2026 · merged in [PR #4](https://github.com/samin1554/inland-resilience/pull/4) and [PR #5](https://github.com/samin1554/inland-resilience/pull/5).
> Quick check that it all works on your machine (only Docker needed): `make docker-test`.

![Team ownership](diagrams/team-ownership.svg)

## At a glance

| Component | Status | Used by |
|---|---|---|
| [1. Contracts v0](#1-contracts-v0-the-shared-language) | ✅ merged | everyone |
| [2. Connector kit + `providers.yaml`](#2-connector-kit-and-providersyaml) | ✅ merged | S4, S5, S6, S7 |
| [3. Reference connectors (4 patterns)](#3-reference-connectors-copy-dont-start-from-scratch) | ✅ merged | S4, S5, S6 |
| [4. `get_evidence()`](#4-get_evidence-the-one-way-to-read-data) | ✅ merged (in-memory cache) | S6, S8, lead's agent |
| [5. Fixtures + shared test suite](#5-fixtures-and-the-shared-test-suite) | ✅ merged | S4, S5, S6, S8 |
| [6. `kit/imagery.py`](#6-kitimagerypy-satellite-pixels) | ✅ merged | S6 |
| [7. Docker + `make` commands](#7-docker-and-make-commands) | ✅ merged (worker only) | everyone, S7 extends |
| [8. Line Fire demo](#8-the-line-fire-demo) | ✅ merged | S6, S8 |
| [9. Decisions + spec corrections](#9-decisions-and-spec-corrections) | ✅ accepted | everyone |
| [Not built yet](#not-built-yet) | job runtime (Milestone 1) · PostGIS cache store · agent (after Milestone 1) | — |

---

## 1. Contracts v0: the shared language

**What:** the exact shapes of everything that crosses a boundary.

| File | Describes | Who reads it |
|---|---|---|
| `contracts/openapi.yaml` | Every public API endpoint (spec §8 + cancel + tiles) | S2 (client + mocks), S3 (handlers) |
| `contracts/evidence.schema.json` | The **Evidence** object every data source becomes | everyone |
| `contracts/analysis-job.schema.json` | The job message Go puts on Redis `jobs` | S3, lead (job runtime) |
| `contracts/job-event.schema.json` | Progress events on Redis `job-events` → SSE | S3, S2, lead |
| `contracts/examples/` | Valid examples of all of the above, **built from real data** | S1/S2 mocks, S3 tests |
| `contracts/examples/invalid/` | Examples that must be rejected | S3 validation tests |

**How to use:** build and test against these files, never against guesses. `make validate-contracts` checks the schemas, the OpenAPI document and every example.

**Guarantee:** every example validates against its schema *and* the worker's Pydantic models (CI-ready test: `apps/worker/tests/test_contracts.py`).

**Expected of you:** if you need a field that isn't there, **don't add it locally**. Open a PR that changes `contracts/`, label it `contract-change`, and request the lead's review.

## 2. Connector kit and `providers.yaml`

**What:** the plumbing for talking to outside data sources (`apps/worker/src/inland_worker/kit/`).
- **`config/providers.yaml`** is the *only* place provider URLs, auth env-var names, timeouts, size limits, cache times and schedules live. It doubles as the **allowlist** of hosts the system may call.
- **`KitHttpClient`**: https only, allowlisted hosts (including links a provider hands back), keys read from `.env` and blanked out in every URL, log and fixture, response-size cap, bounded retries on rate limits and server errors, no redirects.
- **`BaseConnector`**: a connector writes two pure functions, `build_requests()` and `parse()`, plus an optional `follow()` for pages or links.

**Expected of you (S4, S5, S6):** never import `httpx` or call a URL yourself. Add your provider as a block in `providers.yaml` (PR, `contract-change` label) and write only the connector's two functions. Full guide: [connector guide](connectors/connector-guide.md).

## 3. Reference connectors: copy, don't start from scratch

Every data source is one of four patterns. The lead built one working, tested example of each:

| Pattern | Reference | Copy it for | Who |
|---|---|---|---|
| Keyed API (CSV/JSON + key) | `connectors/fire/firms.py` | CIMIS, AirNow | S5 |
| ArcGIS feature service | `connectors/fire/wfigs.py` | CAL FIRE historical, county boundary, BAER/MTBS, hazard zones | S4 (S5 for hazard zones) |
| Follow-the-link API | `connectors/weather/nws_forecast.py` | NWS alerts, USGS | S5 |
| STAC imagery | `connectors/imagery/earth_search_s2.py` + `kit/imagery.py` | Landsat and other collections | S6 |

**How to use:**
```bash
make new-connector NAME=calfire_historical GROUP=fire PATTERN=arcgis   # keyed | arcgis | follow_link | stac
```
This copies the reference, creates the test file (with the shared suite), a fixtures folder and a provider spec, and registers the connector. Then follow the printed next steps.

**Expected of you:** start every new source with its **provider spec** (`docs/connectors/providers/<name>.md`, reviewed by the lead), then fixtures, then code. Don't edit the reference files; suggest changes by PR.

## 4. `get_evidence()`: the one way to read data

**What:** one function that returns normalized evidence from any provider (`apps/worker/src/inland_worker/data/`).
```python
from inland_worker.data import get_evidence

result = await get_evidence("wfigs_current", bbox=(-124.5, 32.5, -114.1, 42.0))
result.items       # list[Evidence], the same shape for every source
result.freshness   # Fresh | Stale(age, reason) | Missing(reason)
result.origin      # "cache" | "live" | "snapshot" | "fixture" | "none"
```
Try it without writing code: `make docker-fetch PROVIDER=wfigs_current ARGS="--bbox=-124.5,32.5,-114.1,42.0"`.

**Guarantees:** fresh cache → live fetch → last good copy flagged `stale_snapshot` → `Missing` (never an empty "success"). Every call leaves a trace record (the future `tool_executions` row).

**Current limit:** the cache is **in memory** until S7's cache tables (ADR-006) exist; then the lead swaps in a PostGIS store behind the same function.

**Expected of you:** S6 and S8 read data only through this (or `kit/imagery.py`), never by calling connectors or providers directly. All sources: [data catalog](data-catalog.md).

## 5. Fixtures and the shared test suite

**What:** real recorded provider responses in `apps/worker/tests/fixtures/<provider>/<case>/`, and a test suite every connector inherits (`inland_worker.kit.testing.ConnectorContract`, spec §21).

**How to use:**
```bash
make record-fixture PROVIDER=<id> CASE=success ARGS="--area sb_county_bbox"   # needs network (+ your key if the source has one)
make derive-fixtures PROVIDER=<id> ARGS="--empty-csv"                         # makes malformed / extra_fields (/ empty)
make test-connector PROVIDER=<id>                                             # runs the whole suite for your connector
```
Set `INLAND_DATA_MODE=fixture` to make **everything** use recordings: no keys, no network.

**Guarantees:** the recorder blanks out keys; the suite checks success, empty, timeout, rate-limit, malformed data, schema drift, timestamps, limitations and "no secrets leaked".

**Expected of you:** every connector ships the four standard cases (`success`, `empty`, `malformed`, `extra_fields`) and passes `make test-connector`.

## 6. `kit/imagery.py`: satellite pixels

**What:** reads Sentinel-2 pixels for an area, correctly ([ADR-009](adr/ADR-009-imagery-without-earth-engine.md)). No account or key.
```python
from inland_worker.data import get_evidence
from inland_worker.kit.imagery import aoi_grid, pick_scene, read_bands

scenes = (await get_evidence("earth_search_s2", area=aoi, date_range={"start": "2024-10-01", "end": "2024-10-31"})).items
grid = aoi_grid(aoi)                                   # repaired area, UTM grid, 20 m
stack = read_bands(pick_scene(scenes), grid, bands=("nir", "swir22"))
stack.arrays["nir"], stack.valid_pct_inside            # reflectance (NaN = cloud / no data), usable %
```
**Guarantees:** reads only the area's pixels; applies the reflectance offset correctly for each image; masks clouds; merges image tiles; only allowlisted image URLs; logs each read.

**Expected of you (S6):** build the science (NDVI, NBR/dNBR, classes, overlays) on top of `read_bands()`, in `apps/worker/src/inland_worker/satellite/`. The kit does no science.

## 7. Docker and `make` commands

**What:** the worker runs identically on any machine. Only Docker Desktop is required. `make help` lists everything.

| Command | Does |
|---|---|
| `make docker-test` | all offline worker tests, in Docker |
| `make docker-test-live` | real provider calls (keys from your `.env`; keyless sources always run) |
| `make docker-fetch PROVIDER=… ARGS=…` | fetch one source and print a summary |
| `make demo-line-fire` | the satellite demo, output in `docs/research/line-fire-2024/output/` |
| `make worker-install` · `make test-worker` · `make lint-worker` | the same without Docker (needs uv) |

**Expected of you (S7):** *extend* `infrastructure/docker-compose.yml` and the `Makefile` (Postgres/PostGIS, Redis, MinIO, API, web, `make dev`, migrations, CI). Keep the existing worker targets working.

## 8. The Line Fire demo

**What:** proof that burn severity works without Earth Engine: our Sentinel-2 dNBR for the 2024 Line Fire vs the official USFS BAER map, **98.5% within one severity class**. See [docs/research/line-fire-2024](research/line-fire-2024/README.md), or run `make demo-line-fire`.

**Expected of you:** S6 starts here (it's the whole pipeline in one readable script). S8 can use its comparison as a first evaluation case.

## 9. Decisions and spec corrections

Where we deliberately differ from the spec. Details are in the [ADRs](adr/README.md).
- **No Google Earth Engine in the MVP:** Sentinel-2 via Earth Search + official BAER/MTBS maps ([ADR-009](adr/ADR-009-imagery-without-earth-engine.md)).
- **CAL FIRE historical perimeters:** use `California_Historic_Fire_Perimeters` (layer 2). The spec's URL only holds 2025 fires ([calfire-historical.md](connectors/providers/calfire-historical.md)).
- **Hybrid ingestion:** scheduled refresh + on-demand ([ADR-001](adr/ADR-001-hybrid-ingestion.md)). **Progress/SSE, retries/cancel, single status writer, cache tables:** ADR-002 to ADR-006.
- **Evidence type `weather_alert`** was added to the contract for NWS alerts.

---

## Not built yet

| Piece | Owner | When | What you can do meanwhile |
|---|---|---|---|
| **Job runtime**: worker consumes `jobs`, moves job status (only writer, ADR-004), publishes `job-events`, retries/cancel/timeouts (ADR-003) | Lead | **Milestone 1** | Build against the job/event schemas; see [Milestone 1](milestone-1.md) |
| **PostGIS cache store** behind `get_evidence()` | Lead | after S7's cache tables (ADR-006) | Nothing changes for callers |
| **The agent** (LangGraph: plan → approved tools → verify → cited answer) | Lead | **after Milestone 1** (a working prototype exists locally) | Build your functions as clean, tested tools; the agent will call them |
| **LLM provider** ([ADR-007](adr/ADR-007-llm-provider.md)) | Lead | with the agent | Nothing |
| **Authentication** ([ADR-008](adr/ADR-008-authentication.md)) | Lead + S3 | before public deployment | S3 builds sessions behind middleware |
