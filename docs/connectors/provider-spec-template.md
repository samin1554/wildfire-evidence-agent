# Provider spec: <Provider name>

> Copy this file to `providers/<provider_id>.md` and fill it in **before** writing code. Mark anything unknown `TODO` rather than guessing.

| Field | Value |
|---|---|
| `provider_id` | e.g. `firms` (the key in `providers.yaml`) |
| Role | Pattern and reference connector to copy |
| Ingestion class | `reference` / `near_real_time` / `on_demand` / `compute` |
| Evidence types | from the allowed list in spec §9 |
| Auth | none / header / query param / path placeholder, plus the env var **name** |
| Docs | official documentation link(s) |
| Status | draft / fixtures recorded / suite passing / live verified |

## 1. Endpoint
Base URL, request template and example request, copied from the official docs or the project spec. Note every host that must be in `allowed_hosts`.

## 2. Query parameters
Which inputs come from `ProviderQuery` (area, date range) and which are provider params (with allowed values and limits).

## 3. Limits and behaviour
Rate limits, max range or area, pagination, typical latency and response size, update frequency. Proposed `timeout_s`, `max_response_bytes`, `cache.ttl` and `schedule`.

## 4. Field → Evidence mapping
| Provider field | Evidence field | Notes / units |
|---|---|---|
| … | `observed_at` | timezone handling |
| … | `geometry` | CRS conversion |
| … | `properties.<name>` | units |

## 5. Quality flags
Conditions that add a `quality_flags` entry (low confidence, generalized geometry, duplicates, missing values…).

## 6. Limitations
The `default_limitations` text, plus any conditional ones. Written for the end user.

## 7. Fixture plan
Which real case to record for `success`, how to get an `empty` response, and how `malformed` / `extra_fields` are made.

## 8. Open questions
