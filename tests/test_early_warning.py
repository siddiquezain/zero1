# tests/test_early_warning.py
"""Tests for risk trajectory and early-warning state."""
from src.intelligence.early_warning import compute_trajectory


def _frames(risk_scores: list[int]) -> list[dict]:
    return [{"step": i + 1, "timestamp": f"2026-09-0{i+1}",
             "cumulative_count": i + 1, "current_frp": 20.0,
             "risk_score": rs, "lat": 17.0, "lon": 80.0}
            for i, rs in enumerate(risk_scores)]


def test_stable_risk():
    result = compute_trajectory(_frames([40, 41, 42, 40]))
    assert result["trajectory"] == "STABLE"
    assert result["state"] in ("STABLE", "WATCH")


def test_increasing_risk():
    result = compute_trajectory(_frames([30, 45, 60, 80]))
    assert result["trajectory"] == "INCREASING"
    assert result["state"] in ("INCREASING", "EARLY WARNING", "HIGH PRIORITY")


def test_decreasing_risk():
    result = compute_trajectory(_frames([80, 60, 40, 30]))
    assert result["trajectory"] == "DECREASING"


def test_insufficient_history():
    result = compute_trajectory(_frames([50]))
    assert result["state"] == "INSUFFICIENT DATA"


def test_empty_frames():
    result = compute_trajectory([])
    assert result["state"] == "INSUFFICIENT DATA"


def test_missing_risk_score_skipped():
    frames = _frames([40, 60])
    frames[0]["risk_score"] = None
    result = compute_trajectory(frames)
    assert "state" in result


def test_missing_frp_skipped():
    frames = _frames([40, 70])
    frames[0]["current_frp"] = None
    result = compute_trajectory(frames)
    assert "state" in result


def test_signals_list_present():
    result = compute_trajectory(_frames([30, 50, 70, 90]))
    assert isinstance(result["signals"], list)


def test_risk_history_matches_input():
    scores = [35, 50, 65, 80]
    result = compute_trajectory(_frames(scores))
    assert result["risk_history"] == scores
