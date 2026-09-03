"""
Thermal behaviour fingerprint computed from a list of alert-dict observations.

All values are derived from actual data — nothing is fabricated.
Output is a plain dict suitable for JSON serialisation and UI display.

Behaviour categories are assessments, not ground truth.
"""
from __future__ import annotations

from datetime import date

# Agricultural months in India (when crop-residue burning is common)
_AGRI_MONTHS = {1, 2, 4, 5, 7, 8, 9, 10, 11}

_LEVELS = ("VERY LOW", "LOW", "MEDIUM", "HIGH", "VERY HIGH")

BEHAVIOUR_CATEGORIES = [
    "Persistent Industrial Signature",
    "Recurring Thermal Source",
    "Rapidly Expanding Fire Signature",
    "Seasonal Agricultural Signature",
    "Isolated Thermal Anomaly",
    "Insufficient Evidence",
]


def _level(value: float, thresholds: tuple[float, ...]) -> str:
    """Map a 0-1 value to a 5-level rating using four thresholds."""
    for i, t in enumerate(thresholds):
        if value <= t:
            return _LEVELS[i]
    return _LEVELS[-1]


def _rate_persistence(n: int) -> str:
    if n <= 1:
        return "VERY LOW"
    if n <= 2:
        return "LOW"
    if n <= 4:
        return "MEDIUM"
    if n <= 8:
        return "HIGH"
    return "VERY HIGH"


def _rate_night_activity(night_ratio: float) -> str:
    return _level(night_ratio, (0.1, 0.3, 0.6, 0.8))


def _rate_frp(mean_frp: float | None) -> str:
    if mean_frp is None:
        return "UNKNOWN"
    if mean_frp < 5:
        return "VERY LOW"
    if mean_frp < 15:
        return "LOW"
    if mean_frp < 40:
        return "MEDIUM"
    if mean_frp < 100:
        return "HIGH"
    return "VERY HIGH"


def _rate_spatial_stability(extent_km: float, n: int) -> str:
    if n <= 1:
        return "VERY HIGH"
    if extent_km < 2:
        return "VERY HIGH"
    if extent_km < 5:
        return "HIGH"
    if extent_km < 15:
        return "MEDIUM"
    if extent_km < 30:
        return "LOW"
    return "VERY LOW"


def _rate_industrial_proximity(min_dist_km: float | None) -> str:
    if min_dist_km is None:
        return "UNKNOWN"
    if min_dist_km < 1:
        return "VERY HIGH"
    if min_dist_km < 3:
        return "HIGH"
    if min_dist_km < 10:
        return "MEDIUM"
    if min_dist_km < 25:
        return "LOW"
    return "VERY LOW"


def _rate_seasonal(fraction: float) -> str:
    return _level(fraction, (0.1, 0.3, 0.6, 0.8))


def _spatial_extent_km(obs: list[dict]) -> float:
    import math
    max_d = 0.0
    lats = [float(o["lat"]) for o in obs]
    lons = [float(o["lon"]) for o in obs]
    for i in range(len(obs)):
        for j in range(i + 1, len(obs)):
            dlat = math.radians(lats[j] - lats[i])
            dlon = math.radians(lons[j] - lons[i])
            a = (math.sin(dlat / 2) ** 2
                 + math.cos(math.radians(lats[i])) * math.cos(math.radians(lats[j]))
                 * math.sin(dlon / 2) ** 2)
            d = 2 * 6371.0 * math.asin(math.sqrt(min(a, 1.0)))
            if d > max_d:
                max_d = d
    return round(max_d, 2)


def _assign_category(persistence: str, night_activity: str, frp_intensity: str,
                     spatial_stability: str, industrial_proximity: str,
                     seasonal_alignment: str, n: int) -> str:
    if n < 2:
        return "Isolated Thermal Anomaly"
    high_set = {"HIGH", "VERY HIGH"}
    low_set = {"LOW", "VERY LOW"}
    if (persistence in high_set
            and industrial_proximity in high_set
            and spatial_stability in high_set):
        return "Persistent Industrial Signature"
    if persistence in high_set and frp_intensity in low_set and seasonal_alignment in high_set:
        return "Seasonal Agricultural Signature"
    if persistence in high_set and spatial_stability in low_set:
        return "Rapidly Expanding Fire Signature"
    if persistence in ("MEDIUM", "HIGH", "VERY HIGH"):
        return "Recurring Thermal Source"
    return "Isolated Thermal Anomaly"


def compute_fingerprint(observations: list[dict]) -> dict:
    """
    Compute a behavioural fingerprint from a list of alert dicts (event observations).

    Returns a plain dict with level strings and a behaviour_category string.
    All fields derived from real data. Missing data → "UNKNOWN" level.
    """
    n = len(observations)
    if n == 0:
        return {
            "observation_count": 0,
            "persistence": "VERY LOW",
            "night_activity": "UNKNOWN",
            "frp_intensity": "UNKNOWN",
            "spatial_stability": "UNKNOWN",
            "industrial_proximity": "UNKNOWN",
            "seasonal_alignment": "UNKNOWN",
            "behaviour_category": "Insufficient Evidence",
        }

    persistence = _rate_persistence(n)

    night_count = sum(1 for o in observations if o.get("day_night") == "N")
    night_ratio = night_count / n
    night_activity = _rate_night_activity(night_ratio)

    frps = [float(o["frp_mw"]) for o in observations if o.get("frp_mw") is not None]
    mean_frp = sum(frps) / len(frps) if frps else None
    frp_intensity = _rate_frp(mean_frp)

    extent_km = _spatial_extent_km(observations) if n > 1 else 0.0
    spatial_stability = _rate_spatial_stability(extent_km, n)

    dists = [float(o["dist_nearest_facility_km"])
             for o in observations if o.get("dist_nearest_facility_km") is not None]
    min_dist = min(dists) if dists else None
    industrial_proximity = _rate_industrial_proximity(min_dist)

    agri_hits = 0
    for o in observations:
        d = o.get("acq_date") or ""
        try:
            m = date.fromisoformat(str(d)[:10]).month
            if m in _AGRI_MONTHS:
                agri_hits += 1
        except (ValueError, TypeError):
            pass
    seasonal_fraction = agri_hits / n
    seasonal_alignment = _rate_seasonal(seasonal_fraction)

    category = _assign_category(
        persistence, night_activity, frp_intensity,
        spatial_stability, industrial_proximity, seasonal_alignment, n,
    )

    return {
        "observation_count": n,
        "persistence": persistence,
        "night_activity": night_activity,
        "frp_intensity": frp_intensity,
        "spatial_stability": spatial_stability,
        "industrial_proximity": industrial_proximity,
        "seasonal_alignment": seasonal_alignment,
        "behaviour_category": category,
        "night_count": night_count,
        "day_count": n - night_count,
        "mean_frp_mw": round(mean_frp, 1) if mean_frp is not None else None,
        "spatial_extent_km": extent_km,
        "min_dist_facility_km": round(min_dist, 2) if min_dist is not None else None,
    }
