"""
Live FIRMS refresh for the dashboard.

Fetches fresh NRT hotspot data for India and re-scores through the existing
Random Forest pipeline. Called at dashboard startup when data is stale.

Skips silently if:
  - FIRMS_MAP_KEY env var is not set
  - stage6_india_scores.parquet is younger than max_age_hours (default 2h)
  - FIRMS API returns empty / errors

Falls back to existing data on any failure — the dashboard always has data.

# ponytail: synchronous refresh blocks startup ~10-60s; add async thread when
# startup latency becomes a complaint (needs st.context for thread-safe rerun).
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from src.ingestion.config import (
    FIRMS_MAP_KEY,
    FIRMS_NRT_DAYS,
)

_NRT_DAYS = min(FIRMS_NRT_DAYS, 5)  # FIRMS NRT API hard cap is 5 days
from src.ingestion.firms import fetch_nrt_area

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_SCORES_PATH = _ROOT / "data/processed/stage6_india_scores.parquet"
_FACILITIES_PATH = _ROOT / "data/processed/facilities.parquet"
_MODEL_PATH = _ROOT / "data/processed/stage6_model.joblib"
_ANOMALY_THRESHOLD = 0.55
_AGRI_MONTHS = {1, 2, 4, 5, 7, 8, 9, 10, 11}

_TRAIN_FEATURES = [
    "bt_kelvin",
    "frp_mw",
    "persistence_count",
    "dist_nearest_facility_km",
    "agri_season_flag",
    "day_night_bin",
    "acq_month",
]


def _age_hours() -> float:
    if not _SCORES_PATH.exists():
        return float("inf")
    return (time.time() - _SCORES_PATH.stat().st_mtime) / 3600


def _bt_col(df: pd.DataFrame) -> str:
    if "bright_ti4" in df.columns:
        return "bright_ti4"
    if "brightness" in df.columns:
        return "brightness"
    raise KeyError(f"No brightness column in FIRMS data; cols: {list(df.columns)}")


def _engineer(firms_raw: pd.DataFrame, facilities: pd.DataFrame, tree: BallTree) -> pd.DataFrame:
    """Minimal feature table for India-only FIRMS rows (no global pipeline needed)."""
    df = firms_raw.copy()

    lat = df["latitude"].values.astype(float)
    lon = df["longitude"].values.astype(float)

    # ~1 km grid key for persistence counting
    grid_key = (np.round(lat / 0.01).astype(int).astype(str) + "_" +
                np.round(lon / 0.01).astype(int).astype(str))
    grid_series = pd.Series(grid_key)
    counts = grid_series.groupby(grid_series).transform("count").values

    # Facility proximity
    query_rad = np.radians(np.column_stack([lat, lon]))
    dists_rad, idxs = tree.query(query_rad, k=1)
    dist_km = dists_rad[:, 0] * 6371.0
    fac_type = facilities.iloc[idxs[:, 0]]["facility_type"].values

    # Temporal
    acq_date = pd.to_datetime(df["acq_date"])
    acq_month = acq_date.dt.month.values
    agri_flag = np.isin(acq_month, list(_AGRI_MONTHS)).astype(int)

    # day_night: D / N string → bin for model; keep string for risk engine
    day_night_str = df["daynight"].values if "daynight" in df.columns else np.full(len(df), "")
    day_night_bin = (pd.Series(day_night_str) == "N").astype(float).values

    bt = df[_bt_col(df)].values.astype(float)
    frp = df["frp"].values.astype(float) if "frp" in df.columns else np.full(len(df), np.nan)
    conf = df["confidence"].astype(str).values if "confidence" in df.columns else np.full(len(df), "n")

    return pd.DataFrame({
        "lat": lat,
        "lon": lon,
        "acq_date": df["acq_date"].values,
        "acq_month": acq_month,
        "day_night": day_night_str,
        "day_night_bin": day_night_bin,
        "bt_kelvin": bt,
        "frp_mw": frp,
        "persistence_count": counts,
        "dist_nearest_facility_km": dist_km,
        "nearest_facility_type": fac_type,
        "agri_season_flag": agri_flag,
        "confidence": conf,
    })


def maybe_refresh(max_age_hours: float = 2.0) -> dict:
    """
    Fetch fresh FIRMS NRT data for India and re-score if data is stale.

    Returns a status dict always (never raises). Caller should clear Streamlit
    cache when status == "refreshed".
    """
    age = _age_hours()

    if age < max_age_hours:
        return {"status": "fresh", "age_hours": round(age, 1)}
    if not FIRMS_MAP_KEY:
        return {"status": "no_key", "age_hours": round(age, 1)}
    if not _MODEL_PATH.exists():
        return {"status": "no_model", "age_hours": round(age, 1)}
    if not _FACILITIES_PATH.exists():
        return {"status": "no_facilities", "age_hours": round(age, 1)}

    log.info("FIRMS data is %.1f h old — fetching live NRT update …", age)

    try:
        # 1. Fetch both products, combine
        pieces = []
        for product in ("VIIRS_SNPP_NRT", "MODIS_NRT"):
            df = fetch_nrt_area(product, _NRT_DAYS)
            if df is not None and len(df) > 0:
                pieces.append(df)

        if not pieces:
            log.warning("FIRMS returned no data — keeping existing snapshot")
            return {"status": "no_data", "age_hours": round(age, 1)}

        firms_raw = pd.concat(pieces, ignore_index=True)
        log.info("Combined raw rows: %d", len(firms_raw))

        # 2. Feature engineering (India-only, lightweight)
        facilities = pd.read_parquet(_FACILITIES_PATH)
        tree = BallTree(np.radians(facilities[["lat", "lon"]].values), metric="haversine")
        feats = _engineer(firms_raw, facilities, tree)

        # 3. ML inference
        pipe = joblib.load(_MODEL_PATH)
        X = feats[_TRAIN_FEATURES].to_numpy(dtype=float, na_value=np.nan)
        y_pred = pipe.predict(X)
        y_prob = pipe.predict_proba(X)

        feats["predicted_label"] = y_pred
        for i, cls in enumerate(pipe.classes_):
            col = f"prob_{cls}"
            feats[col] = y_prob[:, i]
        feats["max_prob"] = y_prob.max(axis=1)
        feats["anomaly_flag"] = (feats["max_prob"] < _ANOMALY_THRESHOLD).astype(int)
        # Alias for alert_store compatibility
        if "prob_B_candidate" not in feats.columns and "prob_B" in feats.columns:
            feats["prob_B_candidate"] = feats["prob_B"]

        # 4. Write scores (replaces the static snapshot)
        _SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
        feats.to_parquet(_SCORES_PATH, index=False)
        log.info("Wrote %d rows → %s", len(feats), _SCORES_PATH.name)

        # 5. Re-seed alert store from fresh scores
        from src.alerting import pipeline
        result = pipeline.run(fresh=True)

        return {
            "status": "refreshed",
            "rows": len(feats),
            "age_hours": round(age, 1),
            "inserted": result["inserted"],
        }

    except Exception as exc:  # noqa: BLE001
        log.error("Live refresh failed (%s) — existing data unchanged", exc)
        return {"status": "error", "error": str(exc), "age_hours": round(age, 1)}
