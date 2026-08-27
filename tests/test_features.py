"""Tests for feature engineering — Stage 4."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.features.engineer import (
    _agri_flag,
    _grid_key_1km,
    _spatial_grid_id,
    _compute_persistence,
    features_from_vnf,
    features_from_firms,
)


# ── Grid helpers ──────────────────────────────────────────────────────────────

def test_spatial_grid_id_1deg():
    lat = pd.Series([28.6, -10.3])
    lon = pd.Series([77.2, 30.7])
    ids = _spatial_grid_id(lat, lon)
    assert ids.iloc[0] == "28_77"
    assert ids.iloc[1] == "-11_30"


def test_grid_key_1km_resolution():
    lat = pd.Series([28.60, 28.61])   # ~1.1 km apart
    lon = pd.Series([77.20, 77.20])
    keys = _grid_key_1km(lat, lon)
    # 28.60 / 0.01 = 2860; 28.61 / 0.01 = 2861
    assert keys.iloc[0] != keys.iloc[1]


def test_grid_key_1km_same_cell():
    lat = pd.Series([28.601, 28.603])  # ~222m apart — same 1km cell
    lon = pd.Series([77.200, 77.201])
    keys = _grid_key_1km(lat, lon)
    assert keys.iloc[0] == keys.iloc[1]


# ── Agri-season flag ─────────────────────────────────────────────────────────

def test_agri_flag_october():
    assert _agri_flag(10) == 1   # Punjab stubble season

def test_agri_flag_january():
    assert _agri_flag(1) == 1    # Australian fire season

def test_agri_flag_march():
    assert _agri_flag(3) == 0    # Not a typical season

def test_agri_flag_series():
    months = pd.Series([10, 3, 8, 6])
    flags = _agri_flag(months)
    assert flags.tolist() == [1, 0, 1, 0]


# ── Persistence ───────────────────────────────────────────────────────────────

def _firms_df(lats, lons, dates=None):
    n = len(lats)
    return pd.DataFrame({
        "latitude": lats,
        "longitude": lons,
        "bright_ti4": [350.0] * n,
        "bright_ti5": [290.0] * n,
        "frp": [5.0] * n,
        "acq_date": dates or ["2026-08-23"] * n,
        "acq_time": [700] * n,
        "satellite": ["N"] * n,
        "instrument": ["VIIRS"] * n,
        "confidence": ["n"] * n,
        "version": ["2.0NRT"] * n,
        "daynight": ["D"] * n,
        "split": ["train_global"] * n,
        "region": ["global"] * n,
    })


def test_persistence_single_detection():
    df = _firms_df([-10.0], [30.0])
    df["grid_key_1km"] = _grid_key_1km(df["latitude"], df["longitude"])
    counts = _compute_persistence(df)
    assert counts.iloc[0] == 1


def test_persistence_same_cell_multiple():
    # Two detections at the same ~1km cell
    df = _firms_df([-10.001, -10.002], [30.001, 30.002])
    df["grid_key_1km"] = _grid_key_1km(df["latitude"], df["longitude"])
    counts = _compute_persistence(df)
    assert counts.iloc[0] == 2
    assert counts.iloc[1] == 2


def test_persistence_different_cells():
    df = _firms_df([-10.0, -11.0], [30.0, 30.0])
    df["grid_key_1km"] = _grid_key_1km(df["latitude"], df["longitude"])
    counts = _compute_persistence(df)
    assert counts.iloc[0] == 1
    assert counts.iloc[1] == 1


# ── features_from_firms ───────────────────────────────────────────────────────

def _dummy_facilities():
    return pd.DataFrame({
        "lat": [-9.0, 30.0, 50.0],
        "lon": [30.0, 70.0, -100.0],
        "facility_type": ["Coal", "Gas", "Solar"],
        "source": ["GPPD", "GPPD", "GPPD"],
    })


def _build_tree(fac):
    from sklearn.neighbors import BallTree
    import numpy as np
    coords = np.radians(fac[["lat", "lon"]].values)
    return BallTree(coords, metric="haversine")


def test_features_from_firms_schema():
    df = _firms_df([-10.0, -11.0], [30.0, 30.5])
    fac = _dummy_facilities()
    tree = _build_tree(fac)
    out = features_from_firms(df, fac, tree)
    required = ["feature_id", "lat", "lon", "bt_kelvin", "frp_mw",
                "persistence_count", "dist_nearest_facility_km",
                "split", "label", "source_dataset"]
    for col in required:
        assert col in out.columns, f"Missing column: {col}"


def test_features_from_firms_bt_kelvin():
    df = _firms_df([-10.0], [30.0])
    fac = _dummy_facilities()
    tree = _build_tree(fac)
    out = features_from_firms(df, fac, tree)
    assert out["bt_kelvin"].iloc[0] == 350.0


def test_features_from_firms_india_holdout_has_no_label():
    df = _firms_df([-10.0], [30.0])
    df["split"] = "india_holdout"
    fac = _dummy_facilities()
    tree = _build_tree(fac)
    out = features_from_firms(df, fac, tree)
    assert pd.isna(out["label"].iloc[0])


def test_features_from_firms_global_gets_B_candidate():
    df = _firms_df([-10.0], [30.0])  # split=train_global by default
    fac = _dummy_facilities()
    tree = _build_tree(fac)
    out = features_from_firms(df, fac, tree)
    assert out["label"].iloc[0] == "B_candidate"


def test_features_from_firms_facility_distance_positive():
    df = _firms_df([-10.0], [30.0])
    fac = _dummy_facilities()
    tree = _build_tree(fac)
    out = features_from_firms(df, fac, tree)
    assert out["dist_nearest_facility_km"].iloc[0] > 0


# ── features_from_vnf ────────────────────────────────────────────────────────

def _dummy_vnf():
    return pd.DataFrame({
        "latitude": [-10.0, 30.0],
        "longitude": [30.0, 60.0],
        "avg_temp": [1800.0, 1650.0],
        "dtc_freq": [95.0, 70.0],
        "flr_type": ["upstream", "refinery"],
        "flr_volume": [1.2, 0.8],
        "year": [2019, 2019],
        "source_dataset": ["VNF", "VNF"],
        "label": ["A", "A"],
        "split": ["train_global", "train_global"],
        "region": ["global", "global"],
    })


def test_features_from_vnf_label_is_A():
    vnf = _dummy_vnf()
    fac = _dummy_facilities()
    tree = _build_tree(fac)
    out = features_from_vnf(vnf, fac, tree)
    assert (out["label"] == "A").all()


def test_features_from_vnf_bt_kelvin_from_avg_temp():
    vnf = _dummy_vnf()
    fac = _dummy_facilities()
    tree = _build_tree(fac)
    out = features_from_vnf(vnf, fac, tree)
    assert out["bt_kelvin"].iloc[0] == 1800.0


def test_features_from_vnf_agri_flag_zero():
    vnf = _dummy_vnf()
    fac = _dummy_facilities()
    tree = _build_tree(fac)
    out = features_from_vnf(vnf, fac, tree)
    assert (out["agri_season_flag"] == 0).all()
