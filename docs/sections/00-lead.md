# Lead: what's built, what's next

The lead owns the **core** every section plugs into: the contracts, the data layer (connector kit, reference connectors, `get_evidence()`, `kit/imagery.py`), the job runtime and, later, the agent. You don't need to know how these work inside, only how to use them and what to expect.

**→ Full details, with usage and what's expected of you: [What's already built](../platform-status.md)**

## Status

| Piece | Status | Where |
|---|---|---|
| Contracts v0 (API spec, evidence, job and event schemas, real examples) | ✅ done | `contracts/` |
| Connector kit + `providers.yaml` + shared test suite + `make new-connector` / `record-fixture` / `derive-fixtures` | ✅ done | `apps/worker/src/inland_worker/kit/` |
| Reference connectors: FIRMS (keyed), WFIGS (ArcGIS), NWS forecast (follow-the-link), Earth Search (STAC imagery) | ✅ done | `apps/worker/src/inland_worker/connectors/` |
| `get_evidence()` (cache → live → stale copy → missing) | ✅ done, in-memory cache | `apps/worker/src/inland_worker/data/` |
| `kit/imagery.py` (satellite pixels for an area) | ✅ done | `apps/worker/src/inland_worker/kit/imagery.py` |
| Docker image + `make docker-*` + Line Fire demo | ✅ done | `infrastructure/`, `Makefile`, `docs/research/` |
| **Job runtime** (Redis consumer, status transitions, progress events, retries/cancel) | ⏳ **Milestone 1** | `apps/worker/src/inland_worker/jobs/` |
| PostGIS cache store | ⏳ after S7's cache tables | `data/` |
| **Agent** (LangGraph, approved tools, guardrails) | ✅ v0 built ([ADR-010](../adr/ADR-010-agent-before-job-runtime.md)); try `python -m inland_worker ask …` | `apps/worker/src/inland_worker/agent/` |

## How the lead works with you

- **Contracts and `providers.yaml` are shared.** Propose changes by PR with the `contract-change` label; the lead reviews.
- **Lead-owned paths** (`contracts/`, `kit/`, `data/`, the reference connectors, `jobs/`, `agent/`) change only through the lead. Suggest improvements by issue or PR.
- **Your "Coming from the lead" checklist** (section 9 of your guide) is kept current: ticked items are done, and the rest is what you're waiting on.
- **Pairing:** Lead + S3 on the API/security boundary and the job flow; Lead + S8 on verification rules for the agent.
