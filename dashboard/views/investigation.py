"""Investigation — why one alert matters + the recommended action.
Assembled from real alert fields only; nothing fabricated."""
from __future__ import annotations

import pandas as pd
import pydeck as pdk
import streamlit as st

from dashboard import data, state
from dashboard import theme as T
from dashboard.components import mapview, ui
from dashboard.shell import topbar


def _kv(rows: list[tuple[str, str]]) -> None:
    body = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:5px 0;'
        f'border-bottom:1px solid {T.BORDER}"><span style="color:{T.T1};font-size:11px">{k}</span>'
        f'<span style="font-family:var(--mono);font-size:11px;color:{T.T0}">{v}</span></div>'
        for k, v in rows
    )
    st.markdown(f'<div class="panel">{body}</div>', unsafe_allow_html=True)


def render() -> None:
    topbar("Investigation")
    aid = st.session_state.get("focus_alert_id")

    if not aid:
        ui.page_header("Investigation", "Select an alert to investigate")
        ui.empty_state("No alert selected.",
                       "Open an alert from the Alerts feed or a marker on the Map, "
                       "or ask the agent \"why is the … alert critical?\".",
                       "")
        top = data.R("risk_score", state.filters(), limit=5)
        ui.section("Or start with the highest-risk alerts")
        for a in top:
            if ui.alert_card(a, ago=a["acq_date"], key_prefix="invpick"):
                state.focus_alert(a["alert_id"]); st.rerun()
        return

    inv = data.INV(aid)
    if not inv.get("found"):
        ui.empty_state("That alert is no longer available.", "It may have been re-seeded.")
        state.focus_alert(None)
        return

    h = inv["header"]
    c = T.SEV_COLOR.get(h["severity"], T.T1)

    # ── incident header ───────────────────────────────────────────────────
    st.markdown(
        f'<div style="display:flex;align-items:flex-start;justify-content:space-between;'
        f'border-bottom:1px solid {T.BORDER};padding-bottom:12px;margin-bottom:14px">'
        f'<div><div style="font-size:11px;color:{T.T1};font-family:var(--mono)">'
        f'{h["output_class_code"]} · {aid}</div>'
        f'<div class="page-h" style="margin-top:4px">{h["output_class_short"]} — {h["location"]}</div>'
        f'<div style="margin-top:6px">{T.sev_chip(h["severity"])} '
        f'<span class="mini">status <em>{h["status"]}</em> · model class probability '
        f'<em>{h["model_class_probability_pct"]}%</em> · predicted <em>{h["predicted_label"] or "—"}</em></span></div>'
        f'</div>'
        f'<div style="text-align:right"><div style="font-size:30px;font-weight:700;'
        f'font-family:var(--mono);color:{c};line-height:1">{h["risk_score"]}<span '
        f'style="font-size:13px;color:{T.T2}">/100</span></div>'
        f'<div style="font-size:10px;color:{T.T2};letter-spacing:.1em">RISK SCORE</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1.25, 1], gap="medium")

    with c1:
        ui.section("Detection")
        d = inv["detection"]
        _kv([
            ("Fire Radiative Power", f'{d["frp_mw"]} MW' if d["frp_mw"] is not None else "not available"),
            ("Brightness temperature", f'{d["bt_kelvin"]} K' if d["bt_kelvin"] is not None else "not available"),
            ("Persistence", f'{d["persistence_count"]} detections in window'),
            ("Detection date", d["acq_date"]),
            ("Day / night", d["day_night"]),
            ("Coordinates", d["coordinates"]),
            ("Instrument", d["instrument"]),
        ])

        ui.section("Context")
        ctx = inv["context"]
        _kv([
            ("District", ctx.get("district") or "outside India"),
            ("State", ctx.get("state") or "outside India"),
            ("Nearest facility", f'{ctx["dist_nearest_facility_km"]} km' if ctx["dist_nearest_facility_km"] is not None else "not available"),
            ("Facility type", ctx["hazard_facility_type"] or "not available"),
            ("Land-cover context", ctx["land_cover_context"] or "not available"),
        ])

        ui.section("Why this was flagged")
        why = inv["why_flagged"]
        if why:
            st.markdown('<div class="panel">' + "".join(
                f'<div style="padding:4px 0;font-size:11.5px"><span style="color:{T.LOW}">✓</span> {w}</div>'
                for w in why) + '</div>', unsafe_allow_html=True)
        else:
            ui.empty_state("Limited supporting signals — low-confidence single detection.")

    with c2:
        ui.section("Location")
        one = data.INV(aid)
        pt = [{
            "alert_id": aid, "lat": one["coords"]["lat"], "lon": one["coords"]["lon"],
            "output_class_short": h["output_class_short"], "severity": h["severity"],
            "risk_score": h["risk_score"], "frp_mw": inv["detection"]["frp_mw"],
            "persistence_count": inv["detection"]["persistence_count"],
            "acq_date": inv["detection"]["acq_date"],
            "place": h["location"], "state": h["state"], "zone": None,
        }]
        st.pydeck_chart(mapview.build_deck(
            pt, colour_by="class", focus_alert_id=aid,
            view=pdk.ViewState(latitude=one["coords"]["lat"], longitude=one["coords"]["lon"],
                               zoom=7.2),
        ), use_container_width=True, height=200)

        ui.section("Classification")
        cl = inv["classification"]
        prob_a_pct = round((cl["prob_A"] or 0) * 100)
        prob_b_pct = round((cl["prob_B_candidate"] or 0) * 100)
        anomaly_val = "YES — pattern anomaly ⚠" if cl["anomaly_flag"] else "no"
        _kv([
            ("Model classification", h["output_class_short"]),
            ("Raw model label", cl["predicted_label"] or "—"),
            ("P(Industrial / Persistent — A)", f"{prob_a_pct}%"),
            ("P(Natural Fire — B)", f"{prob_b_pct}%"),
            ("Anomaly detected", anomaly_val),
        ])
        st.markdown(f'<div class="mini" style="line-height:1.6;margin-top:6px">'
                    f'<em>{cl["framing"]}</em></div>', unsafe_allow_html=True)

        ui.section("Risk assessment")
        factors = inv["risk_assessment"]["factors"]
        if factors:
            st.markdown('<div class="panel">' + "".join(
                f'<div style="display:flex;justify-content:space-between;padding:4px 0;'
                f'font-size:11px"><span>{r}</span>'
                f'<span style="font-family:var(--mono);color:{T.HIGH}">+{p}</span></div>'
                for r, p in factors)
                + f'<div style="display:flex;justify-content:space-between;padding:7px 0 0;'
                f'margin-top:4px;border-top:1px solid {T.BORDER_2};font-size:11.5px;font-weight:700">'
                f'<span>Risk score</span><span style="font-family:var(--mono)">'
                f'{inv["risk_assessment"]["score"]}/100</span></div></div>',
                unsafe_allow_html=True)

    # ── recommended action + manual controls ─────────────────────────────
    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
    ra = inv["recommended_action"]
    st.markdown(
        f'<div class="panel" style="border-left:3px solid {c}">'
        f'<div style="font-size:10.5px;letter-spacing:.12em;color:{T.T1}">RECOMMENDED ACTION</div>'
        f'<div style="font-size:15px;font-weight:700;margin:4px 0 3px">{ra["action"]}</div>'
        f'<div style="font-size:11.5px;color:{T.T1};line-height:1.6">{ra["reason"]}</div></div>',
        unsafe_allow_html=True,
    )
    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Acknowledge", use_container_width=True, key="inv_ack"):
        data.set_status(aid, "acknowledge"); st.rerun()
    if b2.button("Escalate", use_container_width=True, key="inv_esc"):
        data.set_status(aid, "escalate"); st.rerun()
    if b3.button("Resolve", use_container_width=True, key="inv_res"):
        data.set_status(aid, "resolve"); st.rerun()
    if b4.button("Show on map  →", use_container_width=True, key="inv_map"):
        state.request_nav("Map Explorer"); st.rerun()
