"""Tests for src/intelligence/geo.py — offline polygon-based state/district resolver."""
import pandas as pd
import pytest

from src.intelligence import geo


@pytest.mark.parametrize("name,lat,lon,state", [
    ("Jaipur", 26.9124, 75.7873, "Rajasthan"),
    ("Chennai", 13.0827, 80.2707, "Tamil Nadu"),
    ("Angul", 20.8409, 85.1012, "Odisha"),
    ("Paradip", 20.2961, 86.6831, "Odisha"),
    ("Dhanbad", 23.7957, 86.4304, "Jharkhand"),
    ("Bengaluru", 12.9716, 77.5946, "Karnataka"),
    ("Nellore", 14.44, 79.99, "Andhra Pradesh"),
    ("Mumbai", 19.076, 72.8777, "Maharashtra"),
    ("Kolkata", 22.5726, 88.3639, "West Bengal"),
    ("Hyderabad", 17.385, 78.4867, "Telangana"),
    ("Surat", 21.17, 72.83, "Gujarat"),
])
def test_known_locations_resolve_to_correct_state(name, lat, lon, state):
    assert geo.state_for_point(lat, lon) == state, name


def test_points_outside_india_are_flagged_not_moved():
    for name, lat, lon in [("Colombo", 6.93, 79.86), ("Kathmandu", 27.70, 85.30),
                           ("Karachi", 24.86, 67.01), ("Lhasa", 29.65, 91.10)]:
        r = geo.resolve(lat, lon)
        assert r["in_india"] is False, name
        assert r["state"] is None
        assert r["zone"] and r["zone"] != "outside India" or name == "?"


def test_no_lat_lon_swap():
    # 80.27, 13.08 (lon,lat given as lat,lon) is in the ocean off Sumatra -> not India
    assert geo.state_for_point(80.2707, 13.0827) is None
    # correct order IS India
    assert geo.state_for_point(13.0827, 80.2707) == "Tamil Nadu"


def test_state_is_never_inferred_from_a_city_name():
    # a city token must not resolve to a state
    assert geo.canonical_state("bangalore") is None
    assert geo.canonical_state("chennai") is None
    # place_label comes from coordinates only
    assert geo.place_label(13.0827, 80.2707) == "Chennai, Tamil Nadu"


def test_regions_expand_to_states():
    east = geo.states_in_region("eastern india")
    assert {"Odisha", "Jharkhand", "West Bengal", "Bihar"} <= east
    assert geo.normalise_region("east india") == "eastern india"
    assert geo.normalise_region("nonsense") is None


def test_match_locations():
    m = geo.match_locations("persistent sources in Odisha last 7 days")
    assert "Odisha" in m["states"]
    m2 = geo.match_locations("summarise eastern india")
    assert m2["region"] == "eastern india" and "Jharkhand" in m2["states"]


def test_audit_report_shape():
    df = pd.DataFrame({"lat": [20.84, 6.93, 26.91], "lon": [85.10, 79.86, 75.79],
                       "feature_id": ["a", "b", "c"]})
    rep = geo.audit_points(df)
    assert rep["plotted"] == 3
    assert rep["in_india"] == 2          # Angul + Jaipur
    assert rep["outside_india"] == 1     # Colombo
    assert rep["lat_min"] == 6.93 and rep["lat_max"] == 26.91
    assert "Sri Lanka" in rep["outside_zones"]
