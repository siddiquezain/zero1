"""
Historical Fire Timeline — data access and daily severity aggregation.

Severity thresholds mirror risk_engine.py so this module can be shared
with the live alert engine later.
# ponytail: direct SQLite query per call; wrap with @st.cache_data at call site if slow
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

_DB_DEFAULT = Path(__file__).parent.parent / "data/alerts.db"

_SEV_COLOR = {
    "CRITICAL": "#dc1414",
    "HIGH":     "#ff6e00",
    "MODERATE": "#ffd200",
    "LOW":      "#50c850",
}

_SEV_BG = {
    "CRITICAL": "#2d0a0a",
    "HIGH":     "#2d1400",
    "MODERATE": "#2d2500",
    "LOW":      "#0d2d0d",
}

_SEV_EMOJI = {"CRITICAL": "🔴", "HIGH": "🟠", "MODERATE": "🟡", "LOW": "🟢"}


def get_daily_summary(db_path: Path = _DB_DEFAULT) -> pd.DataFrame:
    """
    Aggregate alerts.db by acq_date → one row per date.

    Columns returned:
        acq_date, total_detections, high_confidence, critical_events,
        avg_frp, max_frp, avg_risk_score, max_risk_score,
        severity_label, color_hex, bg_hex, emoji
    Returns empty DataFrame if DB doesn't exist yet.
    """
    if not db_path.exists():
        return pd.DataFrame()
    con = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        """
        SELECT
            acq_date,
            COUNT(*)                                                         AS total_detections,
            SUM(CASE WHEN severity IN ('CRITICAL','HIGH') THEN 1 ELSE 0 END) AS high_confidence,
            SUM(CASE WHEN severity = 'CRITICAL'           THEN 1 ELSE 0 END) AS critical_events,
            ROUND(AVG(frp_mw), 2)                                            AS avg_frp,
            ROUND(MAX(frp_mw), 2)                                            AS max_frp,
            ROUND(AVG(risk_score), 1)                                        AS avg_risk_score,
            MAX(risk_score)                                                   AS max_risk_score
        FROM alerts
        WHERE acq_date != ''
        GROUP BY acq_date
        ORDER BY acq_date
        """,
        con,
    )
    con.close()
    if df.empty:
        return df
    df["severity_label"] = df["max_risk_score"].apply(_day_severity)
    df["color_hex"] = df["severity_label"].map(_SEV_COLOR)
    df["bg_hex"]    = df["severity_label"].map(_SEV_BG)
    df["emoji"]     = df["severity_label"].map(_SEV_EMOJI)
    return df


def get_events_for_range(
    start: date,
    end: date,
    db_path: Path = _DB_DEFAULT,
) -> list[dict]:
    """All alerts with acq_date in [start, end] inclusive, ordered by risk_score DESC."""
    if not db_path.exists():
        return []
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM alerts WHERE acq_date BETWEEN ? AND ? ORDER BY risk_score DESC, created_at DESC",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def _day_severity(max_score: float) -> str:
    """Classify daily severity from max risk_score. Mirrors risk_engine.py bands."""
    if max_score >= 65:
        return "CRITICAL"
    if max_score >= 40:
        return "HIGH"
    if max_score >= 20:
        return "MODERATE"
    return "LOW"
