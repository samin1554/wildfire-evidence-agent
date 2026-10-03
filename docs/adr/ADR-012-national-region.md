# ADR-012: Supported region is the United States (50 states + DC)

## Status
Proposed (Oct 3, 2026), implemented on the `demo/full-stack` branch only. Supersedes ADR-011 (California) on that
branch. Deviates from the spec's San Bernardino County scope; needs the lead's decision before it reaches `main`.

## Context
ADR-011 showed that scope is one outline used three times (API, worker, map) and that per-job cost is bounded by
the area limit, not the region. Going national needs three things California didn't: a national outline,
a national historical-perimeter archive, and offline data outside California.

## Decision
- **Region = the 50 states + DC** from Census TIGERweb (`us_states_boundary`, `kind: reference_layer`), unioned,
  simplified to ~500 m and committed as `apps/worker/config/regions/usa.geojson` (~280 KB) by
  `scripts/build_region_seed.py`, which also writes the DB seed (Go `ST_Within`) and `apps/web/public/region.geojson`
  (map outline + client point-in-polygon check). Territories (PR, GU, VI, AS, MP) are out of scope for now.
- **Limits unchanged** (5,000 km², 3 years); `AREA_OUTSIDE_REGION` unchanged. No contract change.
- **Historical perimeters, one archive per area** (no double counting), chosen by `perimeter_source()` in
  `agent/tools.py`:

  | Area | Source | Coverage |
  |---|---|---|
  | inside California | `calfire_historical` (CAL FIRE FRAP) | 1950 onward |
  | elsewhere | `wfigs_history` (NIFC WFIGS Interagency Perimeters, all years) | ~2016 onward |

  `wfigs_history` is a subclass of the `wfigs_current` reference connector: same host and fields, filtered by
  discovery date; it keeps `incident_type` (WF wildfire / RX prescribed burn) so a prescribed burn is never
  reported as a wildfire.
- **Everything else was already national:** FIRMS and Sentinel-2 (global), NWS and WFIGS current (US).
- `providers.yaml` areas: `conus_bbox` (FIRMS/WFIGS defaults), `alaska_bbox`, `hawaii_bbox`; `ca_bbox` and
  `sb_county_bbox` stay.
- Offline demo data: Line Fire and Thompson Fire (CA), Alexander Mountain Fire (CO), recent detections (CA).

## Consequences and limits
- **Antimeridian:** the Aleutians are split at ±180° (valid MultiPolygon). An area drawn *across* 180° is rejected.
- **Archive floor:** outside California, fires before ~2016 have no official perimeter here; such questions return
  the satellite evidence with an "insufficient official records" limitation. MTBS (1984+) is the next source.
- **Calibration:** dNBR thresholds are forest-calibrated (Key & Benson). Grassland, shrub-steppe, desert and
  tundra need per-ecoregion calibration (S6/S8) before severity classes are trusted nationally. The limitation
  is on every result. The three recorded fires agree with official acreage within 25 % (CO), 17 % (CA) and the
  BAER comparison (Line Fire), which is a start, not an evaluation.
- **Load:** a national audience means FIRMS key limits and caching (ADR-006, S7's ingest runner) matter sooner.
- **Next:** territories, MTBS for older fires, an evaluation set spanning ecoregions (S8).
