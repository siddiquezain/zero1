"""
Cached bridge from the Streamlit layer to src/intelligence.

The dashboard imports ONLY this module + src.intelligence (never src.alerting
directly). Caching lives here; src/intelligence stays framework-agnostic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.intelligence import actions, queries            # noqa: E402
from src.intelligence.agent import ask as agent_ask      # noqa: E402  (re-export)


def ensure_seeded() -> None:
    actions.ensure_seeded()


def _sig() -> float:
    return queries.db_signature()


@st.cache_data(ttl=30, show_spinner=False)
def situation(_sig: float, filters: dict | None = None) -> dict:
    return queries.situation_summary(filters)


@st.cache_data(ttl=30, show_spinner=False)
def alerts(_sig: float, filters: dict | None, limit: int, sort_by: str) -> list[dict]:
    return queries.list_alerts(filters, limit=limit, sort_by=sort_by)


@st.cache_data(ttl=30, show_spinner=False)
def rank(_sig: float, by: str, filters: dict | None, limit: int) -> list[dict]:
    return queries.rank_alerts(by, filters, limit)


@st.cache_data(ttl=30, show_spinner=False)
def investigation(_sig: float, alert_id: str) -> dict:
    return queries.get_investigation(alert_id)


@st.cache_data(ttl=30, show_spinner=False)
def analytics(_sig: float, date_from: str | None, date_to: str | None) -> dict:
    return queries.analytics_summary(date_from, date_to)


@st.cache_data(ttl=30, show_spinner=False)
def baseline(_sig: float, filters: dict | None) -> dict | None:
    return queries.baseline_comparison(filters)


@st.cache_data(ttl=120, show_spinner="Locating nearby facilities…")
def facilities(_sig: float, filters: dict | None, limit: int, radius_km: float) -> list[dict]:
    return queries.facilities_with_activity(filters, limit=limit, radius_km=radius_km)


@st.cache_data(ttl=600, show_spinner=False)
def incidents() -> list[dict]:
    return queries.incidents()


@st.cache_data(ttl=30, show_spinner=False)
def _outside(_sig: float) -> list[dict]:
    return queries.outside_india_alerts()


@st.cache_data(ttl=30, show_spinner=False)
def _audit(_sig: float) -> dict:
    return queries.geo_audit()


@st.cache_data(ttl=30, show_spinner=False)
def date_range(_sig: float) -> tuple[str, str]:
    return queries.data_date_range()


# ── convenience (no leading _sig for callers) ───────────────────────────────
def S(filters=None):            return situation(_sig(), filters)
def A(filters=None, limit=500, sort_by="risk_score"):  return alerts(_sig(), filters, limit, sort_by)
def R(by="risk_score", filters=None, limit=5):         return rank(_sig(), by, filters, limit)
def INV(alert_id):              return investigation(_sig(), alert_id)
def ANALYTICS(df=None, dt=None):return analytics(_sig(), df, dt)
def BASELINE(filters=None):     return baseline(_sig(), filters)
def FACILITIES(filters=None, limit=60, radius_km=10.0): return facilities(_sig(), filters, limit, radius_km)
def DATE_RANGE():               return date_range(_sig())
def outside_india():            return _outside(_sig())
def geo_audit():                return _audit(_sig())


# ── mutations (manual UI only) ─────────────────────────────────────────────
def set_status(alert_id: str, action: str) -> dict:
    r = actions.set_alert_status(alert_id, action)
    st.cache_data.clear()
    return r


def run_pipeline() -> dict:
    r = actions.run_pipeline_fresh()
    st.cache_data.clear()
    return r


# ── read-only exports ─────────────────────────────────────────────────────
def export_geojson(filters=None) -> str:  return actions.export_geojson(filters)
def export_csv(filters=None) -> str:      return actions.export_csv(filters)
def geojson_preview(filters=None, n=3) -> str: return actions.geojson_preview(filters, n)
def incident_report(filters=None, fmt="markdown") -> str:
    return actions.build_incident_report(filters, fmt=fmt)
