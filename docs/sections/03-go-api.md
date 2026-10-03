# Section 3: Go API

**Stack:** Go · `net/http` + chi router · pgx (PostgreSQL) · go-redis · Server-Sent Events · OpenAPI validation · Go's `testing` package
**Pair partner:** the lead (the public API is the security boundary).
**Read first:** [Start here](../guides/start-here.md) · [Learning with AI](../guides/learning-with-ai.md) · [Coding with OpenCode](../guides/coding-with-opencode.md)

---

> **Already built for you** ([details](../platform-status.md))
>
> - **What to validate against:** `contracts/openapi.yaml`, and the job message you put on Redis in `contracts/analysis-job.schema.json`.
> - **Validation test cases:** `contracts/examples/invalid/` (payloads your API must reject) plus the valid ones in `contracts/examples/openapi/`.
> - **Progress you'll relay:** `contracts/job-event.schema.json` + `contracts/examples/job-event/`. Stream names and message layout: [Milestone 1 § interfaces](../milestone-1.md#the-interfaces-so-nobody-waits).
> - **The supported region** is `sb_county_bbox` in `apps/worker/config/providers.yaml` until S4's county polygon lands.
>
> **Your part of Milestone 1:** **S3-0 → S3-2** (+ cancel): create/get analysis, `XADD` to `jobs`, and SSE from `job-events`. You're on the critical path. See [Milestone 1](../milestone-1.md).


## 1. Your job in plain English

You build **the front door** of the system. Every request from the browser goes through your Go server, and nothing reaches the database or the workers without passing your checks.

When a user asks for an analysis, you:
1. **Check the request.** Is the area inside San Bernardino County? Is the polygon valid and not too big? Is the date range allowed?
2. **Create a job** in the database with status `queued`.
3. **Put a small message on the job queue** (Redis Streams) for the Python worker.
4. **Answer immediately** with the job ID. You never make the browser wait for satellite analysis.
5. **Stream progress** to the browser as the worker reports it (Server-Sent Events).
6. **Serve results**: evidence, map layers, reports.

**Analogy:** you're the waiter and the order system. You check the order is on the menu, write the ticket, clip it on the kitchen rail, give the customer a number, and call out updates. You never cook.

![Request lifecycle](../diagrams/request-lifecycle.svg)

**Done looks like:** `POST /v1/analyses` returns a job ID in milliseconds; bad requests get clear error codes; progress streams live; results can be fetched by job ID.

## 2. What you own

| You own | Don't touch |
|---|---|
| `apps/api/**` (all Go code, tests and Go module files) | `contracts/**` (lead: propose changes via a `contract-change` PR) |
| | `database/migrations/**` (S7: you'll *request* schema changes) |
| | anything in `apps/worker`, `apps/web` |

**The rule you enforce:** Go controls requests and jobs. It never calculates NDVI or burn severity, never runs the agent, and never calls data providers. It serves raster overlays the worker has already rendered; it never calls imagery providers.

## 3. Key ideas before you start

| Term | Plain-English meaning |
|---|---|
| **Handler** | A Go function that receives an HTTP request and writes a response. |
| **Router (chi)** | Maps URLs + methods (`POST /v1/analyses`) to handlers, and supports middleware. |
| **Middleware** | Code that wraps every request: logging, rate limiting, sessions, panic recovery. |
| **`context.Context`** | Carries deadlines and cancellation through a request. Pass it to every DB/Redis call. |
| **pgx / connection pool** | The PostgreSQL driver. A *pool* reuses connections efficiently. |
| **Migration** | A versioned SQL file that changes the database schema. S7 owns these. |
| **Redis Stream** | An append-only log of messages. You `XADD` jobs to `jobs` and read progress from `job-events`. |
| **SSE** | You keep a response open and write `id:`/`data:` lines as events arrive; the browser's `EventSource` reads them. |
| **PostGIS check** | Use SQL like `ST_Within(ST_GeomFromGeoJSON($1), county)` so the database does the geometry test. |
| **Single writer** | You insert the job as `queued` and then only *read* its status. The worker makes every later change ([ADR-004](../adr/ADR-004-job-status-single-writer.md)). |

## 4. Learn the stack (week 0)

| Tool | Why | Official docs | Practice exercise |
|---|---|---|---|
| Go | The language | [A Tour of Go](https://go.dev/tour/) · [go.dev/doc](https://go.dev/doc/) | Tour sections: basics, methods/interfaces, concurrency. |
| `net/http` | HTTP server | [Writing Web Applications](https://go.dev/doc/articles/wiki/) | A server with `GET /health` returning JSON. |
| chi | Routing + middleware | [go-chi.io](https://go-chi.io/) | Routes with a URL parameter and a logging middleware. |
| pgx | PostgreSQL | [github.com/jackc/pgx](https://github.com/jackc/pgx) | Insert and read one row using a pool (Postgres in Docker). |
| go-redis | Redis Streams | [redis.io/docs: Streams](https://redis.io/docs/latest/develop/data-types/streams/) · [go-redis](https://github.com/redis/go-redis) | `XADD` a message, then read it back with `XREAD`. |
| SSE | Progress streaming | [MDN: server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events) | A handler that sends a tick every second, flushing each time. |
| oapi-codegen | Go types/validation from OpenAPI | [github.com/oapi-codegen/oapi-codegen](https://github.com/oapi-codegen/oapi-codegen) | Generate types from a small sample spec. |
| Go testing | Tests | [go.dev/doc/tutorial/add-a-test](https://go.dev/doc/tutorial/add-a-test) · [`net/http/httptest`](https://pkg.go.dev/net/http/httptest) | Test your health handler with `httptest`. |

**Learn it with AI:**
```text
I know Python/Java but I'm new to Go. Explain Go error handling, interfaces, and context.Context
using an HTTP handler that reads one row from Postgres with pgx as the example. Point out the
3 mistakes beginners usually make.
```

## 5. Set up your machine

```bash
brew install go            # or https://go.dev/dl/ ; go version should be 1.22+
# Docker Desktop: https://docs.docker.com/get-docker/  (for Postgres + Redis)
git clone https://github.com/samin1554/inland-resilience.git
```
Until `make dev` exists (S7), run Postgres/PostGIS and Redis with the Compose file S7 provides, or temporarily with `docker run` (ask S7 which images).

## 6. Build it step by step

### S3-0 Skeleton + health
- **Goal:** `apps/api` runs on `:8080` with `GET /health`.
- **Steps:** `go mod init`, chi router, structured logging (`log/slog`), graceful shutdown, config from env vars.
- **AI prompt:**
  ```text
  Plan a minimal Go API in apps/api using net/http + chi and log/slog: GET /health returning JSON,
  config from environment variables (DATABASE_URL, REDIS_URL), graceful shutdown on SIGTERM.
  Suggest a folder layout (cmd/, internal/…) and explain why. No code until I approve.
  ```
- **Done when:** `go run ./cmd/api` works and `go test ./...` passes.

### S3-1 Create + get analysis (your first deliverable)
- **Goal:** `POST /v1/analyses` creates a job; `GET /v1/analyses/{id}` returns it.
- **Steps:**
  1. Decode and validate the body against the OpenAPI types.
  2. Validate the geometry in PostGIS: valid, inside the county boundary, area under the limit; date range under the limit.
  3. Insert into `analysis_jobs` with `status='queued'`.
  4. `XADD` a message to the `jobs` stream matching `contracts/analysis-job.schema.json`.
  5. Return `{job_id, status, created_at}` with 202.
- **AI prompt:**
  ```text
  Plan the POST /v1/analyses handler in apps/api following AGENTS.md and ADR-004. Show the exact
  validation order, which checks happen in Go vs in PostGIS SQL, the error codes returned
  (422 with a machine-readable code), and what happens if the Redis XADD fails after the DB insert.
  ```
- **Think about:** if the DB insert succeeds but Redis fails, what does the user see? Discuss options with the lead (e.g. mark the job failed, or retry).
- **Tests:** a success test; outside-county → 422; date range too long → 422; unknown `analysis_type` → 422; invalid polygon → 422. Use `httptest` plus a test database.
- **Done when:** demo with curl: create a job, fetch it, see the queued message in Redis.

### S3-2 SSE progress endpoint
- **Goal:** `GET /v1/analyses/{id}/events` streams progress.
- **Steps:** read `job-events` with `XREAD` (no consumer group, so every API instance sees every event); forward events for this `job_id`; write `id: <seq>`; on reconnect with `Last-Event-ID`, send the current status from the DB first ([ADR-002](../adr/ADR-002-progress-events-and-sse.md)).
- **Tests:** events arrive in order; the stream closes after a terminal state; a reconnect doesn't miss the final state.

### S3-3 Read endpoints
`GET /v1/analyses/{id}/evidence` (paginated), `/layers` (API-relative tile templates), `/report`. Only read what the worker wrote.

### S3-4 Rate limiting, cancel, health
Per-session rate limit on `POST`; `POST /v1/analyses/{id}/cancel` sets `cancel_requested_at` ([ADR-003](../adr/ADR-003-job-retries-and-cancellation.md)); `/health` checks Postgres + Redis.

### S3-5 Tile proxy (later, Milestone 3)
Raster results arrive as worker-rendered PNG overlays with bounds, stored in object storage and served by the API ([ADR-009](../adr/ADR-009-imagery-without-earth-engine.md), amending [ADR-005](../adr/ADR-005-gee-tile-access.md)). The `/v1/tiles/...` route is reserved for tiled output later.

**Common mistakes across tickets:** forgetting `ctx` on DB calls; not flushing SSE writes; logging request bodies that may contain user data; returning Go error strings to users.

## 7. How your work connects

| You need | From | Until ready |
|---|---|---|
| `openapi.yaml`, job schema | Lead | Draft from spec §8 |
| DB tables + county boundary seed | S7 (+ S4 for the boundary) | A local migration you share with S7 |
| Worker progress events | Lead (job runtime) | Publish fake events with `redis-cli XADD` |

| Others need from you | Who |
|---|---|
| Working endpoints + SSE | S2 (they switch off the mock) |
| Job messages on the queue | Lead's worker |

## 8. When you're stuck

Official Go docs are very good; read them first. Then OpenCode in Plan mode → the lead (your pair) → team chat with the request, the response/error, and what you expected.

## 9. Coming from the lead

- [x] `contracts/openapi.yaml` v0 (Go type generation still to set up)
- [ ] Exact limits. Proposed: area ≤ 5,000 km², date range ≤ 3 years, region = `sb_county_bbox` until S4's county polygon. Confirm with the lead before hard-coding
- [x] `contracts/job-event.schema.json` + stream layout (`jobs`, `job-events`, field `payload`, group `workers`) in [Milestone 1](../milestone-1.md#the-interfaces-so-nobody-waits)
- [ ] Session/auth decision ([ADR-008](../adr/ADR-008-authentication.md))
- [ ] What to do when the Redis publish fails after the insert
