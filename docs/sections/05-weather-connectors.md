# Section 5: Weather and environment connectors

**Stack:** Python 3.12 · Pydantic · the project's **connector kit** · pytest
**Pair partner:** Section 7 (platform and data infra): together you make scheduled refreshes and caching work.
**Read first:** [Start here](../guides/start-here.md) · [Connector guide](../connectors/connector-guide.md) (**essential**) · [Learning with AI](../guides/learning-with-ai.md) · [Coding with OpenCode](../guides/coding-with-opencode.md)

---

> **Already built for you** ([details](../platform-status.md))
>
> - **The connector kit** and **two references to copy:** `connectors/weather/nws_forecast.py` (follow-the-link → NWS alerts) and `connectors/fire/firms.py` (keyed API → CIMIS).
> - `make new-connector NAME=<id> GROUP=weather PATTERN=follow_link` (or `keyed`) sets everything up; `make test-connector PROVIDER=<id>` runs the shared suite.
> - **Alerts have their own evidence type:** `weather_alert` (in `contracts/evidence.schema.json`).
>
> **Your part of Milestone 1:** Not on the critical path. Keep going with S5-1 → S5-5 on fixtures.


## 1. Your job in plain English

You connect the app to **weather and environmental conditions**, the context that explains *why* fire behaved the way it did:

| Source | What it tells us | Who builds it |
|---|---|---|
| **NWS forecast** | The forecast for a location. | Lead (reference for *follow-the-link* APIs) |
| **NWS alerts** | Active weather alerts (e.g. Red Flag Warnings). | **You** (copy `nws_forecast.py`) |
| **California CIMIS** | Daily conditions like evapotranspiration, solar radiation, temperature, humidity and wind, from stations and ~2 km modelled estimates. | **You** (copy the `firms.py` keyed-API reference) |
| *Phase two:* AirNow, USGS earthquakes, CAL FIRE hazard zones | Air quality, earthquakes, official hazard classes. | **You** (copy the matching reference) |

Like Section 4, you **translate** each provider's format into our shared *evidence* object. You don't start from a blank file: the lead ships a working **reference connector** for each type of source, and you copy the matching one and change the request and the field mapping. The kit handles HTTP, keys, retries, caching and recordings. Every source is listed in the [data catalog](../data-catalog.md).

**Analogy:** you're the weather reporter for a detective. You bring conditions to the case file with exact times and sources, and you're careful to say whether a number was *measured at a station* or *estimated by a model*.

![Ingestion pipeline](../diagrams/ingestion-pipeline.svg)

**Done looks like:** NWS alerts and CIMIS connectors (copied from the references) pass the shared suite offline, have provider docs and fixtures, and never blur a forecast into an observation or an estimate into a measurement.

## 2. What you own

| You own | Don't touch |
|---|---|
| `apps/worker/src/inland_worker/connectors/weather/**` **except** `nws_forecast.py` | `kit/**`, `data/**`, and the reference connectors `nws_forecast.py`, `fire/firms.py` (lead: suggest changes via PR) |
| `apps/worker/tests/connectors/weather/**` | `providers.yaml`: propose entries via PR |
| `apps/worker/tests/fixtures/{nws_alerts,cimis}/**` | `contracts/**` (lead) |
| `docs/connectors/providers/cimis.md`, the alerts part of `nws.md` (+ phase-two specs) | fire connectors (S4) |

## 3. Key ideas before you start

| Term | Plain-English meaning |
|---|---|
| **Forecast vs observation** | A forecast *predicts*; an observation *measured*. Different evidence types, never mixed. |
| **Issued / updated time** | When a forecast was produced. It's the forecast's `observed_at`. Old forecasts get a `stale_forecast` flag. |
| **NWS `/points` discovery** | You ask `/points/{lat},{lon}` and NWS tells you which forecast URLs to use. **Follow those URLs**; never build grid IDs yourself. |
| **User-Agent header** | NWS requires a descriptive `User-Agent` identifying the app. The kit adds it from `NWS_USER_AGENT`. |
| **Station vs spatial (CIMIS)** | Station = a physical instrument; spatial = a ~2 km modelled estimate. You must record which (`provider_type`). |
| **Units** | Always keep units (`unitOfMeasure=M` = metric for CIMIS). Numbers without units are bugs. |
| **Alert** | An official warning. We show it **for context only**, with a limitation telling users to follow official authorities. |
| **Connector, fixture, evidence** | Same as in the [connector guide](../connectors/connector-guide.md). |

## 4. Learn the stack (week 0)

| Tool | Why | Official docs | Practice exercise |
|---|---|---|---|
| Python, typing, Pydantic, pytest | Core | [Python tutorial](https://docs.python.org/3/tutorial/) · [Pydantic](https://docs.pydantic.dev/latest/) · [pytest](https://docs.pytest.org/en/stable/getting-started.html) | Parse a saved JSON file into Pydantic models; test it. |
| JSON + datetimes | Timestamps | [`datetime` docs](https://docs.python.org/3/library/datetime.html) | Parse `2026-09-23T10:00:00-07:00` and convert it to UTC. |
| NWS API | Forecasts + alerts | [weather.gov API docs](https://www.weather.gov/documentation/services-web-api) | In your browser, open `https://api.weather.gov/points/34.1083,-117.2898` and follow its `forecast` link. |
| CIMIS API | Conditions | [CIMIS Web API](https://et.water.ca.gov/Rest/Index) | Register for a free app key and fetch one week for one point. |
| GeoJSON | Output geometry | [geojson.org](https://geojson.org/) | Represent a forecast point and an alert polygon. |

**Learn it with AI:**
```text
Explain the National Weather Service API's /points discovery flow: why we must follow the returned
forecast/forecastHourly/forecastGridData URLs instead of constructing grid IDs, and what fields
tell me when a forecast was issued. Then list failure cases I should handle.
```

## 5. Set up your machine

Same as S4: Python 3.12+, [uv](https://docs.astral.sh/uv/), clone the repo, OpenCode. Get a **CIMIS app key** from the CIMIS site and put it only in your local `.env` as `CIMIS_APP_KEY=...`. Set `NWS_USER_AGENT` in `.env` to something like `inland-resilience-agent/0.1 your-email@example.com`. Never commit keys or paste them into AI tools.

## 6. Build it step by step

Order for every source: **spec → fixtures → copy the reference → adjust parse → tests → PR**. While the lead builds the references (week 1), do S5-1 and S5-2. They need no kit.

### S5-1 Provider specs: CIMIS + NWS alerts
- **Goal:** understand both sources before any code.
- **Steps:** finish the `TODO`s in [cimis.md](../connectors/providers/cimis.md) (request limits, max date span, QC codes) and the alerts part of [nws.md](../connectors/providers/nws.md) (alert fields, geometry, how expiry works).
- **AI prompt:**
  ```text
  Read docs/connectors/providers/cimis.md and the CIMIS Web API docs. Explain the difference
  between station data and Spatial CIMIS, which fields tell them apart, and what QC codes mean.
  Help me fill the TODOs. No code.
  ```
- **Done when:** the lead approves both specs.

### S5-2 Record fixtures by hand
- **Goal:** saved real responses for offline tests.
- **Steps:** `alerts/active?area=CA` on a day with alerts (`success`) and `alerts/active?point=...` somewhere quiet (`empty`); CIMIS for one spatial target and one station target, plus a future date range (`empty`). Add `malformed` and `extra_fields` copies.
- **Check yourself:** the CIMIS `appKey` appears in the request URL, so **remove it** from any saved request metadata before committing (the recorder will do this automatically later).

### S5-3 Review the NWS forecast reference
- **Goal:** learn the follow-the-link pattern from working code.
- **Steps:** read `nws_forecast.py`, its tests and fixtures; run the tests; ask OpenCode to explain how the kit restricts followed URLs to `api.weather.gov`.

### S5-4 NWS alerts connector (copy `nws_forecast.py`)
- **Goal:** active California alerts, refreshed every 15 minutes.
- **Steps:** `make new-connector NAME=nws_alerts GROUP=weather PATTERN=follow_link`; point it at `/alerts/active`; use the alert evidence type the lead chooses; every item carries *"Shown for context only. Follow official local authorities for emergency guidance."*
- **Important:** alert text comes from outside. It's *data*, and the agent must never follow instructions inside it (S8 and the lead test prompt injection).
- **Tests:** the shared suite; no alerts → `[]`; missing alert geometry → flagged, not dropped.

### S5-5 CIMIS connector (copy `firms.py`)
- **Goal:** daily conditions with honest provenance.
- **Steps:** `make new-connector NAME=cimis GROUP=weather PATTERN=keyed`; the key goes in the `appKey` query param from `CIMIS_APP_KEY` (configured in `providers.yaml`, never in code); metric units; set `properties.provider_type` to `station` or `spatial`; carry QC codes into `quality_flags`; spatial results get the "modelled estimate" limitation.
- **AI prompt:**
  ```text
  I copied connectors/fire/firms.py to connectors/weather/cimis.py. Compare firms.md and cimis.md
  and list what must change: auth style (path placeholder -> query param), request params,
  field mapping, units, provider_type, flags and limitations. Tests first.
  ```
- **Tests:** a spatial result is never labelled a station measurement; future dates → `[]`.

### S5-6 Phase two (only after the historical-fire workflow works end to end)
AirNow (copy `firms.py`; use `/aq/observation/current/ziplatlong/`, **not** the legacy endpoint retiring Sep 30 2026), USGS earthquakes (copy `nws_forecast.py` or `firms.py`), CAL FIRE Fire Hazard Severity Zones (copy `fire/wfigs.py`). Start each with a provider spec from the [template](../connectors/provider-spec-template.md).

## 7. How your work connects

| You need | From | Until ready |
|---|---|---|
| Connector kit + suite | Lead | Plain pytest on `parse` functions |
| `nws_forecast.py` and `firms.py` references | Lead | Specs + fixtures (S5-1, S5-2) |
| Alert evidence type decision | Lead | Draft as `weather_observation` + `kind: alert` |

| Others need from you | Who |
|---|---|
| Schedules (`ingestion.schedule`) for alerts | S7 (ingest mode) |
| Weather context evidence | Lead (agent), S8 (verification) |

## 8. When you're stuck

Connector guide + official provider docs → OpenCode Plan mode → S7 (your pair) for caching/scheduling → the lead for kit questions → team chat with the fixture, the error and your branch.

## 9. Coming from the lead

- [x] Connector kit v0, including support for following URLs (`follow()`)
- [x] Reference connectors `nws_forecast.py` (follow-the-link) and `firms.py` (keyed) with fixtures and tests
- [x] Evidence type for alerts: `weather_alert`
- [ ] Choice of representative point for large areas
- [ ] Rate-limit settings once live usage is observed
