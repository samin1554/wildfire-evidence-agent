# Provider spec: MTBS burn severity (USGS / USFS)

| Field | Value |
|---|---|
| `provider_id` | `mtbs_severity` |
| Pattern | Copy the ArcGIS reference; image-service calls as in `baer-sbs.md` |
| Ingestion class | `on_demand` (cached permanently per fire-year) |
| Evidence types | `satellite_measurement` (official assessment; `properties.assessment_source = "MTBS"`) |
| Auth | none |
| Docs | Service: `https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_MTBS_CONUS/ImageServer` |
| Status | service verified Sep 24, 2026 (yearly mosaics through 2024) · **no data yet for the 2024 Line Fire** (MTBS lags up to ~1 year) |
| Decision | [ADR-009](../../adr/ADR-009-imagery-without-earth-engine.md) |

## Notes
- Maps fires > 1,000 acres in the western US across all ownerships. Classes: unburned to low, low, moderate, high, increased greenness (+ a mask class).
- Use `mosaicRule` `where: year=YEAR`. Returns `NoData` when a fire isn't mapped yet: that's `Missing`, not "unburned".
- Mainly for older fires and for evaluation (S8: computed vs official agreement).

## Limitations
- *MTBS is published months to a year after a fire; recent fires may not be mapped yet.*
