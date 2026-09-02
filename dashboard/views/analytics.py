"""Analytics — time, trends, classification analysis, baseline comparison."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import data, state
from dashboard import theme as T
from dashboard.components import charts, ui
from dashboard.shell import topbar


def render() -> None:
    topbar("Analytics")
    ui.page_header("Analytics", "Temporal and categorical analysis of scored detections")

    lo, hi = data.DATE_RANGE()
    an = data.ANALYTICS()
    daily = an.get("daily", [])

    # ── activity ─────────────────────────────────────────────────────────
    ui.section("Fire activity by date", f"{lo} → {hi}")
    a1, a2 = st.columns([1.7, 1], gap="medium")
    with a1:
        if daily:
            st.plotly_chart(charts.stacked_bars(daily, height=240),
                            use_container_width=True, config={"displayModeBar": False})
        else:
            ui.empty_state("No historical activity recorded yet.")
    with a2:
        t = an["totals"]
        m = st.columns(2)
        m[0].metric("Detections", f'{t["detections"]:,}')
        m[1].metric("Critical", t["critical"])
        m[0].metric("Avg FRP", f'{t["avg_frp"]} MW')
        m[1].metric("Max FRP", f'{t["max_frp"]} MW')

    # ── baseline comparison ─────────────────────────────────────────────
    ui.section("Baseline comparison", "normal FRP band vs current")
    b = data.BASELINE(state.filters())
    if b is None:
        ui.empty_state("Insufficient history for a baseline comparison.",
                       "The FIRMS NRT window is only a few days; a longer archive is "
                       "needed for a meaningful normal band. Shown honestly rather than "
                       "fabricated.")
    else:
        bc = st.columns(3)
        bc[0].markdown(f'<div class="panel"><div class="sec" style="margin-bottom:4px">Normal baseline</div>'
                       f'<div class="kpi-num">{b["baseline_low"]}–{b["baseline_high"]}</div>'
                       f'<div class="kpi-sub">MW · median {b["baseline_median"]} · '
                       f'{b["history_n"]} detections over {b["history_days"]} days</div></div>',
                       unsafe_allow_html=True)
        bc[1].markdown(f'<div class="panel"><div class="sec" style="margin-bottom:4px">Current</div>'
                       f'<div class="kpi-num">{b["current_median"]}</div>'
                       f'<div class="kpi-sub">MW · median on {b["current_date"]}</div></div>',
                       unsafe_allow_html=True)
        dp = b["delta_pct"]
        col = T.HIGH if (dp or 0) > 0 else T.LOW
        bc[2].markdown(f'<div class="panel"><div class="sec" style="margin-bottom:4px">Deviation</div>'
                       f'<div class="kpi-num" style="color:{col}">'
                       f'{("+" if (dp or 0) >= 0 else "")}{dp if dp is not None else "—"}%</div>'
                       f'<div class="kpi-sub">current vs baseline median</div></div>',
                       unsafe_allow_html=True)

    # ── classification / severity / land-cover ─────────────────────────
    ui.section("Classification analysis")
    c1, c2, c3 = st.columns(3, gap="medium")
    with c1:
        st.plotly_chart(charts.donut(an["by_class"], "Alerts",
                        {"Industrial Fire": T.CLS_INDUSTRIAL, "Persistent Source": T.CLS_PERSISTENT,
                         "Natural Fire": T.CLS_NATURAL}),
                        use_container_width=True, config={"displayModeBar": False})
        st.markdown('<div style="text-align:center;font-size:10px;color:#5a6472">by class</div>',
                    unsafe_allow_html=True)
    with c2:
        st.plotly_chart(charts.donut(an["by_severity"], "Alerts", T.SEV_COLOR),
                        use_container_width=True, config={"displayModeBar": False})
        st.markdown('<div style="text-align:center;font-size:10px;color:#5a6472">by severity</div>',
                    unsafe_allow_html=True)
    with c3:
        if an["by_land_cover"]:
            st.plotly_chart(charts.hbar(an["by_land_cover"], T.ACCENT, height=230),
                            use_container_width=True, config={"displayModeBar": False})
            st.markdown('<div style="text-align:center;font-size:10px;color:#5a6472">by land cover</div>',
                        unsafe_allow_html=True)

    if an["by_hazard"]:
        ui.section("Detections by nearby facility type")
        st.dataframe(pd.DataFrame(
            [{"Facility type": k, "Nearby detections": v} for k, v in an["by_hazard"].items()]),
            hide_index=True, use_container_width=True)
