"""Integration tests for event query functions in queries.py."""
from unittest.mock import patch
import pandas as pd
from src.intelligence import queries


_MOCK_ALERTS = [
    {"alert_id": "aaa001", "lat": 17.0, "lon": 80.0, "acq_date": "2026-09-01",
     "frp_mw": 40.0, "bt_kelvin": 330.0, "risk_score": 60, "severity": "HIGH",
     "day_night": "N", "dist_nearest_facility_km": 2.0,
     "nearest_facility_type": "thermal power", "predicted_label": "A",
     "prob_A": 0.75, "prob_B": 0.15, "anomaly_flag": 0, "persistence_count": 2,
     "status": "ALERTED", "output_class": "Persistent Thermal Source",
     "output_class_short": "Persistent Source", "output_class_code": "PS-B",
     "state": "Andhra Pradesh", "district": "Visakhapatnam", "zone": None,
     "narrative": "", "in_india": True, "place": "Visakhapatnam, Andhra Pradesh",
     "land_cover_context": "", "hazard_facility_type": "thermal power",
     "nearest_city": "", "dist_nearest_city_km": 0.0, "near_population": 0,
     "risk_factors": "[]", "created_at": "", "updated_at": "", "acknowledged_at": None},
    {"alert_id": "aaa002", "lat": 17.01, "lon": 80.01, "acq_date": "2026-09-02",
     "frp_mw": 65.0, "bt_kelvin": 340.0, "risk_score": 75, "severity": "HIGH",
     "day_night": "N", "dist_nearest_facility_km": 1.8,
     "nearest_facility_type": "thermal power", "predicted_label": "A",
     "prob_A": 0.80, "prob_B": 0.10, "anomaly_flag": 0, "persistence_count": 2,
     "status": "ALERTED", "output_class": "Persistent Thermal Source",
     "output_class_short": "Persistent Source", "output_class_code": "PS-B",
     "state": "Andhra Pradesh", "district": "Visakhapatnam", "zone": None,
     "narrative": "", "in_india": True, "place": "Visakhapatnam, Andhra Pradesh",
     "land_cover_context": "", "hazard_facility_type": "thermal power",
     "nearest_city": "", "dist_nearest_city_km": 0.0, "near_population": 0,
     "risk_factors": "[]", "created_at": "", "updated_at": "", "acknowledged_at": None},
    {"alert_id": "bbb001", "lat": 22.0, "lon": 88.0, "acq_date": "2026-09-01",
     "frp_mw": 10.0, "bt_kelvin": 310.0, "risk_score": 30, "severity": "LOW",
     "day_night": "D", "dist_nearest_facility_km": 20.0,
     "nearest_facility_type": "other", "predicted_label": "B",
     "prob_A": 0.2, "prob_B": 0.6, "anomaly_flag": 0, "persistence_count": 1,
     "status": "DETECTED", "output_class": "Natural Fire Candidate",
     "output_class_short": "Natural Fire", "output_class_code": "PS-C",
     "state": "West Bengal", "district": "Kolkata", "zone": None,
     "narrative": "", "in_india": True, "place": "Kolkata, West Bengal",
     "land_cover_context": "", "hazard_facility_type": "",
     "nearest_city": "", "dist_nearest_city_km": 0.0, "near_population": 0,
     "risk_factors": "[]", "created_at": "", "updated_at": "", "acknowledged_at": None},
]


def _patch_alerts():
    df = pd.DataFrame(_MOCK_ALERTS)
    df["in_india"] = True
    df["place"] = df["district"] + ", " + df["state"]
    df["output_class_short"] = df["output_class_short"]
    df["output_class_code"] = df["output_class_code"]
    df["hazard_facility_type"] = df["hazard_facility_type"].fillna("")
    # Clear event cache so fresh data is used
    queries._events_cached.cache_clear()
    return patch.object(queries, "_alerts", return_value=df)


def test_list_events_returns_list():
    with _patch_alerts():
        events = queries.list_events()
    assert isinstance(events, list)
    assert len(events) >= 1


def test_nearby_alerts_grouped_into_one_event():
    with _patch_alerts():
        events = queries.list_events()
    # aaa001 and aaa002 are ~1.5km apart on consecutive days → same event
    assert any(len(e.get("alert_ids", [])) == 2 for e in events)


def test_get_event_returns_none_for_missing():
    with _patch_alerts():
        result = queries.get_event("nonexistent")
    assert result is None


def test_get_event_for_alert_finds_event():
    with _patch_alerts():
        result = queries.get_event_for_alert("aaa001")
    assert result is not None
    assert "aaa001" in result["alert_ids"]


def test_get_event_fingerprint_returns_dict():
    with _patch_alerts():
        events = queries.list_events()
        event_id = events[0]["event_id"]
        fp = queries.get_event_fingerprint(event_id)
    assert fp is not None
    assert "behaviour_category" in fp


def test_get_event_evidence_returns_dict():
    with _patch_alerts():
        events = queries.list_events()
        event_id = events[0]["event_id"]
        ev = queries.get_event_evidence(event_id)
    assert ev is not None
    assert "supporting" in ev
    assert "limiting" in ev


def test_get_event_evolution_returns_dict():
    with _patch_alerts():
        events = queries.list_events()
        event_id = events[0]["event_id"]
        evo = queries.get_event_evolution(event_id)
    assert evo is not None
    assert "frames" in evo
    assert "milestones" in evo


def test_get_event_trajectory_returns_dict():
    with _patch_alerts():
        events = queries.list_events()
        event_id = events[0]["event_id"]
        traj = queries.get_event_trajectory(event_id)
    assert traj is not None
    assert "state" in traj
