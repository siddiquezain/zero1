"""
SIH26162 — Industrial Fire & Thermal Anomaly Alert System
Dashboard (Stage 8, v2)

Architecture:
    NASA FIRMS NRT → Classifier → Risk Engine → Alert Store → This Dashboard

Run:
    streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.alerting import alert_store, risk_engine
from src.alerting.pipeline import run as run_pipeline

# ── Constants ─────────────────────────────────────────────────────────────────
INDIA_SCORES = ROOT / "data/processed/stage6_india_scores.parquet"
INCIDENT_SCORES = ROOT / "data/incidents/stage7_incident_scores.parquet"

SEVERITY_EMOJI = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}
SEVERITY_COLOR = {
    "CRITICAL": [220, 20, 20, 240],
    "HIGH":     [255, 110, 0, 220],
    "MEDIUM":   [255, 210, 0, 190],
    "LOW":      [80,  200, 80, 160],
}
STATUS_BADGE = {
    "DETECTED":    "🔵 DETECTED",
    "VALIDATING":  "🟣 VALIDATING",
    "ALERTED":     "🔶 ALERTED",
    "ESCALATED":   "🔴 ESCALATED",
    "MONITORING":  "🟡 MONITORING",
    "EXTINGUISHED":"⬛ EXTINGUISHED",
}

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SIH26162 — Fire Alert System",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.alert-card {
    border-radius: 8px;
    padding: 14px 16px;
    margin-bottom: 10px;
    border-left: 5px solid;
}
.alert-CRITICAL { background: #2d0a0a; border-color: #dc1414; }
.alert-HIGH     { background: #2d1400; border-color: #ff6e00; }
.alert-MEDIUM   { background: #2d2500; border-color: #ffd200; }
.alert-LOW      { background: #0d2d0d; border-color: #50c850; }
.alert-title    { font-size: 16px; font-weight: 700; margin-bottom: 4px; }
.alert-meta     { font-size: 13px; color: #bbb; }
.alert-narrative{ font-size: 13px; color: #ddd; margin-top: 6px; }
.stat-box       { text-align: center; }
</style>
""", unsafe_allow_html=True)


# ── Data loading (cached) ─────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_india_scored():
    if not INDIA_SCORES.exists():
        return pd.DataFrame()
    df = pd.read_parquet(INDIA_SCORES)
    return risk_engine.score_dataframe(df)


@st.cache_data(ttl=60)
def load_incidents():
    if not INCIDENT_SCORES.exists():
        return pd.DataFrame()
    return pd.read_parquet(INCIDENT_SCORES)


def load_alerts(severity_filter, status_filter):
    sev = severity_filter if severity_filter else None
    sta = status_filter if status_filter else None
    return alert_store.get_alerts(severity=sev, status=sta)


# ── Alert card HTML ────────────────────────────────────────────────────────────
def _alert_card(a: dict) -> str:
    sev = a["severity"]
    em = SEVERITY_EMOJI.get(sev, "⚪")
    status = STATUS_BADGE.get(a["status"], a["status"])
    city_info = (
        f"{a['nearest_city']} ({a['dist_nearest_city_km']:.0f} km)"
        if a.get("nearest_city") else "—"
    )
    pop_info = (
        f"{a['near_population']:,}"
        if a.get("near_population", 0) > 0 else "—"
    )
    night_flag = "🌙 Night" if a.get("day_night") == "N" else "☀️ Day"
    return f"""
<div class="alert-card alert-{sev}">
  <div class="alert-title">{em} {sev} &nbsp;|&nbsp; {status}</div>
  <div class="alert-meta">
    📍 {a['lat']:.4f}°N, {a['lon']:.4f}°E &nbsp;·&nbsp;
    🏭 {a.get('nearest_facility_type','?')} ({a['dist_nearest_facility_km']:.1f} km) &nbsp;·&nbsp;
    🌆 {city_info} &nbsp;·&nbsp;
    👥 {pop_info} &nbsp;·&nbsp;
    {night_flag} &nbsp;·&nbsp;
    📅 {a.get('acq_date','?')}
  </div>
  <div class="alert-meta" style="margin-top:4px;">
    🔥 FRP {a['frp_mw']:.1f} MW &nbsp;·&nbsp;
    🔁 Persist {a['persistence_count']}× &nbsp;·&nbsp;
    🤖 Class: {a['predicted_label']} (prob_A={a['prob_A']:.2f}) &nbsp;·&nbsp;
    ⚠️ Score: {a['risk_score']}/100
  </div>
  <div class="alert-narrative">{a['narrative']}</div>
</div>"""


# ── Map layer ──────────────────────────────────────────────────────────────────
def _build_map(scored_df: pd.DataFrame, incidents: pd.DataFrame, show_incidents: bool):
    layers = []

    # FIRMS hotspot layer — coloured by severity
    if not scored_df.empty:
        map_df = scored_df.copy()
        map_df["color"] = map_df["severity"].map(SEVERITY_COLOR)
        map_df["radius"] = map_df["risk_score"].apply(lambda s: 6000 + s * 80)
        map_df["tip"] = map_df.apply(
            lambda r: (
                f"{SEVERITY_EMOJI.get(r['severity'], '')} {r['severity']} | score {r['risk_score']}\n"
                f"FRP {r['frp_mw']:.1f} MW · persist {r['persistence_count']}× · "
                f"{r['dist_nearest_facility_km']:.1f} km from facility\n"
                f"{r['narrative']}"
            ),
            axis=1,
        )
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position=["lon", "lat"],
            get_color="color",
            get_radius="radius",
            pickable=True,
            opacity=0.8,
        ))

    # Confirmed incident overlay
    if show_incidents and not incidents.empty:
        inc = incidents.copy()
        inc["color"] = [255, 255, 255, 255]
        inc["tip"] = inc.apply(
            lambda r: (
                f"📌 {r['incident_id']}: {r['name']}\n"
                f"Date: {r['date']} | Type: {r.get('facility_type','?')}\n"
                f"Anomaly: {'YES' if r['anomaly_flag'] else 'no'} | "
                f"prob_A={r['prob_A']:.2f}"
            ),
            axis=1,
        )
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=inc,
            get_position=["lon", "lat"],
            get_color="color",
            get_radius=18000,
            pickable=True,
            opacity=1.0,
            stroked=True,
            get_line_color=[255, 255, 255],
            line_width_min_pixels=2,
        ))

    view = pdk.ViewState(latitude=22.0, longitude=82.0, zoom=4.5, pitch=0)
    tooltip = {
        "html": "<pre style='font-size:12px;color:white'>{tip}</pre>",
        "style": {"background": "rgba(0,0,0,0.85)", "borderRadius": "6px", "padding": "8px"},
    }
    return pdk.Deck(
        layers=layers,
        initial_view_state=view,
        tooltip=tooltip,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://firms.modaps.eosdis.nasa.gov/img/nasa_logo.png", width=80)
    st.markdown("### SIH26162 — Alert System")
    st.caption("NASA FIRMS NRT · AI Classification · Risk Engine")

    st.divider()
    st.markdown("**Severity filter**")
    sev_filter = st.multiselect(
        "Show severities", ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        default=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        label_visibility="collapsed",
    )

    st.markdown("**Status filter**")
    status_filter = st.multiselect(
        "Show statuses",
        alert_store.LIFECYCLE_STATES,
        default=["DETECTED", "VALIDATING", "ALERTED", "ESCALATED", "MONITORING"],
        label_visibility="collapsed",
    )

    show_incidents = st.checkbox("Show confirmed incidents on map", value=True)

    st.divider()
    st.markdown("**🔄 Refresh pipeline**")
    if st.button("Re-run alert pipeline", use_container_width=True):
        with st.spinner("Running pipeline …"):
            result = run_pipeline(fresh=True)
            load_india_scored.clear()
            load_incidents.clear()
        st.success(
            f"Done — {result['inserted']} alerts · "
            f"CRITICAL: {result['counts']['CRITICAL']} · "
            f"HIGH: {result['counts']['HIGH']}"
        )
        st.rerun()

    st.divider()
    st.markdown("""
**Legend**
🔴 **CRITICAL** — Anomalous + persistent + near infrastructure
🟠 **HIGH** — Anomalous or high FRP or persistent
🟡 **MEDIUM** — Moderate signal, monitoring
🟢 **LOW** — Single low-confidence detection
⬜ **Incident site** — Confirmed past incident
""")

    st.divider()
    st.caption(
        "Model: RandomForest trained globally, India withheld.  \n"
        "Class A labelled via VNF oracle (5 km).  \n"
        "Anomaly = max_prob < 0.55 for both classes.  \n"
        "Framing: *anomalous departure from known patterns*,  \n"
        "not confirmed fire detection."
    )


# ── Main content ───────────────────────────────────────────────────────────────
st.markdown("# 🚨 Industrial Fire & Thermal Anomaly Alert System")
st.caption(
    "Real-time satellite thermal hotspot classification · "
    "NASA FIRMS NRT (VIIRS 375 m) → AI classifier → Risk engine → Alert feed"
)

# ── Stats bar ──────────────────────────────────────────────────────────────────
c = alert_store.counts()
now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Active alerts", c["active"])
col2.metric("🔴 Critical", c["CRITICAL"])
col3.metric("🟠 High", c["HIGH"])
col4.metric("🟡 Medium", c["MEDIUM"])
col5.metric("🟢 Low", c["LOW"])
col6.metric("Last refreshed", now_utc[-9:])  # just time

st.divider()

# ── Layout: alert feed (left) + map (right) ───────────────────────────────────
col_alerts, col_map = st.columns([1, 1.6], gap="medium")

with col_alerts:
    alerts = load_alerts(sev_filter, status_filter)
    st.markdown(f"### Alert Feed — {len(alerts)} alerts")

    if not alerts:
        st.info("No alerts match current filters.")
    else:
        # Group by severity for display
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            if sev not in sev_filter:
                continue
            sev_alerts = [a for a in alerts if a["severity"] == sev]
            if not sev_alerts:
                continue

            with st.expander(
                f"{SEVERITY_EMOJI[sev]} **{sev}** — {len(sev_alerts)} alerts",
                expanded=(sev in ("CRITICAL", "HIGH")),
            ):
                for a in sev_alerts[:20]:  # cap render at 20 per tier
                    st.markdown(_alert_card(a), unsafe_allow_html=True)

                    # Lifecycle action buttons (CRITICAL/HIGH only for demo)
                    if sev in ("CRITICAL", "HIGH") and a["status"] in ("ALERTED", "ESCALATED"):
                        b1, b2, b3 = st.columns(3)
                        if b1.button("Acknowledge", key=f"ack_{a['alert_id']}"):
                            alert_store.update_status(a["alert_id"], "MONITORING")
                            st.rerun()
                        if b2.button("Escalate", key=f"esc_{a['alert_id']}"):
                            alert_store.update_status(a["alert_id"], "ESCALATED")
                            st.rerun()
                        if b3.button("Resolve", key=f"res_{a['alert_id']}"):
                            alert_store.update_status(a["alert_id"], "EXTINGUISHED")
                            st.rerun()

                if len(sev_alerts) > 20:
                    st.caption(f"… and {len(sev_alerts)-20} more {sev} alerts")

with col_map:
    st.markdown("### Live Detection Map")
    scored_df = load_india_scored()
    incidents = load_incidents()

    deck = _build_map(
        scored_df if sev_filter else pd.DataFrame(),
        incidents,
        show_incidents,
    )
    st.pydeck_chart(deck, use_container_width=True, height=580)

    # Map legend row
    ml1, ml2, ml3, ml4 = st.columns(4)
    ml1.markdown("🔴 Critical")
    ml2.markdown("🟠 High")
    ml3.markdown("🟡 Medium")
    ml4.markdown("🟢 Low")

st.divider()

# ── Tabs: lifecycle + incidents + model ────────────────────────────────────────
tab_life, tab_inc, tab_model, tab_limits = st.tabs(
    ["Alert Lifecycle", "Confirmed Incidents", "Model Details", "Limitations"]
)

with tab_life:
    st.markdown("""
**Alert lifecycle states:**

| State | Meaning |
|---|---|
| 🔵 DETECTED | New hotspot detected from FIRMS NRT |
| 🟣 VALIDATING | Checking persistence / cross-referencing facility layer |
| 🔶 ALERTED | Severity confirmed — alert active |
| 🔴 ESCALATED | Not acknowledged, severity rising or persistent |
| 🟡 MONITORING | Acknowledged, situation being watched |
| ⬛ EXTINGUISHED | No further detections — alert closed |

**Flow:** `DETECTED → VALIDATING → ALERTED → ESCALATED → MONITORING → EXTINGUISHED`

HIGH and CRITICAL alerts skip DETECTED/VALIDATING and go directly to ALERTED.
Use the Acknowledge / Escalate / Resolve buttons in the alert feed to transition states.
""")
    # Lifecycle summary table
    all_alerts = alert_store.get_alerts()
    if all_alerts:
        life_df = pd.DataFrame(all_alerts)[["severity", "status"]].value_counts().reset_index()
        life_df.columns = ["Severity", "Status", "Count"]
        st.dataframe(life_df.sort_values(["Severity", "Count"], ascending=[True, False]),
                     hide_index=True, use_container_width=True)

with tab_inc:
    st.markdown("### Confirmed India Industrial Incidents — Anomaly Scoring")
    st.caption(
        "30 manually curated major Indian industrial incidents (2019–2023) scored against the trained model. "
        "21/30 (70%) flagged as anomalous — neither persistent flare (Class A) nor natural fire (Class B). "
        "This is the expected outcome: transient industrial incidents depart from both known pattern types."
    )
    incidents = load_incidents()
    if not incidents.empty:
        show_cols = [
            "incident_id", "name", "date", "state", "facility_type",
            "predicted_label", "prob_A", "prob_B_candidate", "anomaly_flag",
            "dist_nearest_facility_km",
        ]
        styled = incidents[show_cols].rename(columns={
            "prob_B_candidate": "prob_B",
            "dist_nearest_facility_km": "dist_fac_km",
        })
        st.dataframe(styled.sort_values("anomaly_flag", ascending=False),
                     hide_index=True, use_container_width=True)

    st.markdown("#### Case Studies")
    cs1, cs2, cs3 = st.columns(3)
    with cs1:
        st.error("🔴 Jharia Coalfield")
        st.markdown(
            "Underground coal seam fire active since 1916. Flagged anomalous (neither flare nor natural fire). "
            "4 repeat FIRMS detections in 5-day window. 7 km from registered facility."
        )
    with cs2:
        st.success("🟢 Punjab Stubble Burning")
        st.markdown(
            "Seasonal kharif-residue agricultural burning (Oct–Nov). Correctly predicted **Class B** — "
            "natural/agricultural fire. NOT flagged as anomaly. Agri-season flag active."
        )
    with cs3:
        st.warning("🟠 Vizag LG Polymers")
        st.markdown(
            "Styrene gas leak (2020). 12 fatalities. Anomaly-flagged (max_prob=0.52) — "
            "near industrial facility but not a persistent gas-flare pattern. Correctly surfaces as review case."
        )

with tab_model:
    st.markdown("### Model Architecture")
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.markdown("""
**Pipeline:**
- Stage 1: NASA FIRMS NRT (VIIRS 375 m) + VNF gas flare catalogue
- Stage 2: Facility context (GPPD + OSM, 72,624 India facilities)
- Stage 3: Label construction via VNF labeling oracle (5 km proximity)
- Stage 4: Feature engineering (7 features: BT, FRP, persistence, dist_facility, seasonality, day/night, month)
- Stage 5: Spatial grid 80/20 split — India entirely withheld as test region
- Stage 6: RandomForest (300 trees, class_weight=balanced)

**Three-way evaluation:**
| Evaluation | Accuracy | Class A F1 |
|---|---|---|
| Random split (inflated) | 97.25% | 0.24 |
| Spatial holdout (honest) | 98.06% | 0.18 |
| India holdout | scored only | — |
""")
    with col_m2:
        st.markdown("""
**Feature importances (spatial holdout model):**

| Feature | Importance |
|---|---|
| dist_nearest_facility_km | 29.3% |
| day_night_bin | 25.3% |
| bt_kelvin (FIRMS pixel BT) | 21.4% |
| persistence_count | 13.9% |
| frp_mw | 10.1% |
| agri_season_flag | 0.0% |
| acq_month | 0.0% |

**Key design decision:** VNF avg_temp (1,500–2,000 K spectral flame temperature)
is a different physical quantity from FIRMS bt_kelvin (300–500 K pixel BT).
VNF is used as a labeling oracle only — all training in FIRMS feature space.
""")

with tab_limits:
    st.markdown("""
### Scientific Caveats & Limitations

- **No confirmed industrial fire training data exists** anywhere (India or global). The model is trained on
  gas flares (VNF, Class A) vs natural fires (global FIRMS NRT, Class B). "Industrial incident detection"
  is demonstrated via the *anomaly* output — hotspots matching neither class.

- **Class A training set is thin** (1,901 FIRMS examples from VNF proximity oracle in 5-day NRT window).
  Class A spatial-holdout F1 = 0.18. Historical FIRMS archive or GIHS would improve substantially.

- **Incident scores lack thermal features.** Historical FIRMS archive (2019–2023) not downloaded.
  Incident classifications are driven by facility proximity + seasonality only.

- **FIRMS NRT is 5-day window only.** Persistence counts reflect 5 days, not annual patterns.
  VNF annual detection frequency (dtc_freq) is a richer persistence signal.

- **India holdout is locked.** Not used at any training/selection step. All 705 India hotspot
  scores are genuine out-of-sample predictions.

- **Alert severity is heuristic.** Risk scores combine model output + domain rules.
  They reflect *satellite-observable patterns*, not ground-verified fire status.
  Every alert requires human verification before dispatch action.

- **Correct framing:** *"Anomalous departure from known persistent-industrial and natural-fire
  patterns"* — not confirmed fire detection.
""")
