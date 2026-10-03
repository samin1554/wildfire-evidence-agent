# Provider spec: Google Earth Engine, Sentinel-2 SR Harmonized

> **Deferred to phase two by [ADR-009](../../adr/ADR-009-imagery-without-earth-engine.md).** The MVP uses Sentinel-2 via Earth Search ([earth-search-s2.md](earth-search-s2.md)) plus official BAER/MTBS severity. Kept for later use (large AOIs, ECOSTRESS, GOES-19).

| Field | Value |
|---|---|
| `provider_id` | `gee_s2` |
| Owner | Deferred (ADR-009). If adopted in phase two: lead builds an Earth Engine `compute` wrapper, S6 the analysis on top |
| Ingestion class | `compute` (per job; result cache keyed by area hash + date windows + collection + cloud limit) |
| Evidence types | `satellite_measurement`, `deterministic_calculation` |
| Auth | Service account: `GOOGLE_APPLICATION_CREDENTIALS` (path to a mounted secret), `GEE_PROJECT_ID` |
| Docs | https://developers.google.com/earth-engine/guides/python_install · https://developers.google.com/earth-engine/guides/auth · https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED |
| Status | draft |

## 1. Collection
```python
ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
```
Bands: `B4` red · `B8` NIR · `B11` SWIR1 · `B12` SWIR2 · `SCL` scene classification / cloud.
Earth Engine is called through its Python API, not raw HTTP, so the kit's `compute` path wraps `ee` calls with the same timeout, trace and cache rules.

## 2. Operations (Section 6)
| Function | Output |
|---|---|
| `get_satellite_scenes(area, date_range, collection, cloud_limit)` | scene list with acquisition dates and cloud % |
| `calculate_ndvi_change(before, after, area)` | mean NDVI before/after, % change, valid-pixel %, tile-layer metadata |
| `calculate_burn_severity(before, after, area)` | NBR before/after, dNBR stats and class areas |

Formulas: NDVI = (B8 − B4)/(B8 + B4); NBR = (B8 − B12)/(B8 + B12); dNBR = NBR_before − NBR_after.

## 3. Limits and behaviour
- Mask clouds, cloud shadow and no-data using `SCL` **before** statistics (spec §21).
- Report units, resolution (10 m / 20 m bands) and cloud-free pixel coverage with every result.
- Don't download raw archives (spec non-goal). Only statistics, thumbnails and tile URLs leave Earth Engine.
- Tile URLs expire. How the browser gets them is in [ADR-005](../../adr/ADR-005-gee-tile-access.md).

## 4. Evidence mapping
`deterministic_calculation` items carry `properties.method`, `properties.inputs` (scene IDs, dates, cloud limit), `properties.value` + `properties.units`, `properties.valid_pixel_pct`, `properties.resolution_m`. `observed_at` = the later acquisition date.

## 5. Quality flags
`low_valid_pixels` (below a threshold, TODO), `wide_acquisition_gap`, `scene_cloud_above_limit`.

## 6. Limitations
- *Satellite indices indicate vegetation change and burn severity; they are not ground-verified.*
- *Cloud and no-data pixels were excluded; coverage is reported.*

## 7. Fixture plan
Earth Engine can't be replayed like HTTP. Instead: (a) **fixed-array unit tests** for the formulas; (b) recorded result JSON for one historical San Bernardino fire, used as the `compute` fixture; (c) a nightly live test on the same case that checks the numbers stay within tolerance.
