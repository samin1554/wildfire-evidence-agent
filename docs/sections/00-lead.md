# Lead: what you can rely on

The lead builds the core that every section plugs into. You don't need to know how it works inside, only **what it gives you and roughly when**.

| The lead provides | What it means for you | Rough timing |
|---|---|---|
| **Contracts** (`contracts/openapi.yaml`, `evidence.schema.json`, `analysis-job.schema.json`, `job-event.schema.json` + examples) | The exact shapes of API requests, responses, jobs, progress events and evidence. Build against these, never guesses. | Week 1 (v0) |
| **Connector kit** + `make new-connector` / `make record-fixture` / shared test suite | Connector sections write only `build_requests` + `parse`; HTTP, keys, retries, caching and fixtures are handled. | Week 1–2 |
| **Reference connectors**, one per source pattern: `firms` (keyed API), `wfigs_current` (ArcGIS), `nws_forecast` (follow-the-link), `kit/imagery.py` (Sentinel-2 via Earth Search, ADR-009) | Every other source is a copy of one of these. S4, S5 and S6 always start from working code, fixtures and tests. | Week 2–3 |
| **[Data catalog](../data-catalog.md)** | One page listing every source, its `provider_id`, owner, freshness and status. | Kept up to date |
| **`inland_data.get_evidence()`** | The one way to read data inside the worker; it handles cache, freshness and live fallback. | Week 2 |
| **Job runtime** (queue consumer, status transitions, progress events) | Jobs flow from Go to the worker and progress flows back. | Milestone 1 |
| **Agent** (LangGraph workflow, approved tools, guardrails): **built** ([ADR-010](../adr/ADR-010-agent-before-job-runtime.md)) | Your functions become tools the agent can call; it never does the math itself. Try it: `python -m inland_worker ask …` | Done (v0) |
| **`AGENTS.md`**, ADRs, reviews, merges | Project rules for AI agents; decisions; final say on contract changes. | Ongoing |

Contract changes: open a PR labelled `contract-change` and request the lead's review.

Details about the lead's own implementation are intentionally not in this repo yet. Each section guide has a **"Coming from the lead"** checklist that will be filled in as these pieces land.
