# ADR-013: "Active now" activity feed

## Status
Proposed (Oct 3, 2026), implemented on the `demo/full-stack` branch only. Adds `GET /v1/activity` to
`contracts/openapi.yaml` (a contract change, lead-owned).

## Context
Users had to know where to look: draw an area or pick a preset. The data we already pull is national (FIRMS sees
~2,000 detections across the lower 48 in a typical 3-day window), so the app can lead people to where satellites
see heat right now and let them analyse it in one click.

## Decision
- **The worker builds a snapshot; the API only serves it.** `python -m inland_worker activity` (compose service
  `worker-activity`, every 30 min, `ACTIVITY_REFRESH_S`) fetches NASA FIRMS for `conus_bbox`, `alaska_bbox` and
  `hawaii_bbox` (last 2 days) and NIFC WFIGS current perimeters through `get_evidence()`, so caching, traces,
  stale/missing handling and fixture mode are the same as everywhere else (ADR-001, ADR-006). The Go API reads
  the newest row from `activity_snapshots` / `activity_clusters`. No provider calls from the API.
- **Deterministic clustering** (`activity/cluster.py`), never the model:
  - detections inside the US outline are snapped to a 0.05° (~5 km) grid; touching cells (8-way) form a cluster;
  - per cluster: detection count, high-confidence count, max/total FRP, first/last seen, footprint, satellites;
  - official match: the current WFIGS perimeter with the largest overlap gives the incident name, acres,
    containment and incident type (`prescribed burn` is said as such);
  - rank = `3 × high-confidence + detections + ln(1 + total FRP)`, then most recent; top 50 kept;
  - suggested analysis area = cluster bbox + ~3 km, shrunk to ≤ 5,000 km², clipped ~50 m inside the US outline,
    so it passes `POST /v1/analyses` validation unchanged.
- **Labels:** `officially_reported` only with an overlapping official perimeter; otherwise `unverified_detection`.
- **Retention:** the last 10 snapshots; a failed refresh keeps the previous one and logs why. An unavailable
  source still produces a snapshot whose limitations say what is missing.

## Consequences and limits
- FIRMS pixels are ~375 m and arrive 3–4 h after the overpass; clouds and smoke hide fires; industrial heat,
  gas flares and agricultural/prescribed burns also appear. All of this is in every snapshot's limitations, and an
  empty feed says it doesn't mean nothing is burning.
- FIRMS key use: 3 area calls per refresh (one per bbox), 6 per hour, far under the key's limits.
- The grid size trades merging nearby fires against splitting large ones; 5 km suits wildfire-scale clusters.
- Fixture mode runs the same code on the recorded FIRMS/WFIGS data and is badged "recorded data" in the UI.
- Next: per-state names (reverse geocoding from the TIGERweb state layer), a "new since last refresh" flag,
  and a cluster history to show growth.
