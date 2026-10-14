# Data catalog

**Every data source in the project, and how to get it in one line.**

You never call NASA, NWS, ArcGIS or the satellite archives yourself. The data pipeline does that, cleans the result into one standard format (**Evidence**), caches it, keeps it fresh, and hands it to you:

```python
from inland_worker.data import get_evidence, get_reference_layer

result = await get_evidence("firms", area=aoi, date_range=dates)   # any provider_id below
result.items       # list[Evidence]: same shape for every source
result.freshness   # Fresh | Stale(age, reason) | Missing(reason)
```

- **Frontend (S1, S2):** you don't call this. You get the same Evidence objects from the Go API (`GET /v1/analyses/{id}/evidence`), and the mock API serves the examples in `contracts/examples/`.
- **Try it now:** `make worker-install`, then `INLAND_DATA_MODE=fixture uv run python -c "..."` (see `apps/worker/README.md`).
- **Offline:** set `INLAND_DATA_MODE=fixture` and every source below returns recorded real data. No API keys needed.

![Ingestion pipeline](diagrams/ingestion-pipeline.svg)

---

## MVP sources

| `provider_id` | Source | What you get | Evidence type | Freshness | Pattern | Status |
|---|---|---|---|---|---|---|
| `firms` | NASA FIRMS | Satellite heat detections (points) | `satellite_detection` | Refreshed every 30 min | Keyed API | ✅ available (fixtures + live) |
| `wfigs_current` | NIFC WFIGS | Official perimeters of active fires | `official_perimeter` | Refreshed every 30 min | ArcGIS | ✅ available (fixtures + live) |
| `calfire_historical` | CAL FIRE (`California_Historic_Fire_Perimeters`) | Official perimeters of past fires (1950–2025) | `official_perimeter` | Synced nightly | ArcGIS | ✅ implemented (fixtures) |
| `sb_county_boundary` | San Bernardino County | County shape (reference layer) | reference layer | Synced weekly | ArcGIS | planned |
| `nws_forecast` | National Weather Service | Forecast for a point | `weather_forecast` | Per job, cached 1 h | Follow-the-link | ✅ available (fixtures + live) |
| `wfigs_history` | NIFC WFIGS (all years) | Official perimeters of past fires, US, ~2016+ | `official_perimeter` | Synced nightly | ArcGIS | ✅ implemented (fixtures) |
| `us_states_boundary`, `us_counties_boundary` | US Census TIGERweb | Region outline (50 states + DC) and county names | reference layer | Recorded once | ArcGIS | ✅ implemented (fixtures) |
| `nws_alerts` | National Weather Service | Active weather alerts | `weather_alert` | Refreshed every 15 min | Single request (NWS host) | ✅ implemented (fixtures) |
| `cimis` | CA Dept. of Water Resources | ETo, solar radiation, temperature, humidity, wind (station or ~2 km estimate) | `weather_observation` | Per job, cached 24 h | Keyed API | planned |
| `earth_search_s2` | Sentinel-2 L2A via Earth Search (AWS open data) | NDVI, NBR/dNBR, true colour, measured by us | `satellite_measurement`, `deterministic_calculation` | Computed per job, cached (historical dates: permanently) | STAC imagery | ✅ available (fixtures + live) · no key needed |
| `baer_sbs` | USFS BAER Soil Burn Severity | Official soil burn severity classes | `satellite_measurement` (official assessment) | Per job, cached | ArcGIS (image service) | planned · verified for the 2024 Line Fire |
| `mtbs_severity` | USGS/USFS MTBS | Official burn severity (older fires; lags up to ~1 year) | `satellite_measurement` (official assessment) | Per job, cached permanently | ArcGIS (image service) | planned |

## Phase two (after the wildfire workflow works end to end)

| `provider_id` | Source | What you get | Pattern | Built by |
|---|---|---|---|---|
| `calfire_fhsz` | CAL FIRE Fire Hazard Severity Zones | Official hazard classes | ArcGIS | S5 |
| `airnow` | AirNow | Current air quality (preliminary data) | Keyed API | S5 |
| `usgs_earthquakes` | USGS | Earthquake events | Follow-the-link / plain API | S5 |
| `earth_search_landsat` | Landsat 8/9 via Earth Search | Long-term change, land-surface temperature | STAC imagery | S6 |
| `gee_ecostress` | NASA ECOSTRESS via Earth Engine *(if Earth Engine is adopted, ADR-009)* | Heat, vegetation water stress | Earth Engine compute | S6 |
| `gee_goes19` | NOAA GOES-19 via Earth Engine *(if Earth Engine is adopted, ADR-009)* | High-frequency fire hotspots | Earth Engine compute | S6 |
| `sb_county_*` | County open data (roads, hospitals, fire stations) | Infrastructure layers | ArcGIS | S4 |

---

> Satellite imagery uses **no Google Earth Engine** in the MVP: see [ADR-009](adr/ADR-009-imagery-without-earth-engine.md).

## The four source patterns

Every source is one of four kinds. The **first of each kind** is a *reference connector*, so every other source has a working example to copy.

| Pattern | What's tricky about it | Reference | Copy it for |
|---|---|---|---|
| **Keyed API** (CSV/JSON + API key) | Keeping the key secret, parsing, timestamps | `connectors/fire/firms.py` | CIMIS, AirNow |
| **ArcGIS feature service** | Paging through results, ArcGIS JSON → GeoJSON | `connectors/fire/wfigs.py` | CAL FIRE, county boundary, hazard zones, county layers |
| **Follow-the-link API** | Safely following URLs the API returns | `connectors/weather/nws_forecast.py` | NWS alerts, USGS |
| **STAC imagery** | Finding the right scene, reading only the area you need from huge image files, cloud masking | `connectors/imagery/earth_search_s2.py` (find scenes) + `kit/imagery.py` (read pixels) | Landsat and other STAC collections; S6 builds NDVI/dNBR on `read_bands()` |

To add a source: `make new-connector NAME=<id> GROUP=<fire|weather|imagery> PATTERN=<keyed|arcgis|follow_link|stac>` copies the matching reference into place. Then change the URL and the field mapping, record fixtures, and run the tests. Full details: [connector guide](connectors/connector-guide.md).

## What every Evidence item always has

Whatever the source, every item carries: `evidence_type` · `source` · `observed_at` (when the source saw it) · `retrieved_at` (when we fetched it) · `geometry` (GeoJSON, WGS84) · `properties` (with units) · `quality_flags` · `limitations` · `source_url`. Schema: `contracts/evidence.schema.json`.

## Provider specs

Endpoint, fields, limits and limitations for each source: [docs/connectors/providers/](connectors/providers/).
