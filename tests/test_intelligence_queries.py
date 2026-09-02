"""Tests for src/intelligence/queries.py against the seeded alert store."""
import pytest

from src.alerting import alert_store, pipeline
from src.intelligence import queries as q


@pytest.fixture(scope="module", autouse=True)
def _seed():
    if not alert_store.DB_PATH.exists() or alert_store.counts()["total"] == 0:
        pipeline.run(fresh=True)
    q.clear_caches()
    yield


def test_situation_summary_shape():
    s = q.situation_summary()
    assert s["total"] > 0
    assert set(s["severity"]) == {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
    assert sum(s["severity"].values()) == s["total"]
    assert set(s["classification"]) == {"Industrial Fire", "Persistent Source", "Natural Fire"}


def test_product_scope_is_india_only():
    # every alert the product exposes must resolve to an Indian state
    for a in q.list_alerts(None, limit=5000):
        assert a["in_india"] is True
        assert a["state"] is not None
    # the outside-India points still exist, are kept, and are not moved
    outside = q.outside_india_alerts()
    assert len(outside) > 0
    assert all(o["in_india"] is False and o["state"] is None for o in outside)


def test_location_label_is_consistent_with_coordinates():
    # no "City, WrongState" — state comes from point-in-polygon, city never implies state
    for a in q.list_alerts(None, limit=5000):
        assert a["place"], a["alert_id"]
        if a["place"] and ", " in a["place"]:
            head = a["place"].split(", ")[0]
            # the head is a district/city; the tail must be the resolved state
            assert a["place"].endswith(a["state"])


def test_geo_audit_accounts_for_every_stored_alert():
    au = q.geo_audit()
    assert au["in_india"] + au["outside_india"] == au["plotted"]
    assert au["outside_india_bbox"] == 0          # nothing outside the ingestion bbox
    assert 6.0 <= au["lat_min"] and au["lat_max"] <= 37.5
    assert 67.5 <= au["lon_min"] and au["lon_max"] <= 97.5


def test_filters_are_all_honoured():
    crit = q.list_alerts({"severity": ["CRITICAL"]}, limit=1000)
    assert crit and all(a["severity"] == "CRITICAL" for a in crit)

    ind = q.list_alerts({"output_class": ["Industrial Fire"]}, limit=1000)
    assert all("Industrial" in a["output_class"] for a in ind)

    od = q.list_alerts({"state": "Odisha"}, limit=1000)
    assert od and all(a["state"] == "Odisha" for a in od)

    east = q.list_alerts({"region": "eastern india"}, limit=1000)
    assert all(a["state"] in {"Odisha", "Jharkhand", "West Bengal", "Bihar"} for a in east)

    near = q.list_alerts({"max_dist_facility_km": 5}, limit=1000)
    assert all(a["dist_nearest_facility_km"] <= 5 for a in near if a["dist_nearest_facility_km"] is not None)

    hi = q.list_alerts({"min_risk": 60}, limit=1000)
    assert all(a["risk_score"] >= 60 for a in hi)


def test_rank_alerts_is_sorted_desc():
    top = q.rank_alerts("risk_score", limit=5)
    assert top == sorted(top, key=lambda a: a["risk_score"], reverse=True)


def test_investigation_why_flagged_only_true_signals():
    top = q.rank_alerts("risk_score", limit=1)[0]
    inv = q.get_investigation(top["alert_id"])
    assert inv["found"] is True
    why = inv["why_flagged"]
    a = q.get_alert(top["alert_id"])
    if not a["anomaly_flag"]:
        assert not any("Pattern anomaly" in w for w in why)
    if a["day_night"] != "N":
        assert not any("Night-time" in w for w in why)
    # risk factors reconstruct the score
    assert sum(pts for _, pts in inv["risk_assessment"]["factors"]) == inv["risk_assessment"]["score"]


def test_investigation_missing_alert():
    inv = q.get_investigation("does-not-exist")
    assert inv["found"] is False


def test_compare_regions_returns_two_sides():
    c = q.compare_regions("Odisha", "Jharkhand")
    assert c["a"]["total"] >= 0 and c["b"]["total"] >= 0
    assert c["a"]["name"] == "Odisha"


def test_facilities_with_activity():
    facs = q.facilities_with_activity({"severity": ["CRITICAL", "HIGH"]}, limit=10)
    for f in facs:
        assert f["nearby_detections"] >= 1
        assert f["max_risk"] >= 0


def test_timeframe_is_data_relative():
    lo, hi = q.data_date_range()
    df, dt = q.resolve_timeframe("last 7 days")
    assert dt == hi and df <= hi
    df2, dt2 = q.resolve_timeframe("today")
    assert df2 == hi == dt2
