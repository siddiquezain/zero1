"""
Read-only data access for SIH26162 — the single place the UI and the agent get data.

Built on the existing engines:
    src/alerting/alert_store.py   (SQLite alert store + lifecycle)
    src/alerting/risk_engine.py   (classification + severity + risk factors)
    data/processed/stage6_india_scores.parquet   (scored FIRMS detections)
    data/incidents/stage7_incident_scores.parquet
    data/processed/facilities.parquet

No Streamlit import. Every function returns plain data (dict / list[dict] / DataFrame).
The Streamlit layer is responsible for caching (st.cache_data at the call site).

Every list/summary function accepts an optional `filters` dict:
    severity              list[str]   e.g. ["CRITICAL", "HIGH"]
    status                list[str]
    output_class          list[str]   canonical or short ("Industrial Fire", ...)
    state                 str | list[str]
    region                str         e.g. "eastern india"
    date_from / date_to   "YYYY-MM-DD"
    near_facility_type    str         hazard-type keyword ("thermal power", "refinery", ...)
    max_dist_facility_km  float
    min_risk              int
    search                str         free text over city / state / narrative
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd

from src.alerting import alert_store, risk_engine
from src.intelligence import facility_fingerprint as _ff
from src.intelligence import geo

_ROOT = Path(__file__).resolve().parents[2]
INDIA_SCORES = _ROOT / "data/processed/stage6_india_scores.parquet"
INCIDENT_SCORES = _ROOT / "data/incidents/stage7_incident_scores.parquet"
FACILITIES = _ROOT / "data/processed/facilities.parquet"

OC_INDUSTRIAL = risk_engine.OUTPUT_CLASS_INDUSTRIAL_FIRE
OC_PERSISTENT = risk_engine.OUTPUT_CLASS_PERSISTENT_SOURCE
OC_NATURAL = risk_engine.OUTPUT_CLASS_NATURAL_FIRE

OUTPUT_CLASS_SHORT = {
    OC_INDUSTRIAL: "Industrial Fire",
    OC_PERSISTENT: "Persistent Source",
    OC_NATURAL: "Natural Fire",
}
OUTPUT_CLASS_CODE = {
    OC_INDUSTRIAL: "PS-A",
    OC_PERSISTENT: "PS-B",
    OC_NATURAL: "PS-C",
}
SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


# ── normalisation helpers ────────────────────────────────────────────────────
def normalise_output_class(value: str | None) -> str | None:
    if not value:
        return None
    v = str(value).strip().lower()
    if v in (c.lower() for c in (OC_INDUSTRIAL, OC_PERSISTENT, OC_NATURAL)):
        for c in (OC_INDUSTRIAL, OC_PERSISTENT, OC_NATURAL):
            if c.lower() == v:
                return c
    if "industrial" in v or "abnormal" in v or "anomal" in v:
        return OC_INDUSTRIAL
    if "persistent" in v or "flare" in v or "ps-b" in v:
        return OC_PERSISTENT
    if "natural" in v or "forest" in v or "agri" in v or "wildfire" in v or "ps-c" in v:
        return OC_NATURAL
    return None


# ── alert loading ────────────────────────────────────────────────────────────
def db_signature() -> float:
    """Cheap cache key for the alert store (mtime). 0.0 if the DB is absent."""
    try:
        return alert_store.DB_PATH.stat().st_mtime
    except OSError:
        return 0.0


_db_signature = db_signature  # backwards-compatible alias


def is_seeded() -> bool:
    return alert_store.DB_PATH.exists()


@lru_cache(maxsize=8)
def _load_alerts_cached(_sig: float) -> pd.DataFrame:
    """
    Every stored alert, annotated with authoritative geography from its
    coordinates (never transformed). `in_india` distinguishes the India
    monitoring dataset from FIRMS points that fall in the ingestion bbox but
    outside India (Sri Lanka, Pakistan, ...).
    """
    rows = alert_store.get_alerts(limit=100000)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = geo.annotate(df, "lat", "lon")           # -> state, district, in_india, zone
    df["place"] = [
        (f"{d}, {s}" if isinstance(d, str) and d else (s if isinstance(s, str) and s else z))
        for d, s, z in zip(df["district"], df["state"], df["zone"])
    ]
    df["output_class_short"] = df["output_class"].map(OUTPUT_CLASS_SHORT).fillna(df["output_class"])
    df["output_class_code"] = df["output_class"].map(OUTPUT_CLASS_CODE).fillna("")
    df["hazard_facility_type"] = df["hazard_facility_type"].fillna("")
    return df


def _all_alerts() -> pd.DataFrame:
    """Every stored alert, India + outside-India (for the map context layer / audit)."""
    return _load_alerts_cached(db_signature()).copy()


def _alerts() -> pd.DataFrame:
    """The India monitoring dataset — the default scope for every product surface."""
    df = _all_alerts()
    if df.empty:
        return df
    return df[df["in_india"]].reset_index(drop=True)


def _frp_reference() -> float:
    """Median FRP across the India monitoring dataset — the 'elevated FRP' threshold."""
    try:
        s = _alerts()["frp_mw"].dropna()
        return float(s.median()) if len(s) else 10.0
    except Exception:
        return 10.0


# ── date helpers (data-relative, not wall-clock) ─────────────────────────────
@lru_cache(maxsize=1)
def data_date_range() -> tuple[str, str]:
    df = _alerts()
    if df.empty or "acq_date" not in df:
        today = date.today().isoformat()
        return today, today
    dates = sorted(d for d in df["acq_date"].dropna().unique() if d)
    return (dates[0], dates[-1]) if dates else (date.today().isoformat(),) * 2


def resolve_timeframe(spec: str | None) -> tuple[str | None, str | None]:
    """
    Turn a phrase into (date_from, date_to). Relative to the DATA's latest date,
    because the FIRMS NRT window is a fixed 5-day slice, not 'now'.
    """
    if not spec:
        return None, None
    lo, hi = data_date_range()
    hi_d = date.fromisoformat(hi)
    s = str(spec).strip().lower()
    if s in ("today", "now", "latest", "current"):
        return hi, hi
    if s in ("yesterday",):
        d = (hi_d - timedelta(days=1)).isoformat()
        return d, d
    import re
    m = re.search(r"(\d+)\s*(day|days|d|week|weeks|w)", s)
    if m:
        n = int(m.group(1)) * (7 if m.group(2).startswith("w") else 1)
        return (hi_d - timedelta(days=n)).isoformat(), hi
    if "week" in s:
        return (hi_d - timedelta(days=7)).isoformat(), hi
    if "all" in s or "everything" in s:
        return lo, hi
    return None, None


# ── filtering ────────────────────────────────────────────────────────────────
def _apply_filters(df: pd.DataFrame, filters: dict | None) -> pd.DataFrame:
    if df.empty or not filters:
        return df
    f = filters
    out = df

    if f.get("severity"):
        sev = [s.upper() for s in _as_list(f["severity"])]
        out = out[out["severity"].isin(sev)]
    if f.get("status"):
        sts = [s.upper() for s in _as_list(f["status"])]
        out = out[out["status"].isin(sts)]
    if f.get("output_class"):
        classes = {normalise_output_class(c) for c in _as_list(f["output_class"])}
        classes.discard(None)
        if classes:
            out = out[out["output_class"].isin(classes)]

    states = geo.resolve_state_filter(_as_list(f.get("state")), f.get("region"))
    if states:
        out = out[out["state"].isin(states)]

    if f.get("date_from"):
        out = out[out["acq_date"] >= str(f["date_from"])]
    if f.get("date_to"):
        out = out[out["acq_date"] <= str(f["date_to"])]

    if f.get("near_facility_type"):
        kw = str(f["near_facility_type"]).strip().lower()
        haz = risk_engine.classify_hazard_type(kw).lower()
        out = out[
            out["hazard_facility_type"].str.lower().str.contains(kw, na=False)
            | (out["hazard_facility_type"].str.lower() == haz)
        ]
    if f.get("max_dist_facility_km") is not None:
        out = out[out["dist_nearest_facility_km"] <= float(f["max_dist_facility_km"])]
    if f.get("min_risk") is not None:
        out = out[out["risk_score"] >= int(f["min_risk"])]

    if f.get("search"):
        q = str(f["search"]).strip().lower()
        hay = (
            out["place"].fillna("").str.lower() + " "
            + out["district"].fillna("").str.lower() + " "
            + out["state"].fillna("").str.lower() + " "
            + out["nearest_city"].fillna("").str.lower() + " "
            + out["narrative"].fillna("").str.lower() + " "
            + out["output_class"].fillna("").str.lower()
        )
        out = out[hay.str.contains(q, na=False, regex=False)]
    return out


def _as_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return [x for x in v if x is not None]
    return [v]


def _row_to_alert(r: pd.Series) -> dict:
    prob_top = max(float(r.get("prob_A") or 0), float(r.get("prob_B") or 0))
    return {
        "alert_id": r["alert_id"],
        "lat": float(r["lat"]), "lon": float(r["lon"]),
        "output_class": _s(r["output_class"]),
        "output_class_short": _s(r.get("output_class_short")) or _s(r["output_class"]),
        "output_class_code": _s(r.get("output_class_code")),
        "severity": _s(r["severity"]),
        "status": _s(r["status"]),
        "risk_score": int(r["risk_score"]),
        "frp_mw": _num(r.get("frp_mw")),
        "bt_kelvin": _num(r.get("bt_kelvin")),
        "persistence_count": int(r.get("persistence_count") or 1),
        "dist_nearest_facility_km": _num(r.get("dist_nearest_facility_km")),
        "hazard_facility_type": _s(r.get("hazard_facility_type")),
        "land_cover_context": _s(r.get("land_cover_context")),
        "nearest_city": _s(r.get("nearest_city")),
        "dist_nearest_city_km": _num(r.get("dist_nearest_city_km")),
        "state": _s(r.get("state")) or None,
        "district": _s(r.get("district")) or None,
        "zone": _s(r.get("zone")) or None,
        "in_india": bool(r.get("in_india")),
        "place": _s(r.get("place")) or None,
        "predicted_label": _s(r.get("predicted_label")),
        "prob_A": _num(r.get("prob_A")), "prob_B": _num(r.get("prob_B")),
        "anomaly_flag": int(r.get("anomaly_flag") or 0),
        "model_class_probability": round(prob_top, 3),
        "acq_date": _s(r.get("acq_date")),
        "day_night": _s(r.get("day_night")),
        "narrative": _s(r.get("narrative")),
        "risk_factors": list(r.get("risk_factors") or []),
    }


def _num(v):
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return round(f, 2)
    except (TypeError, ValueError):
        return None


def _s(v) -> str:
    """Coerce a possibly-NaN / None value to a clean string."""
    if v is None:
        return ""
    if isinstance(v, float) and v != v:
        return ""
    s = str(v)
    return "" if s.lower() in ("nan", "none") else s


def _sorted(df: pd.DataFrame, by: str) -> pd.DataFrame:
    if df.empty:
        return df
    if by in ("risk", "risk_score"):
        return df.sort_values(["risk_score", "acq_date"], ascending=[False, False])
    if by in ("frp", "frp_mw"):
        return df.sort_values("frp_mw", ascending=False)
    if by in ("persistence", "persistence_count"):
        return df.sort_values("persistence_count", ascending=False)
    if by in ("recent", "date", "acq_date"):
        return df.sort_values("acq_date", ascending=False)
    if by == "severity":
        return df.assign(_o=df["severity"].map(SEVERITY_ORDER)).sort_values(
            ["_o", "risk_score"], ascending=[False, False]).drop(columns="_o")
    return df.sort_values("risk_score", ascending=False)


# ── public: alert queries ────────────────────────────────────────────────────
def list_alerts(filters: dict | None = None, limit: int = 500,
                sort_by: str = "risk_score") -> list[dict]:
    df = _apply_filters(_alerts(), filters)
    df = _sorted(df, sort_by).head(limit)
    return [_row_to_alert(r) for _, r in df.iterrows()]


def rank_alerts(by: str = "risk_score", filters: dict | None = None,
                limit: int = 5) -> list[dict]:
    return list_alerts(filters, limit=limit, sort_by=by)


def get_alert(alert_id: str) -> dict | None:
    df = _alerts()
    if df.empty:
        return None
    hit = df[df["alert_id"] == alert_id]
    if hit.empty:
        return None
    return _row_to_alert(hit.iloc[0])


def count_alerts(filters: dict | None = None) -> int:
    return len(_apply_filters(_alerts(), filters))


# ── public: investigation ────────────────────────────────────────────────────
def get_investigation(alert_id: str) -> dict:
    a = get_alert(alert_id)
    if a is None:
        return {"alert_id": alert_id, "found": False}

    prob_pct = round(a["model_class_probability"] * 100)
    day = "Night" if a["day_night"] == "N" else "Day" if a["day_night"] == "D" else "Unknown"
    haz = a["hazard_facility_type"] or "industrial facility"
    frp_ref = _frp_reference()

    why: list[str] = []
    if a["anomaly_flag"]:
        why.append("Pattern anomaly — matches neither the persistent-industrial nor the "
                   "natural-fire pattern learned by the model")
    if a["persistence_count"] >= 2:
        why.append(f"Repeat detections — {a['persistence_count']} in the observation window")
    if a["dist_nearest_facility_km"] is not None and a["dist_nearest_facility_km"] < 5:
        why.append(f"Near industrial infrastructure — {a['dist_nearest_facility_km']:.1f} km "
                   f"from {haz}")
    if a["land_cover_context"] == "Industrial Land Use":
        why.append("Industrial land-use match at the detection location")
    if a["frp_mw"] is not None and a["frp_mw"] >= max(frp_ref, 5):
        why.append(f"Elevated Fire Radiative Power — {a['frp_mw']:.1f} MW "
                   f"(vs ~{frp_ref:.1f} MW typical)")
    if a["day_night"] == "N":
        why.append("Night-time detection (less solar noise; consistent with a continuous source)")
    if a["predicted_label"] == "A":
        why.append("Model leans toward a persistent industrial thermal source")

    factors = [(str(x[0]), int(x[1])) for x in a["risk_factors"]
               if isinstance(x, (list, tuple)) and len(x) == 2]

    action, reason = _recommended_action(a)

    return {
        "alert_id": alert_id,
        "found": True,
        "header": {
            "output_class": a["output_class"],
            "output_class_short": a["output_class_short"],
            "output_class_code": a["output_class_code"],
            "location": _place_label(a),
            "state": a["state"],
            "district": a["district"],
            "in_india": a["in_india"],
            "risk_score": a["risk_score"],
            "severity": a["severity"],
            "status": a["status"],
            "model_class_probability_pct": prob_pct,
            "predicted_label": a["predicted_label"],
        },
        "detection": {
            "frp_mw": a["frp_mw"],
            "bt_kelvin": a["bt_kelvin"],
            "persistence_count": a["persistence_count"],
            "acq_date": a["acq_date"],
            "day_night": day,
            "coordinates": f"{a['lat']:.4f}, {a['lon']:.4f}",
            "instrument": "NASA FIRMS — VIIRS 375 m / MODIS 1 km",
        },
        "context": {
            "district": a["district"],
            "state": a["state"],
            "dist_nearest_facility_km": a["dist_nearest_facility_km"],
            "hazard_facility_type": a["hazard_facility_type"],
            "land_cover_context": a["land_cover_context"],
        },
        "why_flagged": why,
        "classification": {
            "output_class": a["output_class"],
            "predicted_label": a["predicted_label"],
            "prob_A": a["prob_A"],
            "prob_B_candidate": a["prob_B"],
            "anomaly_flag": a["anomaly_flag"],
            "framing": ("Anomalous departure from known persistent-industrial and "
                        "natural-fire patterns — not a confirmed fire. Requires human "
                        "verification."),
        },
        "risk_assessment": {
            "score": a["risk_score"],
            "severity": a["severity"],
            "factors": factors,
        },
        "recommended_action": {"action": action, "reason": reason},
        "narrative": a["narrative"],
        "coords": {"lat": a["lat"], "lon": a["lon"]},
    }


def _place_label(a: dict) -> str:
    """Location string from authoritative point-in-polygon geography.
    Never derives a state from a city name (requirement #6)."""
    if a.get("place"):
        return a["place"]
    if a.get("district") and a.get("state"):
        return f"{a['district']}, {a['state']}"
    if a.get("state"):
        return a["state"]
    if a.get("zone") and a["zone"] != "outside India":
        return f"{a['zone']} (outside India)"
    return f"{a['lat']:.3f}, {a['lon']:.3f}"


def _recommended_action(a: dict) -> tuple[str, str]:
    sev = a["severity"]
    if sev == "CRITICAL":
        return ("ESCALATE FOR FIELD VERIFICATION",
                "Persistent high-intensity thermal anomaly near industrial infrastructure "
                "— cannot be confirmed from satellite alone.")
    if sev == "HIGH":
        return ("PRIORITISE FOR ANALYST REVIEW",
                "Signal strength and industrial context warrant a closer look before "
                "the next satellite pass.")
    if sev == "MEDIUM":
        return ("MONITOR — RE-ASSESS ON NEXT PASS",
                "Moderate signal; confirm whether the detection persists.")
    return ("LOG — NO IMMEDIATE ACTION",
            "Low-confidence single detection with limited supporting context.")


# ── public: situation / summary ──────────────────────────────────────────────
def situation_summary(filters: dict | None = None) -> dict:
    df = _apply_filters(_alerts(), filters)
    total = len(df)
    active = int((df["status"] != "EXTINGUISHED").sum()) if total else 0

    def _sev(s):
        return int((df["severity"] == s).sum()) if total else 0

    def _cls(c):
        return int((df["output_class"] == c).sum()) if total else 0

    lo, hi = data_date_range()
    return {
        "total": total,
        "active": active,
        "severity": {
            "CRITICAL": _sev("CRITICAL"), "HIGH": _sev("HIGH"),
            "MEDIUM": _sev("MEDIUM"), "LOW": _sev("LOW"),
        },
        "classification": {
            "Industrial Fire": _cls(OC_INDUSTRIAL),
            "Persistent Source": _cls(OC_PERSISTENT),
            "Natural Fire": _cls(OC_NATURAL),
        },
        "by_status": {k: int(v) for k, v in df["status"].value_counts().items()} if total else {},
        "data_window": {"from": lo, "to": hi},
        "top_states": (
            df[df["state"].notna()]["state"].value_counts().head(5).to_dict() if total else {}
        ),
    }


def compare_regions(region_a: str, region_b: str,
                    filters: dict | None = None) -> dict:
    def side(name):
        f = dict(filters or {})
        f.pop("state", None)
        f["region"] = name
        f_states = geo.resolve_state_filter(None, name)
        if not f_states:
            # maybe a bare state name was passed
            cs = geo.canonical_state(name)
            f.pop("region", None)
            f["state"] = cs or name
        s = situation_summary(f)
        top = rank_alerts("risk_score", f, limit=3)
        return {
            "name": name.title(),
            "total": s["total"],
            "active": s["active"],
            "severity": s["severity"],
            "classification": s["classification"],
            "top_alerts": [
                {"alert_id": t["alert_id"], "risk_score": t["risk_score"],
                 "output_class_short": t["output_class_short"],
                 "location": _place_label(t)} for t in top
            ],
        }
    return {"a": side(region_a), "b": side(region_b)}


# ── public: analytics ────────────────────────────────────────────────────────
def _daily_summary() -> pd.DataFrame:
    """Per-day severity aggregation over the India monitoring dataset."""
    df = _alerts()
    if df.empty:
        return pd.DataFrame()
    g = df[df["acq_date"] != ""].groupby("acq_date")
    out = pd.DataFrame({
        "detections": g.size(),
        "critical": g["severity"].apply(lambda s: (s == "CRITICAL").sum()),
        "high": g["severity"].apply(lambda s: (s == "HIGH").sum()),
        "medium": g["severity"].apply(lambda s: (s == "MEDIUM").sum()),
        "low": g["severity"].apply(lambda s: (s == "LOW").sum()),
        "avg_frp": g["frp_mw"].mean().round(2),
        "max_frp": g["frp_mw"].max().round(2),
        "max_risk": g["risk_score"].max(),
    }).reset_index().sort_values("acq_date")
    return out


def analytics_summary(date_from: str | None = None,
                      date_to: str | None = None) -> dict:
    daily = _daily_summary()
    if not daily.empty and (date_from or date_to):
        if date_from:
            daily = daily[daily["acq_date"] >= date_from]
        if date_to:
            daily = daily[daily["acq_date"] <= date_to]

    df = _alerts()
    if df.empty:
        return {"daily": [], "by_class": {}, "by_severity": {}, "by_land_cover": {},
                "by_hazard": {}, "totals": {}}
    m = pd.Series(True, index=df.index)
    if date_from:
        m &= df["acq_date"] >= date_from
    if date_to:
        m &= df["acq_date"] <= date_to
    d = df[m]

    return {
        "daily": daily.to_dict("records"),
        "by_class": {OUTPUT_CLASS_SHORT.get(k, k): int(v)
                     for k, v in d["output_class"].value_counts().items()},
        "by_severity": {k: int(v) for k, v in d["severity"].value_counts().items()},
        "by_land_cover": {k: int(v) for k, v in
                          d["land_cover_context"].value_counts().head(10).items()},
        "by_hazard": {k: int(v) for k, v in
                      d["hazard_facility_type"].value_counts().head(10).items() if k},
        "totals": {
            "detections": int(len(d)),
            "avg_frp": round(float(d["frp_mw"].dropna().mean() or 0), 2),
            "max_frp": round(float(d["frp_mw"].dropna().max() or 0), 2),
            "critical": int((d["severity"] == "CRITICAL").sum()),
        },
    }


def baseline_comparison(filters: dict | None = None) -> dict | None:
    """
    Normal FRP band (median +/- IQR over the available history) vs the latest day.
    Returns None when there is not enough history to be meaningful — the UI shows
    an honest 'insufficient history' state rather than a fabricated number.
    """
    df = _apply_filters(_alerts(), filters)
    if df.empty:
        return None
    days = sorted(d for d in df["acq_date"].dropna().unique() if d)
    if len(days) < 3:
        return None
    latest = days[-1]
    hist = df[df["acq_date"] < latest]["frp_mw"].dropna()
    cur = df[df["acq_date"] == latest]["frp_mw"].dropna()
    if len(hist) < 10 or len(cur) < 1:
        return None
    q1, med, q3 = (float(hist.quantile(0.25)), float(hist.median()),
                   float(hist.quantile(0.75)))
    cur_med = float(cur.median())
    delta_pct = round((cur_med - med) / med * 100) if med else None
    return {
        "baseline_low": round(q1, 1), "baseline_median": round(med, 1),
        "baseline_high": round(q3, 1),
        "current_median": round(cur_med, 1),
        "current_date": latest,
        "delta_pct": delta_pct,
        "history_days": len(days) - 1,
        "history_n": int(len(hist)),
    }


# ── public: facilities ───────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _india_facilities() -> pd.DataFrame:
    f = pd.read_parquet(FACILITIES)
    f = f[f["country"] == "IND"].reset_index(drop=True)
    return f


@lru_cache(maxsize=1)
def _facility_index():
    """(BallTree over India facilities, facilities DataFrame). The single
    facility-association implementation — every caller that needs a
    detection→facility match reuses this, never builds its own tree."""
    from sklearn.neighbors import BallTree
    import numpy as np
    fac = _india_facilities()
    tree = BallTree(np.radians(fac[["lat", "lon"]].values), metric="haversine")
    return tree, fac


def _facility_record(idx: int) -> dict:
    _, fac = _facility_index()
    r = fac.iloc[int(idx)]
    name = r.get("name")
    return {
        "facility_id": str(r["facility_id"]),
        "name": name if isinstance(name, str) and name else "(unnamed site)",
        "facility_type": str(r["facility_type"]),
        "hazard_type": risk_engine.classify_hazard_type(str(r["facility_type"])),
        "source": str(r["source"]),
        "lat": float(r["lat"]), "lon": float(r["lon"]),
        "state": geo.state_for_point(float(r["lat"]), float(r["lon"])),
    }


def _facility_by_id(facility_id: str) -> dict | None:
    _, fac = _facility_index()
    hits = fac.index[fac["facility_id"].astype(str) == str(facility_id)]
    return _facility_record(int(hits[0])) if len(hits) else None


def facilities_with_activity(filters: dict | None = None, limit: int = 60,
                             radius_km: float = 10.0) -> list[dict]:
    alerts = _apply_filters(_alerts(), filters)
    if alerts.empty:
        return []
    try:
        import numpy as np
        tree, fac = _facility_index()
        q = np.radians(alerts[["lat", "lon"]].values)
        dist_rad, idx = tree.query(q, k=1)
        dist_km = dist_rad[:, 0] * 6371.0
        fac_idx = idx[:, 0]
    except Exception:
        return []
    fps = _facility_fingerprints_cached(db_signature())
    devs = _facility_deviations_cached(db_signature())

    alerts = alerts.reset_index(drop=True)
    rows = []
    for i in range(len(alerts)):
        if dist_km[i] > radius_km:
            continue
        rows.append((int(fac_idx[i]), float(dist_km[i]), alerts.iloc[i]))
    if not rows:
        return []

    groups: dict[int, list] = {}
    for fi, d, a in rows:
        groups.setdefault(fi, []).append((d, a))

    out = []
    for fi, items in groups.items():
        frec = _facility_record(fi)
        a_rows = [a for _, a in items]
        risks = [int(a["risk_score"]) for a in a_rows]
        classes = pd.Series([a["output_class_short"] for a in a_rows]).value_counts().to_dict()
        repeat = sum(1 for a in a_rows if int(a.get("persistence_count") or 1) >= 2)
        fp = fps.get(frec["facility_id"]) or {}
        dev = devs.get(frec["facility_id"]) or {}
        out.append({
            **frec,
            "nearby_detections": len(a_rows),
            "repeat_detections": repeat,
            "max_risk": max(risks) if risks else 0,
            "classes": classes,
            "min_distance_km": round(min(d for d, _ in items), 2),
            # additive thermal-fingerprint context (safe defaults when unavailable)
            "baseline_quality": fp.get("baseline_quality", "INSUFFICIENT_BASELINE"),
            "deviation_level": dev.get("thermal_deviation_level", "INSUFFICIENT_BASELINE"),
            "deviation_score": dev.get("thermal_deviation_score"),
        })
    out.sort(key=lambda r: (r["max_risk"], r["nearby_detections"]), reverse=True)
    return out[:limit]


# ── public: facility thermal fingerprinting ─────────────────────────────────
def _alerts_near_facility(flat: float, flon: float,
                          radius_km: float = _ff.ASSOC_RADIUS_KM,
                          exclude_ids: tuple = ()) -> list[dict]:
    """India detections within `radius_km` of a point (haversine), as alert dicts.
    `exclude_ids` drops an event's own detections for a leave-one-out baseline."""
    df = _alerts()
    if df.empty:
        return []
    import numpy as np
    la = np.radians(df["lat"].to_numpy(dtype=float))
    lo = np.radians(df["lon"].to_numpy(dtype=float))
    fla, flo = np.radians(flat), np.radians(flon)
    d = 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(
        np.sin((la - fla) / 2) ** 2
        + np.cos(fla) * np.cos(la) * np.sin((lo - flo) / 2) ** 2, 0, 1)))
    sub = df[d <= radius_km]
    if exclude_ids:
        sub = sub[~sub["alert_id"].isin(set(exclude_ids))]
    return [_row_to_alert(r) for _, r in sub.iterrows()]


@lru_cache(maxsize=4)
def _facility_fingerprints_cached(_sig: float) -> dict:
    """facility_id -> baseline dict, for every India facility that has >=1
    detection within the association radius."""
    df = _alerts()
    if df.empty:
        return {}
    import numpy as np
    tree, _fac = _facility_index()
    dist_rad, idx = tree.query(np.radians(df[["lat", "lon"]].to_numpy(dtype=float)), k=1)
    dist_km = dist_rad[:, 0] * 6371.0
    fac_idx = idx[:, 0]
    rows = [_row_to_alert(r) for _, r in df.iterrows()]
    groups: dict[int, list[dict]] = {}
    for i, row in enumerate(rows):
        if dist_km[i] <= _ff.ASSOC_RADIUS_KM:
            groups.setdefault(int(fac_idx[i]), []).append(row)
    out: dict[str, dict] = {}
    for fi, obs in groups.items():
        frec = _facility_record(fi)
        out[frec["facility_id"]] = {
            **_ff.build_facility_baseline(frec, obs),
            "facility_state": frec["state"], "hazard_type": frec["hazard_type"],
            "lat": frec["lat"], "lon": frec["lon"],
        }
    return out


def get_facility_fingerprint(facility_id: str,
                             exclude_event_id: str | None = None) -> dict | None:
    """Thermal baseline for one facility. `exclude_event_id` leaves that event's
    own detections out (so the baseline is 'the facility's other activity')."""
    frec = _facility_by_id(facility_id)
    if frec is None:
        return None
    exclude_ids: tuple = ()
    if exclude_event_id:
        ev = get_event(exclude_event_id)
        if ev:
            exclude_ids = tuple(ev.get("alert_ids") or [])
    if not exclude_ids:
        cached = _facility_fingerprints_cached(db_signature()).get(str(facility_id))
        if cached is not None:
            return cached
    obs = _alerts_near_facility(frec["lat"], frec["lon"], exclude_ids=exclude_ids)
    return {**_ff.build_facility_baseline(frec, obs),
            "facility_state": frec["state"], "hazard_type": frec["hazard_type"],
            "lat": frec["lat"], "lon": frec["lon"]}


def get_event_deviation(event_id: str) -> dict | None:
    """How far a thermal event departs from its nearest facility's baseline."""
    ev = get_event(event_id)
    if not ev:
        return None
    import numpy as np
    tree, _fac = _facility_index()
    d_rad, idx = tree.query(
        np.radians([[ev["centroid_lat"], ev["centroid_lon"]]]), k=1)
    dist_km = float(d_rad[0, 0] * 6371.0)
    if dist_km > _ff.ASSOC_RADIUS_KM:
        return {
            "event_id": event_id, "facility_id": None, "facility_name": None,
            "dist_facility_km": round(dist_km, 2),
            "thermal_deviation_score": None,
            "thermal_deviation_level": "NO_FACILITY",
            "thermal_behavior_class": "INSUFFICIENT_BASELINE",
            "baseline_quality": "NO_FACILITY",
            "signals": [], "evidence": [], "baseline": None,
            "interpretation": "No known facility within the association radius.",
            "note": (f"Nearest known facility is {dist_km:.1f} km away — outside the "
                     f"{_ff.ASSOC_RADIUS_KM:.0f} km association radius; no facility "
                     f"baseline applies to this event."),
        }
    frec = _facility_record(int(idx[0, 0]))
    # Full facility profile (NOT leave-one-out): with a ~5-day FIRMS window most
    # facilities have a single burst of activity, so excluding the scored event
    # collapses every baseline. The event's peak is still compared against the
    # facility's distribution — a spike stands out even when it is part of it.
    baseline = get_facility_fingerprint(frec["facility_id"])
    dev = _ff.compare_event_to_baseline(ev, baseline)
    overlap = len(set(ev.get("alert_ids") or []))
    total = (baseline or {}).get("observation_count") or 0
    dev.update({
        "event_id": event_id, "dist_facility_km": round(dist_km, 2),
        "baseline": baseline,
        "baseline_overlap": {"event_obs": overlap, "baseline_obs": total,
                             "dominated": total > 0 and overlap / total >= 0.6},
    })
    return dev


def get_alert_deviation(alert_id: str) -> dict | None:
    ev = get_event_for_alert(alert_id)
    return get_event_deviation(ev["event_id"]) if ev else None


@lru_cache(maxsize=4)
def _facility_deviations_cached(_sig: float) -> dict:
    """facility_id -> the highest-deviation event assessment for that facility."""
    best: dict[str, dict] = {}
    for e in _events_cached(db_signature()):
        dev = get_event_deviation(e.event_id)
        fid = dev.get("facility_id") if dev else None
        if not fid:
            continue
        sc = dev.get("thermal_deviation_score")
        if fid not in best:
            best[fid] = dev
        elif sc is not None and (best[fid].get("thermal_deviation_score") or -1) < sc:
            best[fid] = dev
    return best


def rank_facilities_by_deviation(limit: int = 10) -> list[dict]:
    devs = _facility_deviations_cached(db_signature())
    rows = []
    for fid, dev in devs.items():
        b = dev.get("baseline") or {}
        rows.append({
            "facility_id": fid,
            "facility_name": dev.get("facility_name") or b.get("facility_name"),
            "facility_type": b.get("facility_type"),
            "state": b.get("facility_state"),
            "thermal_deviation_score": dev.get("thermal_deviation_score"),
            "thermal_deviation_level": dev.get("thermal_deviation_level"),
            "thermal_behavior_class": dev.get("thermal_behavior_class"),
            "baseline_quality": b.get("baseline_quality", "INSUFFICIENT_BASELINE"),
            "evidence": dev.get("evidence", []),
            "event_id": dev.get("event_id"),
        })
    rows.sort(key=lambda r: (r["thermal_deviation_score"] is not None,
                             r["thermal_deviation_score"] or 0), reverse=True)
    return rows[:limit]


def find_abnormal_facilities(limit: int = 10,
                             min_level: str = "ABNORMAL") -> list[dict]:
    order = _ff.DEVIATION_LEVELS
    cut = order.index(min_level) if min_level in order else 2
    return [r for r in rank_facilities_by_deviation(limit=200)
            if r["thermal_deviation_level"] in order[cut:]][:limit]


def facility_fingerprint_summary() -> dict:
    fps = _facility_fingerprints_cached(db_signature())
    devs = _facility_deviations_cached(db_signature())
    total = len(fps)
    insufficient = sum(1 for v in fps.values()
                       if v.get("baseline_quality") == "INSUFFICIENT_BASELINE")
    by_level: dict[str, int] = {}
    for d in devs.values():
        lvl = d.get("thermal_deviation_level", "INSUFFICIENT_BASELINE")
        by_level[lvl] = by_level.get(lvl, 0) + 1
    abnormal = by_level.get("ABNORMAL", 0) + by_level.get("HIGHLY_ABNORMAL", 0)
    return {
        "facilities_with_activity": total,
        "baseline_available": total - insufficient,
        "insufficient_baseline": insufficient,
        "events_assessed": len(devs),
        "abnormal_events": abnormal,
        "by_level": by_level,
    }


# ── public: incidents ────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def incidents() -> list[dict]:
    if not INCIDENT_SCORES.exists():
        return []
    df = pd.read_parquet(INCIDENT_SCORES)
    recs = []
    for _, r in df.iterrows():
        recs.append({
            "incident_id": r["incident_id"],
            "name": r["name"],
            "date": str(r["date"]),
            "state": r.get("state"),
            "facility_type": r.get("facility_type"),
            "lat": float(r["lat"]), "lon": float(r["lon"]),
            "predicted_label": r.get("predicted_label"),
            "prob_A": _num(r.get("prob_A")),
            "prob_B_candidate": _num(r.get("prob_B_candidate")),
            "anomaly_flag": int(r.get("anomaly_flag") or 0),
            "dist_nearest_facility_km": _num(r.get("dist_nearest_facility_km")),
            "description": r.get("description"),
        })
    return recs


def outside_india_alerts(limit: int = 5000) -> list[dict]:
    """FIRMS points that fall in the ingestion bounding box but outside every
    Indian state polygon (Sri Lanka, Pakistan, ...). Kept, plotted on the map as
    an explicit 'regional context' layer — never moved into India, never dropped."""
    df = _all_alerts()
    if df.empty:
        return []
    df = df[~df["in_india"]].head(limit)
    return [_row_to_alert(r) for _, r in df.iterrows()]


def geo_audit() -> dict:
    """Development validation for the plotted detection layer (requirement #10)."""
    df = _all_alerts()
    if df.empty:
        return {"plotted": 0}
    rep = geo.audit_points(df, "lat", "lon", sample=6)
    rep["india_dataset_note"] = (
        "The FIRMS ingestion used a rectangular India bounding box "
        f"(lat {geo.INDIA_BBOX[0]}-{geo.INDIA_BBOX[1]}, lon {geo.INDIA_BBOX[2]}-"
        f"{geo.INDIA_BBOX[3]}), which also captures parts of neighbouring "
        "countries. Points are plotted at their true coordinates; only points "
        "inside an Indian state polygon are counted as India alerts."
    )
    return rep


# ── public: thermal events ────────────────────────────────────────────────────
@lru_cache(maxsize=8)
def _events_cached(_sig: float) -> list:
    from src.intelligence.clustering import cluster_alerts
    alerts_list = [_row_to_alert(r) for _, r in _alerts().iterrows()]
    return cluster_alerts(alerts_list)


def _event_to_dict(e) -> dict:
    from dataclasses import asdict
    return asdict(e)


def _get_event_observations(e) -> list[dict]:
    df = _alerts()
    obs_df = df[df["alert_id"].isin(e.alert_ids)]
    return [_row_to_alert(r) for _, r in obs_df.iterrows()]


def list_events(filters: dict | None = None, sort_by: str = "risk_score",
                limit: int = 500) -> list[dict]:
    events = _events_cached(db_signature())
    dicts = [_event_to_dict(e) for e in events]
    if filters:
        if filters.get("severity"):
            sevs = {s.upper() for s in _as_list(filters["severity"])}
            dicts = [d for d in dicts if d["severity"] in sevs]
        states = geo.resolve_state_filter(_as_list(filters.get("state")), filters.get("region"))
        if states:
            dicts = [d for d in dicts if d.get("state") in states]
        if filters.get("min_risk"):
            dicts = [d for d in dicts if d["risk_score"] >= int(filters["min_risk"])]
    if sort_by in ("frp", "frp_mw"):
        dicts.sort(key=lambda d: d.get("peak_frp_mw") or 0, reverse=True)
    else:
        dicts.sort(key=lambda d: d.get("risk_score", 0), reverse=True)
    return dicts[:limit]


def get_event(event_id: str) -> dict | None:
    events = _events_cached(db_signature())
    for e in events:
        if e.event_id == event_id:
            return _event_to_dict(e)
    return None


def get_event_for_alert(alert_id: str) -> dict | None:
    events = _events_cached(db_signature())
    for e in events:
        if alert_id in e.alert_ids:
            return _event_to_dict(e)
    return None


def get_event_fingerprint(event_id: str) -> dict | None:
    from src.intelligence.fingerprint import compute_fingerprint
    events = _events_cached(db_signature())
    for e in events:
        if e.event_id == event_id:
            return compute_fingerprint(_get_event_observations(e))
    return None


def get_event_evidence(event_id: str) -> dict | None:
    from src.intelligence.evidence import build_evidence
    events = _events_cached(db_signature())
    for e in events:
        if e.event_id == event_id:
            return build_evidence(e, _get_event_observations(e))
    return None


def get_event_evolution(event_id: str) -> dict | None:
    from src.intelligence.evolution import build_evolution
    events = _events_cached(db_signature())
    for e in events:
        if e.event_id == event_id:
            return build_evolution(_get_event_observations(e))
    return None


def get_event_trajectory(event_id: str) -> dict | None:
    from src.intelligence.early_warning import compute_trajectory
    evo = get_event_evolution(event_id)
    if not evo:
        return None
    return compute_trajectory(evo["frames"])


def find_increasing_risk_events(limit: int = 10) -> list[dict]:
    events = _events_cached(db_signature())
    result = []
    for e in events:
        traj = get_event_trajectory(e.event_id)
        if traj and traj.get("trajectory") == "INCREASING":
            d = _event_to_dict(e)
            d["trajectory"] = traj
            result.append(d)
    result.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
    return result[:limit]


def events_situation() -> dict:
    """Summary counts for the event layer (Command Center KPIs)."""
    events = _events_cached(db_signature())
    total = len(events)
    high_risk = sum(1 for e in events if e.risk_score >= 60)
    persistent = sum(1 for e in events if e.observation_count >= 3)
    early_warn = 0
    for e in events:
        traj = get_event_trajectory(e.event_id)
        if traj and traj.get("state") in ("EARLY WARNING", "HIGH PRIORITY"):
            early_warn += 1
    return {
        "total_events": total,
        "high_risk_events": high_risk,
        "persistent_sources": persistent,
        "early_warnings": early_warn,
    }


def clear_caches() -> None:
    _load_alerts_cached.cache_clear()
    _events_cached.cache_clear()
    data_date_range.cache_clear()
    _india_facilities.cache_clear()
    _facility_index.cache_clear()
    _facility_fingerprints_cached.cache_clear()
    _facility_deviations_cached.cache_clear()
    incidents.cache_clear()
    geo._resolve_cached.cache_clear()
