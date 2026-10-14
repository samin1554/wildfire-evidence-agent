# Provider spec: NIFC WFIGS current interagency fire perimeters

| Field | Value |
|---|---|
| `provider_id` | `wfigs_current` |
| Role | reference connector for the *ArcGIS* pattern (copied for CAL FIRE, county boundary, hazard zones) |
| Ingestion class | `near_real_time` (refresh the county extent on a schedule; live per job if stale) |
| Evidence types | `official_perimeter` |
| Auth | none |
| Docs | https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0 |
| Status | done: live-recorded fixtures, shared suite passing, live smoke test passing |

## 1. Endpoint
```text
BASE = https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0

{BASE}/query
  ?where=1%3D1
  &geometry=-117.8,33.8,-114.1,35.9
  &geometryType=esriGeometryEnvelope
  &inSR=4326
  &spatialRel=esriSpatialRelIntersects
  &outFields=*
  &returnGeometry=true
  &outSR=4326
  &f=geojson
```
`allowed_hosts: [services3.arcgis.com]`

## 2. Query parameters
Envelope from `ProviderQuery.area`. No date filter: this layer holds **current** perimeters only.

## 3. Limits and behaviour
- ArcGIS feature services page their results. TODO: read `maxRecordCount` from the layer metadata and handle `exceededTransferLimit` by paging.
- Proposed schedule every 30 min, TTL 30 min, `timeout_s: 30`, `max_response_bytes: 25 MB`.

## 4. Field → Evidence mapping
| Field | Evidence field | Notes |
|---|---|---|
| feature geometry | `geometry` | GeoJSON, 4326 |
| incident name / ID fields | `properties.incident_name`, `source_record_id` | TODO: confirm exact attribute names from layer metadata |
| perimeter date/time field | `observed_at` | TODO: confirm field |
| layer or feature edit/update time | `properties.source_updated_at` | spec §11.3: store the source update time with every feature |
| acreage field | `properties.acres` | TODO: confirm field |

## 5. Quality flags
- `missing_update_time` when no source update time is available.

## 6. Limitations
- Default: *Current perimeters reflect the latest reported mapping and may lag the fire's actual extent.*

## 7. Fixture plan
`success`: the county envelope on a day with an active incident. `empty`: county envelope on a quiet day (the layer usually returns zero features for the county off-season). Also `malformed` and `extra_fields`.

## 8. Open questions
- Exact attribute names (§4). Pull them from `?f=json` on the layer URL when recording.
