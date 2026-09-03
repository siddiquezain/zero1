"""
Facility Thermal Fingerprinting — regression tests.

Covers: sufficient / insufficient history, normal / elevated / highly-abnormal
events, missing FRP / BT / facility, day-night and persistence deviation,
determinism, no-fabrication, and guards that the existing risk engine, alert
lifecycle, dashboard import and offline agent are unaffected.
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from src.intelligence import facility_fingerprint as ff

_FACILITY = {"facility_id": "F1", "name": "Test Plant",
             "facility_type": "thermal power", "lat": 17.0, "lon": 80.0}


def _obs(frp=10.0, bt=315.0, persist=2, dn="N", date="2026-08-24"):
    return {"frp_mw": frp, "bt_kelvin": bt, "persistence_count": persist,
            "day_night": dn, "acq_date": date}


def _history(n=8, **kw):
    days = ["2026-08-23", "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27"]
    return [_obs(date=days[i % len(days)], **kw) for i in range(n)]


def _event(peak_frp=10.0, max_bt=315.0, persist=2, night=3, day=0,
           start="2026-08-25"):
    return {"peak_frp_mw": peak_frp, "max_bt_kelvin": max_bt,
            "persistence_count": persist, "night_count": night, "day_count": day,
            "start_date": start}


# ── 1. sufficient history → a baseline ──────────────────────────────────────
def test_sufficient_history_builds_baseline():
    b = ff.build_facility_baseline(_FACILITY, _history(9))
    assert b["baseline_quality"] in ("LIMITED", "OK")
    assert b["observation_count"] == 9
    assert b["active_days"] >= ff.MIN_ACTIVE_DAYS
    assert b["frp"] is not None and b["frp"]["median"] > 0
    assert b["baseline_start"] and b["baseline_end"]


# ── 2. insufficient history → INSUFFICIENT_BASELINE, nothing invented ───────
def test_insufficient_history_is_flagged_not_invented():
    b = ff.build_facility_baseline(_FACILITY, _history(3))
    assert b["baseline_quality"] == "INSUFFICIENT_BASELINE"
    assert b["frp"] is None and b["bt"] is None
    assert b["median_persistence"] is None
    assert b["typical_day_night"] is None
    assert b["notes"]


def test_one_day_history_is_insufficient_even_with_many_obs():
    b = ff.build_facility_baseline(
        _FACILITY, [_obs(date="2026-08-24") for _ in range(12)])
    assert b["baseline_quality"] == "INSUFFICIENT_BASELINE"


# ── 3/4/5. normal / elevated / highly-abnormal events ──────────────────────
def test_normal_event_scores_normal():
    b = ff.build_facility_baseline(_FACILITY, _history(9, frp=10.0, persist=2, dn="N"))
    dev = ff.compare_event_to_baseline(_event(peak_frp=10.0, persist=2, night=3, day=0), b)
    assert dev["thermal_deviation_level"] == "NORMAL"
    assert dev["thermal_behavior_class"] == "NORMAL"
    assert dev["thermal_deviation_score"] < 20


def test_elevated_event_scores_elevated():
    b = ff.build_facility_baseline(_FACILITY, _history(9, frp=10.0, persist=2, dn="N"))
    dev = ff.compare_event_to_baseline(
        _event(peak_frp=26.0, persist=2, night=3, day=0), b)
    assert dev["thermal_deviation_level"] == "ELEVATED"
    assert 20 <= dev["thermal_deviation_score"] < 45


def test_highly_abnormal_event_scores_highly_abnormal():
    b = ff.build_facility_baseline(_FACILITY, _history(9, frp=10.0, persist=2, dn="N"))
    dev = ff.compare_event_to_baseline(
        _event(peak_frp=600.0, max_bt=380.0, persist=12, night=0, day=5), b)
    assert dev["thermal_deviation_level"] == "HIGHLY_ABNORMAL"
    assert dev["thermal_behavior_class"] == "ABNORMAL"
    assert dev["thermal_deviation_score"] >= 70
    # every evidence line cites a real, computed comparison
    assert dev["evidence"]
    assert any("MW" in e for e in dev["evidence"])


# ── 6/7. missing FRP / brightness temperature handled ──────────────────────
def test_missing_frp_handled():
    hist = _history(9)
    for o in hist:
        o["frp_mw"] = None
    b = ff.build_facility_baseline(_FACILITY, hist)
    assert b["frp"] is None                      # not fabricated
    dev = ff.compare_event_to_baseline(_event(peak_frp=None, max_bt=360.0), b)
    assert dev["thermal_deviation_score"] is not None   # still scored on BT
    assert not any("FRP" in e for e in dev["evidence"])


def test_missing_bt_handled():
    hist = _history(9)
    for o in hist:
        o["bt_kelvin"] = None
    b = ff.build_facility_baseline(_FACILITY, hist)
    assert b["bt"] is None
    dev = ff.compare_event_to_baseline(_event(peak_frp=200.0, max_bt=None), b)
    assert dev["thermal_deviation_score"] is not None


def test_event_with_no_comparable_signal():
    hist = _history(9)
    for o in hist:
        o["frp_mw"] = None
        o["bt_kelvin"] = None
        o["day_night"] = ""
    b = ff.build_facility_baseline(_FACILITY, hist)
    # baseline still has persistence; an event matching it → NORMAL, score defined
    dev = ff.compare_event_to_baseline(_event(peak_frp=None, max_bt=None, persist=2), b)
    assert dev["thermal_behavior_class"] in ("NORMAL", "INSUFFICIENT_BASELINE")


# ── 8. no baseline → deviation refuses gracefully ─────────────────────────
def test_no_baseline_gives_insufficient_deviation():
    b = ff.build_facility_baseline(_FACILITY, _history(2))
    dev = ff.compare_event_to_baseline(_event(peak_frp=500.0), b)
    assert dev["thermal_deviation_score"] is None
    assert dev["thermal_deviation_level"] == "INSUFFICIENT_BASELINE"
    assert dev["thermal_behavior_class"] == "INSUFFICIENT_BASELINE"
    assert dev["evidence"]                       # explains why


def test_none_baseline_object_handled():
    dev = ff.compare_event_to_baseline(_event(), None)
    assert dev["thermal_deviation_score"] is None


# ── 9. day / night deviation ─────────────────────────────────────────────
def test_day_night_deviation_detected():
    b = ff.build_facility_baseline(_FACILITY, _history(9, dn="N"))       # night-active
    dev = ff.compare_event_to_baseline(_event(night=0, day=5), b)        # daytime event
    assert any("day" in e.lower() and "night" in e.lower() for e in
               [s["detail"] for s in dev["signals"]])
    dn = next(s for s in dev["signals"] if s["name"] == "day_night")
    assert dn["score"] > 0


def test_day_night_match_is_not_flagged():
    b = ff.build_facility_baseline(_FACILITY, _history(9, dn="N"))
    dev = ff.compare_event_to_baseline(_event(night=4, day=0), b)
    dn = next(s for s in dev["signals"] if s["name"] == "day_night")
    assert dn["score"] == 0


# ── 10. persistence deviation ────────────────────────────────────────────
def test_persistence_deviation_detected():
    b = ff.build_facility_baseline(_FACILITY, _history(9, persist=2))
    dev = ff.compare_event_to_baseline(_event(peak_frp=10.0, persist=9), b)
    p = next(s for s in dev["signals"] if s["name"] == "persistence")
    assert p["score"] > 0
    assert any("persistence" in e.lower() for e in dev["evidence"])


# ── 11. determinism ─────────────────────────────────────────────────────
def test_output_is_deterministic():
    hist = _history(9, frp=12.0)
    ev = _event(peak_frp=45.0, persist=5)
    r1 = ff.compare_event_to_baseline(ev, ff.build_facility_baseline(_FACILITY, hist))
    r2 = ff.compare_event_to_baseline(ev, ff.build_facility_baseline(_FACILITY, hist))
    assert r1 == r2
    assert ff.build_facility_baseline(_FACILITY, hist) == ff.build_facility_baseline(_FACILITY, hist)


# ── 12. no fabricated precision when a stat has too few points ───────────
def test_robust_stats_need_a_minimum_sample():
    assert ff._robust_stats([1.0, 2.0]) is None          # < MIN_STAT_N
    s = ff._robust_stats([1.0, 2.0, 3.0, 4.0, 5.0])
    assert s and s["n"] == 5 and s["median"] == 3.0


def test_classify_and_class_helpers():
    assert ff.classify_deviation(None) == "INSUFFICIENT_BASELINE"
    assert ff.classify_deviation(0) == "NORMAL"
    assert ff.classify_deviation(30) == "ELEVATED"
    assert ff.classify_deviation(55) == "ABNORMAL"
    assert ff.classify_deviation(90) == "HIGHLY_ABNORMAL"
    assert ff.behavior_class("HIGHLY_ABNORMAL") == "ABNORMAL"
    assert ff.behavior_class("ELEVATED") == "NORMAL"


# ── 13. existing risk engine unaffected + opt-in helper ─────────────────
def test_risk_engine_scoring_unchanged():
    from src.alerting import risk_engine
    row = {"lat": 21.17, "lon": 72.83, "frp_mw": 32.0, "persistence_count": 4,
           "dist_nearest_facility_km": 0.6, "nearest_facility_type": "refinery",
           "anomaly_flag": 1, "predicted_label": "A", "confidence": "h",
           "day_night": "N", "agri_season_flag": 0}
    r1 = risk_engine.score_row(dict(row))
    r2 = risk_engine.score_row(dict(row))
    assert r1.score == r2.score == sum(p for _, p in r1.factors)
    assert r1.severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW")


def test_deviation_factor_helper_is_additive_and_optional():
    from src.alerting import risk_engine
    assert risk_engine.deviation_factor(None) is None
    assert risk_engine.deviation_factor(10) is None           # below ELEVATED band
    f = risk_engine.deviation_factor(80)
    assert f and isinstance(f[1], int) and f[1] > 0
    # score_row never calls it — a plain row carries no deviation factor
    r = risk_engine.score_row({"lat": 20.0, "lon": 85.0, "frp_mw": 5.0})
    assert not any("deviat" in reason.lower() for reason, _ in r.factors)


# ── 14. alert lifecycle unchanged ──────────────────────────────────────
def test_alert_lifecycle_states_unchanged():
    from src.alerting import alert_store
    from src.intelligence import actions
    assert alert_store.LIFECYCLE_STATES == [
        "DETECTED", "VALIDATING", "ALERTED", "ESCALATED", "MONITORING", "EXTINGUISHED"]
    assert actions._ACTION_TO_STATUS == {
        "acknowledge": "MONITORING", "escalate": "ESCALATED", "resolve": "EXTINGUISHED"}


# ── 15. dashboard still imports ────────────────────────────────────────
def test_dashboard_modules_import():
    import importlib
    for m in ("dashboard.views.investigation", "dashboard.views.facilities",
              "dashboard.views.analytics", "dashboard.data"):
        importlib.import_module(m)


# ── 16. offline agent still works + new tools are read-only ────────────
def test_agent_tools_are_all_read_only():
    from src.intelligence.agent import tools
    for name in ("get_facility_fingerprint", "get_event_deviation",
                 "rank_facilities_by_deviation", "find_abnormal_facilities",
                 "facility_fingerprint_summary"):
        assert name in tools.REGISTRY
    banned = ("acknowledge", "escalate", "resolve", "delete", "update",
              "set_status", "insert", "write", "retrain")
    for n in tools.REGISTRY:
        assert not any(b in n for b in banned)


def test_offline_agent_answers_deviation_query():
    from src.intelligence.agent import runtime
    reply = runtime.ask("which facilities are behaving abnormally")
    assert reply.text and reply.mode == "deterministic"
    reply2 = runtime.ask("facility thermal baseline summary")
    assert reply2.text


# ── integration: queries layer against the seeded store ───────────────
_MOCK = [
    {"alert_id": f"m{i:03d}", "lat": 17.0 + (i % 3) * 0.01, "lon": 80.0 + (i % 3) * 0.01,
     "acq_date": ["2026-08-23", "2026-08-24", "2026-08-25"][i % 3],
     "frp_mw": 10.0 if i < 8 else 120.0, "bt_kelvin": 315.0, "risk_score": 45,
     "severity": "MEDIUM", "day_night": "N", "dist_nearest_facility_km": 1.0,
     "nearest_facility_type": "thermal power", "predicted_label": "A",
     "prob_A": 0.7, "prob_B": 0.2, "anomaly_flag": 0, "persistence_count": 2,
     "status": "ALERTED", "output_class": "Persistent Industrial Thermal Source",
     "output_class_short": "Persistent Source", "output_class_code": "PS-B",
     "state": "Andhra Pradesh", "district": "Visakhapatnam", "zone": None,
     "narrative": "", "in_india": True, "place": "Visakhapatnam, Andhra Pradesh",
     "land_cover_context": "", "hazard_facility_type": "thermal power",
     "nearest_city": "", "dist_nearest_city_km": 0.0, "near_population": 0,
     "risk_factors": "[]", "created_at": "", "updated_at": "", "acknowledged_at": None}
    for i in range(9)
]


def _patched_queries():
    from src.intelligence import queries
    df = pd.DataFrame(_MOCK)
    queries.clear_caches()
    return patch.object(queries, "_alerts", return_value=df)


def test_queries_event_deviation_end_to_end():
    from src.intelligence import queries
    with _patched_queries():
        events = queries.list_events()
        assert events
        dev = queries.get_event_deviation(events[0]["event_id"])
    assert dev is not None
    assert dev["thermal_deviation_level"] in (
        *ff.DEVIATION_LEVELS, "INSUFFICIENT_BASELINE", "NO_FACILITY")
    assert "baseline" in dev


def test_queries_fingerprint_summary_shape():
    from src.intelligence import queries
    with _patched_queries():
        s = queries.facility_fingerprint_summary()
    assert set(s) >= {"facilities_with_activity", "baseline_available",
                      "insufficient_baseline", "events_assessed", "by_level"}
    assert s["baseline_available"] + s["insufficient_baseline"] == s["facilities_with_activity"]


@pytest.fixture(autouse=True)
def _restore_caches():
    yield
    from src.intelligence import queries
    queries.clear_caches()
