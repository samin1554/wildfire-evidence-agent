# Sections: who builds what

> **New to the project?** Read [Start here](../guides/start-here.md), then [What's already built](../platform-status.md), then your section guide below. The team's current goal is **[Milestone 1](../milestone-1.md)**.

Eight sections plus the lead. Each section owns a set of paths that **no other section edits** except by pull request with that owner's review. See the [team ownership diagram](../diagrams/team-ownership.html).

| # | Section | Doc | Builds against | First deliverable |
|---|---|---|---|---|
| 0 | Lead: contracts, data layer, job runtime, agent | [00-lead](00-lead.md) | — | ✅ contracts + data layer done · job runtime next |
| 1 | Map frontend | [01-map-frontend](01-map-frontend.md) | GeoJSON fixtures | FIRMS fixture on the map with legend + popup |
| 2 | Analysis UI | [02-analysis-ui](02-analysis-ui.md) | OpenAPI mocks | Mocked job with staged progress + evidence cards |
| 3 | Go API | [03-go-api](03-go-api.md) | OpenAPI, migrations | `POST`/`GET /v1/analyses` against Postgres |
| 4 | Fire connectors | [04-fire-connectors](04-fire-connectors.md) | Lead's ArcGIS reference (`wfigs`), fixtures | CAL FIRE + county boundary specs and fixtures, then connectors |
| 5 | Weather/env connectors | [05-weather-connectors](05-weather-connectors.md) | Lead's `nws_forecast` + `firms` references, fixtures | NWS alerts + CIMIS specs and fixtures, then connectors |
| 6 | Satellite analysis | [06-satellite-analysis](06-satellite-analysis.md) | Lead's `kit/imagery.py` (Earth Search, ADR-009) | NDVI before/after for a fixed polygon |
| 7 | Platform + data infra | [07-platform-data-infra](07-platform-data-infra.md) | — | `make dev` with all health checks green |
| 8 | Evidence + evaluation | [08-evidence-evaluation](08-evidence-evaluation.md) | Evidence schema, fixtures | Confidence-label rules over fixture evidence |

## Path ownership (no overlaps)

| Path | Owner |
|---|---|
| `contracts/**` | Lead |
| `apps/worker/pyproject.toml`, `apps/worker/src/inland_worker/{__main__.py,contracts,kit,data,agent,jobs}/**`, `apps/worker/config/providers.yaml` | Lead |
| `apps/web/*` (root config), `apps/web/src/{app,map}/**` | S1 |
| `apps/web/src/{analysis,api}/**` | S2 (`api/generated/` is generated, never hand-edited) |
| `apps/api/**` | S3 |
| Reference connectors: `connectors/fire/{firms,wfigs}.py`, `connectors/weather/nws_forecast.py`, `connectors/imagery/earth_search_s2.py` + their tests and fixtures | Lead |
| All other `apps/worker/src/inland_worker/connectors/fire/**` + tests and fixtures | S4 |
| All other `apps/worker/src/inland_worker/connectors/weather/**` + tests and fixtures | S5 |
| `apps/worker/src/inland_worker/satellite/**`, `apps/worker/tests/satellite/**` | S6 |
| `infrastructure/**`, `database/**`, `Makefile`, `.github/**`, `.env.example`, `apps/worker/src/inland_worker/ingest/**` | S7 |
| `apps/worker/src/inland_worker/{evidence,reports}/**`, `apps/worker/eval/**`, `docs/evaluation.md` | S8 |
| `docs/adr/**`, `docs/connectors/{connector-guide,provider-spec-template}.md`, `docs/diagrams/**`, `docs/guides/**`, `docs/data-catalog.md`, `AGENTS.md`, `docs/architecture.md`, `docs/safety-model.md` | Lead |
| `docs/connectors/providers/<p>.md` | That provider's builder (see the [data catalog](../data-catalog.md)) |
| `docs/onboarding.md`, `CONTRIBUTING.md` | S7 |

Shared files everyone *adds to* but the lead reviews: `providers.yaml`, `contracts/**`. Changes to either need a PR labelled `contract-change`.

## Where we are and what's next

| Stage | What | Status |
|---|---|---|
| Foundation | Contracts v0, connector kit, 4 reference connectors, `get_evidence()`, `kit/imagery.py`, Docker | ✅ done (lead) · [details](../platform-status.md) |
| **Milestone 1** | One request through web → Go → Redis → worker → SSE → web, on recorded data | ⏳ **now**: S1, S2, S3, S7 + lead's job runtime · [plan](../milestone-1.md) |
| In parallel | S4/S5 connectors (copy the references), S6 science on `kit/imagery.py`, S8 rules on fixture evidence | ⏳ now |
| Milestone 2 | Live data for all sources, caching in PostGIS | next |
| Milestone 3–4 | Satellite layers in the UI; the agent (plan → approved tools → verify → cited answer) | after Milestone 1 |

**Nobody waits on anybody.** Frontend uses OpenAPI mocks, connectors use recorded fixtures, the worker runs in `INLAND_DATA_MODE=fixture`.

## Pairing (spec §16, rotate every ~2 weeks)

- Lead + S3: public API and security boundary
- S1 + S4: normalized geography renders correctly
- S2 + S6: calculations become understandable evidence
- S5 + S7: ingest scheduling and cache tables
- S8 + Lead: verification rules inside the agent

## Every ticket uses the spec §17 format

Outcome · Input · Output · Files · Depends on · Acceptance · Fixture · Success test · Failure/empty test · 2-minute demo. Keep tickets to 1–2 days.

## Definition of done (spec §25)
Acceptance criteria pass · automated tests pass · no secrets in code, fixtures or logs · input/output match the schemas · failure and empty paths implemented · user-facing data shows source + timestamp · limitations visible · docs updated · a teammate can run and demo it · reviewed and merged.
