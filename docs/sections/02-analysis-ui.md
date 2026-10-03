# Section 2: Analysis UI

**Stack:** React · TypeScript · TanStack Query · Plotly · Server-Sent Events · MSW (mock API) · Vitest · a few Playwright tests
**Pair partner:** Section 6 (satellite analysis): together you turn numbers into evidence people understand.
**Read first:** [Start here](../guides/start-here.md) · [Learning with AI](../guides/learning-with-ai.md) · [Coding with OpenCode](../guides/coding-with-opencode.md)

---

> **Already built for you** ([details](../platform-status.md))
>
> - **The API spec:** `contracts/openapi.yaml` (every endpoint, including cancel). Generate your types and mock server from it.
> - **Mock data:** `contracts/examples/openapi/` (create request/response, a running job, an error, a layer) and `contracts/examples/job-event/` (a full `queued → completed` sequence plus a `failed` one) for fake SSE.
> - **The result format:** the `Report` schema in `openapi.yaml` (short answer, sections with evidence ids, confidence label, limitations, sources).
> - **Evidence to render as cards:** `contracts/examples/evidence/*.json`, and the rules for each field in `contracts/evidence.schema.json`.
>
> **Your part of Milestone 1:** **S2-1 → S2-4**: the typed client + mock, the form and staged progress, evidence cards, and SSE reconnect. See [Milestone 1](../milestone-1.md).


## 1. Your job in plain English

You build **the conversation side** of the app: the panel next to the map where the user asks a question and reads the answer.

The user types a question, picks a date range, and uses the area drawn on the map (from S1). They press Analyse. Satellite analysis can take a minute, so your panel shows **live progress** ("Retrieving data… Processing satellite imagery… Checking evidence…"). When it's done, you show the answer as **evidence cards**: each fact with its source, when it was observed, when we fetched it, and its limitations. You also show a clear confidence label and charts.

**Analogy:** you're the parcel-tracking page. You place the order, watch it move through each stage, and when it arrives you get an itemised receipt showing what's in the box and where each item came from.

![Request lifecycle](../diagrams/request-lifecycle.svg)

**Done looks like:** submit a question → watch the stages → see evidence cards, a confidence label, limitations and charts. Errors, empty results and stale data each look deliberately different.

## 2. What you own

| You own | Don't touch (ask the owner) |
|---|---|
| `apps/web/src/analysis/**` (form, progress, evidence cards, charts, report view) | `apps/web/src/map/**`, `apps/web/src/app/**`, root web config (S1) |
| `apps/web/src/api/**` (typed API client + hooks + mock API) | `contracts/**` (lead) |
| (`apps/web/src/api/generated/` is generated from `openapi.yaml`: never hand-edit) | `apps/api`, `apps/worker` |

## 3. Key ideas before you start

| Term | Plain-English meaning |
|---|---|
| **REST API** | The browser talks to our Go server with HTTP requests like `POST /v1/analyses`. |
| **OpenAPI** | A file (`contracts/openapi.yaml`) that precisely describes every endpoint. We generate TypeScript types from it, so frontend and backend can't drift apart. |
| **Job / job ID** | Analysis is slow, so the API replies instantly with an ID, and you track progress with it. |
| **Job states** | `queued → validating → retrieving_data → processing_satellite → verifying_evidence → generating_report → completed`, or `failed` / `cancelled`. |
| **Server-Sent Events (SSE)** | A one-way live stream from server to browser over HTTP, using the browser's built-in `EventSource`. We use it for progress. |
| **Server state** | Data that lives on the server (jobs, evidence). TanStack Query fetches, caches and refreshes it for you. |
| **Mock API** | A fake server in the browser (MSW) that returns realistic responses, so you can build before the Go API exists. |
| **Evidence card** | One fact with its provenance: category, source, times, measurements + units, quality flags, limitations, link. |
| **Confidence label** | One of: *Unverified detection*, *Corroborated signal*, *Officially reported*, *Insufficient evidence*. Never a percentage. |

![Job states](../diagrams/job-state-machine.svg)

## 4. Learn the stack (week 0)

| Tool | Why | Official docs | Practice exercise |
|---|---|---|---|
| React + TypeScript | UI | [react.dev/learn](https://react.dev/learn) · [typescriptlang.org/docs](https://www.typescriptlang.org/docs/) | A form with validation that shows errors inline. |
| TanStack Query | Fetching + caching server data | [tanstack.com/query](https://tanstack.com/query/latest/docs/framework/react/overview) | Fetch a public JSON API with `useQuery`; show loading/error states. |
| Server-Sent Events | Live progress | [MDN: Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events) | A tiny Node server that sends a count every second; show it live in the browser. |
| MSW (Mock Service Worker) | Fake API during development | [mswjs.io/docs](https://mswjs.io/docs/) | Mock `GET /hello` and render the response. |
| openapi-typescript | TS types from `openapi.yaml` | [openapi-ts.dev](https://openapi-ts.dev/) | Generate types from a small sample OpenAPI file. |
| Plotly.js | Charts | [plotly.com/javascript](https://plotly.com/javascript/) | A before/after bar chart with a units label. |
| Playwright | A few end-to-end tests | [playwright.dev](https://playwright.dev/docs/intro) | Test "click button → text appears". |

**Learn it with AI:**
```text
Explain how I'd show live progress for a long-running job in React using Server-Sent Events
(EventSource) alongside TanStack Query. Cover: reconnecting, closing the stream when the job
finishes, and avoiding memory leaks in useEffect. Use a tiny example.
```

## 5. Set up your machine

Same as S1: Node.js LTS, clone the repo, OpenCode. You work inside the Vite app S1 creates (ticket S1-0). Until then, build components in your own branch with a temporary Vite app and move them in once S1-0 merges.

## 6. Build it step by step

### S2-1 Mock API + typed client
- **Goal:** the frontend can call every endpoint, against a mock.
- **Steps:** generate types from `contracts/openapi.yaml` into `src/api/generated/`; write small hooks (`useCreateAnalysis`, `useAnalysis(id)`, `useEvidence(id)`); set up MSW handlers returning the examples from `contracts/examples/`.
- **AI prompt:**
  ```text
  Plan a typed API layer in apps/web/src/api: generate types from contracts/openapi.yaml with
  openapi-typescript, write TanStack Query hooks for POST /v1/analyses and GET /v1/analyses/{id},
  and add MSW handlers that return the example payloads from contracts/examples. The mock must be
  switchable off with an env flag (not a secret). List files first.
  ```
- **Check yourself:** no hand-written copies of API types; field names match the contract exactly.
- **Done when:** a test calls the hook against MSW and gets typed data.

### S2-2 Analysis form + staged progress (your first deliverable)
- **Goal:** submit a question, then watch the job move through its stages.
- **Steps:** a form (question, analysis type, date range, area from S1); on submit → `POST` → job ID → open an `EventSource` on `/v1/analyses/{id}/events` → update a progress list. The mock SSE sends one event per state.
- **AI prompt:**
  ```text
  Plan an AnalysisForm and JobProgress component in apps/web/src/analysis. On submit, call the
  create hook, then subscribe to SSE events for the job ID and show each of the 9 job states with
  a clear label. Close the EventSource on completed/failed/cancelled and on unmount. Show how the
  mock will emit SSE events for local development.
  ```
- **Check yourself:** all 9 states have labels; `failed` shows `error_message`; `cancelled` looks neutral, not like an error.
- **Tests:** a state-to-label mapping test; the form blocks submit with no area and shows why.
- **Done when:** a mocked run shows every stage, and the failed/cancelled variants work.

### S2-3 Evidence cards + confidence label
- **Goal:** show each piece of evidence honestly.
- **Steps:** an `EvidenceCard` showing category, source, `observed_at`, `retrieved_at`, measurements with units, quality flags, limitations and a source link. Plus a `ConfidenceLabel` chip with the four states.
- **Rules:**
  - `agent_inference` cards look visibly different and are labelled **"Inference"**.
  - A `stale_snapshot` quality flag shows a **"Stale data"** badge.
  - No evidence at all shows **"Insufficient evidence"**, never "Nothing found".
  - Never show a confidence percentage.
- **Tests:** one test per rule above, using fixtures.
- **Done when:** every evidence type in the schema renders correctly from fixtures.

### S2-4 Reconnect without losing progress
- **Goal:** a dropped connection resumes cleanly.
- **Steps:** use the SSE event IDs; on reconnect the browser sends `Last-Event-ID` automatically with `EventSource`; also re-fetch the job status once on reconnect ([ADR-002](../adr/ADR-002-progress-events-and-sse.md)).
- **Tests:** simulate a disconnect in the mock and assert that no stage goes missing.

### S2-5 Charts + limitations panel
- **Goal:** before/after charts from S6's numbers (NDVI, dNBR) with units and dates, and a limitations panel collecting every limitation from the result.
- **Pair with S6** so the chart says exactly what the calculation means.

## 7. How your work connects

| You need | From | Until ready, use |
|---|---|---|
| `openapi.yaml`, schemas, examples | Lead | Draft examples from the connector guide |
| Drawn polygon | S1 | A hard-coded polygon fixture |
| Real API + SSE | S3 | MSW mocks |
| Calculation output shape | S6 | Example numbers agreed with S6 |

## 8. When you're stuck

Official docs → OpenCode in Plan mode ("explain, don't fix") → S1 (you share the app) or S6 → team chat, with the error, what you tried, a screenshot and your branch name.

## 9. Coming from the lead

- [x] `contracts/openapi.yaml` v0 and `job-event.schema.json` with examples in `contracts/examples/`
- [x] Evidence types: the `EvidenceType` enum in `contracts/evidence.schema.json`. Quality flags seen so far: `low_confidence`, `missing_frp`, `stale_snapshot`, `stale_forecast`, `partial_aoi_coverage`, `missing_update_time`, `missing_geometry`
- [x] Result/report shape: the `Report` schema in `contracts/openapi.yaml` (sections with `evidence_ids`, confidence label, limitations, sources)
- [ ] Decision on the auth/session model ([ADR-008](../adr/ADR-008-authentication.md))
