"""Facilities — what is happening around known industrial infrastructure."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import data, state
from dashboard import theme as T
from dashboard.components import filterbar, ui
from dashboard.shell import topbar


def render() -> None:
    topbar("Facilities")
    ui.page_header("Facilities",
                   "Known Indian industrial facilities with nearby thermal detections")

    filterbar.render(key="fac_fb", show_status=False, show_class=True)
    radius = st.slider("Search radius (km)", 2, 25, 10, key="fac_radius")

    facs = data.FACILITIES(state.filters(), limit=120, radius_km=float(radius))
    if not facs:
        ui.empty_state("No known facilities have nearby detections for this scope.",
                       "Increase the radius or widen the filters.")
        return

    ui.section(f"{len(facs)} facilities with nearby activity", f"within {radius} km")
    df = pd.DataFrame([{
        "Facility": f["name"],
        "Type": f["hazard_type"],
        "State": f.get("state") or "—",
        "Source": f["source"],
        "Nearby": f["nearby_detections"],
        "Repeat": f["repeat_detections"],
        "Max risk": f["max_risk"],
        "Nearest (km)": f["min_distance_km"],
    } for f in facs])
    st.dataframe(df, hide_index=True, use_container_width=True, height=430)

    ui.section("Focus a facility")
    names = [f["name"] for f in facs[:40]]
    pick = st.selectbox("Facility", names, key="fac_pick")
    fac = next((f for f in facs if f["name"] == pick), None)
    if fac:
        cc = st.columns(4)
        cc[0].metric("Nearby detections", fac["nearby_detections"])
        cc[1].metric("Repeat (persist ≥2)", fac["repeat_detections"])
        cc[2].metric("Max nearby risk", f'{fac["max_risk"]}/100')
        cc[3].metric("Nearest detection", f'{fac["min_distance_km"]} km')
        st.markdown(f'<div class="mini">Classes nearby: '
                    + " · ".join(f'{k} {v}' for k, v in fac["classes"].items())
                    + '</div>', unsafe_allow_html=True)
        if st.button("Show this area on the map  →", key="fac_tomap"):
            state.set_filters({"state": [fac["state"]] if fac.get("state") else [],
                               "max_dist_facility_km": float(radius)})
            state.request_nav("Map Explorer"); st.rerun()
