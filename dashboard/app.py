"""
SIH26162 — India Fire Intelligence Platform.

Streamlit shell. Presentation only: every page reads data through dashboard/data.py
-> src/intelligence/ -> the existing src/alerting + ML outputs. No business logic
lives here.

Run:  streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from dashboard import data, state
from dashboard import theme as T
from src.ingestion.config import FIRMS_MAP_KEY

T.inject("India Fire Intelligence")
state.init()
data.ensure_seeded()

_refresh = data.maybe_refresh()
if _refresh["status"] == "refreshed":
    st.toast(f"Live data: {_refresh['rows']} hotspots fetched from NASA FIRMS NRT.", icon="🛰️")
elif _refresh["status"] == "error":
    st.toast("FIRMS refresh failed — showing cached data.", icon="⚠️")

from dashboard import shell                                    # noqa: E402
from dashboard.views import (alerts, analytics, command_center, facilities,      # noqa: E402
                             investigation, limitations, map_explorer, model, reports)

_PAGES = {
    "Command Center": (command_center.render, ":material/dashboard:", "Overview & summary"),
    "Alerts": (alerts.render, ":material/notifications_active:", "Active alert feed"),
    "Investigation": (investigation.render, ":material/frame_inspect:", "Detailed analysis"),
    "Map Explorer": (map_explorer.render, ":material/map:", "Live detection map"),
    "Analytics": (analytics.render, ":material/insights:", "Trends & baseline"),
    "Facilities": (facilities.render, ":material/factory:", "Industrial infrastructure"),
    "Reports / GIS": (reports.render, ":material/description:", "GIS & downloads"),
    "Model": (model.render, ":material/account_tree:", "Pipeline & performance"),
    "Limitations": (limitations.render, ":material/info:", "Data & system limits"),
}

# apply a pending navigation request from a button / the agent
_requested = state.take_nav_request()

pages = [st.Page(fn, title=name, icon=icon, url_path=name.lower().replace(" / ", "-").replace(" ", "-"),
                 default=(name == "Command Center"))
         for name, (fn, icon, _sub) in _PAGES.items()]

with st.sidebar:
    shell.brand()

nav = st.navigation(pages, position="sidebar")

with st.sidebar:
    if FIRMS_MAP_KEY:
        shell.sidebar_refresh_card()
    shell.sidebar_agent_card()
    st.markdown(
        '<div style="font-size:9px;color:#5a6472;padding:10px 6px;line-height:1.6">'
        'Anomalous departures from known thermal patterns — <b>not</b> confirmed '
        'fires. Every alert requires human verification.</div>',
        unsafe_allow_html=True,
    )

if _requested and _requested != nav.title:
    # st.navigation can't be re-pointed mid-run; switch on this run.
    try:
        st.switch_page(next(p for p in pages if p.title == _requested))
    except Exception:
        pass

nav.run()
