"""Alerts — the full prioritised, filterable feed + manual lifecycle actions."""
from __future__ import annotations

import streamlit as st

from dashboard import data, state
from dashboard import theme as T
from dashboard.components import filterbar, ui
from dashboard.shell import topbar

_PAGE = 12


def render() -> None:
    topbar("Alerts")
    ui.page_header("Alerts", "Full alert feed — DETECT → CLASSIFY → VALIDATE → PRIORITIZE → ACT")

    tab_det, tab_evt = st.tabs(["DETECTIONS", "THERMAL EVENTS"])

    with tab_det:
        filterbar.render(key="alerts_fb")
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)

        alerts = data.A(state.filters(), limit=2000, sort_by="risk_score")
        if not alerts:
            ui.empty_state("No alerts match the current filters.",
                           "Widen the severity, state or date window.", "Use Clear to reset.")
        else:
            npages = max(1, (len(alerts) + _PAGE - 1) // _PAGE)
            page = min(st.session_state.get("alert_page", 0), npages - 1)
            ui.section(f"{len(alerts)} alerts", f"page {page+1} / {npages}")

            cur_sev = None
            for a in alerts[page * _PAGE:(page + 1) * _PAGE]:
                if a["severity"] != cur_sev:
                    cur_sev = a["severity"]
                    n = sum(1 for x in alerts if x["severity"] == cur_sev)
                    c = T.SEV_COLOR[cur_sev]
                    st.markdown(
                        f'<div style="font-size:10.5px;font-weight:700;letter-spacing:.1em;'
                        f'color:{c};padding:10px 0 4px;border-bottom:1px solid {T.BORDER}">'
                        f'{cur_sev} · {n}</div>', unsafe_allow_html=True)

                c1, c2 = st.columns([3, 1])
                with c1:
                    ui.alert_card(a, ago=a["acq_date"], show_button=False, key_prefix="al")
                with c2:
                    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
                    if st.button("View investigation  →", key=f"inv_{a['alert_id']}",
                                 use_container_width=True):
                        state.focus_alert(a["alert_id"])
                        state.request_nav("Investigation")
                        st.rerun()

                with st.expander("Assessment · manual actions"):
                    st.markdown(
                        f'<div class="mini" style="line-height:1.7">{a["narrative"]}</div>',
                        unsafe_allow_html=True)
                    if a["status"] not in ("EXTINGUISHED",):
                        b1, b2, b3 = st.columns(3)
                        if b1.button("Acknowledge", key=f"ack_{a['alert_id']}",
                                     disabled=a["status"] == "MONITORING"):
                            r = data.set_status(a["alert_id"], "acknowledge")
                            st.toast("Acknowledged → MONITORING" if r.get("ok") else f"Error: {r.get('error')}", icon="✅" if r.get("ok") else "🚨")
                            st.rerun()
                        if b2.button("Escalate", key=f"esc_{a['alert_id']}"):
                            r = data.set_status(a["alert_id"], "escalate")
                            st.toast("Escalated → ESCALATED" if r.get("ok") else f"Error: {r.get('error')}", icon="🚨" if r.get("ok") else "🚨")
                            st.rerun()
                        if b3.button("Resolve", key=f"res_{a['alert_id']}"):
                            r = data.set_status(a["alert_id"], "resolve")
                            st.toast("Resolved → EXTINGUISHED" if r.get("ok") else f"Error: {r.get('error')}", icon="🟢" if r.get("ok") else "🚨")
                            st.rerun()

            pg_cols = st.columns([1, 4, 1])
            if pg_cols[0].button("◀ Prev", key="al_prev", disabled=(page == 0)):
                st.session_state["alert_page"] = page - 1; st.rerun()
            pg_cols[1].markdown(
                f'<div style="text-align:center;font-size:11px;color:{T.T2};padding-top:8px">'
                f'page {page + 1} / {npages}</div>', unsafe_allow_html=True)
            if pg_cols[2].button("Next ▶", key="al_next", disabled=(page >= npages - 1)):
                st.session_state["alert_page"] = page + 1; st.rerun()

    with tab_evt:
        st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)
        events = data.EVENTS(state.filters(), limit=500)
        if not events:
            ui.empty_state("No thermal events in the current data window.", "", "")
        else:
            ui.section(f"{len(events)} thermal events", "sorted by risk score")
            for ev in events[:50]:
                ev_id = ev["event_id"]
                sev = ev.get("severity", "LOW")
                c = T.SEV_COLOR.get(sev, T.T1)
                obs = ev.get("observation_count", 1)
                loc = (f'{ev.get("district") or ""}, {ev.get("state") or ""}'.strip(", ")
                       or f'{ev.get("centroid_lat", 0):.3f}, {ev.get("centroid_lon", 0):.3f}')
                st.markdown(
                    f'<div class="panel" style="border-left:3px solid {c};margin-bottom:4px">'
                    f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
                    f'<div>'
                    f'<div style="font-size:10px;font-family:var(--mono);color:{T.T2}">'
                    f'EVENT #{ev_id} · {obs} detection{"s" if obs != 1 else ""}</div>'
                    f'<div style="font-size:13px;font-weight:600;margin-top:2px">'
                    f'{ev.get("output_class_short", "—")} — {loc}</div>'
                    f'</div>'
                    f'<div style="font-family:var(--mono);font-size:18px;font-weight:700;color:{c}">'
                    f'{ev.get("risk_score", 0)}</div>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
                if ev.get("alert_ids"):
                    first_aid = ev["alert_ids"][0]
                    if st.button(f"Investigate →", key=f"ev_inv_{ev_id}"):
                        state.focus_alert(first_aid)
                        state.request_nav("Investigation")
                        st.rerun()
