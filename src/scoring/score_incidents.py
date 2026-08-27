"""
Stage 7 — Score confirmed India incidents through the trained classifier.

Context: The 30 confirmed incidents are dated 2019–2023. Historical FIRMS
archive is not yet downloaded, so we cannot retrieve the exact FIRMS detection
at the incident location and time.

What we CAN compute for each incident location:
    dist_nearest_facility_km   — from facilities.parquet BallTree
    agri_season_flag           — from incident date month
    acq_month                  — from incident date month

Thermal features (bt_kelvin, frp_mw, persistence_count, day_night_bin) are
set to NaN. The model pipeline's SimpleImputer fills them with training-set
medians, so scoring still works — but predictions lean on geographic/seasonal
features, not thermal signatures.

Expected outcome (per context.md): confirmed industrial fire incidents should
land in neither Class A (persistent flare) nor Class B (natural fire) cleanly,
because industrial fires are transient anomalies — different from both.
Anomaly flag = max_prob < 0.55.

Output:
    data/incidents/stage7_incident_scores.parquet
    reports/stage7_incident_report.txt
"""
from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

log = logging.getLogger(__name__)

INCIDENTS_CSV = Path("data/incidents/confirmed_incidents_india.csv")
FACILITIES_PARQUET = Path("data/processed/facilities.parquet")
MODEL_PATH = Path("data/processed/stage6_model.joblib")
SCORES_OUT = Path("data/incidents/stage7_incident_scores.parquet")
REPORT_OUT = Path("reports/stage7_incident_report.txt")

EARTH_RADIUS_KM = 6371.0
ANOMALY_THRESHOLD = 0.55

TRAIN_FEATURES = [
    "bt_kelvin",
    "frp_mw",
    "persistence_count",
    "dist_nearest_facility_km",
    "agri_season_flag",
    "day_night_bin",
    "acq_month",
]

_AGRI_MONTHS = {10, 11, 4, 5, 7, 8, 9, 1, 2}


def _nearest_facility(lats, lons, facilities):
    coords_rad = np.radians(facilities[["lat", "lon"]].values)
    tree = BallTree(coords_rad, metric="haversine")
    query_rad = np.radians(np.column_stack([lats, lons]))
    dists_rad, idxs = tree.query(query_rad, k=1)
    dists_km = dists_rad[:, 0] * EARTH_RADIUS_KM
    fac_type = facilities.iloc[idxs[:, 0]]["facility_type"].values
    return dists_km, fac_type


def score_incidents(
    incidents_csv: Path = INCIDENTS_CSV,
    facilities_parquet: Path = FACILITIES_PARQUET,
    model_path: Path = MODEL_PATH,
    scores_out: Path = SCORES_OUT,
    report_out: Path = REPORT_OUT,
) -> pd.DataFrame:
    log.info("Loading incidents …")
    inc = pd.read_csv(incidents_csv)
    log.info("Loaded %d incidents", len(inc))

    log.info("Loading facilities …")
    fac = pd.read_parquet(facilities_parquet)

    log.info("Loading model …")
    pipe = joblib.load(model_path)

    # ── Compute available features from coordinates + date ────────────────────
    inc["acq_month"] = pd.to_datetime(inc["date"]).dt.month
    inc["agri_season_flag"] = inc["acq_month"].apply(
        lambda m: 1 if m in _AGRI_MONTHS else 0
    )

    dist_km, fac_type = _nearest_facility(
        inc["lat"].values, inc["lon"].values, fac
    )
    inc["dist_nearest_facility_km"] = dist_km
    inc["nearest_facility_type"] = fac_type

    # Thermal features unknown (no historical FIRMS) → NaN → imputed by pipeline
    inc["bt_kelvin"] = np.nan
    inc["frp_mw"] = np.nan
    inc["persistence_count"] = np.nan
    inc["day_night_bin"] = np.nan  # incident time unknown

    # ── Score ─────────────────────────────────────────────────────────────────
    X = inc[TRAIN_FEATURES].to_numpy(dtype=float, na_value=np.nan)
    y_pred = pipe.predict(X)
    y_prob = pipe.predict_proba(X)
    classes = pipe.classes_

    inc["predicted_label"] = y_pred
    for i, cls in enumerate(classes):
        inc[f"prob_{cls}"] = y_prob[:, i]
    inc["max_prob"] = y_prob.max(axis=1)
    inc["anomaly_flag"] = (inc["max_prob"] < ANOMALY_THRESHOLD).astype(int)

    # ── Build report ──────────────────────────────────────────────────────────
    lines = [
        "SIH26162 — Stage 7 Incident Scoring Report",
        "=" * 60,
        "",
        "Context: thermal features (bt_kelvin, frp_mw, persistence_count,",
        "day_night_bin) are NaN — no historical FIRMS archive for 2019–2023.",
        "Model imputes NaN with training medians. Scoring is driven by",
        "dist_nearest_facility_km, agri_season_flag, acq_month.",
        "",
        f"Total incidents: {len(inc)}",
        f"Anomaly-flagged (max_prob < {ANOMALY_THRESHOLD}): "
        f"{inc['anomaly_flag'].sum()} ({100*inc['anomaly_flag'].mean():.1f}%)",
        "",
        "Predicted label distribution:",
        f"  {inc['predicted_label'].value_counts().to_dict()}",
        "",
        "=" * 60,
        "Per-incident scores:",
        "",
    ]

    for _, row in inc.iterrows():
        flag = "*** ANOMALY ***" if row["anomaly_flag"] else ""
        lines.append(
            f"{row['incident_id']:<10} {row['name'][:45]:<46} "
            f"pred={row['predicted_label']:<12} "
            f"prob_A={row['prob_A']:.3f}  prob_B={row['prob_B_candidate']:.3f}  "
            f"max={row['max_prob']:.3f}  dist_fac={row['dist_nearest_facility_km']:.1f}km  "
            f"{flag}"
        )

    lines += [
        "",
        "=" * 60,
        "Interpretation:",
        "",
        "Incidents predicted as ANOMALY (max_prob < 0.55) are hotspots",
        "that the model cannot confidently classify as either a persistent",
        "industrial flare (Class A) or a natural/agricultural fire (Class B).",
        "This is the expected outcome for transient industrial fires — they",
        "depart from both known pattern types.",
        "",
        "Incidents predicted as Class A: the incident site resembles a known",
        "gas flare site (near industrial facility, potentially nighttime).",
        "This is plausible for refineries / oil/gas facilities.",
        "",
        "Incidents predicted as Class B: the model sees an event pattern more",
        "consistent with a natural fire (low facility proximity or agri season).",
        "",
        "NOTE: Without historical FIRMS data, thermal features are imputed.",
        "Scores should be treated as baseline geographic context, not a definitive",
        "classification of the incident event itself.",
    ]

    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text("\n".join(lines))
    log.info("Report → %s", report_out)

    scores_out.parent.mkdir(parents=True, exist_ok=True)
    inc.to_parquet(scores_out, index=False)
    log.info("Scores → %s", scores_out)

    return inc


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    df = score_incidents()

    print("\n=== Stage 7 Summary ===")
    print(f"Incidents scored: {len(df)}")
    print(f"Anomaly-flagged: {df['anomaly_flag'].sum()} ({100*df['anomaly_flag'].mean():.1f}%)")
    print(f"\nPredicted label distribution:")
    print(df["predicted_label"].value_counts())
    print(f"\nSample output:")
    cols = ["incident_id", "name", "predicted_label", "prob_A", "prob_B_candidate", "anomaly_flag"]
    print(df[cols].to_string(index=False))
