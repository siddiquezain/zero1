"""
Stage 5 — Assemble training data: VNF labeling oracle + spatial split.

DESIGN DECISION (critical):
  VNF avg_temp is spectral flame temperature (1500–2000 K).
  FIRMS bright_ti4 is 4 µm mixed-pixel brightness temperature (300–500 K).
  These are NOT the same physical quantity. Training on both as 'bt_kelvin'
  would produce a trivially perfect classifier that fails at India inference
  time — all India FIRMS NRT hotspots have bt_kelvin < 500 K, so they'd never
  be predicted as Class A.

  Solution: use VNF as a LABELING ORACLE only.
    1. Build a spatial index of known VNF gas-flare sites.
    2. FIRMS global rows within VNF_ORACLE_KM → label = "A"
    3. Remaining FIRMS global rows → label = "B_candidate"
    4. VNF rows EXCLUDED from training (wrong feature space for inference).

  All training examples are now in FIRMS feature space — the same space used
  at India deployment time.

Training features (all FIRMS-native, available at inference):
    bt_kelvin             4 µm pixel BT (K) — still useful within FIRMS class
    frp_mw                Fire Radiative Power (MW)
    persistence_count     same-1km-cell detections in NRT window
    dist_nearest_facility_km
    agri_season_flag
    day_night_bin         1 = daytime, 0 = nighttime
    acq_month             1–12

Output:
    data/processed/stage5_train.parquet
    data/processed/stage5_val.parquet
    data/processed/stage5_india_holdout.parquet
    data/processed/stage5_labeled.parquet   (train + val combined)
    data/processed/stage5_vnf_oracle.parquet (VNF rows, excluded from training)
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from src.model.split import (
    LeakageError,
    assign_split_by_coords,
    check_no_grid_overlap,
    check_no_india_in_training,
)

log = logging.getLogger(__name__)

FEATURES_PATH = Path("data/processed/features_stage4.parquet")
OUT_DIR = Path("data/processed")
VNF_ORACLE_KM = 5.0
EARTH_RADIUS_KM = 6371.0

TRAIN_FEATURES = [
    "bt_kelvin",
    "frp_mw",
    "persistence_count",
    "dist_nearest_facility_km",
    "agri_season_flag",
    "day_night_bin",
    "acq_month",
]


def _encode_day_night(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["day_night_bin"] = df.get("day_night", pd.Series(dtype=str)).map(
        {"D": 1.0, "N": 0.0}
    )
    return df


def _vnf_oracle_label(
    firms_global: pd.DataFrame,
    vnf_global: pd.DataFrame,
    radius_km: float,
) -> pd.Series:
    """
    For each FIRMS global row, return "A" if within radius_km of any VNF site,
    else "B_candidate".
    """
    oracle_coords_rad = np.radians(vnf_global[["lat", "lon"]].values)
    oracle_tree = BallTree(oracle_coords_rad, metric="haversine")

    query_rad = np.radians(firms_global[["lat", "lon"]].values)
    radius_rad = radius_km / EARTH_RADIUS_KM
    matches = oracle_tree.query_radius(query_rad, r=radius_rad)
    near_mask = np.array([len(m) > 0 for m in matches])

    labels = pd.Series(
        np.where(near_mask, "A", "B_candidate"),
        index=firms_global.index,
        dtype=str,
    )

    n_a = near_mask.sum()
    log.info(
        "VNF oracle (%.1f km): FIRMS Class A = %d / %d (%.2f%%)",
        radius_km, n_a, len(firms_global),
        100 * n_a / len(firms_global) if len(firms_global) else 0,
    )
    if n_a < 100:
        log.warning(
            "Only %d FIRMS Class A examples from VNF oracle. "
            "Consider increasing VNF_ORACLE_KM or adding historical FIRMS archive.",
            n_a,
        )
    return labels


def assemble(
    features_path: Path = FEATURES_PATH,
    vnf_oracle_km: float = VNF_ORACLE_KM,
    out_dir: Path = OUT_DIR,
) -> dict[str, pd.DataFrame]:
    """
    Run Stage 5 assembly. Returns dict with keys train / val / india / all.
    """
    log.info("Loading feature table: %s", features_path)
    df = pd.read_parquet(features_path)
    log.info("Loaded %d rows | splits: %s", len(df), df["split"].value_counts().to_dict())

    # ── Separate VNF (oracle) from FIRMS (deployment-space) ───────────────────
    vnf_mask = df["source_dataset"] == "VNF"
    vnf_rows = df[vnf_mask]
    firms_rows = df[~vnf_mask]

    log.info("VNF rows (oracle, excluded from training): %d", len(vnf_rows))
    log.info("FIRMS rows (training/inference space): %d", len(firms_rows))

    vnf_global = vnf_rows[vnf_rows["split"] == "train_global"]
    log.info("VNF global sites available as oracle: %d", len(vnf_global))

    # ── Separate FIRMS global from FIRMS India holdout ──────────────────────
    firms_global = firms_rows[firms_rows["split"] != "india_holdout"].copy()
    firms_india = firms_rows[firms_rows["split"] == "india_holdout"].copy()
    log.info("FIRMS global rows: %d | FIRMS India holdout: %d",
             len(firms_global), len(firms_india))

    # ── VNF labeling oracle: relabel FIRMS rows near VNF sites ───────────────
    firms_global["label"] = _vnf_oracle_label(firms_global, vnf_global, vnf_oracle_km)

    # ── Encode day/night ─────────────────────────────────────────────────────
    firms_global = _encode_day_night(firms_global)
    firms_india = _encode_day_night(firms_india)

    # ── Spatial grid split (80/20) on labeled FIRMS global rows ──────────────
    # assign_split_by_coords re-runs India check + grid-cell 80/20 split.
    # All firms_global rows should be non-India (confirmed by ingest guards).
    firms_global = assign_split_by_coords(firms_global, lat_col="lat", lon_col="lon")

    train = firms_global[firms_global["split"] == "train_global"].copy()
    val = firms_global[firms_global["split"] == "validation_global"].copy()

    # ── Leakage checks ────────────────────────────────────────────────────────
    check_no_india_in_training(firms_global)
    check_no_grid_overlap(train, val)
    log.info("All leakage checks passed.")

    log.info(
        "Final splits — train: %d (A=%d, B=%d)  val: %d (A=%d, B=%d)  india: %d",
        len(train),
        (train["label"] == "A").sum(),
        (train["label"] == "B_candidate").sum(),
        len(val),
        (val["label"] == "A").sum(),
        (val["label"] == "B_candidate").sum(),
        len(firms_india),
    )

    # ── Save ─────────────────────────────────────────────────────────────────
    out_dir.mkdir(parents=True, exist_ok=True)
    train.to_parquet(out_dir / "stage5_train.parquet", index=False)
    val.to_parquet(out_dir / "stage5_val.parquet", index=False)
    firms_india.to_parquet(out_dir / "stage5_india_holdout.parquet", index=False)

    all_labeled = pd.concat([train, val], ignore_index=True)
    all_labeled.to_parquet(out_dir / "stage5_labeled.parquet", index=False)

    vnf_rows.to_parquet(out_dir / "stage5_vnf_oracle.parquet", index=False)

    log.info("Stage 5 complete. Files saved to %s", out_dir)
    return {"train": train, "val": val, "india": firms_india, "all": all_labeled}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    splits = assemble()

    print("\n=== Stage 5 Summary ===")
    for name, df in splits.items():
        if name == "india":
            print(f"{name}: {len(df)} rows (no label — holdout)")
        else:
            print(f"{name}: {len(df)} rows | labels: {df['label'].value_counts().to_dict()}")
    print(f"\nTraining features: {TRAIN_FEATURES}")
