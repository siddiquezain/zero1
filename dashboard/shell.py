"""Application shell: sidebar brand block + top status bar."""
from __future__ import annotations

import datetime as _dt

import streamlit as st

from dashboard import data, state
from dashboard import theme as T
from dashboard.agent import panel as agent_panel
from src.ingestion.refresh import _age_hours as _firms_age_hours
from src.ingestion.config import FIRMS_MAP_KEY


def _ist_now() -> str:
    return _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=5, minutes=30))).strftime("%H:%M IST")


def brand() -> None:
    st.markdown(
        '<div class="brand"><div class="brand-mark">🔥</div><div>'
        '<div class="brand-id">SIH · 26162</div>'
        '<div class="brand-name">India Fire Intelligence</div>'
        '<div class="brand-sub">AI · Geospatial · Near-real-time</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )


def sidebar_refresh_card() -> None:
    """Sidebar FIRMS refresh control — only rendered when FIRMS_MAP_KEY is set."""
    age = _firms_age_hours()
    if age < 2:
        age_str = "just now"
    elif age < 48:
        age_str = f"{age:.0f}h ago"
    else:
        age_str = f"{age / 24:.0f} days ago"
    st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="panel" style="padding:9px 12px">'
        f'<div style="font-size:11px;font-weight:700">FIRMS NRT Feed</div>'
        f'<div style="font-size:10px;color:#5a6472;margin-top:2px">Last fetch: {age_str}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if st.button("↻  Refresh Data", key="side_refresh", use_container_width=True):
        with st.spinner("Fetching live FIRMS data…"):
            result = data.maybe_refresh(max_age_hours=0)
        if result["status"] == "refreshed":
            st.toast(f"Refreshed: {result['rows']} hotspots loaded.", icon="🛰️")
            st.rerun()
        elif result["status"] == "no_data":
            st.toast("FIRMS returned no data — try again shortly.", icon="⚠️")
        elif result["status"] == "error":
            st.toast(f"Error: {result.get('error', 'unknown')}", icon="🚨")


def sidebar_agent_card() -> None:
    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="panel" style="padding:11px 12px">'
        '<div style="font-size:11.5px;font-weight:700">Fire Intelligence Agent</div>'
        '<div style="font-size:10px;color:#5a6472;margin-top:3px;line-height:1.5">'
        'Ask questions in plain English — read-only.</div></div>',
        unsafe_allow_html=True,
    )
    if st.button("⌘  Ask Agent", key="side_ask_agent", use_container_width=True, type="primary"):
        agent_panel.open_dialog(_agent_context())


def _agent_context() -> dict:
    return {
        "page": st.session_state.get("_active_page"),
        "filters": state.filters(),
        "focus_alert_id": st.session_state.get("focus_alert_id"),
    }


def _nrt_badge() -> str:
    """Green LIVE dot when FIRMS key is set and data is fresh (<2h); amber snapshot otherwise."""
    if FIRMS_MAP_KEY and _firms_age_hours() < 2.0:
        return ('<span class="dot" style="background:#22c55e;box-shadow:0 0 0 3px rgba(34,197,94,0.2)"></span>'
                'LIVE NRT')
    return ('<span class="dot" style="background:#f59e0b;box-shadow:0 0 0 3px rgba(245,158,11,0.2)"></span>'
            'NRT SNAPSHOT')


def topbar(active_page: str) -> None:
    st.session_state["_active_page"] = active_page
    s = data.S()
    crit = s["severity"]["CRITICAL"]
    lo, hi = data.DATE_RANGE()
    st.markdown(
        f'<div class="topbar">'
        f'<div style="display:flex;align-items:center;gap:14px">'
        f'<div class="tb-pills">'
        f'<span class="tb-pill">{_nrt_badge()}</span>'
        f'<span class="tb-pill">{_ist_now()}</span>'
        f'<span class="tb-pill">VIIRS 375m / MODIS 1km</span>'
        f'<span class="tb-pill">window {lo} → {hi}</span>'
        f'</div>'
        f'<span class="tb-title">{active_page}</span>'
        f'</div>'
        f'<div class="tb-right">'
        f'<span class="tb-badge">🔔<b>{crit}</b></span>'
        f'<span>Team ZeroOne · Operator</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
