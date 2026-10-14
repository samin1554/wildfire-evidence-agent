# Provider spec: NASA FIRMS (Area API)

| Field | Value |
|---|---|
| `provider_id` | `firms` |
| Role | reference connector for the *keyed API* pattern (copied for CIMIS, AirNow) |
| Ingestion class | `near_real_time` (refresh the SB County bbox every 30 min; live query per job if stale) |
| Evidence types | `satellite_detection` |
| Auth | Path placeholder `{MAP_KEY}` ← env `FIRMS_MAP_KEY` (free key: https://firms.modaps.eosdis.nasa.gov/api/map_key/) |
| Docs | https://firms.modaps.eosdis.nasa.gov/api/area/ |
| Status | done: live-recorded fixtures (21 SB County detections, Sep 2026), shared suite + live test passing |

## 1. Endpoint
```text
https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{WEST,SOUTH,EAST,NORTH}/{DAYS}
```
Example for the coarse San Bernardino County box:
```text
https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_NOAA21_NRT/-117.8,33.8,-114.1,35.9/2
```
`allowed_hosts: [firms.modaps.eosdis.nasa.gov]`

## 2. Query parameters
| Input | Source | Allowed |
|---|---|---|
| bbox | `ProviderQuery.area` → bounding box | must fall inside the supported region |
| `source` | param | `VIIRS_NOAA21_NRT`, `VIIRS_NOAA20_NRT`, `VIIRS_SNPP_NRT`, `LANDSAT_NRT` |
| `days` | param | 1–5 (the API's day range) |

Historical ranges beyond 5 days are **not** available from this endpoint. TODO: decide whether historical fire analysis needs the FIRMS archive (a separate download) or relies on perimeters plus Sentinel-2.

## 3. Limits and behaviour
- Cache key: `source, bbox, days` (spec §11.2). Proposed TTL 30 min.
- Rate limit: **5,000 transactions per 10 minutes per MAP_KEY** (from the key-issue email, Sep 2026). One Area API call = one transaction, so the 30-minute schedule plus per-job fetches stays far below it; the kit's 429 retries cover bursts.
- Proposed `timeout_s: 20`, `max_response_bytes: 10 MB`.

## 4. Field → Evidence mapping
| FIRMS field | Evidence field | Notes |
|---|---|---|
| `longitude`, `latitude` | `geometry` (Point) | already WGS84 |
| `acq_date` + `acq_time` | `observed_at` | `acq_time` is HHMM UTC → ISO 8601 UTC |
| `satellite`, `instrument` | `properties.satellite`, `properties.instrument` | |
| `confidence` | `properties.confidence` | VIIRS uses categories, Landsat differs; keep the raw value and add `properties.confidence_scheme` |
| `frp` | `properties.frp` | fire radiative power, MW |
| `daynight` | `properties.daynight` | `D` / `N` |
| — | `source` | `"NASA FIRMS"` |
| — | `source_url` | `https://firms.modaps.eosdis.nasa.gov/` |

## 5. Quality flags
- `low_confidence` when the VIIRS confidence is low.
- `missing_frp` when `frp` is empty.

## 6. Limitations
- Default: *A thermal anomaly is not an officially confirmed wildfire.*
- Never label one hotspot as a confirmed wildfire (spec §15). Corroboration happens in the evidence rules, not the connector.

## 7. Fixture plan
- `success`: VIIRS NOAA-21 over the SB box on a day with detections (e.g. during the 2024 Line Fire, **if** within the retrievable window when recorded; otherwise any recent active day).
- `empty`: a small quiet bbox inside the county.
- `malformed`: truncated CSV. `extra_fields`: success plus an extra column.

## 8. Open questions
- The historical-archive question in §2.
