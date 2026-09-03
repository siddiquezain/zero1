"""Tests for thermal event clustering."""
import pytest
from src.intelligence.clustering import cluster_alerts, ThermalEvent


def _alert(alert_id, lat, lon, acq_date, frp_mw=10.0, risk_score=40,
           severity="MEDIUM", day_night="D", bt_kelvin=320.0,
           dist_nearest_facility_km=5.0, predicted_label="B",
           anomaly_flag=0, state="Andhra Pradesh"):
    return {
        "alert_id": alert_id,
        "lat": lat, "lon": lon,
        "acq_date": acq_date,
        "frp_mw": frp_mw,
        "bt_kelvin": bt_kelvin,
        "risk_score": risk_score,
        "severity": severity,
        "day_night": day_night,
        "dist_nearest_facility_km": dist_nearest_facility_km,
        "nearest_facility_type": "thermal power",
        "predicted_label": predicted_label,
        "prob_A": 0.6, "prob_B": 0.3,
        "anomaly_flag": anomaly_flag,
        "persistence_count": 1,
        "state": state,
        "district": None, "zone": None,
        "output_class": "Persistent Thermal Source",
        "output_class_short": "Persistent Source",
        "output_class_code": "PS-B",
        "status": "ALERTED",
        "narrative": "",
    }


def test_nearby_same_day_detections_cluster_together():
    alerts = [
        _alert("a01", 17.0, 80.0, "2026-09-01"),
        _alert("a02", 17.01, 80.01, "2026-09-01"),  # ~1.5km away
    ]
    events = cluster_alerts(alerts)
    assert len(events) == 1
    assert "a01" in events[0].alert_ids
    assert "a02" in events[0].alert_ids


def test_distant_detections_become_different_events():
    alerts = [
        _alert("b01", 17.0, 80.0, "2026-09-01"),
        _alert("b02", 20.0, 83.0, "2026-09-01"),  # ~400km away
    ]
    events = cluster_alerts(alerts)
    assert len(events) == 2


def test_temporally_distant_detections_split():
    alerts = [
        _alert("c01", 17.0, 80.0, "2026-09-01"),
        _alert("c02", 17.01, 80.01, "2026-09-11"),
    ]
    events = cluster_alerts(alerts, temporal_days=3)
    assert len(events) == 2


def test_identical_input_produces_identical_event_ids():
    alerts = [
        _alert("d01", 17.0, 80.0, "2026-09-01"),
        _alert("d02", 17.01, 80.01, "2026-09-01"),
    ]
    events1 = cluster_alerts(alerts)
    events2 = cluster_alerts(alerts)
    assert events1[0].event_id == events2[0].event_id


def test_empty_input():
    assert cluster_alerts([]) == []


def test_single_detection():
    alerts = [_alert("e01", 17.0, 80.0, "2026-09-01")]
    events = cluster_alerts(alerts)
    assert len(events) == 1
    assert events[0].observation_count == 1


def test_missing_frp_handled():
    a = _alert("f01", 17.0, 80.0, "2026-09-01")
    a["frp_mw"] = None
    events = cluster_alerts([a])
    assert events[0].peak_frp_mw is None
    assert events[0].mean_frp_mw is None


def test_missing_acq_date_handled():
    a = _alert("g01", 17.0, 80.0, "")
    a["acq_date"] = None
    events = cluster_alerts([a])
    assert len(events) == 1


def test_duplicate_alert_ids_deduplicated():
    a = _alert("h01", 17.0, 80.0, "2026-09-01")
    events = cluster_alerts([a, a])
    event_ids_flat = [aid for e in events for aid in e.alert_ids]
    assert event_ids_flat.count("h01") == 1


def test_mixed_unrelated_detections():
    alerts = [
        _alert("i01", 17.0, 80.0, "2026-09-01"),
        _alert("i02", 17.01, 80.01, "2026-09-01"),
        _alert("i03", 22.0, 88.0, "2026-09-01"),
    ]
    events = cluster_alerts(alerts)
    assert len(events) == 2


def test_event_aggregates_correctly():
    alerts = [
        _alert("j01", 17.0, 80.0, "2026-09-01", frp_mw=20.0, risk_score=50,
               severity="HIGH", day_night="N"),
        _alert("j02", 17.01, 80.01, "2026-09-02", frp_mw=30.0, risk_score=70,
               severity="CRITICAL", day_night="D"),
    ]
    events = cluster_alerts(alerts)
    assert len(events) == 1
    e = events[0]
    assert e.peak_frp_mw == 30.0
    assert e.night_count == 1
    assert e.day_count == 1
    assert e.risk_score == 70
    assert e.severity == "CRITICAL"
    assert e.duration_days == 1
