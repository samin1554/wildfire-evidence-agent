"""Trends and persistence from history (pure functions; the runner supplies History)."""

from inland_worker.activity.trends import History, apply, is_persistent, trend


def test_trend_statuses():
    assert trend(10, History(False, None, 1)) == {"status": "new", "detections_24h_ago": 0}
    assert trend(10, History(True, None, 3)) is None  # no snapshot ~24 h ago yet
    assert trend(10, History(None, None, 0)) is None  # no history at all yet: not "new", unknown
    assert trend(13, History(True, 10, 3))["status"] == "growing"
    assert trend(12, History(True, 10, 3))["status"] == "stable"
    assert trend(7, History(True, 10, 3))["status"] == "shrinking"
    assert trend(5, History(True, 0, 3))["status"] == "growing"  # quiet yesterday, active again


def test_persistence_needs_five_days_and_no_official_perimeter():
    assert is_persistent(History(True, 3, 5), official=False)
    assert not is_persistent(History(True, 3, 4), official=False)
    assert not is_persistent(History(True, 3, 12), official=True)  # a long official wildfire is never demoted


def cluster(cid, score, official=None, last="2026-10-03T06:00:00+00:00"):
    return {"id": cid, "score": score, "detections": 10, "official": official, "last_seen": last}


def test_persistent_clusters_rank_lower_but_stay_listed():
    clusters = [cluster("flare", 30.0), cluster("fire", 20.0)]
    hist = {"flare": History(True, 10, 9), "fire": History(False, None, 1)}
    out = apply(clusters, hist)
    assert [c["id"] for c in out] == ["fire", "flare"] and [c["rank"] for c in out] == [1, 2]
    flare = out[1]
    assert flare["persistent_heat_source"] and flare["days_seen"] == 9 and flare["score"] == 9.0
    assert out[0]["trend"]["status"] == "new" and not out[0]["persistent_heat_source"]


def test_no_history_means_new_and_not_persistent():
    (c,) = apply([cluster("a", 5.0)], {})
    assert c["trend"]["status"] == "new" and c["persistent_heat_source"] is False
