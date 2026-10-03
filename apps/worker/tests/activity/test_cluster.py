"""Clustering and ranking of heat detections (ADR-013): deterministic, honest labels, valid analysis areas."""

from datetime import UTC, datetime, timedelta

from shapely.geometry import box, mapping, shape

from inland_worker.activity.cluster import MAX_AREA_KM2, area_km2, cluster_detections, suggested_area
from inland_worker.agent.guardrails import region
from inland_worker.contracts.models import Evidence

T0 = datetime(2026, 9, 22, 9, 0, tzinfo=UTC)


def det(lon, lat, conf="nominal", frp=2.0, minutes=0, i=None):
    return Evidence(
        id=i or f"d{lon}_{lat}_{minutes}",
        evidence_type="satellite_detection",
        source="NASA FIRMS",
        observed_at=T0 + timedelta(minutes=minutes),
        retrieved_at=T0 + timedelta(hours=3),
        geometry={"type": "Point", "coordinates": [lon, lat]},
        properties={"confidence": conf, "frp": frp, "satellite": "N21"},
        quality_flags=[],
        limitations=["A thermal anomaly is not an officially confirmed wildfire."],
        source_url="https://firms.modaps.eosdis.nasa.gov/",
    )


def perimeter(geom, name="Test Fire", kind="wildfire"):
    return Evidence(
        id=f"p-{name}",
        evidence_type="official_perimeter",
        source="NIFC WFIGS Interagency Perimeters (current)",
        observed_at=T0,
        retrieved_at=T0,
        geometry=mapping(geom),
        properties={
            "incident_name": name,
            "gis_acres": 1234.6,
            "percent_contained": 40,
            "incident_type": kind,
        },
        quality_flags=[],
        limitations=["x"],
        source_url="https://example.org",
    )


def test_neighbours_merge_and_distant_groups_stay_apart():
    near = [det(-105.30, 40.45), det(-105.27, 40.46), det(-105.24, 40.47)]  # ~3 km steps: one cluster
    far = [det(-110.0, 44.0)]
    clusters = cluster_detections(near + far)
    assert sorted(len(c.detections) for c in clusters) == [1, 3]


def test_ranking_prefers_high_confidence_and_intensity_then_recency():
    strong = [det(-105.3, 40.45, "high", 50.0, i=f"s{k}", minutes=k) for k in range(3)]
    weak = [det(-110.0, 44.0, "low", 0.5, i=f"w{k}", minutes=k) for k in range(5)]
    clusters = cluster_detections(strong + weak)
    assert [len(c.detections) for c in clusters] == [3, 5] and [c.rank for c in clusters] == [1, 2]
    assert clusters[0].high_confidence == 3 and clusters[0].max_frp == 50.0
    assert clusters[0].first_seen == T0 and clusters[0].last_seen == T0 + timedelta(minutes=2)


def test_official_perimeter_match_and_prescribed_burn_label():
    pts = [det(-105.30, 40.45), det(-105.29, 40.45)]
    wf = cluster_detections(pts, [perimeter(box(-105.32, 40.43, -105.28, 40.47))])[0]
    assert wf.label == "officially_reported" and wf.official["incident_name"] == "Test Fire"
    assert wf.official["gis_acres"] == 1235
    rx = cluster_detections(
        pts, [perimeter(box(-105.32, 40.43, -105.28, 40.47), "Unit 7", "prescribed burn")]
    )[0]
    assert rx.official["incident_type"] == "prescribed burn"
    nothing = cluster_detections(pts, [perimeter(box(-100, 30, -99.9, 30.1))])[0]
    assert nothing.label == "unverified_detection" and nothing.official is None


def test_suggested_area_is_inside_the_us_and_under_the_limit():
    us = region()
    # a coastal cluster (Malibu): the box would reach into the ocean; it gets clipped to land
    coastal = cluster_detections([det(-118.78, 34.04), det(-118.76, 34.05)], region=us)[0]
    assert us.contains(coastal.suggested_area)
    # a huge spread-out footprint is shrunk below the per-job limit
    big = suggested_area(box(-112, 38, -108, 41), us)
    assert area_km2(big) <= MAX_AREA_KM2 and us.contains(big)
    assert shape(mapping(big)).geom_type == "Polygon"


def test_no_detections_means_no_clusters():
    assert cluster_detections([]) == []
