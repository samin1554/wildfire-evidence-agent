# Architecture Decision Records

| ADR | Title | Status |
|---|---|---|
| [001](ADR-001-hybrid-ingestion.md) | Hybrid ingestion through a worker `--mode=ingest` | Accepted |
| [002](ADR-002-progress-events-and-sse.md) | Progress events stream and SSE delivery | Accepted |
| [003](ADR-003-job-retries-and-cancellation.md) | Job retries, dead-letter and cancellation | Accepted |
| [004](ADR-004-job-status-single-writer.md) | Single writer for `analysis_jobs.status` | Accepted |
| [005](ADR-005-gee-tile-access.md) | Earth Engine tile access through the API | Accepted · amended by 009 |
| [006](ADR-006-cache-and-snapshots.md) | Cache and last-known-good snapshot tables | Accepted |
| [007](ADR-007-llm-provider.md) | LLM provider for the agent (OpenRouter free models) | Accepted |
| [008](ADR-008-authentication.md) | Authentication | **Open** |
| [009](ADR-009-imagery-without-earth-engine.md) | Satellite imagery without Earth Engine (MVP) | Accepted |
| [010](ADR-010-agent-before-job-runtime.md) | Build the agent before the job runtime | Accepted |

"Proposed" means a recommendation ready for the lead to accept. "Open" means options only; no recommendation is final.
Spec §26 says the core architecture must not change without an explicit decision. These records are those decisions.
