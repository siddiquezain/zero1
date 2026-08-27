"""
Stage 3 — Match confirmed incidents against FIRMS hotspot data.

For each confirmed incident (lat/lon/date), search FIRMS VIIRS/MODIS data
for hotspots within a spatial buffer and ±N day window.

CRITICAL CONSTRAINTS:
- A matched hotspot is NOT ground truth that the incident was satellite-detected.
- An unmatched incident is a FINDING (possible satellite omission), not noise to drop.
- `matched: yes/no` column must be preserved in output.

Output: /data/incidents/matched_incidents.parquet
        /data/incidents/match_summary.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from src.ingestion.config import FIRMS_RAW, INCIDENTS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

INCIDENTS_CSV = INCIDENTS_DIR / "confirmed_incidents_india.csv"
OUTPUT_PARQUET = INCIDENTS_DIR / "matched_incidents.parquet"
SUMMARY_JSON = INCIDENTS_DIR / "match_summary.json"

# Spatial buffer for proximity matching
SPATIAL_BUFFER_KM = 1.0  # 1 km (roughly 3 VIIRS pixels at 375 m)

# Temporal window: incident date ± TEMPORAL_DAYS
TEMPORAL_DAYS = 1


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    r = 6371.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def load_firms_all() -> pd.DataFrame | None:
    """Load all FIRMS parquet files from /data/raw/firms/ into one DataFrame."""
    parquets = list(FIRMS_RAW.glob("*.parquet"))
    if not parquets:
        log.warning("No FIRMS parquet files found in %s — run firms.py first.", FIRMS_RAW)
        return None

    dfs = []
    for p in parquets:
        df = pd.read_parquet(p)
        # Normalise column names (VIIRS uses 'latitude','longitude'; MODIS similar)
        df = df.rename(columns={"latitude": "lat", "longitude": "lon"})
        if "acq_date" in df.columns:
            df["acq_date"] = pd.to_datetime(df["acq_date"])
        dfs.append(df)

    combined = pd.concat(dfs, ignore_index=True)
    log.info("Loaded %d FIRMS rows from %d file(s)", len(combined), len(parquets))
    return combined


def match_incident(
    incident: pd.Series,
    firms: pd.DataFrame,
    buffer_km: float = SPATIAL_BUFFER_KM,
    temporal_days: int = TEMPORAL_DAYS,
) -> list[dict]:
    """Return list of matching FIRMS rows for one incident."""
    if firms is None or firms.empty:
        return []

    inc_date = pd.to_datetime(incident["date"])
    date_lo = inc_date - timedelta(days=temporal_days)
    date_hi = inc_date + timedelta(days=temporal_days)

    # Temporal filter first (fast)
    if "acq_date" in firms.columns:
        window = firms[firms["acq_date"].between(date_lo, date_hi)]
    else:
        window = firms  # no date column — skip temporal filter

    if window.empty:
        return []

    # Spatial filter: vectorised haversine
    ilat, ilon = float(incident["lat"]), float(incident["lon"])
    dists = window.apply(
        lambda row: haversine_km(ilat, ilon, row["lat"], row["lon"]), axis=1
    )
    nearby = window[dists <= buffer_km].copy()
    nearby["dist_km"] = dists[nearby.index]

    return nearby.to_dict("records")


def run_matching() -> pd.DataFrame:
    """
    Match all confirmed incidents against available FIRMS data.
    Preserves unmatched incidents with matched=no.
    """
    incidents = pd.read_csv(INCIDENTS_CSV)
    log.info("Loaded %d confirmed incidents from %s", len(incidents), INCIDENTS_CSV)

    firms = load_firms_all()  # May be None if no FIRMS data yet

    results = []
    for _, inc in incidents.iterrows():
        matches = match_incident(inc, firms) if firms is not None else []

        if matches:
            for m in matches:
                row = inc.to_dict()
                row["matched"] = "yes"
                row["firms_lat"] = m.get("lat")
                row["firms_lon"] = m.get("lon")
                row["firms_brightness"] = m.get("brightness")
                row["firms_frp"] = m.get("frp")
                row["firms_acq_date"] = str(m.get("acq_date", ""))
                row["firms_dist_km"] = m.get("dist_km")
                results.append(row)
        else:
            row = inc.to_dict()
            row["matched"] = "no"
            row["firms_lat"] = None
            row["firms_lon"] = None
            row["firms_brightness"] = None
            row["firms_frp"] = None
            row["firms_acq_date"] = None
            row["firms_dist_km"] = None
            # NOTE: unmatched = finding (possible satellite omission), NOT an error
            results.append(row)

    df = pd.DataFrame(results)

    n_matched = (df["matched"] == "yes").sum()
    n_unmatched = (df["matched"] == "no").sum()
    log.info(
        "Matching complete: %d incidents, %d matched, %d unmatched (satellite omissions)",
        len(incidents), n_matched, n_unmatched,
    )

    return df


def save_results(df: pd.DataFrame) -> None:
    INCIDENTS_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PARQUET, index=False)
    log.info("Saved matched incidents → %s", OUTPUT_PARQUET)

    summary = {
        "total_incidents": int(len(df["incident_id"].unique())),
        "matched_yes": int((df["matched"] == "yes").sum()),
        "matched_no": int((df["matched"] == "no").sum()),
        "match_rate_pct": round(
            100 * (df["matched"] == "yes").mean(), 1
        ),
        "note": (
            "Unmatched incidents are satellite-omission findings, "
            "NOT discarded rows. Both matched and unmatched are valid pipeline output."
        ),
        "spatial_buffer_km": SPATIAL_BUFFER_KM,
        "temporal_window_days": TEMPORAL_DAYS,
        "run_utc": datetime.now(timezone.utc).isoformat(),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2))
    log.info("Match summary → %s", SUMMARY_JSON)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    df = run_matching()
    save_results(df)

    if (df["matched"] == "no").all():
        firms_files = list(FIRMS_RAW.glob("*.parquet"))
        if not firms_files:
            print(
                "\nNote: No FIRMS parquet files found. "
                "Run src/ingestion/firms.py after setting FIRMS_MAP_KEY in .env."
            )
        else:
            print(
                f"\nNote: {len(firms_files)} FIRMS file(s) loaded but no temporal matches found.\n"
                "Confirmed incidents are from 2019–2023; available FIRMS is NRT (recent 5 days).\n"
                "Historical FIRMS archive data is required to match past incidents.\n"
                "This is a known limitation — unmatched incidents are preserved as satellite-omission findings."
            )
