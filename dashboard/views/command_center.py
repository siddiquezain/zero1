"""Command Center — the operational overview. Answers what / how bad / where /
what needs attention / what next in ~10 seconds."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import data, state
from dashboard import theme as T
from dashboard.agent import panel as agent_panel
from dashboard.components import charts, mapview, ui
from dashboard.shell import topbar


def _delta(daily: list[dict], key: str) -> tuple[str, str]:
    if len(daily) < 3:
        return "", T.T1
    cur = daily[-1].get(key) or 0
    prior = [d.get(key) or 0 for d in daily[:-1]]
    base = sum(prior) / len(prior) if prior else 0
    if base == 0:
        return ("new activity" if cur else "—"), T.T1
    pct = round((cur - base) / base * 100)
    arrow = "▲" if pct > 0 else "▼" if pct < 0 else "■"
    col = T.CRIT if (pct > 5 and key in ("critical", "high")) else \
          T.LOW if pct < -5 else T.T1
    return f"{arrow} {abs(pct)}% vs {len(prior)}-day avg", col


def render() -> None:
    topbar("Command Center")
    s = data.S()
    an = data.ANALYTICS()
    daily = an.get("daily", [])

    main, side = st.columns([2.8, 1], gap="medium")

    with main:
        # ── KPI row ────────────────────────────────────────────────────────
        k = st.columns(5, gap="small")
        with k[0]:
            ui.kpi(s["active"], "Active Alerts", "requiring attention",
                   icon="🔔", color=T.T0)
        for col, (lbl, key, sev_col) in zip(k[1:4], [
                ("Critical", "CRITICAL", T.CRIT), ("High", "HIGH", T.HIGH),
                ("Medium", "MEDIUM", T.MED)]):
            tr, trc = _delta(daily, key.lower())
            with col:
                ui.kpi(s["severity"][key], lbl, "priority", color=sev_col,
                       trend=tr, trend_color=trc)
        with k[4]:
            ui.kpi(s["classification"]["Natural Fire"], "Natural Fire", "PS-C · monitoring",
                   icon="🌿", color=T.LOW)

        st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

        # ── Event KPI row ──────────────────────────────────────────────────
        es = data.EVENTS_SIT()
        ek = st.columns(4, gap="small")
        with ek[0]:
            ui.kpi(es["total_events"], "Thermal Events", "clustered detections", icon="⬡")
        with ek[1]:
            ui.kpi(es["high_risk_events"], "High-Risk Events", "risk ≥ 60", color=T.HIGH)
        with ek[2]:
            ui.kpi(es["persistent_sources"], "Persistent Sources", "≥3 observations", color=T.MED)
        with ek[3]:
            ui.kpi(es["early_warnings"], "Early Warnings", "trajectory increasing", color=T.CRIT)
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)

        # ── map + priority alerts ─────────────────────────────────────────
        m, p = st.columns([1.55, 1], gap="medium")
        with m:
            ui.section("Live Detection Map", "India & neighbouring regions")
            alerts = data.A(state.filters(), limit=1500, sort_by="risk_score")
            deck = mapview.build_deck(
                alerts, colour_by="class",
                incidents=data.incidents() if st.session_state.get("show_incidents") else None,
                focus_alert_id=st.session_state.get("focus_alert_id"),
            )
            st.pydeck_chart(deck, use_container_width=True, height=360)
            ui.legend([("Industrial Fire (PS-A)", T.CLS_INDUSTRIAL),
                       ("Persistent Source (PS-B)", T.CLS_PERSISTENT),
                       ("Natural Fire (PS-C)", T.CLS_NATURAL),
                       ("Confirmed Incident", T.CLS_INCIDENT)])
        with p:
            ui.section("Priority Alerts", "top by risk")
            top = data.R("risk_score", state.filters(), limit=4)
            for a in top:
                if ui.alert_card(a, ago=a["acq_date"], key_prefix="cc"):
                    state.focus_alert(a["alert_id"]); state.request_nav("Investigation"); st.rerun()
            if st.button("View all alerts  →", key="cc_viewall", use_container_width=True):
                state.request_nav("Alerts"); st.rerun()

        st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

        # ── donuts + timeline ─────────────────────────────────────────────
        d1, d2, d3 = st.columns([1, 1, 1.35], gap="medium")
        with d1:
            ui.section("By Classification")
            st.plotly_chart(charts.donut(s["classification"], "Alerts",
                            {"Industrial Fire": T.CLS_INDUSTRIAL,
                             "Persistent Source": T.CLS_PERSISTENT,
                             "Natural Fire": T.CLS_NATURAL}),
                            use_container_width=True, config={"displayModeBar": False})
        with d2:
            ui.section("By Severity")
            st.plotly_chart(charts.donut(s["severity"], "Alerts", T.SEV_COLOR),
                            use_container_width=True, config={"displayModeBar": False})
        with d3:
            ui.section("Fire Activity Timeline", f"last {len(daily)} days")
            if daily:
                st.plotly_chart(charts.stacked_bars(daily),
                                use_container_width=True, config={"displayModeBar": False})
            else:
                ui.empty_state("No historical activity yet.")

        st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

        # ── recent detections + quick actions ────────────────────────────
        r, q = st.columns([1.6, 1], gap="medium")
        with r:
            ui.section("Recent Detections", "latest scored")
            recent = data.A(state.filters(), limit=8, sort_by="recent")
            df = pd.DataFrame([{
                "Date": a["acq_date"],
                "Location": a.get("place") or a.get("state") or a.get("zone") or "—",
                "Class": a["output_class_code"] or a["output_class_short"],
                "Severity": a["severity"],
                "FRP": a["frp_mw"], "Persist": f'{a["persistence_count"]}x',
                "Risk": f'{a["risk_score"]}/100', "Status": a["status"],
            } for a in recent])
            st.dataframe(df, hide_index=True, use_container_width=True, height=310)
        with q:
            ui.section("Quick Actions")
            qa = st.columns(2)
            if qa[0].button("📄  Generate report", use_container_width=True, key="qa_rep"):
                state.request_nav("Reports / GIS"); st.rerun()
            if qa[1].button("🗺  Open full map", use_container_width=True, key="qa_map"):
                state.request_nav("Map Explorer"); st.rerun()
            if qa[0].button("⌗  Export GIS data", use_container_width=True, key="qa_gis"):
                state.request_nav("Reports / GIS"); st.rerun()
            if qa[1].button("↻  Re-run pipeline", use_container_width=True, key="qa_pipe"):
                with st.spinner("Re-scoring detections…"):
                    data.run_pipeline()
                st.rerun()
            b = data.BASELINE(state.filters())
            if b:
                st.markdown(
                    f'<div class="panel" style="margin-top:8px">'
                    f'<div class="sec" style="margin-bottom:6px">FRP vs baseline</div>'
                    f'<div class="mini">Normal band <em>{b["baseline_low"]}–{b["baseline_high"]}</em> MW '
                    f'· latest <em>{b["current_median"]}</em> MW'
                    + (f' · <em style="color:{T.HIGH}">{b["delta_pct"]:+d}%</em>'
                       if b["delta_pct"] is not None else "")
                    + '</div></div>', unsafe_allow_html=True)

    with side:
        with st.container(border=True):
            agent_panel.render({"page": "Command Center", "filters": state.filters(),
                                "focus_alert_id": st.session_state.get("focus_alert_id")})
