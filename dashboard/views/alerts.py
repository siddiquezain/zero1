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

    filterbar.render(key="alerts_fb")
    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)

    alerts = data.A(state.filters(), limit=2000, sort_by="risk_score")
    if not alerts:
        ui.empty_state("No alerts match the current filters.",
                       "Widen the severity, state or date window.",
                       "Use Clear to reset.")
        return

    npages = max(1, (len(alerts) + _PAGE - 1) // _PAGE)
    page = min(st.session_state.get("alert_page", 0), npages - 1)
    ui.section(f"{len(alerts)} alerts", f"page {page+1} / {npages}")

    cur_sev = None
    for a in alerts[page * _PAGE:(page + 1) * _PAGE]:
        if a["severity"] != cur_sev:
            cur_sev = a["severity"]
            n = sum(1 for x in alerts if x["severity"] == cur_sev)
            c = T.SEV_COLOR[cur_sev]
            st.markdown(f'<div style="font-size:10.5px;font-weight:700;letter-spacing:.1em;'
                        f'color:{c};padding:10px 0 4px;border-bottom:1px solid {T.BORDER}">'
                        f'{cur_sev} · {n}</div>', unsafe_allow_html=True)

        c1, c2 = st.columns([3, 1])
        with c1:
            ui.alert_card(a, ago=a["acq_date"], show_button=False, key_prefix="al")
        with c2:
            st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
            if st.button("View investigation  →", key=f"inv_{a['alert_id']}",
                         use_container_width=True):
                state.focus_alert(a["alert_id"]); state.request_nav("Investigation"); st.rerun()

        with st.expander("Assessment · manual actions"):
            st.markdown(f'<div class="mini" style="line-height:1.7">{a["narrative"]}</div>',
                        unsafe_allow_html=True)
            if a["status"] not in ("EXTINGUISHED",):
                b1, b2, b3 = st.columns(3)
                if b1.button("Acknowledge", key=f"ack_{a['alert_id']}"):
                    data.set_status(a["alert_id"], "acknowledge"); st.rerun()
                if b2.button("Escalate", key=f"esc_{a['alert_id']}"):
                    data.set_status(a["alert_id"], "escalate"); st.rerun()
                if b3.button("Resolve", key=f"res_{a['alert_id']}"):
                    data.set_status(a["alert_id"], "resolve"); st.rerun()

    if npages > 1:
        p1, p2, p3 = st.columns([1, 2, 1])
        if p1.button("← Prev", disabled=page == 0, use_container_width=True, key="al_prev"):
            st.session_state["alert_page"] = page - 1; st.rerun()
        p2.markdown(f'<div style="text-align:center;font-size:10px;color:{T.T1};'
                    f'font-family:var(--mono);padding:6px">{page+1} / {npages}</div>',
                    unsafe_allow_html=True)
        if p3.button("Next →", disabled=page >= npages - 1, use_container_width=True, key="al_next"):
            st.session_state["alert_page"] = page + 1; st.rerun()
