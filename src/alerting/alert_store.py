"""
SQLite-backed alert store with lifecycle state management.

Lifecycle:
    DETECTED → VALIDATING → ALERTED → ESCALATED → MONITORING → EXTINGUISHED

Transitions happen automatically based on time + re-detection, or manually
via acknowledge / escalate / resolve actions.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("data/alerts.db")

LIFECYCLE_STATES = [
    "DETECTED",
    "VALIDATING",
    "ALERTED",
    "ESCALATED",
    "MONITORING",
    "EXTINGUISHED",
]

SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    alert_id              TEXT PRIMARY KEY,
    lat                   REAL,
    lon                   REAL,
    severity              TEXT,
    status                TEXT,
    risk_score            INTEGER,
    frp_mw                REAL,
    bt_kelvin             REAL,
    persistence_count     INTEGER,
    dist_nearest_facility_km REAL,
    nearest_facility_type TEXT,
    predicted_label       TEXT,
    prob_A                REAL,
    prob_B                REAL,
    anomaly_flag          INTEGER,
    nearest_city          TEXT,
    dist_nearest_city_km  REAL,
    near_population       INTEGER,
    acq_date              TEXT,
    day_night             TEXT,
    narrative             TEXT,
    created_at            TEXT,
    updated_at            TEXT,
    acknowledged_at       TEXT
);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute(_SCHEMA)
    con.commit()
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_alerts(rows: list[dict]) -> int:
    """
    Insert new alerts from a list of dicts. Skips rows whose (lat, lon, acq_date)
    already have an active alert (prevents duplication on re-run).
    Returns number of rows inserted.
    """
    con = _connect()
    inserted = 0
    for row in rows:
        # Dedup: skip if same location + date already has an alert
        existing = con.execute(
            "SELECT 1 FROM alerts WHERE lat=? AND lon=? AND acq_date=? AND status != 'EXTINGUISHED'",
            (row["lat"], row["lon"], row.get("acq_date", "")),
        ).fetchone()
        if existing:
            continue

        now = _now()
        # Progress DETECTED → VALIDATING immediately for HIGH/CRITICAL
        if row.get("severity") in ("CRITICAL", "HIGH"):
            status = "ALERTED"
        elif row.get("severity") == "MEDIUM":
            status = "VALIDATING"
        else:
            status = "DETECTED"

        con.execute(
            """INSERT INTO alerts (
                alert_id, lat, lon, severity, status, risk_score,
                frp_mw, bt_kelvin, persistence_count,
                dist_nearest_facility_km, nearest_facility_type,
                predicted_label, prob_A, prob_B, anomaly_flag,
                nearest_city, dist_nearest_city_km, near_population,
                acq_date, day_night, narrative, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4())[:12],
                row["lat"], row["lon"],
                row.get("severity", "LOW"),
                status,
                int(row.get("risk_score", 0)),
                float(row.get("frp_mw", 0) or 0),
                float(row.get("bt_kelvin", 0) or 0),
                int(row.get("persistence_count", 1) or 1),
                float(row.get("dist_nearest_facility_km", 0) or 0),
                str(row.get("nearest_facility_type", "") or ""),
                str(row.get("predicted_label", "") or ""),
                float(row.get("prob_A", 0) or 0),
                float(row.get("prob_B_candidate", 0) or 0),
                int(row.get("anomaly_flag", 0) or 0),
                str(row.get("nearest_city", "") or ""),
                float(row.get("dist_nearest_city_km", 0) or 0),
                int(row.get("near_population", 0) or 0),
                str(row.get("acq_date", "") or ""),
                str(row.get("day_night", "") or ""),
                str(row.get("narrative", "") or ""),
                now, now,
            ),
        )
        inserted += 1
    con.commit()
    con.close()
    return inserted


def get_alerts(
    severity: list[str] | None = None,
    status: list[str] | None = None,
    limit: int = 500,
) -> list[dict]:
    """Fetch alerts, optionally filtered. Returns list of dicts sorted by severity then time."""
    con = _connect()
    clauses, params = [], []
    if severity:
        placeholders = ",".join("?" * len(severity))
        clauses.append(f"severity IN ({placeholders})")
        params.extend(severity)
    if status:
        placeholders = ",".join("?" * len(status))
        clauses.append(f"status IN ({placeholders})")
        params.extend(status)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = con.execute(
        f"SELECT * FROM alerts {where} ORDER BY risk_score DESC, created_at DESC LIMIT ?",
        [*params, limit],
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def update_status(alert_id: str, new_status: str) -> None:
    assert new_status in LIFECYCLE_STATES, f"Unknown status: {new_status}"
    con = _connect()
    con.execute(
        "UPDATE alerts SET status=?, updated_at=? WHERE alert_id=?",
        (new_status, _now(), alert_id),
    )
    if new_status == "MONITORING":
        con.execute(
            "UPDATE alerts SET acknowledged_at=? WHERE alert_id=?",
            (_now(), alert_id),
        )
    con.commit()
    con.close()


def counts() -> dict:
    """Return severity + status counts for the dashboard header."""
    con = _connect()
    rows = con.execute(
        "SELECT severity, status, COUNT(*) as n FROM alerts GROUP BY severity, status"
    ).fetchall()
    con.close()

    result: dict = {"total": 0, "CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "active": 0}
    for row in rows:
        result["total"] += row["n"]
        result[row["severity"]] = result.get(row["severity"], 0) + row["n"]
        if row["status"] not in ("EXTINGUISHED",):
            result["active"] += row["n"]
    return result


def clear_all() -> None:
    """Drop and recreate the alerts table (for fresh pipeline runs)."""
    con = _connect()
    con.execute("DROP TABLE IF EXISTS alerts")
    con.execute(_SCHEMA)
    con.commit()
    con.close()
