# Provider spec: Sentinel-2 L2A via Earth Search (AWS open data)

| Field | Value |
|---|---|
| `provider_id` | `earth_search_s2` |
| Role | `kit/imagery.py` (STAC imagery reference: search, scene choice, windowed reads, `scl` mask) · **S6**: NDVI / NBR / dNBR functions and overlays on top |
| Ingestion class | `compute` (per job; results cached by AOI hash + date windows + cloud limit; historical results never change) |
| Evidence types | `satellite_measurement`, `deterministic_calculation` |
| Auth | none (no account or key) |
| Docs | https://element84.com/earth-search/ · STAC API root `https://earth-search.aws.element84.com/v1` |
| Status | **available**: `earth_search_s2` connector (scene search, live-recorded fixtures, shared suite) + `kit/imagery.py` (pixel reads); live test and the [Line Fire demo](../../research/line-fire-2024/README.md) pass |
| Decision | [ADR-009](../../adr/ADR-009-imagery-without-earth-engine.md) |

## 1. Endpoints
```text
STAC search:  POST https://earth-search.aws.element84.com/v1/search
  {"collections": ["sentinel-2-l2a"], "bbox": [w, s, e, n],
   "datetime": "2024-10-01T00:00:00Z/2024-10-20T00:00:00Z",
   "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}], "limit": 5}

Assets (COGs):  https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/...
```
`allowed_hosts: [earth-search.aws.element84.com, sentinel-cogs.s3.us-west-2.amazonaws.com]`

## 2. Assets we use
| Asset | Band | Resolution | Used for |
|---|---|---|---|
| `red` | B04 | 10 m | NDVI |
| `nir` | B08 | 10 m | NDVI, NBR |
| `swir22` | B12 | 20 m | NBR (resample to 10 m or compute at 20 m, stated in output) |
| `scl` | Scene classification | 20 m | cloud / shadow / no-data mask |
| `visual` | True colour | 10 m | before/after thumbnails |

Verified item example: `S2B_11SNT_20241009_0_L2A` (2024-10-09, cloud 0.01%) over the Line Fire area.

## 3. Limits and behaviour
- **Scaling (critical):** reflectance = DN × `scale` + `offset` from `raster:bands`, **but apply `offset` only if `earthsearch:boa_offset_applied` is false**. Check it per item: some items have the offset already applied while the asset metadata still advertises it. Wrong handling gives dNBR values > 2.
- **Duplicates:** the same tile can appear twice on one date (e.g. Sentinel-2A and 2C both passing: `S2A_…_0_L2A`, `S2C_…_1_L2A`). The connector keeps the least cloudy per tile and lists the chosen scene ids in the evidence.
- Read **only the AOI window** from each COG (HTTP range requests). Never download whole scenes (spec non-goal).
- Pick the least-cloudy scene inside each date window **measured over the AOI** (scene-level `eo:cloud_cover` is only a first filter).
- Mask `scl` classes for cloud, cloud shadow, cirrus, snow and no-data **before** statistics. TODO: list exact SCL class values from the ESA product spec.
- Proposed limits: AOI ≤ the Go-enforced maximum; `timeout_s: 60` per read; results cached permanently for fixed historical dates.

## 4. Output → Evidence
`deterministic_calculation` items with `properties`: `method` (ndvi_change / dnbr), `before_scene`, `after_scene`, acquisition dates, `cloud_limit`, `valid_pixel_pct`, `resolution_m`, `value(s)` + `units`, class areas (acres, computed in a projected CRS). `observed_at` = the later acquisition. A PNG overlay + bounds goes into `artifacts`.

## 5. Quality flags
`low_valid_pixels`, `wide_acquisition_gap`, `scene_cloud_above_limit`, `no_scene_in_window` (the last becomes `Missing`, never an empty success).

## 6. Limitations
- *Satellite indices indicate vegetation change and burn severity; they are not ground-verified.*
- *Cloud, shadow and no-data pixels were excluded; valid coverage is reported.*
- Attribution: *Contains modified Copernicus Sentinel data (year).* TODO: link the Copernicus legal notice.

## 7. Fixture plan
Recorded STAC search responses (JSON) + small AOI-window arrays saved as `.npz` for the Line Fire before/after; formula tests on fixed arrays (S6-1).
