# src/intelligence/early_warning.py
"""
Risk trajectory analysis from ordered evolution frames.

Computes:
  - trajectory: INCREASING | STABLE | DECREASING
  - state: INSUFFICIENT DATA | STABLE | WATCH | INCREASING | EARLY WARNING | HIGH PRIORITY
  - signals: list of contributing reasons
  - risk_history: ordered list of risk scores

NEVER claims fire certainty. NEVER predicts the future.
Describes observed trend in existing data only.
"""
from __future__ import annotations


def compute_trajectory(frames: list[dict]) -> dict:
    """
    Compute a risk trajectory from ordered evolution frames.

    Derives risk_scores from frames internally.

    Returns:
        state, trajectory, delta, risk_history, signals
    """
    if not frames:
        return {"state": "INSUFFICIENT DATA", "trajectory": "UNKNOWN",
                "delta": 0, "risk_history": [], "signals": []}

    risk_scores = [int(f["risk_score"]) for f in frames if f.get("risk_score") is not None]

    if len(risk_scores) < 2:
        return {"state": "INSUFFICIENT DATA", "trajectory": "UNKNOWN",
                "delta": 0, "risk_history": risk_scores, "signals": []}

    delta = risk_scores[-1] - risk_scores[0]
    signals: list[str] = []

    if delta > 5:
        trajectory = "INCREASING"
    elif delta < -5:
        trajectory = "DECREASING"
    else:
        trajectory = "STABLE"

    if delta > 0:
        signals.append(f"Risk score increased by {delta} points over {len(risk_scores)} observations")
    elif delta < 0:
        signals.append(f"Risk score decreased by {abs(delta)} points over {len(risk_scores)} observations")
    else:
        signals.append("Risk score is stable across observations")

    frps = [float(f["current_frp"]) for f in frames if f.get("current_frp") is not None]
    if len(frps) >= 2:
        frp_delta = frps[-1] - frps[0]
        if frp_delta > 5:
            signals.append(f"Fire Radiative Power increased from {frps[0]:.1f} to {frps[-1]:.1f} MW")
        elif frp_delta < -5:
            signals.append(f"Fire Radiative Power decreased from {frps[0]:.1f} to {frps[-1]:.1f} MW")

    latest_risk = risk_scores[-1]
    if trajectory == "INCREASING" and latest_risk >= 80:
        state = "HIGH PRIORITY"
    elif trajectory == "INCREASING" and latest_risk >= 60:
        state = "EARLY WARNING"
    elif trajectory == "INCREASING":
        state = "INCREASING"
    elif trajectory == "STABLE" and latest_risk >= 60:
        state = "WATCH"
    elif trajectory == "STABLE":
        state = "STABLE"
    else:  # DECREASING
        state = "STABLE"

    return {
        "state": state,
        "trajectory": trajectory,
        "delta": delta,
        "risk_history": risk_scores,
        "signals": signals,
    }
