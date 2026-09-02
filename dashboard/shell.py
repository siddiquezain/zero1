"""Application shell: sidebar brand block + top status bar."""
from __future__ import annotations

import datetime as _dt

import streamlit as st

from dashboard import data, state
from dashboard import theme as T
from dashboard.agent import panel as agent_panel


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


def topbar(active_page: str) -> None:
    st.session_state["_active_page"] = active_page
    s = data.S()
    crit = s["severity"]["CRITICAL"]
    lo, hi = data.DATE_RANGE()
    st.markdown(
        f'<div class="topbar">'
        f'<div style="display:flex;align-items:center;gap:14px">'
        f'<div class="tb-pills">'
        f'<span class="tb-pill"><span class="dot"></span>LIVE</span>'
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
