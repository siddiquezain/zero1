"""Map Explorer — WHERE are the thermal anomalies? All map layers + click-to-investigate."""
from __future__ import annotations

import pandas as pd
import pydeck as pdk
import streamlit as st

from dashboard import data, state
from dashboard import theme as T
from dashboard.components import filterbar, mapview, ui
from dashboard.shell import topbar


def render() -> None:
    topbar("Map Explorer")
    ui.page_header("Map Explorer",
                   "Every scored thermal detection at its true coordinates over India")

    filterbar.render(key="map_fb", show_status=False)

    ctrl, canvas = st.columns([1, 4.2], gap="medium")
    with ctrl:
        ui.section("Layers")
        colour_by = st.radio("Colour markers by", ["class", "severity"],
                             index=0 if st.session_state.get("map_colour_by") == "class" else 1,
                             key="map_cb", format_func=str.title)
        st.session_state["map_colour_by"] = colour_by
        show_inc = st.checkbox("Confirmed incidents", value=st.session_state.get("show_incidents", True),
                               key="map_inc")
        show_fac = st.checkbox("Industrial facilities", value=st.session_state.get("show_facilities", False),
                               key="map_fac")
        show_out = st.checkbox("Regional context (outside India)",
                               value=st.session_state.get("show_outside", False), key="map_out",
                               help="FIRMS points that fall in the ingestion bounding box but "
                                    "outside every Indian state polygon (Sri Lanka, Pakistan, …). "
                                    "Shown at their true location, dimmed — not part of the India "
                                    "monitoring dataset.")
        show_events = st.checkbox(
            "Thermal Events",
            value=False,
            key="map_events",
            help="Event centroids — one amber circle per clustered thermal event.",
        )
        st.session_state["show_incidents"] = show_inc
        st.session_state["show_facilities"] = show_fac
        st.session_state["show_outside"] = show_out
        st.session_state["show_events"] = show_events
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
        ui.legend([("Industrial Fire", T.CLS_INDUSTRIAL), ("Persistent Source", T.CLS_PERSISTENT),
                   ("Natural Fire", T.CLS_NATURAL), ("Confirmed Incident", T.CLS_INCIDENT),
                   ("Facility", T.ACCENT), ("Outside India", "#7b8493")] if colour_by == "class" else
                  [("Critical", T.CRIT), ("High", T.HIGH), ("Medium", T.MED), ("Low", T.LOW),
                   ("Outside India", "#7b8493")])

    with canvas:
        alerts = data.A(state.filters(), limit=3000, sort_by="risk_score")
        ui.section("Detection Map", f"{len(alerts)} India detections")
        deck = mapview.build_deck(
            alerts, colour_by=colour_by,
            incidents=data.incidents() if show_inc else None,
            facilities=data.FACILITIES(state.filters(), limit=200, radius_km=12) if show_fac else None,
            outside=data.outside_india() if show_out else None,
            focus_alert_id=st.session_state.get("focus_alert_id"),
        )
        st.pydeck_chart(deck, use_container_width=True, height=520)

        if show_events:
            ev_list = data.EVENTS(state.filters(), limit=300)
            if ev_list:
                ev_pts = [
                    {
                        "lat": e["centroid_lat"],
                        "lon": e["centroid_lon"],
                        "label": f'EVENT #{e["event_id"]} · {e["observation_count"]} obs · risk {e["risk_score"]}',
                    }
                    for e in ev_list
                ]
                ev_layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=ev_pts,
                    get_position=["lon", "lat"],
                    get_radius=8000,
                    get_fill_color=[245, 158, 11, 180],
                    pickable=True,
                )
                ev_deck = pdk.Deck(
                    layers=[ev_layer],
                    initial_view_state=deck.initial_view_state,
                    tooltip={"text": "{label}"},
                    map_style=deck.map_style,
                )
                ui.section(f"{len(ev_list)} thermal events", "centroid overlay")
                st.markdown(
                    f'<div style="font-size:10px;color:{T.T2};margin-bottom:4px">'
                    f'Amber circles = event centroids. Click a detection marker above to investigate.</div>',
                    unsafe_allow_html=True,
                )
                st.pydeck_chart(ev_deck, use_container_width=True, height=300)

    # ── development data-validation report (requirement #10) ──────────────
    aud = data.geo_audit()
    with st.expander(f"Data validation — {aud.get('in_india', 0)} India · "
                     f"{aud.get('outside_india', 0)} outside India · "
                     f"{aud.get('outside_india_bbox', 0)} outside bbox"):
        st.markdown(f'<div class="mini" style="line-height:1.7">'
                    f'{aud.get("india_dataset_note", "")}</div>', unsafe_allow_html=True)
        m = st.columns(4)
        m[0].metric("Plotted total", aud.get("plotted", 0))
        m[1].metric("Inside India", aud.get("in_india", 0))
        m[2].metric("Outside India", aud.get("outside_india", 0))
        m[3].metric("Outside bbox", aud.get("outside_india_bbox", 0))
        c = st.columns(2)
        c[0].markdown(f'<div class="mini">lat range <em>{aud.get("lat_min")}</em> → '
                      f'<em>{aud.get("lat_max")}</em><br>lon range <em>{aud.get("lon_min")}</em> → '
                      f'<em>{aud.get("lon_max")}</em></div>', unsafe_allow_html=True)
        c[1].markdown('<div class="mini">outside-India by region:<br>'
                      + "<br>".join(f'· {k}: {v}' for k, v in aud.get("outside_zones", {}).items())
                      + '</div>', unsafe_allow_html=True)
        st.markdown('<div class="mini" style="margin-top:8px">sample India detections '
                    '(id · lat · lon · district · state):</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(aud.get("sample_in_india", [])),
                     hide_index=True, use_container_width=True)
        st.markdown('<div class="mini">sample outside-India detections:</div>',
                    unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(aud.get("sample_outside", [])),
                     hide_index=True, use_container_width=True)

    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
    ui.section("Top detections in view", "click to investigate")
    for a in data.R("risk_score", state.filters(), limit=6):
        c1, c2 = st.columns([4, 1])
        with c1:
            ui.alert_card(a, ago=a["acq_date"], show_button=False, key_prefix="mx")
        if c2.button("Investigate →", key=f"mx_{a['alert_id']}", use_container_width=True):
            state.focus_alert(a["alert_id"]); state.request_nav("Investigation"); st.rerun()
