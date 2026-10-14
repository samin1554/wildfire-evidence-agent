# AGENTS.md: rules for AI coding agents in this repo

This file is read by AI coding agents (OpenCode, Codex, Claude Code and others). Humans: see `README.md`.

## What this project is
Inland Resilience Agent: evidence-backed geospatial analysis for San Bernardino County (wildfire impact first). It is a research tool, **not** an emergency, evacuation or prediction service. Never generate evacuation guidance.

## Architecture (do not change without an ADR in docs/adr/)
- `apps/web`: React + TypeScript + Vite + MapLibre. Presentation only. Never calls providers or holds secrets.
- `apps/api`: Go (net/http + chi + pgx). Public API, validation, job creation, SSE. No scientific calculations.
- `apps/worker`: Python 3.12+. Connectors, geospatial math, LangGraph agent. The only app that talks to external providers.
- PostgreSQL + PostGIS, Redis Streams. Local dev via `make dev` (Docker Compose).

## Rules
1. **Contracts are the source of truth:** `contracts/openapi.yaml` and `contracts/*.schema.json`. Never rename or reshape shared fields locally. Propose a `contract-change` instead.
2. **No secrets.** Never read, print, log or commit `.env`, API keys, service-account JSON or auth headers. New config goes in `.env.example` with an empty value. Never use a `VITE_` prefix for secrets.
3. **Network access to providers only through the worker's connector kit** (`apps/worker/src/inland_worker/kit/`). Provider URLs live only in `apps/worker/config/providers.yaml`. No ad-hoc `httpx`/`requests`/`fetch` calls to external services.
4. **Fixtures before live APIs.** Tests must run offline on recorded fixtures (`INLAND_DATA_MODE=fixture`).
5. **Every change needs tests:** a success case and an empty/failure case. Don't delete or weaken tests to make them pass.
6. **The LLM plans and explains; code calculates.** NDVI, areas, distances, overlaps and confidence are computed by deterministic functions, never by the model.
7. **Honest evidence.** Every user-facing fact carries source, observed time, retrieved time and limitations. A FIRMS hotspot is never a "confirmed fire"; missing data never means "nothing happened".
8. **No new dependencies** without saying so explicitly in the plan, so the human can approve it.
9. **Small steps.** Prefer minimal diffs; don't reformat unrelated code.

## Commands
`make dev` · `make test` · `make lint` · `make fixtures` · `make migrate` · `make seed`

## Where to read more
- Running the stack: `docs/demo/README.md`
- Connector guide: `docs/connectors/connector-guide.md`
- Decisions: `docs/adr/`
