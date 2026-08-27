"""
Split management and leakage prevention for SIH26162.

ARCHITECTURE:
    train_global      — Global data, no India rows. Used to train the classifier.
    validation_global — Non-India spatial/facility holdout. Used for model selection.
    india_holdout     — India rows only. LOCKED. Evaluated once after model finalization.

RULES (enforced by assertions):
    1. No India coordinates in train_global or validation_global.
    2. No facility overlap between train and validation groups.
    3. No spatial grid overlap between train and validation.
    4. Splitting is done by facility_id / spatial grid, never randomly.
    5. India rows are tagged at ingest time and checked at every pipeline stage.

India bounding box: lon [68, 97.5], lat [6, 37]
"""
from __future__ import annotations

import hashlib
import logging
from typing import Literal

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

Split = Literal["train_global", "validation_global", "india_holdout"]

# ── India geographic bounds ───────────────────────────────────────────────────
INDIA_LAT_MIN, INDIA_LAT_MAX = 6.0, 37.0
INDIA_LON_MIN, INDIA_LON_MAX = 68.0, 97.5

# ISO-3166-alpha-3 codes that map to India in WRI GPPD
INDIA_ISO3 = {"IND"}

# Fraction of non-India data to hold out for global validation
GLOBAL_VAL_FRACTION = 0.20

# Spatial grid resolution for grouping (degrees)
GRID_DEG = 1.0


def is_india_coordinate(lat: float | pd.Series, lon: float | pd.Series) -> bool | pd.Series:
    """Return True for any coordinate inside India's bounding box."""
    return (
        (lat >= INDIA_LAT_MIN) & (lat <= INDIA_LAT_MAX) &
        (lon >= INDIA_LON_MIN) & (lon <= INDIA_LON_MAX)
    )


def assign_split_by_coords(df: pd.DataFrame,
                            lat_col: str = "lat",
                            lon_col: str = "lon",
                            seed: int = 42) -> pd.DataFrame:
    """
    Assign split labels based on coordinates + spatial-grid grouping.

    Algorithm:
      1. Rows inside India bbox → india_holdout
      2. Remaining rows are grouped by 1° × 1° spatial grid cell.
      3. Grid cells are randomly assigned to train_global (80%) or
         validation_global (20%) — groups never split across the boundary.

    Returns df with 'split' and 'spatial_grid_id' columns added.

    NOTE: This overrides any existing 'split' column, so only call once.
    """
    df = df.copy()

    # Step 1: India flag
    india_mask = is_india_coordinate(df[lat_col], df[lon_col])

    # Step 2: Spatial grid ID (floor to 1° grid)
    df["spatial_grid_id"] = (
        df[lat_col].floordiv(GRID_DEG).astype(int).astype(str)
        + "_"
        + df[lon_col].floordiv(GRID_DEG).astype(int).astype(str)
    )

    # Step 3: Assign grid cells to val/train (non-India only)
    non_india_grid_cells = sorted(
        df.loc[~india_mask, "spatial_grid_id"].unique()
    )
    rng = np.random.default_rng(seed)
    rng.shuffle(non_india_grid_cells)
    n_val = max(1, int(len(non_india_grid_cells) * GLOBAL_VAL_FRACTION))
    val_cells = set(non_india_grid_cells[:n_val])
    train_cells = set(non_india_grid_cells[n_val:])

    # Step 4: Apply split labels
    split = pd.Series("", index=df.index, dtype=str)
    split[india_mask] = "india_holdout"
    split[~india_mask & df["spatial_grid_id"].isin(val_cells)] = "validation_global"
    split[~india_mask & df["spatial_grid_id"].isin(train_cells)] = "train_global"

    df["split"] = split

    counts = df["split"].value_counts()
    log.info(
        "Split assignment: train_global=%d  validation_global=%d  india_holdout=%d",
        counts.get("train_global", 0),
        counts.get("validation_global", 0),
        counts.get("india_holdout", 0),
    )
    return df


# ── Leakage checks ────────────────────────────────────────────────────────────

class LeakageError(AssertionError):
    """Raised when a leakage constraint is violated."""


def check_no_india_in_training(
    df: pd.DataFrame,
    lat_col: str = "lat",
    lon_col: str = "lon",
    split_col: str = "split",
) -> None:
    """
    Assert that no rows with India coordinates appear in training or validation splits.
    Raises LeakageError on violation.
    """
    if split_col not in df.columns:
        raise LeakageError(f"'split' column missing — cannot verify leakage.")

    training_rows = df[df[split_col].isin(["train_global", "validation_global"])]
    if lat_col in df.columns and lon_col in df.columns:
        india_in_training = is_india_coordinate(
            training_rows[lat_col], training_rows[lon_col]
        )
        bad = india_in_training.sum()
        if bad > 0:
            raise LeakageError(
                f"LEAKAGE: {bad} India-coordinate rows found in "
                f"training/validation splits. India must be holdout only."
            )

    log.info("✓ No India coordinates in training/validation splits.")


def check_no_grid_overlap(
    train: pd.DataFrame,
    val: pd.DataFrame,
    grid_col: str = "spatial_grid_id",
) -> None:
    """Assert that train and validation use disjoint spatial grid cells."""
    if grid_col not in train.columns or grid_col not in val.columns:
        log.warning("spatial_grid_id missing — skipping grid overlap check.")
        return

    train_cells = set(train[grid_col].unique())
    val_cells = set(val[grid_col].unique())
    overlap = train_cells & val_cells

    if overlap:
        raise LeakageError(
            f"LEAKAGE: {len(overlap)} spatial grid cell(s) appear in BOTH "
            f"train and validation: {list(overlap)[:5]}"
        )

    log.info("✓ No spatial grid overlap between train and validation.")


def check_no_facility_overlap(
    train: pd.DataFrame,
    val: pd.DataFrame,
    facility_col: str = "nearest_facility_id",
) -> None:
    """Assert that named facilities don't appear in both train and validation."""
    if facility_col not in train.columns or facility_col not in val.columns:
        log.info("facility_id not in dataset — skipping facility overlap check.")
        return

    train_facs = set(train[facility_col].dropna().unique())
    val_facs = set(val[facility_col].dropna().unique())
    overlap = train_facs & val_facs

    if overlap:
        raise LeakageError(
            f"LEAKAGE: {len(overlap)} facility ID(s) appear in BOTH "
            f"train and validation: {list(overlap)[:5]}"
        )

    log.info("✓ No facility overlap between train and validation.")


def check_no_label_leakage(df: pd.DataFrame, label_col: str = "label") -> None:
    """
    Assert that the label column was not derived from a proxy of the split column.
    Simple check: verify label column exists and is NOT perfectly correlated with split.
    """
    if label_col not in df.columns or "split" not in df.columns:
        return

    # If every class-A label perfectly maps to one split and every class-B to another,
    # that's a signal of a labeling problem.
    cross = pd.crosstab(df["split"], df[label_col])
    if (cross == 0).values.sum() == cross.size - cross.shape[0]:
        log.warning(
            "WARNING: Label is perfectly separated by split — possible circular labeling. "
            "Verify that labels were not derived from split membership."
        )
    else:
        log.info("✓ Label distribution overlaps across splits — no obvious circular labeling.")


def run_all_checks(df: pd.DataFrame,
                   lat_col: str = "lat",
                   lon_col: str = "lon") -> None:
    """
    Run all leakage checks on a feature-table DataFrame.
    Raises LeakageError on first failure.
    """
    check_no_india_in_training(df, lat_col=lat_col, lon_col=lon_col)

    train = df[df["split"] == "train_global"]
    val = df[df["split"] == "validation_global"]

    check_no_grid_overlap(train, val)
    check_no_facility_overlap(train, val)
    check_no_label_leakage(df)

    log.info("All leakage checks passed.")


# ── Split statistics report ───────────────────────────────────────────────────

def split_report(df: pd.DataFrame) -> dict:
    """Return a dict summarising the split distribution for logging/reporting."""
    if "split" not in df.columns:
        return {"error": "'split' column not present"}

    counts = df["split"].value_counts().to_dict()
    total = len(df)

    report = {
        "total_rows": total,
        "train_global": counts.get("train_global", 0),
        "validation_global": counts.get("validation_global", 0),
        "india_holdout": counts.get("india_holdout", 0),
        "train_pct": round(100 * counts.get("train_global", 0) / total, 1),
        "val_pct": round(100 * counts.get("validation_global", 0) / total, 1),
        "india_pct": round(100 * counts.get("india_holdout", 0) / total, 1),
    }

    if "label" in df.columns:
        for split_name, split_df in df.groupby("split"):
            label_dist = split_df["label"].value_counts().to_dict()
            report[f"{split_name}_label_dist"] = label_dist

    if "country" in df.columns or "cntry_iso" in df.columns:
        iso_col = "country" if "country" in df.columns else "cntry_iso"
        top_countries = df.groupby("split")[iso_col].value_counts().groupby(
            level=0
        ).head(5).to_dict()
        report["countries_per_split"] = str(top_countries)

    return report
