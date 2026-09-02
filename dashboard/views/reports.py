"""Reports / GIS — filter-aware GeoJSON / CSV export + incident report."""
from __future__ import annotations

import datetime as _dt

import streamlit as st

from dashboard import data, state
from dashboard.components import filterbar, ui
from dashboard.shell import topbar


def render() -> None:
    topbar("Reports / GIS")
    ui.page_header("Reports / GIS",
                   "Export the current picture for GIS tools or a briefing — respects active filters")

    filterbar.render(key="rep_fb")
    f = state.filters()
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M")
    n = len(data.A(f, limit=100000))

    ui.section("GIS export", f"{n} alerts in scope")
    c = st.columns(3)
    c[0].download_button("Download GeoJSON", data=data.export_geojson(f),
                         file_name=f"sih26162_alerts_{stamp}.geojson",
                         mime="application/geo+json", use_container_width=True)
    c[1].download_button("Download CSV", data=data.export_csv(f),
                         file_name=f"sih26162_alerts_{stamp}.csv",
                         mime="text/csv", use_container_width=True)
    c[2].download_button("Incident report (Markdown)",
                         data=data.incident_report(f, "markdown"),
                         file_name=f"sih26162_incident_report_{stamp}.md",
                         mime="text/markdown", use_container_width=True)

    ui.section("GeoJSON preview", "first 3 features")
    st.code(data.geojson_preview(f, 3), language="json")

    ui.section("Incident report preview")
    st.markdown(data.incident_report(f, "markdown"))
