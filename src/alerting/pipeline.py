"""
Alert pipeline — runs end-to-end:
    FIRMS India scores → risk engine → alert store

Usage:
    python -m src.alerting.pipeline           # seed from existing scores
    python -m src.alerting.pipeline --fresh   # clear DB first, then reseed
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from src.alerting import alert_store, risk_engine

log = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent.parent
INDIA_SCORES_PATH = _ROOT / "data/processed/stage6_india_scores.parquet"
INCIDENT_SCORES_PATH = _ROOT / "data/incidents/stage7_incident_scores.parquet"


def run(fresh: bool = False) -> dict:
    """
    Seed the alert store from the current India FIRMS scores.
    Returns a summary dict.
    """
    if fresh:
        log.info("Clearing alert store …")
        alert_store.clear_all()

    # ── Score FIRMS India hotspots ─────────────────────────────────────────────
    log.info("Loading India FIRMS scores: %s", INDIA_SCORES_PATH)
    df = pd.read_parquet(INDIA_SCORES_PATH)
    log.info("Scoring %d rows …", len(df))
    scored = risk_engine.score_dataframe(df)

    dist = scored["severity"].value_counts().to_dict()
    log.info("Severity distribution: %s", dist)

    rows = scored.to_dict(orient="records")
    n = alert_store.insert_alerts(rows)
    log.info("Inserted %d new alerts (skipped %d duplicates)", n, len(rows) - n)

    c = alert_store.counts()
    log.info("Alert store: %s", c)
    return {"inserted": n, "counts": c, "severity_dist": dist}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true",
                        help="Clear the alert DB before seeding")
    args = parser.parse_args()

    result = run(fresh=args.fresh)
    print("\n=== Alert Pipeline Summary ===")
    print(f"Inserted: {result['inserted']}")
    print(f"Severity: {result['severity_dist']}")
    print(f"Counts:   {result['counts']}")
