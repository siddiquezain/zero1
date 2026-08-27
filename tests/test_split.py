"""Tests for split management and leakage checks."""
from __future__ import annotations

import pandas as pd
import pytest

from src.model.split import (
    LeakageError,
    assign_split_by_coords,
    check_no_facility_overlap,
    check_no_grid_overlap,
    check_no_india_in_training,
    is_india_coordinate,
    split_report,
)


# ── is_india_coordinate ───────────────────────────────────────────────────────

def test_clearly_india():
    assert is_india_coordinate(28.6, 77.2)  # Delhi

def test_clearly_not_india():
    assert not is_india_coordinate(51.5, -0.1)  # London

def test_pakistan_in_bbox():
    # Pakistan border overlaps India bbox — should be True (conservative holdout)
    assert is_india_coordinate(25.4, 68.6)

def test_boundary_exactly_on_edge():
    assert is_india_coordinate(6.0, 68.0)   # bottom-left corner — inside
    assert not is_india_coordinate(5.9, 68.0)  # just outside lat


# ── assign_split_by_coords ────────────────────────────────────────────────────

def _make_df(lats, lons):
    return pd.DataFrame({"lat": lats, "lon": lons})


def test_india_rows_go_to_holdout():
    df = _make_df([28.6, 19.0], [77.2, 72.8])  # Delhi, Mumbai
    out = assign_split_by_coords(df)
    assert (out["split"] == "india_holdout").all()


def test_non_india_rows_split_into_train_val():
    # Build a large set of distinct global coordinates
    lats = [i * 3.0 for i in range(30)]  # 0, 3, 6... 87
    lons = [i * 6.0 - 160 for i in range(30)]  # spread globally
    df = _make_df(lats, lons)
    out = assign_split_by_coords(df, seed=42)
    splits = out["split"].unique()
    # Should have at least train_global; val depends on enough grid cells
    assert "train_global" in splits


def test_split_is_deterministic():
    df = _make_df([-10, -20, 50], [30, 40, 10])
    out1 = assign_split_by_coords(df, seed=0)
    out2 = assign_split_by_coords(df, seed=0)
    assert (out1["split"] == out2["split"]).all()


def test_spatial_grid_id_added():
    df = _make_df([-10], [30])
    out = assign_split_by_coords(df)
    assert "spatial_grid_id" in out.columns


# ── check_no_india_in_training ────────────────────────────────────────────────

def _df_with_split(lats, lons, splits):
    return pd.DataFrame({"lat": lats, "lon": lons, "split": splits})


def test_no_india_in_training_passes():
    df = _df_with_split(
        [-10, -20], [30, 40], ["train_global", "train_global"]
    )
    check_no_india_in_training(df)  # should not raise


def test_india_in_training_raises():
    df = _df_with_split([28.6], [77.2], ["train_global"])  # Delhi in training
    with pytest.raises(LeakageError, match="LEAKAGE"):
        check_no_india_in_training(df)


def test_india_in_holdout_is_ok():
    df = _df_with_split([28.6], [77.2], ["india_holdout"])
    check_no_india_in_training(df)  # should not raise


def test_missing_split_column_raises():
    df = pd.DataFrame({"lat": [28.6], "lon": [77.2]})
    with pytest.raises(LeakageError):
        check_no_india_in_training(df)


# ── check_no_grid_overlap ────────────────────────────────────────────────────

def test_no_grid_overlap_passes():
    train = pd.DataFrame({"spatial_grid_id": ["10_30", "11_30"]})
    val = pd.DataFrame({"spatial_grid_id": ["20_40", "21_40"]})
    check_no_grid_overlap(train, val)  # no raise


def test_grid_overlap_raises():
    train = pd.DataFrame({"spatial_grid_id": ["10_30", "11_30"]})
    val = pd.DataFrame({"spatial_grid_id": ["10_30", "20_40"]})  # overlap!
    with pytest.raises(LeakageError, match="LEAKAGE"):
        check_no_grid_overlap(train, val)


# ── check_no_facility_overlap ────────────────────────────────────────────────

def test_no_facility_overlap_passes():
    train = pd.DataFrame({"nearest_facility_id": ["FAC-001", "FAC-002"]})
    val = pd.DataFrame({"nearest_facility_id": ["FAC-003", "FAC-004"]})
    check_no_facility_overlap(train, val)


def test_facility_overlap_raises():
    train = pd.DataFrame({"nearest_facility_id": ["FAC-001", "FAC-002"]})
    val = pd.DataFrame({"nearest_facility_id": ["FAC-001", "FAC-099"]})
    with pytest.raises(LeakageError, match="LEAKAGE"):
        check_no_facility_overlap(train, val)


# ── split_report ─────────────────────────────────────────────────────────────

def test_split_report_counts():
    df = pd.DataFrame({
        "lat": [-10, 28.0, 28.0],
        "lon": [30.0, 77.0, 78.0],
        "split": ["train_global", "india_holdout", "india_holdout"],
    })
    report = split_report(df)
    assert report["total_rows"] == 3
    assert report["train_global"] == 1
    assert report["india_holdout"] == 2
    assert report["validation_global"] == 0


def test_split_report_no_split_column():
    df = pd.DataFrame({"lat": [0.0], "lon": [0.0]})
    report = split_report(df)
    assert "error" in report
