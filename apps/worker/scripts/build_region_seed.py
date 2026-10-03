"""Build the supported region (ADR-012; ADR-011 for California) from Census TIGERweb state outlines.

    uv run python scripts/build_region_seed.py --record              # fetch the US once (network, no keys) + rebuild
    uv run python scripts/build_region_seed.py                       # rebuild outputs from the committed US outline
    uv run python scripts/build_region_seed.py --region california   # the California-only outline (ADR-011)
    uv run python scripts/build_region_seed.py --counties            # record US county outlines (place names, ADR-013)

The fetch goes through the connector kit (allowlisted host, URL from providers.yaml `us_states_boundary`).
Outputs, generated from apps/worker/config/regions/<region>.geojson (the active region, `usa` by default):
  - database/seeds/0001_region.sql          reference_layers row `region` (what the Go API validates against)
  - apps/web/public/region.geojson          the outline drawn on the map
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from inland_worker.kit.config import load_providers
from inland_worker.kit.connector import ProviderRequest
from inland_worker.kit.http import KitHttpClient
from inland_worker.kit.imagery import repair

WORKER = Path(__file__).resolve().parents[1]
REPO = WORKER.parents[1]
REGIONS_DIR = WORKER / "config" / "regions"
SEED = REPO / "database" / "seeds" / "0001_region.sql"
WEB = REPO / "apps" / "web" / "public" / "region.geojson"
PROVIDER = "us_states_boundary"
TERRITORIES = ("PR", "GU", "VI", "AS", "MP", "UM")  # out of scope for now (ADR-012)
REGIONS = {
    # name: (TIGERweb where clause, display name, simplify tolerance in degrees)
    "usa": (f"STUSAB NOT IN ({','.join(repr(t) for t in TERRITORIES)})", "the United States", 0.005),
    "california": ("STUSAB='CA'", "California", 0.001),
}


# state FIPS → USPS code (50 states + DC); used to name counties "Grant County, OR"
STATE_FIPS = {
    "01": "AL",
    "02": "AK",
    "04": "AZ",
    "05": "AR",
    "06": "CA",
    "08": "CO",
    "09": "CT",
    "10": "DE",
    "11": "DC",
    "12": "FL",
    "13": "GA",
    "15": "HI",
    "16": "ID",
    "17": "IL",
    "18": "IN",
    "19": "IA",
    "20": "KS",
    "21": "KY",
    "22": "LA",
    "23": "ME",
    "24": "MD",
    "25": "MA",
    "26": "MI",
    "27": "MN",
    "28": "MS",
    "29": "MO",
    "30": "MT",
    "31": "NE",
    "32": "NV",
    "33": "NH",
    "34": "NJ",
    "35": "NM",
    "36": "NY",
    "37": "NC",
    "38": "ND",
    "39": "OH",
    "40": "OK",
    "41": "OR",
    "42": "PA",
    "44": "RI",
    "45": "SC",
    "46": "SD",
    "47": "TN",
    "48": "TX",
    "49": "UT",
    "50": "VT",
    "51": "VA",
    "53": "WA",
    "54": "WV",
    "55": "WI",
    "56": "WY",
}
COUNTIES = REGIONS_DIR / "us_counties.geojson"


async def fetch_counties() -> dict:
    """Every county (or equivalent) in the 50 states + DC, generalized to ~1 km: enough to name a place."""
    cfg = load_providers().get("us_counties_boundary")
    client = KitHttpClient(cfg)
    features, offset = [], 0
    states = ",".join(repr(f) for f in STATE_FIPS)
    while True:
        resp = await client.get(
            ProviderRequest(
                path="/query",
                label=f"counties-{offset}",
                params={
                    "where": f"STATE IN ({states})",
                    "outFields": "NAME,STATE,GEOID",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "maxAllowableOffset": "0.005",
                    "geometryPrecision": "4",
                    "orderByFields": "GEOID",
                    "resultOffset": str(offset),
                    "resultRecordCount": "500",
                    "f": "geojson",
                },
            )
        )
        page = resp.json().get("features") or []
        for f in page:
            if f.get("geometry"):
                a = f["properties"]
                features.append(
                    {
                        "type": "Feature",
                        "geometry": mapping(repair(f["geometry"])),
                        "properties": {
                            "name": a["NAME"],
                            "state": STATE_FIPS[a["STATE"]],
                            "geoid": a["GEOID"],
                        },
                    }
                )
        if len(page) < 500:
            break
        offset += 500
    if len(features) < 3100:
        raise SystemExit(f"expected ~3,143 counties, got {len(features)}")
    return {
        "type": "FeatureCollection",
        "properties": {
            "source": cfg.display_name,
            "source_url": cfg.source_url,
            "retrieved_at": resp.retrieved_at.astimezone(UTC).isoformat(),
        },
        "features": features,
    }


async def fetch(region: str) -> dict:
    where, name, tolerance = REGIONS[region]
    cfg = load_providers().get(PROVIDER)
    client = KitHttpClient(cfg)
    resp = await client.get(
        ProviderRequest(
            path="/query",
            label="state",
            params={
                "where": where,
                "outFields": "NAME,STUSAB",
                "returnGeometry": "true",
                "outSR": "4326",
                "maxAllowableOffset": str(tolerance / 4),
                "geometryPrecision": "5",
                "f": "geojson",
            },
        )
    )
    features = resp.json().get("features") or []
    states = sorted(f["properties"]["STUSAB"] for f in features)
    expected = 51 if region == "usa" else 1  # 50 states + DC
    if len(states) != expected:
        raise SystemExit(f"expected {expected} state outlines for {region}, got {len(states)}: {states}")
    geom = unary_union([repair(f["geometry"]) for f in features]).simplify(tolerance, preserve_topology=True)
    geom = repair(geom)
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": {
                    "name": name,
                    "states": states,
                    "source": cfg.display_name,
                    "source_url": cfg.source_url,
                    "retrieved_at": resp.retrieved_at.astimezone(UTC).isoformat(),
                    "simplified_deg": tolerance,
                },
            }
        ],
    }


def build(outline: dict) -> None:
    geom = shape(outline["features"][0]["geometry"])
    if not geom.is_valid or geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise SystemExit("region outline is not a valid polygon")
    props = outline["features"][0]["properties"]
    gj = json.dumps(mapping(geom), separators=(",", ":"))
    SEED.write_text(
        f"-- The supported region: {props['name']} (ADR-012). GENERATED by apps/worker/scripts/build_region_seed.py from\n"
        f"-- {props['source']} ({props['source_url']}), retrieved {props['retrieved_at']}, simplified\n"
        f"-- {props['simplified_deg']} deg. Do not edit by hand. Idempotent: safe to run twice.\n"
        "INSERT INTO reference_layers (id, name, geometry, source)\n"
        "VALUES (\n"
        "    'region',\n"
        f"    '{props['name']}',\n"
        f"    ST_Multi(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON('{gj}'), 4326))),\n"
        f"    '{props['source']}'\n"
        ")\n"
        "ON CONFLICT (id) DO UPDATE SET geometry = EXCLUDED.geometry, name = EXCLUDED.name,\n"
        "    source = EXCLUDED.source, updated_at = now();\n"
    )
    WEB.parent.mkdir(parents=True, exist_ok=True)
    WEB.write_text(json.dumps(outline, separators=(",", ":")) + "\n")
    print(f"wrote {SEED.relative_to(REPO)} and {WEB.relative_to(REPO)} ({len(gj) // 1024} KB geometry)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record", action="store_true", help="fetch the outline from TIGERweb first (network)")
    ap.add_argument("--region", default="usa", choices=sorted(REGIONS))
    ap.add_argument("--counties", action="store_true", help="record US county outlines (network) and exit")
    args = ap.parse_args()
    if args.counties:
        fc = asyncio.run(fetch_counties())
        COUNTIES.write_text(json.dumps(fc, separators=(",", ":")) + "\n")
        print(f"recorded {len(fc['features'])} counties → {COUNTIES.relative_to(REPO)}")
        raise SystemExit(0)
    outline_path = REGIONS_DIR / f"{args.region}.geojson"
    if args.record:
        outline = asyncio.run(fetch(args.region))
        outline_path.parent.mkdir(parents=True, exist_ok=True)
        outline_path.write_text(json.dumps(outline, separators=(",", ":")) + "\n")
        print(f"recorded {outline_path.relative_to(REPO)} at {datetime.now(UTC):%Y-%m-%d}")
    build(json.loads(outline_path.read_text()))
