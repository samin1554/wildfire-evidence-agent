# ADR-011: Supported region is California (from San Bernardino County)

## Status
Superseded by [ADR-012](ADR-012-national-region.md) on the demo branch. Was: Proposed (Oct 3, 2026), implemented on the `demo/full-stack` branch only. Deviates from the spec's San Bernardino
County scope; needs the lead's decision before it reaches `main`.

## Context
The product is scoped to San Bernardino County (spec §11.2, `sb_county_bbox`). The demo showed that nothing in the
architecture depends on the county: per-job work is bounded by the area limit (5,000 km²), not by the region, and
the core sources already cover far more than the county. Expanding is mostly a question of *which outline decides
scope* and *which sources and calibrations are valid inside it*.

| Source | Coverage | Inside California |
|---|---|---|
| NASA FIRMS, Sentinel-2 (Earth Search) | global | ✓ |
| NIFC WFIGS current perimeters, NWS forecasts/alerts | United States | ✓ |
| CAL FIRE historical perimeters (`calfire_historical`) | California | ✓ |
| CIMIS weather, CAL FIRE FHSZ hazard zones | California | ✓ (phase two) |
| BAER / MTBS burn severity | United States | ✓ |
| San Bernardino County layers (roads, stations…) | county | ✗ county only (phase two, optional) |

## Decision
- **The supported region is California's outline**, not a box. It comes from the US Census TIGERweb states layer
  (`ca_state_boundary` in `providers.yaml`, `kind: reference_layer`), fetched once through the kit by
  `apps/worker/scripts/build_region_seed.py`, simplified to ~100 m, and committed as
  `apps/worker/config/regions/california.geojson`. The same script generates:
  - `database/seeds/0001_region.sql` → `reference_layers.region`, which the Go API checks with `ST_Within`;
  - `apps/web/public/california.geojson`, the outline drawn on the map.
  The worker's guardrail checks the same outline (defence in depth). One source, three consumers, a test keeps
  them in sync (`tests/test_region.py`).
- **Limits are unchanged**: area ≤ 5,000 km², date range ≤ 3 years, error code `AREA_OUTSIDE_REGION`.
  No contract change.
- `providers.yaml` gains `areas.ca_bbox`; FIRMS, WFIGS and CAL FIRE default to it. `sb_county_bbox` stays.
- Offline demo data covers three areas: Line Fire 2024, Thompson Fire 2024 (Oroville), recent detections near
  Victorville. Other areas run live, or return an honest "insufficient evidence" in fixture mode.

## Consequences
- Users can analyse anywhere in the state; validation is exact at the state line (Reno, Lake Tahoe's Nevada side and
  the ocean are rejected).
- **Science caveat, unchanged but more visible:** dNBR thresholds are forest-calibrated (Key & Benson). They are
  less reliable in chaparral (already noted), grassland, desert and alpine areas. S6/S8 should calibrate per
  ecoregion before results are presented as severity classes statewide; the limitation text stays on every result.
- S8's evaluation set should include fires outside Southern California (the Thompson Fire is a first one).
- Load grows with the user base, not the map: FIRMS key limits and caching (ADR-006, S7's ingest runner) matter
  sooner.

## Path to the whole United States
The same mechanism scales: a US outline (lower 48 + Alaska + Hawaii) from the same TIGERweb layer, plus a national
historical-perimeter connector (NIFC InterAgency Fire Perimeter History, MTBS) in place of CAL FIRE. Antimeridian
handling (the Aleutians) and per-ecoregion calibration are the real work; the plumbing doesn't change.
