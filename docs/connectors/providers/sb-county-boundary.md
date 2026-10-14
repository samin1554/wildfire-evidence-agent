# Provider spec: San Bernardino County boundary

| Field | Value |
|---|---|
| `provider_id` | `sb_county_boundary` |
| Pattern | Copy the `wfigs` ArcGIS reference; note this layer returns ArcGIS JSON, not GeoJSON |
| Ingestion class | `reference` (sync on deploy plus weekly; used by the Go API for request validation and by the worker for clipping) |
| Evidence types | none. This is a reference layer served via `get_reference_layer`, not evidence. |
| Auth | none |
| Docs | https://services.arcgis.com/aA3snZwJfFkVyDuP/ArcGIS/rest/services/SBCoBoundary/FeatureServer |
| Status | draft |

## 1. Endpoint
```text
BASE = https://services.arcgis.com/aA3snZwJfFkVyDuP/ArcGIS/rest/services/SBCoBoundary/FeatureServer/0

{BASE}/query
  ?where=1%3D1
  &outFields=*
  &returnGeometry=true
  &outSR=4326
  &f=json
```
`allowed_hosts: [services.arcgis.com]`

Note the response is **ArcGIS JSON** (`f=json`), not GeoJSON. The connector converts it (spec §11.5).

## 2. Query parameters
None.

## 3. Limits and behaviour
Small, rarely changes. Store in the PostGIS table `reference_layers` (see [ADR-006](../../adr/ADR-006-cache-and-snapshots.md)). The Go API reads the same geometry to validate that request polygons fall inside the supported region.

## 4. Output
A single (Multi)Polygon in 4326, validated with `ST_IsValid` and repaired explicitly with `ST_MakeValid` if needed (spec §21), plus the retrieval time.

## 5. Quality flags
`geometry_repaired` if a repair was needed.

## 6. Limitations
None for users. It's used for scope checks.

## 7. Fixture plan
Record once and commit it. It also becomes `database/fixtures/sb_county_boundary.geojson` for seeding.

## 8. Open questions
- Additional county layers from https://data-sbcounty.opendata.arcgis.com/ (roads, hospitals, fire stations) are phase two. Their URLs go in `providers.yaml` too.
