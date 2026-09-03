"""
Event evolution: ordered timeline of observations with milestones.

Milestones are derived only from data — no semantic labels are invented.
The frame sequence supports UI replay (slider-based).
"""
from __future__ import annotations


def _safe_date(d) -> str:
    return str(d)[:10] if d else ""


def _sort_key(o: dict) -> str:
    return _safe_date(o.get("acq_date") or "")


def build_evolution(observations: list[dict]) -> dict:
    """
    Build an ordered evolution dict from a list of alert-dict observations.

    Returns:
        observation_count, start_date, end_date,
        frames: [{step, timestamp, cumulative_count, current_frp, risk_score, lat, lon, day_night}],
        milestones: [{timestamp, label, detail}]
    """
    if not observations:
        return {
            "observation_count": 0,
            "start_date": None,
            "end_date": None,
            "frames": [],
            "milestones": [],
        }

    sorted_obs = sorted(observations, key=_sort_key)
    n = len(sorted_obs)

    frames = []
    for i, o in enumerate(sorted_obs):
        frames.append({
            "step": i + 1,
            "timestamp": _safe_date(o.get("acq_date")),
            "cumulative_count": i + 1,
            "current_frp": o.get("frp_mw"),
            "risk_score": int(o.get("risk_score") or 0),
            "lat": float(o["lat"]),
            "lon": float(o["lon"]),
            "day_night": o.get("day_night", ""),
        })

    milestones: list[dict] = []

    # First detection (always)
    first = sorted_obs[0]
    milestones.append({
        "timestamp": _safe_date(first.get("acq_date")),
        "label": "First Detection",
        "detail": (f"FRP {first.get('frp_mw')} MW" if first.get("frp_mw") is not None
                   else "Thermal anomaly detected"),
    })

    # Persistence detected (second observation)
    if n >= 2:
        second = sorted_obs[1]
        milestones.append({
            "timestamp": _safe_date(second.get("acq_date")),
            "label": "Persistence Detected",
            "detail": "Source confirmed across multiple satellite overpasses",
        })

    # FRP peak (if not first observation)
    frp_vals = [(i, o.get("frp_mw")) for i, o in enumerate(sorted_obs)
                if o.get("frp_mw") is not None]
    if frp_vals and len(frp_vals) > 1:
        peak_i, peak_frp = max(frp_vals, key=lambda x: x[1])
        if peak_i > 0:
            milestones.append({
                "timestamp": _safe_date(sorted_obs[peak_i].get("acq_date")),
                "label": "Peak FRP Observed",
                "detail": f"{peak_frp} MW — highest thermal intensity in event window",
            })

    # Risk threshold crossed (risk_score >= 60)
    risk_vals = [(i, int(o.get("risk_score") or 0)) for i, o in enumerate(sorted_obs)]
    for i, rs in risk_vals:
        if rs >= 60 and i > 0:
            milestones.append({
                "timestamp": _safe_date(sorted_obs[i].get("acq_date")),
                "label": "High-Risk Threshold Crossed",
                "detail": f"Risk score reached {rs}/100",
            })
            break

    # Sort milestones chronologically
    milestones.sort(key=lambda m: m["timestamp"])

    start_date = _safe_date(sorted_obs[0].get("acq_date"))
    end_date = _safe_date(sorted_obs[-1].get("acq_date"))

    return {
        "observation_count": n,
        "start_date": start_date or None,
        "end_date": end_date or None,
        "frames": frames,
        "milestones": milestones,
    }
