# Provider spec: California CIMIS

| Field | Value |
|---|---|
| `provider_id` | `cimis` |
| Pattern | Copy the `firms` keyed-API reference |
| Ingestion class | `on_demand` |
| Evidence types | `weather_observation` |
| Auth | Query param `appKey` ← env `CIMIS_APP_KEY` |
| Docs | https://et.water.ca.gov/Rest/Index |
| Status | draft |

## 1. Endpoint
```text
https://et.water.ca.gov/api/data
  ?appKey={CIMIS_APP_KEY}
  &targets=lat=34.1083,lng=-117.2898
  &startDate=2026-09-01
  &endDate=2026-09-07
  &unitOfMeasure=M
  &dataItems=day-asce-eto,day-sol-rad-avg
```
`allowed_hosts: [et.water.ca.gov]`

## 2. Query parameters
Target from the area's representative point; dates from `date_range`; `unitOfMeasure=M` (metric) always.
Station-level items available: `day-air-tmp-avg`, `day-air-tmp-max`, `day-air-tmp-min`, `day-rel-hum-avg`, `day-precip`, `day-wind-spd-avg`, `day-asce-eto`, `day-sol-rad-avg`.

## 3. Limits and behaviour
TODO: request limits and max date span per call. Proposed TTL 24 h for past dates.

## 4. Field → Evidence mapping
| Field | Evidence field | Notes |
|---|---|---|
| record date | `observed_at` | daily value |
| each data item | `properties.<item>` with `properties.units` | metric |
| provider type | `properties.provider_type` = `station` or `spatial` | **required** (spec §11.7) |
| station ID / coordinates | `source_record_id`, `geometry` | |

## 5. Quality flags
Carry CIMIS QC codes through as `quality_flags`.

## 6. Limitations
- Spatial CIMIS: *ETo and solar radiation are ~2 km modelled estimates, not station measurements.* The agent must never describe spatial estimates as direct measurements; `provider_type` is how it knows.

## 7. Fixture plan
One `lat,lng` target (spatial) and one station target; `empty` = a future date range.
