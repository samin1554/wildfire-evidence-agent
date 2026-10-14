# Provider spec: BAER Soil Burn Severity (USFS)

| Field | Value |
|---|---|
| `provider_id` | `baer_sbs` |
| Pattern | Copy the `wfigs` ArcGIS reference; this is an **image** service, so use `identify`/`computeHistograms`/`exportImage` instead of feature `query` |
| Ingestion class | `on_demand` (per job, cached; assessments change rarely) |
| Evidence types | `satellite_measurement` (official assessment; `properties.assessment_source = "BAER"`) |
| Auth | none |
| Docs | Service: `https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_BAER_SoilBurnSeverityClassification/ImageServer` · contact: BAER Imagery Support Program |
| Status | verified Sep 24, 2026: `identify` and `exportImage` (GeoTIFF on our own UTM grid) work; real classes across the 2024 Line Fire |
| Decision | [ADR-009](../../adr/ADR-009-imagery-without-earth-engine.md) |

## 1. Endpoint
```text
{BASE}/identify      point sample (used for verification)
{BASE}/computeHistograms   class pixel counts inside the fire/AOI polygon (preferred for summaries)
{BASE}/exportImage   rendered PNG for a map overlay
mosaicRule: {"mosaicMethod":"esriMosaicAttribute","where":"beginyear<=YEAR AND endyear>=YEAR"}
```
`allowed_hosts: [imagery.geoplatform.gov]`. Service is Web Mercator (wkid 3857); pass `inSR=4326` for inputs.

## 2. Classes (service legend)
Pixel values: **1 = Unburned to very low · 2 = Low · 3 = Moderate · 4 = High · 5 = Masked (developed)**. Confirmed Sep 24, 2026 by a pixel-level comparison over the Line Fire ([research](../../research/line-fire-2024/README.md)).

## 3. Output → Evidence
One item per fire/AOI: `properties.class_area_acres` per class, `properties.assessment_source="BAER"`, `properties.year`, `properties.units="acres"`. Geometry = the AOI or fire perimeter. `observed_at` = the assessment year's start (TODO: find a precise assessment date field).

## 4. Limitations
- *BAER soil burn severity describes post-fire soil condition from an emergency assessment; it is not a vegetation mortality measurement.*
- *Only fires that received a BAER assessment are covered.*

## 5. Fixture plan
Recorded `computeHistograms` JSON for the Line Fire; `empty` = an AOI with no BAER coverage.
