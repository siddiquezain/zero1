"""
Stage 4 — Feature engineering.

Produces a unified feature table from:
  - VNF (Class A — persistent industrial flares, global)
  - FIRMS NRT (hotspots — globally tagged train_global or india_holdout)

Unified feature schema (all sources):
    feature_id           str      unique row ID
    lat / lon            float
    spatial_grid_id      str      1°×1° grid cell (for split grouping)
    grid_key_1km         str      0.01°×0.01° cell (for persistence counting)
    source_dataset       str      VNF | FIRMS_VIIRS_NRT | FIRMS_MODIS_NRT
    split                str      train_global | validation_global | india_holdout
    label                str      A | B_candidate | None

    # Thermal
    bt_kelvin            float    primary brightness temp (K)
    bt_11_kelvin         float    11µm channel (K) — FIRMS only
    frp_mw               float    Fire Radiative Power (MW) — FIRMS only
    avg_temp_K           float    VNF annual mean temp (K) — VNF only

    # Temporal
    acq_date             str
    acq_year             int
    acq_month            int      (NaN for VNF annual summaries)
    day_night            str      D / N / NaN

    # Persistence
    persistence_count    int      same-1km-cell detections in NRT window — FIRMS
    persistence_pct      float    detection-frequency % — VNF (dtc_freq)

    # Facility proximity — FEATURE ONLY, never a label
    dist_nearest_facility_km   float
    nearest_facility_type      str
    nearest_facility_source    str

    # Season
    agri_season_flag     int      1 if month is in known burning season for the region

    # Confidence / quality
    confidence           str

    # VNF-specific (NaN for FIRMS)
    flr_type             str
    flr_volume           float

LEAKAGE SAFEGUARDS:
  - No India rows in train_global (enforced by run_all_checks before saving).
  - Facility proximity is a feature, never used as a label.
  - label column is assigned only from VNF (Class A) or left as B_candidate
    pending land-cover validation (FIRMS global rows).
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from src.ingestion.config import FIRMS_RAW, PROCESSED_DIR, VNF_RAW
from src.model.split import run_all_checks, split_report

log = logging.getLogger(__name__)

# ── Agricultural burning season by month (conservative global list) ───────────
# Maps month → regions where agricultural/controlled burning is likely.
# Used to set agri_season_flag=1; improves Class B discrimination.
_AGRI_MONTHS = {
    10, 11,  # Oct–Nov: Punjab/Haryana kharif residue burning
    4, 5,    # Apr–May: pre-monsoon burning; rabi residue
    7, 8, 9, # Jul–Sep: Amazon / African savannas peak season
    1, 2,    # Jan–Feb: Australian fire season
}


def _agri_flag(month: float | pd.Series) -> int | pd.Series:
    if isinstance(month, pd.Series):
        return month.apply(lambda m: 1 if (not pd.isna(m) and int(m) in _AGRI_MONTHS) else 0)
    return 1 if (not pd.isna(month) and int(month) in _AGRI_MONTHS) else 0


# ── Grid keys ─────────────────────────────────────────────────────────────────

def _spatial_grid_id(lat: pd.Series, lon: pd.Series) -> pd.Series:
    """1°×1° grid cell string for split grouping."""
    return lat.floordiv(1.0).astype(int).astype(str) + "_" + lon.floordiv(1.0).astype(int).astype(str)


def _grid_key_1km(lat: pd.Series, lon: pd.Series) -> pd.Series:
    """~1 km grid cell key (0.01° resolution) for persistence counting."""
    return (lat / 0.01).round().astype(int).astype(str) + "_" + (lon / 0.01).round().astype(int).astype(str)


# ── Persistence count (FIRMS) ─────────────────────────────────────────────────

def _compute_persistence(df: pd.DataFrame) -> pd.Series:
    """
    Count how many times each ~1 km grid cell was detected within the loaded
    NRT window (5 days). Higher = more persistent source.

    Ponytail: simple groupby count — fast, no spatial indexing needed here.
    """
    if "grid_key_1km" not in df.columns:
        df = df.copy()
        df["grid_key_1km"] = _grid_key_1km(df["lat"], df["lon"])
    return df.groupby("grid_key_1km")["grid_key_1km"].transform("count")


# ── Facility proximity via BallTree (haversine) ───────────────────────────────

def _build_facility_index(facilities: pd.DataFrame):
    """Build a BallTree on facility lat/lon for fast nearest-neighbour queries."""
    try:
        from sklearn.neighbors import BallTree
    except ImportError:
        raise ImportError("scikit-learn required for facility proximity. pip install scikit-learn")

    coords_rad = np.radians(facilities[["lat", "lon"]].values)
    tree = BallTree(coords_rad, metric="haversine")
    return tree


def _query_nearest_facility(
    lats: pd.Series,
    lons: pd.Series,
    facilities: pd.DataFrame,
    tree,
    earth_radius_km: float = 6371.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Return (dist_km, facility_type, facility_source) for nearest facility.
    Efficient: one BallTree query for all points.
    """
    query_rad = np.radians(np.column_stack([lats.values, lons.values]))
    dists_rad, idxs = tree.query(query_rad, k=1)
    dists_km = dists_rad[:, 0] * earth_radius_km
    fac_rows = facilities.iloc[idxs[:, 0]]

    return (
        pd.Series(dists_km, index=lats.index),
        pd.Series(fac_rows["facility_type"].values, index=lats.index),
        pd.Series(fac_rows["source"].values, index=lats.index),
    )


# ── VNF → features ───────────────────────────────────────────────────────────

def features_from_vnf(vnf: pd.DataFrame, facilities: pd.DataFrame, tree) -> pd.DataFrame:
    """Map VNF columns to the unified feature schema."""
    lat, lon = vnf["latitude"], vnf["longitude"]
    dist_km, fac_type, fac_src = _query_nearest_facility(lat, lon, facilities, tree)

    df = pd.DataFrame({
        "feature_id": [f"VNF-{uuid.uuid4().hex[:8]}" for _ in range(len(vnf))],
        "lat": lat.values,
        "lon": lon.values,
        "spatial_grid_id": _spatial_grid_id(lat, lon).values,
        "grid_key_1km": _grid_key_1km(lat, lon).values,
        "source_dataset": "VNF",
        "split": vnf["split"].values,
        "label": "A",  # Pre-labelled by ORNL — DO NOT change

        # Thermal
        "bt_kelvin": vnf["avg_temp"].values,         # Annual mean, K
        "bt_11_kelvin": np.nan,
        "frp_mw": np.nan,                            # VNF has flr_volume, not FRP
        "avg_temp_K": vnf["avg_temp"].values,

        # Temporal
        "acq_date": None,
        "acq_year": vnf["year"].values,
        "acq_month": np.nan,
        "day_night": None,

        # Persistence — dtc_freq is % of clear-sky obs with a detected flare
        "persistence_count": np.nan,
        "persistence_pct": vnf["dtc_freq"].values,

        # Facility proximity
        "dist_nearest_facility_km": dist_km.values,
        "nearest_facility_type": fac_type.values,
        "nearest_facility_source": fac_src.values,

        # Season
        "agri_season_flag": 0,  # Gas flares are not seasonal

        # Quality
        "confidence": None,

        # VNF-specific
        "flr_type": vnf["flr_type"].values,
        "flr_volume": vnf["flr_volume"].values,
    })

    log.info("VNF features: %d rows (label=A, split distribution: %s)",
             len(df), df["split"].value_counts().to_dict())
    return df


# ── FIRMS → features ─────────────────────────────────────────────────────────

def _firms_bt_col(df: pd.DataFrame) -> str:
    """Return the brightness temperature column name for this FIRMS product."""
    if "bright_ti4" in df.columns:
        return "bright_ti4"
    if "brightness" in df.columns:
        return "brightness"
    raise KeyError(f"No recognised BT column in FIRMS data. Columns: {list(df.columns)}")


def _firms_bt11_col(df: pd.DataFrame) -> str | None:
    if "bright_ti5" in df.columns:
        return "bright_ti5"
    if "bright_t31" in df.columns:
        return "bright_t31"
    return None


def _source_name(df: pd.DataFrame) -> str:
    if "bright_ti4" in df.columns:
        return "FIRMS_VIIRS_NRT"
    return "FIRMS_MODIS_NRT"


def features_from_firms(df: pd.DataFrame, facilities: pd.DataFrame, tree,
                        persistence_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Map a single FIRMS parquet (VIIRS or MODIS) to the unified feature schema.

    persistence_df: optional DataFrame with pre-computed persistence counts
                    (if None, computed from df itself — only counts within this file).
    """
    lat = df["latitude"]
    lon = df["longitude"]

    bt_col = _firms_bt_col(df)
    bt11_col = _firms_bt11_col(df)

    acq_date = pd.to_datetime(df["acq_date"])

    # Grid keys
    grid_1km = _grid_key_1km(lat, lon)

    # Persistence count within this NRT window
    if persistence_df is not None:
        # Use pre-computed cross-file persistence
        persist_count = grid_1km.map(
            persistence_df.set_index("grid_key_1km")["persistence_count"]
        ).fillna(1)
    else:
        # Count within this file only (lower bound — accurate if single region)
        persist_counts = df.copy()
        persist_counts["grid_key_1km"] = grid_1km
        persist_map = persist_counts.groupby("grid_key_1km").size()
        persist_count = grid_1km.map(persist_map).fillna(1)

    # Facility proximity
    dist_km, fac_type, fac_src = _query_nearest_facility(lat, lon, facilities, tree)

    # Agri-season flag
    agri = _agri_flag(acq_date.dt.month)

    # Confidence: normalise to string
    conf = df["confidence"].astype(str) if "confidence" in df.columns else pd.Series([None] * len(df))

    # Label: FIRMS global rows are B_candidate — pending land-cover validation.
    # India rows have no label yet (holdout — not used in training).
    labels = df["split"].map({
        "train_global": "B_candidate",
        "validation_global": "B_candidate",
        "india_holdout": None,
    })

    out = pd.DataFrame({
        "feature_id": [f"FIRMS-{uuid.uuid4().hex[:8]}" for _ in range(len(df))],
        "lat": lat.values,
        "lon": lon.values,
        "spatial_grid_id": _spatial_grid_id(lat, lon).values,
        "grid_key_1km": grid_1km.values,
        "source_dataset": _source_name(df),
        "split": df["split"].values,
        "label": labels.values,

        # Thermal
        "bt_kelvin": df[bt_col].values,
        "bt_11_kelvin": df[bt11_col].values if bt11_col else np.nan,
        "frp_mw": df["frp"].values if "frp" in df.columns else np.nan,
        "avg_temp_K": np.nan,  # VNF-only

        # Temporal
        "acq_date": df["acq_date"].values,
        "acq_year": acq_date.dt.year.values,
        "acq_month": acq_date.dt.month.values,
        "day_night": df["daynight"].values if "daynight" in df.columns else None,

        # Persistence
        "persistence_count": persist_count.values,
        "persistence_pct": np.nan,  # VNF-only

        # Facility proximity
        "dist_nearest_facility_km": dist_km.values,
        "nearest_facility_type": fac_type.values,
        "nearest_facility_source": fac_src.values,

        # Season
        "agri_season_flag": agri.values,

        # Quality
        "confidence": conf.values,

        # VNF-specific (NaN for FIRMS)
        "flr_type": None,
        "flr_volume": np.nan,
    })

    log.info("FIRMS features (%s): %d rows (label distribution: %s)",
             _source_name(df), len(out), out["label"].value_counts(dropna=False).to_dict())
    return out


# ── Cross-file persistence (all FIRMS combined) ───────────────────────────────

def compute_global_persistence(firms_parquets: list[Path]) -> pd.DataFrame:
    """
    Load all FIRMS parquet files and return a DataFrame with per-1km-cell
    persistence counts across the full NRT window.

    This is the correct way to count persistence — counting within one file
    (one region, 5 days) underestimates for overlapping orbital swaths.
    """
    pieces = []
    for p in firms_parquets:
        df = pd.read_parquet(p, columns=["latitude", "longitude"])
        df["grid_key_1km"] = _grid_key_1km(df["latitude"], df["longitude"])
        pieces.append(df[["grid_key_1km"]])

    combined = pd.concat(pieces, ignore_index=True)
    counts = combined.groupby("grid_key_1km").size().reset_index(name="persistence_count")
    log.info("Persistence index: %d unique 1-km grid cells", len(counts))
    return counts


# ── Main pipeline ────────────────────────────────────────────────────────────

def build_feature_table(
    vnf_parquet: Path = VNF_RAW / "vnf_combined.parquet",
    firms_dir: Path = FIRMS_RAW,
    facility_parquet: Path = PROCESSED_DIR / "facilities.parquet",
    out_path: Path = PROCESSED_DIR / "features_stage4.parquet",
) -> pd.DataFrame:
    """
    Build the unified feature table and save it to parquet.

    Runs full leakage checks before saving.
    """
    # ── Load facilities ──────────────────────────────────────────────────────
    log.info("Loading facility table …")
    facilities = pd.read_parquet(facility_parquet)
    log.info("Facilities: %d rows", len(facilities))
    tree = _build_facility_index(facilities)

    # ── Load VNF ──────────────────────────────────────────────────────────────
    log.info("Loading VNF …")
    vnf = pd.read_parquet(vnf_parquet)
    vnf_features = features_from_vnf(vnf, facilities, tree)

    # ── Load FIRMS — compute cross-file persistence first ───────────────────
    firms_parquets = sorted(firms_dir.glob("*.parquet"))
    if not firms_parquets:
        log.warning("No FIRMS parquet files found in %s.", firms_dir)
        firms_features = pd.DataFrame()
    else:
        log.info("Computing cross-file persistence index …")
        persistence_df = compute_global_persistence(firms_parquets)

        log.info("Processing %d FIRMS files …", len(firms_parquets))
        firms_parts = []
        for p in firms_parquets:
            df = pd.read_parquet(p)
            firms_parts.append(features_from_firms(df, facilities, tree, persistence_df))
        firms_features = pd.concat(firms_parts, ignore_index=True)

    # ── Combine ───────────────────────────────────────────────────────────────
    parts = [vnf_features]
    if not firms_features.empty:
        parts.append(firms_features)
    combined = pd.concat(parts, ignore_index=True)

    log.info("Combined feature table: %d rows", len(combined))
    log.info("Label distribution: %s", combined["label"].value_counts(dropna=False).to_dict())
    log.info("Split distribution: %s", combined["split"].value_counts().to_dict())

    # ── Leakage checks ────────────────────────────────────────────────────────
    log.info("Running leakage checks …")
    run_all_checks(combined)
    log.info("Leakage checks passed.")

    # ── Save ─────────────────────────────────────────────────────────────────
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(out_path, index=False)
    log.info("Feature table saved → %s (%d rows)", out_path, len(combined))

    return combined


if __name__ == "__main__":
    import json
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    df = build_feature_table()

    print("\n=== Stage 4 Feature Table Summary ===")
    print(f"Total rows: {len(df):,}")
    print(f"\nSplit distribution:")
    print(df["split"].value_counts())
    print(f"\nLabel distribution:")
    print(df["label"].value_counts(dropna=False))
    print(f"\nSource distribution:")
    print(df["source_dataset"].value_counts())
    print(f"\nBrightness temp (bt_kelvin) stats:")
    print(df["bt_kelvin"].describe())
    print(f"\nFRP (frp_mw) stats:")
    print(df["frp_mw"].describe())
    print(f"\nPersistence stats:")
    print(f"  persistence_pct (VNF): {df['persistence_pct'].describe()}")
    print(f"  persistence_count (FIRMS): {df['persistence_count'].describe()}")
    print(f"\nFacility proximity:")
    print(f"  dist_nearest_facility_km: {df['dist_nearest_facility_km'].describe()}")
    print(f"  nearest_facility_type top-5: {df['nearest_facility_type'].value_counts().head()}")
    print(f"\nAgri-season_flag: {df['agri_season_flag'].value_counts().to_dict()}")
    print(f"\nFeature columns: {list(df.columns)}")
