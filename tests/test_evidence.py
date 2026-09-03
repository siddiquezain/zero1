"""Tests for evidence stack builder."""
from src.intelligence.clustering import ThermalEvent
from src.intelligence.evidence import build_evidence, EvidenceItem


def _make_event(**kwargs):
    defaults = dict(
        event_id="abcd1234",
        alert_ids=["a01"],
        centroid_lat=17.0, centroid_lon=80.0,
        start_date="2026-09-01", end_date="2026-09-03",
        duration_days=2, observation_count=3,
        spatial_extent_km=2.0,
        peak_frp_mw=80.0, mean_frp_mw=50.0,
        max_bt_kelvin=340.0, mean_bt_kelvin=325.0,
        night_count=2, day_count=1,
        persistence_count=3,
        dist_nearest_facility_km=1.5,
        nearest_facility_type="thermal power plant",
        predicted_class="A", model_probability=0.82,
        anomaly_flag=0, risk_score=75, severity="HIGH",
        state="Andhra Pradesh", district="Visakhapatnam",
        zone=None, output_class="Persistent Thermal Source",
        output_class_short="Persistent Source", output_class_code="PS-B",
    )
    defaults.update(kwargs)
    return ThermalEvent(**defaults)


def _make_obs(n=3, frp=50.0, dist=1.5, day_night="N"):
    return [
        {"frp_mw": frp, "bt_kelvin": 330.0, "day_night": day_night,
         "dist_nearest_facility_km": dist, "acq_date": "2026-09-01",
         "risk_score": 75, "anomaly_flag": 0, "persistence_count": n}
        for _ in range(n)
    ]


def test_build_evidence_returns_dict():
    ev = _make_event()
    result = build_evidence(ev, _make_obs())
    assert isinstance(result, dict)
    assert "supporting" in result
    assert "limiting" in result


def test_supporting_has_evidence_items():
    ev = _make_event()
    result = build_evidence(ev, _make_obs())
    for item in result["supporting"]:
        assert "category" in item
        assert "label" in item
        assert "value" in item
        assert "direction" in item
        assert item["direction"] == "SUPPORTING"


def test_limiting_has_evidence_items():
    ev = _make_event()
    result = build_evidence(ev, _make_obs())
    assert len(result["limiting"]) > 0


def test_no_fabrication_when_frp_missing():
    ev = _make_event(peak_frp_mw=None, mean_frp_mw=None)
    obs2 = [{"frp_mw": None, "bt_kelvin": None, "day_night": "D",
              "dist_nearest_facility_km": 1.5, "acq_date": "2026-09-01",
              "risk_score": 40, "anomaly_flag": 0, "persistence_count": 1}]
    result = build_evidence(ev, obs2)
    assert isinstance(result, dict)


def test_counts_are_consistent():
    ev = _make_event()
    result = build_evidence(ev, _make_obs())
    assert result["total_supporting"] == len(result["supporting"])
    assert result["total_limiting"] == len(result["limiting"])


def test_single_observation_event():
    ev = _make_event(observation_count=1, night_count=0, day_count=1,
                     duration_days=0, start_date="2026-09-01", end_date="2026-09-01")
    result = build_evidence(ev, _make_obs(n=1))
    assert isinstance(result, dict)


def test_anomaly_flag_creates_limiting_evidence():
    ev = _make_event(anomaly_flag=1)
    result = build_evidence(ev, _make_obs())
    limiting_labels = [i["label"] for i in result["limiting"]]
    assert any("anomal" in l.lower() or "pattern" in l.lower() for l in limiting_labels)
