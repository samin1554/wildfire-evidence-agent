# Provider spec: CAL FIRE historical fire perimeters

> **Spec correction (verified Sep 24, 2026):** the URL in spec §11.4, `2025_California_Fire_Perimeters_View`, contains **only 2025 fires** (521 records). For historical analysis use
> `https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/ArcGIS/rest/services/California_Historic_Fire_Perimeters/FeatureServer/2`
> (18,064 fires, 1950–2025, includes the 2024 Line Fire: 43,975.61 acres, unit BDF). Same fields (`FIRE_NAME`, `YEAR_`, `GIS_ACRES`, `ALARM_DATE`, …). See ADR-009 § Consequences.

| Field | Value |
|---|---|
| `provider_id` | `calfire_historical` |
| Pattern | Copy the `wfigs` ArcGIS reference |
| Ingestion class | `reference` (sync nightly into a PostGIS reference table; jobs query PostGIS) |
| Evidence types | `official_perimeter` |
| Auth | none |
| Docs | https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/ArcGIS/rest/services/2025_California_Fire_Perimeters_View/FeatureServer/0 |
| Status | demo connector on `demo/full-stack` (layer 2 URL below); S4 owns the production version |

## 1. Endpoint
```text
BASE = https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/ArcGIS/rest/services/2025_California_Fire_Perimeters_View/FeatureServer/0

{BASE}/query
  ?where=YEAR_%3E%3D2020
  &geometry=-117.8,33.8,-114.1,35.9
  &geometryType=esriGeometryEnvelope
  &inSR=4326
  &spatialRel=esriSpatialRelIntersects
  &outFields=FIRE_NAME,YEAR_,GIS_ACRES,ALARM_DATE,CONT_DATE,CAUSE,AGENCY
  &returnGeometry=true
  &outSR=4326
  &f=geojson
```
`allowed_hosts: [services1.arcgis.com]`

## 2. Query parameters
The nightly sync pulls the whole county envelope for `YEAR_ >= 2020`. Jobs then filter in PostGIS by area and date range; they don't call the service.

## 3. Limits and behaviour
- Paging as for any ArcGIS feature service (TODO: `maxRecordCount`).
- The service name contains a year (`2025_...`). Datasets may be republished under new service IDs (spec §11.5), so the URL lives only in `providers.yaml`.
- Proposed schedule nightly; `timeout_s: 60`; `max_response_bytes: 50 MB`.

## 4. Field → Evidence mapping
| Field | Evidence field | Notes |
|---|---|---|
| geometry | `geometry` | 4326 |
| `FIRE_NAME` | `properties.fire_name` | |
| `YEAR_` | `properties.year` | |
| `GIS_ACRES` | `properties.gis_acres` | acres |
| `ALARM_DATE` | `observed_at` | epoch ms → UTC |
| `CONT_DATE` | `properties.containment_date` | may be null |
| `CAUSE`, `AGENCY` | `properties.cause`, `properties.agency` | coded values; TODO: decode table |

## 5. Quality flags
- Perimeters can be **invalid geometries** (the 2024 Line Fire has a self-touching ring). Repair with `make_valid` and add `geometry_repaired`.
`missing_alarm_date`, `missing_containment_date`, `possible_duplicate` (same name + year + overlapping geometry).

## 6. Limitations
- Default: *Historical perimeter records may contain omissions, duplicates, or generalized geometry.* (spec §11.4)

## 7. Fixture plan
`success`: county envelope, `YEAR_ >= 2024` (includes the Line Fire). `empty`: `YEAR_ >= 2100`. Plus `malformed` and `extra_fields`.

## 8. Open questions
- Where to find the CAUSE/AGENCY code tables.
