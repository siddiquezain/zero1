"""Facilities — what is happening around known industrial infrastructure."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import data, state
from dashboard import theme as T
from dashboard.components import filterbar, ui
from dashboard.shell import topbar

# fixed detection→facility search radius (matches the fingerprint association radius)
_RADIUS_KM = 10.0


def render() -> None:
    topbar("Facilities")
    ui.page_header("Facilities",
                   "Known Indian industrial facilities with nearby thermal detections")

    filterbar.render(key="fac_fb", show_status=False, show_class=True)

    facs = data.FACILITIES(state.filters(), limit=120, radius_km=_RADIUS_KM)
    if not facs:
        ui.empty_state("No known facilities have nearby detections for this scope.",
                       "Widen the filters.")
        return

    ui.section(f"{len(facs)} facilities with nearby activity",
               f"within {_RADIUS_KM:.0f} km")
    df = pd.DataFrame([{
        "Facility": f["name"],
        "Type": f["hazard_type"],
        "State": f.get("state") or "—",
        "Nearby": f["nearby_detections"],
        "Repeat": f["repeat_detections"],
        "Max risk": f["max_risk"],
        "Baseline": f.get("baseline_quality", "—"),
        "Deviation": (f'{f["deviation_score"]}/100 · {f["deviation_level"]}'
                      if f.get("deviation_score") is not None else f.get("deviation_level", "—")),
        "Nearest (km)": f["min_distance_km"],
    } for f in facs])
    st.dataframe(df, hide_index=True, use_container_width=True, height=430)
    st.markdown(
        f'<div class="mini" style="color:{T.T2};margin-top:2px">Baseline = the '
        f'facility\'s own observed thermal profile (INSUFFICIENT_BASELINE when history '
        f'is too thin — the FIRMS NRT window is ~5 days). Deviation is a behavioural '
        f'signal, separate from the risk score.</div>', unsafe_allow_html=True)

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

        fp = data.FACILITY_FP(fac["facility_id"])
        if fp:
            ui.section("Thermal baseline", "the facility's own observed profile")
            if fp.get("baseline_quality") == "INSUFFICIENT_BASELINE":
                ui.empty_state(
                    "Insufficient history for a baseline.",
                    (fp.get("notes") or [""])[0]
                    or "Needs ≥6 detections across ≥2 days within 10 km.")
            else:
                frp = fp.get("frp") or {}
                bt = fp.get("bt") or {}
                bc = st.columns(4)
                bc[0].metric("Typical peak FRP",
                             f'{frp.get("median")} MW' if frp else "—")
                bc[1].metric("Typical brightness",
                             f'{bt.get("median")} K' if bt else "—")
                bc[2].metric("Typical persistence", fp.get("median_persistence") or "—")
                bc[3].metric("Typical timing", fp.get("typical_day_night") or "—")
                st.markdown(
                    f'<div class="mini" style="color:{T.T2}">Window '
                    f'{fp.get("baseline_start")} → {fp.get("baseline_end")} · '
                    f'{fp.get("observation_count")} obs / {fp.get("active_days")} days · '
                    f'quality {fp.get("baseline_quality")}. Short-window profile — not a '
                    f'long-run archive.</div>', unsafe_allow_html=True)
        if st.button("Show this area on the map  →", key="fac_tomap"):
            state.set_filters({"state": [fac["state"]] if fac.get("state") else [],
                               "max_dist_facility_km": _RADIUS_KM})
            state.request_nav("Map Explorer"); st.rerun()
