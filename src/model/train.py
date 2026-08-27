"""
Stage 6 — Train & validate the hotspot classifier.

Model: RandomForestClassifier (tabular data, explainability priority over accuracy).

THREE-WAY EVALUATION (required per new.txt and context.md):
  1. Random-split baseline   — train/test random 80/20 on the labeled set.
                               Shows inflated accuracy (leakage benchmark).
  2. Spatial holdout          — train on stage5_train, evaluate on stage5_val.
                               Honest performance with spatial leakage prevented.
  3. India geographic holdout — score stage5_india_holdout. No ground-truth
                               labels available; output class distribution only.

The GAP between (1) and (2) is explicitly reported — it is evidence that the
leakage problem was handled correctly, not a failure to hide.

Classes:
    "A"           — Persistent industrial thermal source (gas flare, kiln, …)
    "B_candidate" — Natural / agricultural fire

An "anomaly" is a hotspot that scores with low confidence for BOTH classes.
Threshold for anomaly: max_prob < ANOMALY_THRESHOLD.

Output:
    data/processed/stage6_model.joblib
    data/processed/stage6_india_scores.parquet   (with predicted class + probs)
    reports/stage6_evaluation.txt
    reports/stage6_feature_importance.csv
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

TRAIN_PATH = Path("data/processed/stage5_train.parquet")
VAL_PATH = Path("data/processed/stage5_val.parquet")
INDIA_PATH = Path("data/processed/stage5_india_holdout.parquet")
MODEL_OUT = Path("data/processed/stage6_model.joblib")
INDIA_SCORES_OUT = Path("data/processed/stage6_india_scores.parquet")
EVAL_REPORT_OUT = Path("reports/stage6_evaluation.txt")
FEAT_IMP_OUT = Path("reports/stage6_feature_importance.csv")

TRAIN_FEATURES = [
    "bt_kelvin",
    "frp_mw",
    "persistence_count",
    "dist_nearest_facility_km",
    "agri_season_flag",
    "day_night_bin",
    "acq_month",
]

ANOMALY_THRESHOLD = 0.55  # max class prob below this → flagged as anomaly


def _load_Xy(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    X = df[TRAIN_FEATURES].to_numpy(dtype=float, na_value=np.nan)
    y = df["label"].to_numpy(dtype=str)
    return X, y


def _make_pipeline():
    """RF classifier with median imputation (fit on train, applied to all)."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("clf", RandomForestClassifier(
            n_estimators=300,
            min_samples_leaf=10,
            class_weight="balanced",
            n_jobs=-1,
            random_state=42,
        )),
    ])


def _report_metrics(y_true, y_pred, y_prob, label: str, classes) -> str:
    from sklearn.metrics import classification_report, confusion_matrix

    lines = [f"\n{'='*60}", f"  {label}", f"{'='*60}"]

    # Confusion matrix
    cm = confusion_matrix(y_true, y_pred, labels=classes)
    lines.append(f"\nConfusion matrix (rows=true, cols=pred):")
    lines.append(f"  Classes: {classes}")
    lines.append(f"  {cm}")

    # Classification report
    lines.append(f"\nClassification report:")
    lines.append(classification_report(y_true, y_pred, labels=classes))

    # Anomaly rate: rows where max_prob < ANOMALY_THRESHOLD
    if y_prob is not None:
        max_probs = y_prob.max(axis=1)
        anomaly_mask = max_probs < ANOMALY_THRESHOLD
        lines.append(
            f"Anomaly flag rate (max_prob < {ANOMALY_THRESHOLD}): "
            f"{anomaly_mask.sum()} / {len(y_true)} "
            f"({100*anomaly_mask.mean():.1f}%)"
        )

    return "\n".join(lines)


def train(
    train_path: Path = TRAIN_PATH,
    val_path: Path = VAL_PATH,
    india_path: Path = INDIA_PATH,
    model_out: Path = MODEL_OUT,
    india_scores_out: Path = INDIA_SCORES_OUT,
    eval_report_out: Path = EVAL_REPORT_OUT,
    feat_imp_out: Path = FEAT_IMP_OUT,
) -> dict:
    """Run Stage 6 training and evaluation. Returns summary dict."""
    from sklearn.model_selection import train_test_split
    import joblib

    # ── Load data ─────────────────────────────────────────────────────────────
    log.info("Loading Stage 5 splits …")
    train_df = pd.read_parquet(train_path)
    val_df = pd.read_parquet(val_path)
    india_df = pd.read_parquet(india_path)

    log.info("Train: %d rows | Val: %d rows | India: %d rows",
             len(train_df), len(val_df), len(india_df))
    log.info("Train labels: %s", train_df["label"].value_counts().to_dict())
    log.info("Val labels:   %s", val_df["label"].value_counts().to_dict())

    X_train, y_train = _load_Xy(train_df)
    X_val, y_val = _load_Xy(val_df)

    all_df = pd.concat([train_df, val_df], ignore_index=True)
    X_all, y_all = _load_Xy(all_df)
    classes = sorted(all_df["label"].dropna().unique())
    log.info("Classes: %s", classes)

    report_lines = [
        "SIH26162 — Stage 6 Evaluation Report",
        "=" * 60,
        f"\nClasses: {classes}",
        f"Training features: {TRAIN_FEATURES}",
        f"\nData sizes:",
        f"  Train (spatial holdout): {len(train_df)} rows",
        f"  Val   (spatial holdout): {len(val_df)} rows",
        f"  India (geographic holdout, no labels): {len(india_df)} rows",
        f"\nClass distribution (train):",
        f"  {train_df['label'].value_counts().to_dict()}",
        f"\nDesign note: VNF avg_temp (1500–2000 K spectral flame temperature)",
        f"is NOT used as a training feature. VNF serves as a labeling oracle only.",
        f"All training examples are in FIRMS feature space (bt_kelvin 300–500 K),",
        f"matching the India inference-time feature space.",
        f"\nAnomaly threshold: max class probability < {ANOMALY_THRESHOLD}",
    ]

    # ── 1. Random-split baseline (inflated — shows leakage cost) ─────────────
    log.info("Fitting random-split baseline …")
    X_rb_train, X_rb_test, y_rb_train, y_rb_test = train_test_split(
        X_all, y_all, test_size=0.2, random_state=42
    )
    pipe_rb = _make_pipeline()
    pipe_rb.fit(X_rb_train, y_rb_train)
    y_rb_pred = pipe_rb.predict(X_rb_test)
    y_rb_prob = pipe_rb.predict_proba(X_rb_test)

    from sklearn.metrics import accuracy_score
    rb_acc = accuracy_score(y_rb_test, y_rb_pred)
    log.info("Random-split baseline accuracy: %.4f", rb_acc)
    report_lines.append(
        _report_metrics(y_rb_test, y_rb_pred, y_rb_prob, "1. Random-split baseline (INFLATED)", classes)
    )
    report_lines.append(f"\nBaseline accuracy: {rb_acc:.4f}")

    # ── 2. Spatial holdout (honest) ───────────────────────────────────────────
    log.info("Fitting spatial holdout model …")
    pipe_sh = _make_pipeline()
    pipe_sh.fit(X_train, y_train)
    y_val_pred = pipe_sh.predict(X_val)
    y_val_prob = pipe_sh.predict_proba(X_val)

    sh_acc = accuracy_score(y_val, y_val_pred)
    log.info("Spatial holdout accuracy: %.4f", sh_acc)
    report_lines.append(
        _report_metrics(y_val, y_val_pred, y_val_prob,
                        "2. Spatial holdout (HONEST — train on global, test on held-out grids)",
                        classes)
    )
    report_lines.append(f"\nSpatial holdout accuracy: {sh_acc:.4f}")

    # ── Leakage gap report ─────────────────────────────────────────────────────
    gap = rb_acc - sh_acc
    report_lines.append(
        f"\n{'='*60}\n"
        f"LEAKAGE GAP = {rb_acc:.4f} (random) − {sh_acc:.4f} (spatial) = {gap:.4f}\n"
        f"This gap confirms that random splitting inflates accuracy by {gap*100:.1f} pp.\n"
        f"The spatial holdout figure is the honest estimate of geographic generalization.\n"
        f"{'='*60}"
    )
    log.info("Leakage gap: %.4f (%.1f pp)", gap, gap * 100)

    # ── 3. India geographic holdout (scoring only, no labels) ────────────────
    log.info("Scoring India holdout …")
    if len(india_df) > 0:
        X_india = india_df[TRAIN_FEATURES].values.astype(float)
        y_india_pred = pipe_sh.predict(X_india)
        y_india_prob = pipe_sh.predict_proba(X_india)

        max_probs = y_india_prob.max(axis=1)
        anomaly_mask = max_probs < ANOMALY_THRESHOLD

        pred_dist = pd.Series(y_india_pred).value_counts().to_dict()
        report_lines.append(
            f"\n{'='*60}\n"
            f"  3. India geographic holdout (NO LABELS — inference only)\n"
            f"{'='*60}\n"
            f"\nPredicted class distribution for {len(india_df)} India FIRMS hotspots:\n"
            f"  {pred_dist}\n"
            f"\nAnomaly flag (max_prob < {ANOMALY_THRESHOLD}):\n"
            f"  {anomaly_mask.sum()} / {len(india_df)} rows ({100*anomaly_mask.mean():.1f}%)\n"
            f"\n(No accuracy reported — India is locked holdout with no ground-truth labels)\n"
        )
        log.info("India predictions: %s", pred_dist)
        log.info("India anomaly rate: %.1f%%", 100 * anomaly_mask.mean())

        # Save India scores
        india_out = india_df.copy()
        india_out["predicted_label"] = y_india_pred
        for i, cls in enumerate(pipe_sh.classes_):
            india_out[f"prob_{cls}"] = y_india_prob[:, i]
        india_out["anomaly_flag"] = anomaly_mask.astype(int)
        india_out.to_parquet(india_scores_out, index=False)
        log.info("India scores saved → %s", india_scores_out)
    else:
        report_lines.append("\n3. India holdout: 0 rows — no India FIRMS NRT data available.")

    # ── Feature importance ─────────────────────────────────────────────────────
    clf = pipe_sh.named_steps["clf"]
    imp = pd.DataFrame({
        "feature": TRAIN_FEATURES,
        "importance": clf.feature_importances_,
    }).sort_values("importance", ascending=False)

    report_lines.append(f"\n{'='*60}")
    report_lines.append("Feature importances (spatial holdout model):")
    for _, row in imp.iterrows():
        report_lines.append(f"  {row['feature']:40s} {row['importance']:.4f}")

    # ── Save model and reports ─────────────────────────────────────────────────
    model_out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe_sh, model_out)
    log.info("Model saved → %s", model_out)

    eval_report_out.parent.mkdir(parents=True, exist_ok=True)
    eval_report_out.write_text("\n".join(report_lines))
    log.info("Evaluation report → %s", eval_report_out)

    imp.to_csv(feat_imp_out, index=False)
    log.info("Feature importance → %s", feat_imp_out)

    summary = {
        "random_split_accuracy": round(rb_acc, 4),
        "spatial_holdout_accuracy": round(sh_acc, 4),
        "leakage_gap_pp": round(gap * 100, 2),
        "india_rows_scored": len(india_df),
        "classes": classes,
        "top_feature": imp.iloc[0]["feature"],
    }
    log.info("Stage 6 complete: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    result = train()
    print("\n=== Stage 6 Summary ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
