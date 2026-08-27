"""
Core ingestion tests — runs without any API keys or downloaded data.
Tests logic, not network calls.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.ingestion.facilities import normalise_gppd
from src.ingestion.utils import sha256
from src.labeling.match_incidents import haversine_km, match_incident


# ── normalise_gppd ────────────────────────────────────────────────────────────

def _fake_gppd(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "gppd_idnr": "WRI0000001",
        "latitude": "28.0",
        "longitude": "77.0",
        "primary_fuel": "Coal",
        "name": "Test Plant",
        "country": "IND",
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


def test_normalise_gppd_schema():
    df = normalise_gppd(_fake_gppd([{}]))
    assert set(["facility_id", "lat", "lon", "facility_type", "source", "name", "country"]).issubset(df.columns)


def test_normalise_gppd_id_prefix():
    df = normalise_gppd(_fake_gppd([{"gppd_idnr": "WRI9999"}]))
    assert df["facility_id"].iloc[0] == "GPPD-WRI9999"


def test_normalise_gppd_drops_bad_coords():
    rows = [
        {"latitude": "28.0", "longitude": "77.0"},   # good
        {"latitude": "NaN", "longitude": "77.0"},     # bad lat
        {"latitude": "28.0", "longitude": "bad"},     # bad lon
    ]
    df = normalise_gppd(_fake_gppd(rows))
    assert len(df) == 1  # only the good row survives


def test_normalise_gppd_source_column():
    df = normalise_gppd(_fake_gppd([{}]))
    assert (df["source"] == "GPPD").all()


# ── haversine ────────────────────────────────────────────────────────────────

def test_haversine_same_point():
    assert haversine_km(28.0, 77.0, 28.0, 77.0) == pytest.approx(0.0)


def test_haversine_known_distance():
    # Delhi (28.6139, 77.2090) to Agra (27.1767, 78.0081)
    # Straight-line ~178 km (not road distance)
    d = haversine_km(28.6139, 77.2090, 27.1767, 78.0081)
    assert 170 < d < 190


def test_haversine_symmetry():
    d1 = haversine_km(28.0, 77.0, 19.0, 73.0)
    d2 = haversine_km(19.0, 73.0, 28.0, 77.0)
    assert d1 == pytest.approx(d2)


# ── match_incident ────────────────────────────────────────────────────────────

def _fake_incident(lat=17.69, lon=83.22, date="2020-05-07") -> pd.Series:
    return pd.Series({"incident_id": "TEST-001", "lat": lat, "lon": lon, "date": date})


def _fake_firms(lat=17.69, lon=83.22, date="2020-05-07") -> pd.DataFrame:
    return pd.DataFrame([{"lat": lat, "lon": lon, "acq_date": pd.Timestamp(date),
                          "brightness": 420.0, "frp": 15.0}])


def test_match_incident_exact_match():
    inc = _fake_incident()
    firms = _fake_firms()
    matches = match_incident(inc, firms, buffer_km=1.0, temporal_days=1)
    assert len(matches) == 1


def test_match_incident_too_far():
    inc = _fake_incident(lat=17.69, lon=83.22)
    # Put hotspot 50 km away
    firms = _fake_firms(lat=18.1, lon=83.22)
    matches = match_incident(inc, firms, buffer_km=1.0, temporal_days=1)
    assert len(matches) == 0


def test_match_incident_outside_temporal_window():
    inc = _fake_incident(date="2020-05-07")
    firms = _fake_firms(date="2020-05-10")  # 3 days away
    matches = match_incident(inc, firms, buffer_km=1.0, temporal_days=1)
    assert len(matches) == 0


def test_match_incident_no_firms():
    inc = _fake_incident()
    matches = match_incident(inc, None, buffer_km=1.0, temporal_days=1)
    assert matches == []


def test_match_incident_empty_firms():
    inc = _fake_incident()
    matches = match_incident(inc, pd.DataFrame(), buffer_km=1.0, temporal_days=1)
    assert matches == []


# ── sha256 ───────────────────────────────────────────────────────────────────

def test_sha256(tmp_path):
    f = tmp_path / "test.txt"
    f.write_bytes(b"hello")
    result = sha256(f)
    assert len(result) == 64
    assert result == sha256(f)  # deterministic
