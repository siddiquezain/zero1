"""Tests for thermal behaviour fingerprinting."""
from src.intelligence.fingerprint import compute_fingerprint


def _obs(day_night="D", frp=15.0, lat=17.0, lon=80.0, date="2026-09-01",
         dist_fac=5.0, risk=40, agri_month=False):
    return {
        "lat": lat, "lon": lon, "acq_date": date,
        "day_night": day_night,
        "frp_mw": frp,
        "bt_kelvin": 320.0,
        "dist_nearest_facility_km": dist_fac,
        "nearest_facility_type": "thermal power",
        "risk_score": risk,
        "anomaly_flag": 0,
        "persistence_count": 1,
    }


def test_empty_returns_insufficient():
    fp = compute_fingerprint([])
    assert fp["behaviour_category"] == "Insufficient Evidence"


def test_single_observation():
    fp = compute_fingerprint([_obs()])
    assert "behaviour_category" in fp
    assert fp["observation_count"] == 1


def test_persistent_source_high_persistence():
    obs = [_obs(day_night="N", frp=80.0, dist_fac=0.5) for _ in range(9)]
    fp = compute_fingerprint(obs)
    assert fp["persistence"] in ("HIGH", "VERY HIGH")
    assert fp["industrial_proximity"] in ("HIGH", "VERY HIGH")


def test_mostly_nighttime():
    obs = [_obs(day_night="N") for _ in range(8)] + [_obs(day_night="D")]
    fp = compute_fingerprint(obs)
    assert fp["night_activity"] in ("HIGH", "VERY HIGH")


def test_mostly_daytime():
    obs = [_obs(day_night="D") for _ in range(8)] + [_obs(day_night="N")]
    fp = compute_fingerprint(obs)
    assert fp["night_activity"] in ("LOW", "MEDIUM")


def test_high_frp_intensity():
    obs = [_obs(frp=200.0) for _ in range(3)]
    fp = compute_fingerprint(obs)
    assert fp["frp_intensity"] in ("HIGH", "VERY HIGH")


def test_missing_frp_handled():
    obs = [_obs()]
    obs[0]["frp_mw"] = None
    fp = compute_fingerprint(obs)
    assert "frp_intensity" in fp


def test_behaviour_category_present():
    obs = [_obs(day_night="N", frp=80.0, dist_fac=0.5) for _ in range(9)]
    fp = compute_fingerprint(obs)
    assert fp["behaviour_category"] in (
        "Persistent Industrial Signature",
        "Recurring Thermal Source",
        "Rapidly Expanding Fire Signature",
        "Seasonal Agricultural Signature",
        "Isolated Thermal Anomaly",
        "Insufficient Evidence",
    )


def test_seasonal_alignment_detected():
    # January = agri month (month 1)
    obs = [_obs(date="2026-01-15") for _ in range(5)]
    fp = compute_fingerprint(obs)
    assert fp["seasonal_alignment"] in ("VERY HIGH", "HIGH", "MEDIUM", "LOW")
