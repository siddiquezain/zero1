"""Tests for event evolution timeline builder."""
from src.intelligence.evolution import build_evolution


def _obs(acq_date, frp=15.0, risk=40):
    return {"acq_date": acq_date, "frp_mw": frp, "risk_score": risk,
            "lat": 17.0, "lon": 80.0, "day_night": "D",
            "bt_kelvin": 320.0, "alert_id": acq_date}


def test_chronological_ordering():
    obs = [_obs("2026-09-03"), _obs("2026-09-01"), _obs("2026-09-02")]
    evo = build_evolution(obs)
    dates = [f["timestamp"] for f in evo["frames"]]
    assert dates == sorted(dates)


def test_duplicate_timestamps_handled():
    obs = [_obs("2026-09-01"), _obs("2026-09-01")]
    evo = build_evolution(obs)
    assert evo["observation_count"] == 2
    assert len(evo["frames"]) == 2


def test_single_observation():
    obs = [_obs("2026-09-01", frp=20.0, risk=50)]
    evo = build_evolution(obs)
    assert evo["observation_count"] == 1
    assert evo["start_date"] == "2026-09-01"
    assert evo["end_date"] == "2026-09-01"
    assert len(evo["milestones"]) >= 1  # at least "First Detection"


def test_missing_timestamp_handled():
    obs = [_obs(None), _obs("2026-09-01")]
    evo = build_evolution(obs)
    assert evo["observation_count"] == 2


def test_empty_event():
    evo = build_evolution([])
    assert evo["observation_count"] == 0
    assert evo["frames"] == []
    assert evo["milestones"] == []


def test_frames_have_cumulative_count():
    obs = [_obs("2026-09-01"), _obs("2026-09-02"), _obs("2026-09-03")]
    evo = build_evolution(obs)
    for i, f in enumerate(evo["frames"]):
        assert f["cumulative_count"] == i + 1


def test_deterministic_frame_generation():
    obs = [_obs("2026-09-01", frp=10.0), _obs("2026-09-02", frp=20.0)]
    evo1 = build_evolution(obs)
    evo2 = build_evolution(obs)
    assert evo1["frames"] == evo2["frames"]
    assert evo1["milestones"] == evo2["milestones"]


def test_peak_frp_milestone_detected():
    obs = [_obs("2026-09-01", frp=10.0), _obs("2026-09-02", frp=100.0),
           _obs("2026-09-03", frp=50.0)]
    evo = build_evolution(obs)
    labels = [m["label"] for m in evo["milestones"]]
    assert any("peak" in l.lower() or "frp" in l.lower() for l in labels)


def test_risk_threshold_milestone():
    obs = [_obs("2026-09-01", frp=10.0, risk=30),
           _obs("2026-09-02", frp=80.0, risk=75)]
    evo = build_evolution(obs)
    labels = [m["label"] for m in evo["milestones"]]
    assert any("risk" in l.lower() or "threshold" in l.lower() for l in labels)
