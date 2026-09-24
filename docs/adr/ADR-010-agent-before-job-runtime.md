# ADR-010: Build the agent before the job runtime

## Status
Accepted (Sep 24, 2026). Deviates from spec §26 ("Do not add LangGraph until the fixture vertical slice works").

## Context
The lead wants the agentic system in place before the team builds their parts, so everyone targets a working core. The spec defers the agent until Milestone 1 (a request travelling through all three apps) to avoid building the agent on unproven plumbing.

## Decision
- Build the agent now as a **standalone, fully tested function**: `run_analysis(question, area, date_range, llm=…, data=…)` in `apps/worker/src/inland_worker/agent/`. It needs no Redis, Postgres or Go. The job runtime will call it later and publish progress around it.
- The risk the spec guards against is covered differently: the agent runs on the **real data pipeline** (connectors, `inland_data`, `kit/imagery`) in fixture mode, and is tested end to end, including declines, bad model output, model outages, prompt injection and citation checks.
- Workflow (LangGraph): `parse → validate_scope → (decline | plan → run_tools → verify → explain)`.
- **Baselines owned by other sections**, clearly marked in code: `satellite/burn.py` (S6) and `agent/verify.py` rules (S8 moves and extends them in `evidence/`).

## Consequences
- The team sees and can call the real agent from day one (`python -m inland_worker ask …`).
- Milestone 1 still has to happen (job runtime, Go API, SSE); the agent plugs in as one step.
- Some agent code may change when S8's verification rules and S4's official historical sources land. Expected, and cheap.
