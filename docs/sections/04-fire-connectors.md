# Section 4: Fire data connectors

**Stack:** Python 3.12 · Pydantic · the project's **connector kit** · pytest
**Pair partner:** Section 1 (map frontend): check that your data draws correctly on the map.
**Read first:** [Start here](../guides/start-here.md) · [Connector guide](../connectors/connector-guide.md) (**essential**) · [Learning with AI](../guides/learning-with-ai.md) · [Coding with OpenCode](../guides/coding-with-opencode.md)

---

> **Already built for you** ([details](../platform-status.md))
>
> - **The connector kit** and **the ArcGIS reference** (`connectors/fire/wfigs.py`, live-recorded fixtures, full tests): you copy it with `make new-connector NAME=<id> GROUP=fire PATTERN=arcgis`.
> - **The FIRMS reference** (`connectors/fire/firms.py`) to read and learn from.
> - **Checked facts:** the spec's CAL FIRE URL only has 2025 fires; use `California_Historic_Fire_Perimeters` ([calfire-historical.md](../connectors/providers/calfire-historical.md)). BAER was verified on the Line Fire ([baer-sbs.md](../connectors/providers/baer-sbs.md)).
> - Test yours with `make test-connector PROVIDER=<id>`.
>
> **Your part of Milestone 1:** Not on the critical path. Keep going with S4-1 → S4-5 on fixtures; your connectors plug into the same flow afterwards.


## 1. Your job in plain English

You connect the app to **the fire and county data sources**. You aren't starting from scratch: the lead builds a fully working connector for each *type* of source (the **reference connectors**), and you build the rest by copying the matching one.

| Source | What it tells us | Who builds it |
|---|---|---|
| **NASA FIRMS** | Satellites spotted something hot here, at this time (a *thermal detection*, not a confirmed fire). | Lead (reference; you review and test it on the map with S1) |
| **NIFC WFIGS current perimeters** | The official outline of fires burning right now. | Lead (reference for all ArcGIS sources) |
| **CAL FIRE historical perimeters** | Official outlines of past fires (e.g. the 2024 Line Fire). | **You** (copy `wfigs.py`) |
| **San Bernardino County boundary** | The shape of the county, which we use to check requests are in scope. | **You** (copy `wfigs.py`) |
| *Phase two:* county infrastructure layers (roads, hospitals, fire stations) | What might be affected. | **You** (copy `wfigs.py`) |

Every source is listed in the [data catalog](../data-catalog.md).

Each source speaks its own "language" (CSV, ArcGIS JSON, GeoJSON, different field names and time formats). Your job is to **translate each one into our single shared format**: the *evidence* object. After you, nobody else in the project has to know how FIRMS formats its CSV.

**Analogy:** you're a translator at the UN. Each delegate speaks a different language; you turn everything into one language, and you must preserve meaning exactly, including the caveats.

The lead builds the **connector kit**, which does all the hard plumbing (HTTP requests, API keys, retries, timeouts, caching, test recordings), and the **WFIGS reference connector**, which already solves the tricky ArcGIS parts (paging, geometry conversion). For each of your sources you copy that reference and change two small, pure functions: *build the request* and *parse the response*.

![Ingestion pipeline](../diagrams/ingestion-pipeline.svg)

**Done looks like:** CAL FIRE historical and the county boundary each have a connector (copied from the WFIGS reference) that passes the shared test suite offline, a provider spec and recorded fixtures, and their output shows up correctly on S1's map.

## 2. What you own

| You own | Don't touch |
|---|---|
| `apps/worker/src/inland_worker/connectors/fire/**` **except** `firms.py` and `wfigs.py` | `kit/**`, `data/**`, and the reference connectors `connectors/fire/{firms,wfigs}.py` (lead: suggest changes via PR) |
| `apps/worker/tests/connectors/fire/**` | `apps/worker/config/providers.yaml`: **propose** entries via PR; the lead reviews |
| `apps/worker/tests/fixtures/{calfire_historical,sb_county_boundary}/**` | `contracts/**` (lead) |
| `docs/connectors/providers/{calfire-historical,sb-county-boundary}.md` | other connectors (S5), satellite code (S6) |

## 3. Key ideas before you start

| Term | Plain-English meaning |
|---|---|
| **Connector** | A class that knows one provider: how to ask (`build_requests`) and how to translate the answer (`parse`). |
| **Evidence object** | Our one shared format: type, source, `observed_at`, `retrieved_at`, geometry, properties, quality flags, limitations, source URL. |
| **Pure function** | Same input → same output, no network or files. `parse` is pure, which makes it easy to test. |
| **Fixture / recording** | A saved real response, replayed in tests so nobody needs API keys. |
| **`observed_at` vs `retrieved_at`** | When the satellite or agency saw it vs when *we* downloaded it. Never mix them up. |
| **GeoJSON / WGS84** | Standard map-shape JSON using longitude/latitude (`[lng, lat]`). |
| **ArcGIS FeatureServer** | Esri's web service used by many agencies. You query it with URL parameters; results can be paged. |
| **Pydantic model** | A Python class that validates data types for you. |
| **Quality flag** | A note like `low_confidence` attached to an item, instead of throwing it away. |
| **Limitation** | Plain-language caveat shown to users, e.g. *"A thermal anomaly is not an officially confirmed wildfire."* |

## 4. Learn the stack (week 0)

| Tool | Why | Official docs | Practice exercise |
|---|---|---|---|
| Python 3.12 | The language | [docs.python.org/3/tutorial](https://docs.python.org/3/tutorial/) | Read a CSV with the `csv` module and convert rows to dicts. |
| Type hints | Clear interfaces | [typing docs](https://docs.python.org/3/library/typing.html) | Type a function `parse(rows: list[dict]) -> list[Detection]`. |
| Pydantic | Validation | [docs.pydantic.dev](https://docs.pydantic.dev/latest/) | Model a FIRMS row; see what happens with a bad value. |
| pytest | Tests | [docs.pytest.org](https://docs.pytest.org/en/stable/getting-started.html) | Test your CSV parser with a small fixture file. |
| GeoJSON | Output geometry | [geojson.org](https://geojson.org/) | Convert 3 lat/lon rows into a GeoJSON FeatureCollection. |
| ArcGIS REST query | WFIGS, CAL FIRE, county | [Esri: Query (Feature Service/Layer)](https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/) | Open the CAL FIRE query URL from the provider spec in your browser with `f=geojson`. |
| NASA FIRMS API | Hotspots | [FIRMS Area API](https://firms.modaps.eosdis.nasa.gov/api/area/) | Get a free MAP_KEY and fetch 1 day for the county box in your browser. |

**Learn it with AI:**
```text
I'm writing a Python function that converts NASA FIRMS CSV rows into GeoJSON point features.
Explain acq_date + acq_time (HHMM, UTC) and how to turn them into a timezone-aware ISO 8601
datetime. Then list 5 edge cases I should test (empty file, missing frp, extra column, ...).
```

## 5. Set up your machine

```bash
# Python 3.12+: https://www.python.org/downloads/  (or brew install python@3.12)
# uv (fast Python package manager, recommended): https://docs.astral.sh/uv/
git clone https://github.com/samin1554/inland-resilience.git
```
Get your own free **FIRMS MAP_KEY** at https://firms.modaps.eosdis.nasa.gov/api/map_key/. Put it only in your local `.env` as `FIRMS_MAP_KEY=...`. **Never** commit it or paste it into an AI chat. WFIGS, CAL FIRE and the county boundary need no key.

## 6. Build it step by step

Always follow the order **spec → fixtures → copy the reference → adjust parse → tests → PR**. The [connector guide §3](../connectors/connector-guide.md#3-writing-a-connector) has the full shape.

**While the lead builds the references (week 1):** you do S4-1 and S4-2. They need no kit and no code, just understanding the data.

### S4-1 Provider specs for your sources
- **Goal:** understand CAL FIRE historical and the county boundary completely before any code.
- **Steps:** resolve the `TODO`s in [calfire-historical.md](../connectors/providers/calfire-historical.md) and [sb-county-boundary.md](../connectors/providers/sb-county-boundary.md): open each layer's metadata page (the base URL with `?f=json`) and write down the exact field names, `maxRecordCount`, and the meaning of the CAUSE/AGENCY codes.
- **AI prompt:**
  ```text
  Read docs/connectors/providers/calfire-historical.md. Explain what an ArcGIS FeatureServer
  "layer metadata" page tells me (fields, maxRecordCount, geometry type) and how to read it.
  Then help me fill in the field-mapping table. Don't write code.
  ```
- **Done when:** the lead approves both specs in a PR.

### S4-2 Record fixtures by hand
- **Goal:** real saved responses so everything can be tested offline.
- **Steps:** in your browser (or `curl`), run the query URLs from the specs and save the responses into `tests/fixtures/<provider>/<case>/`: `success`, `empty` (e.g. `YEAR_ >= 2100`), `malformed` (a truncated copy), `extra_fields` (success + an extra field). Once the lead ships `make record-fixture`, re-record with it.
- **Check yourself:** these sources need no key, but check that no personal data or tokens are in the files anyway.

### S4-3 Review the FIRMS reference with S1
- **Goal:** learn the pattern by reading working code, and check it renders.
- **Steps:** read `firms.py`, its tests and its fixtures; ask OpenCode to explain every function; run its tests; with S1, draw its fixture output on the map and report anything that looks wrong (flipped coordinates, bad times) to the lead.
- **AI prompt:**
  ```text
  Walk me through apps/worker/src/inland_worker/connectors/fire/firms.py and its tests. For each
  function: what it does, why it's pure, and which line I would change to support a different
  provider. Then quiz me with 3 questions.
  ```

### S4-4 CAL FIRE historical connector (copy the WFIGS reference)
- **Goal:** past fire perimeters as `official_perimeter` evidence.
- **Steps:** `make new-connector NAME=calfire_historical GROUP=fire PATTERN=arcgis`; change the query (`where=YEAR_>=2020` on `California_Historic_Fire_Perimeters` layer 2 (the spec's URL only holds 2025 fires; see the note in the provider spec), `outFields`); map `FIRE_NAME`, `YEAR_`, `GIS_ACRES`, `ALARM_DATE` (epoch ms → UTC), `CONT_DATE`, `CAUSE`, `AGENCY`; add the `possible_duplicate` and missing-date flags; nightly `reference` class.
- **AI prompt:**
  ```text
  I copied connectors/fire/wfigs.py to calfire_historical.py. Compare the two provider specs
  (wfigs.md vs calfire-historical.md) and list exactly what must change: query params, field
  mapping, date handling, flags, limitations. Paging should already work from the reference;
  confirm it. Tests first.
  ```
- **Tests:** the shared suite, plus epoch-ms dates, a null `CONT_DATE`, and duplicate detection.
- **Done when:** `make test-connector PROVIDER=calfire_historical` passes offline and S1 can draw the Line Fire perimeter.

### S4-5 County boundary connector (copy the WFIGS reference)
- **Goal:** the county shape as valid GeoJSON, used by S3 for request checks and by S1 for the map.
- **Differences from the reference:** this layer is queried with `f=json` (ArcGIS JSON), so use the reference's ArcGIS→GeoJSON converter; output is a reference layer (`get_reference_layer`), not evidence; validate/repair the geometry; also save it as `database/fixtures/sb_county_boundary.geojson` for S7's seed (coordinate with S7).
- **Tests:** a valid polygon; coordinates inside the expected county bounding box.

### S4-6 Official burn severity: BAER (then MTBS)
- **Goal:** official burn-severity classes for a fire or area, as `satellite_measurement` evidence labelled as an official assessment ([ADR-009](../adr/ADR-009-imagery-without-earth-engine.md)).
- **Steps:** start from [baer-sbs.md](../connectors/providers/baer-sbs.md). Copy the ArcGIS reference, but these are **image** services: use `computeHistograms` over the fire/AOI polygon to get pixel counts per class, and turn them into acres per class. Confirm the pixel value → class mapping first (TODO in the spec). Then do [mtbs.md](../connectors/providers/mtbs.md) the same way. MTBS returns `NoData` for fires it hasn't mapped yet: that's `Missing`, never "unburned".
- **Check with:** the 2024 Line Fire (BAER has Low/Moderate classes inside it; MTBS has no data yet).
- **Hand-off:** S8 compares these official classes with S6's measured dNBR.

### S4-7 Phase two: county infrastructure layers
After the wildfire workflow works end to end: roads, hospitals and fire stations from https://data-sbcounty.opendata.arcgis.com/, each a copy of the ArcGIS reference.

**Common mistakes:** `[lat, lng]` order (must be `[lng, lat]`); naive datetimes without a timezone; editing the reference file instead of your copy; dropping rows with missing fields instead of flagging them.

## 7. How your work connects

| You need | From | Until ready |
|---|---|---|
| Connector kit + shared test suite | Lead | Write `parse` as plain functions with pytest, then plug them in |
| WFIGS reference connector (ArcGIS pattern) | Lead | Specs + fixtures (S4-1, S4-2) |
| Evidence schema | Lead | The example in the connector guide |

| Others need from you | Who |
|---|---|
| Evidence that renders on the map | S1 |
| County boundary seed | S7, S3 |
| Perimeters for corroboration | S8 |
| Scheduled refresh entries | S7 (ingest mode) |

## 8. When you're stuck

Re-read the connector guide and the provider's official docs → OpenCode in Plan mode → S1 (your pair) for "does it draw right?" → the lead for anything about the kit → team chat with your fixture, the error and your branch name.

## 9. Coming from the lead

- [x] Connector kit v0: `BaseConnector`, `make new-connector`, `make record-fixture`, `make derive-fixtures`, shared suite (`inland_worker.kit.testing.ConnectorContract`)
- [x] Reference connectors `firms.py` (keyed) and `wfigs.py` (ArcGIS) with fixtures and tests (all live-recorded)
- [x] `evidence.schema.json` v0 + examples in `contracts/examples/evidence/`
- [x] `apps/worker/config/providers.yaml` with the `firms` and `wfigs_current` blocks to copy
- [ ] Decision on FIRMS historical archive access (see the open question in `firms.md`)
