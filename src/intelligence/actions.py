"""
Read-only outputs (GeoJSON / CSV / incident report) + manual-UI helpers.

The agent's tool registry only exposes the read-only exporters here.
`set_alert_status` and `run_pipeline_fresh` are used ONLY by the manual Streamlit
UI (Alerts / Investigation pages, the pipeline control) — they are NOT registered
as agent tools this round.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone

import pandas as pd

from src.alerting import alert_store, pipeline
from src.intelligence import queries

_CSV_COLUMNS = [
    "alert_id", "lat", "lon", "output_class", "output_class_code", "severity",
    "status", "risk_score", "land_cover_context", "hazard_facility_type",
    "frp_mw", "persistence_count", "dist_nearest_facility_km",
    "district", "state", "in_india", "acq_date", "day_night", "narrative",
]


def _filtered(filters: dict | None) -> list[dict]:
    return queries.list_alerts(filters, limit=100000)


# ── GeoJSON export ───────────────────────────────────────────────────────────
def export_geojson(filters: dict | None = None) -> str:
    alerts = _filtered(filters)
    features = []
    for a in alerts:
        props = {k: a.get(k) for k in _CSV_COLUMNS if k not in ("lat", "lon")}
        props["risk_factors"] = a.get("risk_factors")
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [a["lon"], a["lat"]]},
            "properties": props,
        })
    return json.dumps(
        {"type": "FeatureCollection",
         "metadata": {
             "source": "SIH26162 India Fire Intelligence Platform",
             "generated_utc": datetime.now(timezone.utc).isoformat(),
             "feature_count": len(features),
             "note": "Anomalous departures from known thermal patterns — not confirmed fires.",
         },
         "features": features},
        indent=2,
    )


def export_csv(filters: dict | None = None) -> str:
    alerts = _filtered(filters)
    if not alerts:
        return ",".join(_CSV_COLUMNS) + "\n"
    df = pd.DataFrame(alerts)
    for c in _CSV_COLUMNS:
        if c not in df.columns:
            df[c] = None
    return df[_CSV_COLUMNS].to_csv(index=False)


def geojson_preview(filters: dict | None = None, n: int = 3) -> str:
    doc = json.loads(export_geojson(filters))
    doc["features"] = doc["features"][:n]
    return json.dumps(doc, indent=2)


# ── Incident report ─────────────────────────────────────────────────────────
def build_incident_report(filters: dict | None = None, fmt: str = "markdown") -> str:
    f = dict(filters or {})
    f.setdefault("severity", ["CRITICAL", "HIGH"])
    alerts = queries.list_alerts(f, limit=100000, sort_by="risk_score")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lo, hi = queries.data_date_range()

    if fmt == "csv":
        return export_csv(f)

    lines = [
        "# SIH26162 — Incident Report",
        "",
        f"*Generated {now}. Detection window {lo} to {hi}.*",
        "",
        "> Anomalous departures from known persistent-industrial and natural-fire "
        "patterns. Not confirmed fires. Every entry requires human verification.",
        "",
        f"**{len(alerts)} alert(s)** match the current filters "
        f"({_describe_filters(f)}).",
        "",
    ]
    if not alerts:
        lines.append("_No alerts match — nothing to report._")
        return "\n".join(lines)

    by_class: dict[str, int] = {}
    for a in alerts:
        by_class[a["output_class_short"]] = by_class.get(a["output_class_short"], 0) + 1
    lines.append("## Summary")
    for k, v in sorted(by_class.items(), key=lambda x: -x[1]):
        lines.append(f"- {k}: {v}")
    lines += ["", "## Alerts", "",
              "| Rank | Class | Severity | Location | Risk | FRP (MW) | Persist | Date | Status |",
              "|---|---|---|---|---|---|---|---|---|"]
    for i, a in enumerate(alerts[:100], 1):
        loc = a.get("place") or a.get("state") or a.get("zone") or \
              f"{a['lat']:.3f},{a['lon']:.3f}"
        lines.append(
            f"| {i} | {a['output_class_short']} | {a['severity']} | {loc} | "
            f"{a['risk_score']}/100 | {a['frp_mw'] if a['frp_mw'] is not None else '—'} | "
            f"{a['persistence_count']}x | {a['acq_date']} | {a['status']} |"
        )
    return "\n".join(lines)


def _describe_filters(f: dict) -> str:
    parts = []
    if f.get("severity"):
        parts.append("severity " + "/".join(f["severity"]))
    if f.get("output_class"):
        parts.append("class " + "/".join(str(c) for c in f["output_class"]))
    if f.get("state"):
        parts.append("state " + str(f["state"]))
    if f.get("region"):
        parts.append("region " + str(f["region"]))
    if f.get("date_from") or f.get("date_to"):
        parts.append(f"{f.get('date_from', '…')}–{f.get('date_to', '…')}")
    return ", ".join(parts) or "no filters"


# ── manual-UI only (NOT agent tools) ────────────────────────────────────────
_ACTION_TO_STATUS = {
    "acknowledge": "MONITORING",
    "escalate": "ESCALATED",
    "resolve": "EXTINGUISHED",
}


def set_alert_status(alert_id: str, action: str) -> dict:
    """Manual operator action only. Not exposed to the agent."""
    action = action.lower()
    if action not in _ACTION_TO_STATUS:
        return {"ok": False, "error": f"unknown action {action!r}"}
    alert_store.update_status(alert_id, _ACTION_TO_STATUS[action])
    queries.clear_caches()
    return {"ok": True, "alert_id": alert_id, "new_status": _ACTION_TO_STATUS[action]}


def run_pipeline_fresh() -> dict:
    r = pipeline.run(fresh=True)
    queries.clear_caches()
    return r


def ensure_seeded() -> bool:
    """Seed the alert store on first run. Returns True if a seed happened."""
    if queries.is_seeded():
        return False
    pipeline.run(fresh=True)
    queries.clear_caches()
    return True
