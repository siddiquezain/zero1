"""
SIH26162 — AI-Based Detection and Classification of Industrial Fires
and Persistent Thermal Sources Using NASA FIRMS, OSM & Satellite Data

PS Deliverables:
  i.  Classification and segregation of Industrial fires from forest fires
      and other natural fires.
  ii. GIS-based solution for data storage, visualization as overlay over maps.

Run:  streamlit run dashboard/app.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.alerting import alert_store
from src.alerting.risk_engine import (
    OUTPUT_CLASS_INDUSTRIAL_FIRE,
    OUTPUT_CLASS_NATURAL_FIRE,
    OUTPUT_CLASS_PERSISTENT_SOURCE,
    score_dataframe,
)
from src.alerting.pipeline import run as run_pipeline

# ── Paths ──────────────────────────────────────────────────────────────────────
INDIA_SCORES = ROOT / "data/processed/stage6_india_scores.parquet"
INCIDENT_SCORES = ROOT / "data/incidents/stage7_incident_scores.parquet"

# ── PS output class config ─────────────────────────────────────────────────────
# Maps PS output class → (emoji, colour [R,G,B,A], short label)
OUTPUT_CLASS_CFG = {
    OUTPUT_CLASS_INDUSTRIAL_FIRE:    ("🔴", [220,  20,  20, 240], "Industrial Fire"),
    OUTPUT_CLASS_PERSISTENT_SOURCE:  ("🟠", [255, 140,   0, 220], "Persistent Source"),
    OUTPUT_CLASS_NATURAL_FIRE:       ("🟢", [ 50, 200,  80, 180], "Natural Fire"),
}
SEVERITY_EMOJI = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}
STATUS_BADGE = {
    "DETECTED":    "🔵 DETECTED",
    "VALIDATING":  "🟣 VALIDATING",
    "ALERTED":     "🔶 ALERTED",
    "ESCALATED":   "🔴 ESCALATED",
    "MONITORING":  "🟡 MONITORING",
    "EXTINGUISHED":"⬛ EXTINGUISHED",
}

# ── Auto-seed alert DB on first run ───────────────────────────────────────────
if not (ROOT / "data/alerts.db").exists():
    run_pipeline(fresh=True)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SIH26162 — Industrial Fire Detection",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.alert-card { border-radius:8px; padding:14px 16px; margin-bottom:10px; border-left:5px solid; }
.alert-CRITICAL { background:#2d0a0a; border-color:#dc1414; }
.alert-HIGH     { background:#2d1400; border-color:#ff6e00; }
.alert-MEDIUM   { background:#2d2500; border-color:#ffd200; }
.alert-LOW      { background:#0d2d0d; border-color:#50c850; }
.class-tag { display:inline-block; padding:3px 8px; border-radius:4px;
             font-weight:700; font-size:13px; margin-bottom:6px; }
.tag-fire   { background:#5c1010; color:#ff6060; }
.tag-source { background:#4a2800; color:#ffaa50; }
.tag-natural{ background:#0d3d1a; color:#60dd80; }
</style>
""", unsafe_allow_html=True)


# ── Data loaders ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_scored():
    if not INDIA_SCORES.exists():
        return pd.DataFrame()
    return score_dataframe(pd.read_parquet(INDIA_SCORES))


@st.cache_data(ttl=60)
def load_incidents():
    if not INCIDENT_SCORES.exists():
        return pd.DataFrame()
    return pd.read_parquet(INCIDENT_SCORES)


def _class_tag(output_class: str) -> str:
    css = {"Industrial Fire / Abnormal Thermal Event": "tag-fire",
           "Persistent Industrial Thermal Source":     "tag-source",
           "Forest / Agricultural Fire":               "tag-natural"}.get(output_class, "")
    em, _, short = OUTPUT_CLASS_CFG.get(output_class, ("⚪", [], output_class))
    return f'<span class="class-tag {css}">{em} {short}</span>'


def _alert_card(a: dict) -> str:
    sev = a["severity"]
    status = STATUS_BADGE.get(a["status"], a["status"])
    output_class = a.get("output_class", "")
    city = a.get("nearest_city", "—")
    city_dist = a.get("dist_nearest_city_km", 0)
    pop = a.get("near_population", 0)
    land = a.get("land_cover_context", "—")
    haz = a.get("hazard_facility_type", "—")
    night = "🌙 Night" if a.get("day_night") == "N" else "☀️ Day"
    return f"""
<div class="alert-card alert-{sev}">
  {_class_tag(output_class)}
  <div style="font-size:13px;font-weight:700;color:#eee;margin-bottom:4px;">
    {SEVERITY_EMOJI.get(sev,'')} {sev} &nbsp;|&nbsp; {status}
  </div>
  <div style="font-size:12px;color:#bbb;line-height:1.7;">
    📍 {a['lat']:.4f}°N, {a['lon']:.4f}°E &nbsp;·&nbsp;
    🏭 {haz} ({a['dist_nearest_facility_km']:.1f} km) &nbsp;·&nbsp;
    🌿 {land}<br>
    🌆 {city} ({city_dist:.0f} km) &nbsp;·&nbsp;
    👥 {pop:,} &nbsp;·&nbsp;
    {night} &nbsp;·&nbsp; 📅 {a.get('acq_date','?')}
  </div>
  <div style="font-size:12px;color:#bbb;margin-top:4px;">
    🔥 FRP {a['frp_mw']:.1f} MW &nbsp;·&nbsp;
    🔁 Persist {a['persistence_count']}× &nbsp;·&nbsp;
    ⚠️ Risk score {a['risk_score']}/100
  </div>
  <div style="font-size:12px;color:#ccc;margin-top:6px;">{a['narrative']}</div>
</div>"""


# ── GeoJSON export ─────────────────────────────────────────────────────────────
def _alerts_to_geojson(alerts: list[dict]) -> str:
    """Convert alert list to GeoJSON FeatureCollection (GIS deliverable ii)."""
    features = []
    for a in alerts:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [a["lon"], a["lat"]]},
            "properties": {
                "alert_id":            a["alert_id"],
                "output_class":        a.get("output_class", ""),
                "severity":            a["severity"],
                "status":              a["status"],
                "risk_score":          a["risk_score"],
                "land_cover_context":  a.get("land_cover_context", ""),
                "hazard_facility_type":a.get("hazard_facility_type", ""),
                "frp_mw":              a["frp_mw"],
                "persistence_count":   a["persistence_count"],
                "dist_facility_km":    a["dist_nearest_facility_km"],
                "nearest_city":        a.get("nearest_city", ""),
                "acq_date":            a.get("acq_date", ""),
                "narrative":           a.get("narrative", ""),
            },
        })
    return json.dumps({"type": "FeatureCollection", "features": features}, indent=2)


# ── Map layers ────────────────────────────────────────────────────────────────
def _build_map(scored: pd.DataFrame, incidents: pd.DataFrame,
               show_incidents: bool, colour_by: str) -> pdk.Deck:
    layers = []

    if not scored.empty:
        df = scored.copy()
        if colour_by == "Output Class (PS classification)":
            df["color"] = df["output_class"].map(
                {k: v[1] for k, v in OUTPUT_CLASS_CFG.items()}
            )
        else:  # severity
            sev_color = {"CRITICAL":[220,20,20,240],"HIGH":[255,110,0,220],
                         "MEDIUM":[255,210,0,190],"LOW":[80,200,80,160]}
            df["color"] = df["severity"].map(sev_color)

        df["radius"] = df["risk_score"].apply(lambda s: 5000 + s * 90)
        df["tip"] = df.apply(lambda r: (
            f"{OUTPUT_CLASS_CFG.get(r['output_class'],('⚪',[],r['output_class']))[0]} "
            f"{r.get('output_class','')}\n"
            f"Severity: {r.get('severity','')} | Score: {r.get('risk_score',0)}\n"
            f"FRP {r['frp_mw']:.1f} MW · Persist {r['persistence_count']}× · "
            f"{r['dist_nearest_facility_km']:.1f} km from facility\n"
            f"Land cover: {r.get('land_cover_context','')}\n"
            f"Facility: {r.get('hazard_facility_type','')}"
        ), axis=1)
        layers.append(pdk.Layer("ScatterplotLayer", data=df,
            get_position=["lon","lat"], get_color="color", get_radius="radius",
            pickable=True, opacity=0.85))

    if show_incidents and not incidents.empty:
        inc = incidents.copy()
        inc["color"] = [[255,255,255,230]] * len(inc)
        inc["tip"] = inc.apply(lambda r: (
            f"📌 {r['incident_id']}: {r['name']}\n"
            f"Date: {r['date']} | Facility: {r.get('facility_type','?')}\n"
            f"Anomaly: {'✅ YES' if r['anomaly_flag'] else 'no'} | "
            f"prob_A={r['prob_A']:.2f}"
        ), axis=1)
        layers.append(pdk.Layer("ScatterplotLayer", data=inc,
            get_position=["lon","lat"], get_color="color", get_radius=20000,
            pickable=True, opacity=1.0, stroked=True,
            get_line_color=[255,255,255], line_width_min_pixels=2))

    return pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(latitude=22.0, longitude=82.0, zoom=4.5),
        tooltip={"html":"<pre style='font-size:12px;color:white'>{tip}</pre>",
                 "style":{"background":"rgba(0,0,0,0.85)","borderRadius":"6px","padding":"8px"}},
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔥 SIH26162")
    st.caption("AI-Based Detection and Classification of Industrial Fires\nand Persistent Thermal Sources")
    st.divider()

    st.markdown("**Severity filter**")
    sev_filter = st.multiselect("Severity", ["CRITICAL","HIGH","MEDIUM","LOW"],
        default=["CRITICAL","HIGH","MEDIUM","LOW"], label_visibility="collapsed")

    st.markdown("**Status filter**")
    status_filter = st.multiselect("Status", alert_store.LIFECYCLE_STATES,
        default=["DETECTED","VALIDATING","ALERTED","ESCALATED","MONITORING"],
        label_visibility="collapsed")

    show_incidents = st.checkbox("Show confirmed incident sites", value=True)
    colour_by = st.radio("Map colour by",
        ["Output Class (PS classification)", "Alert Severity"], index=0)

    st.divider()
    st.markdown("**🔄 Refresh**")
    if st.button("Re-run pipeline", use_container_width=True):
        with st.spinner("Running …"):
            r = run_pipeline(fresh=True)
            load_scored.clear(); load_incidents.clear()
        st.success(f"Done — CRITICAL:{r['counts']['CRITICAL']} HIGH:{r['counts']['HIGH']}")
        st.rerun()

    st.divider()
    st.markdown("""
**PS Output Classes**
🔴 **Industrial Fire / Abnormal Thermal Event**
Accidental fires, gas leaks, explosions, abnormal thermal events.

🟠 **Persistent Industrial Thermal Source**
Continuous industrial heat: gas flares, refineries, steel plants, kilns.

🟢 **Forest / Agricultural Fire**
Wildfires, paddy-stubble burning, savanna fires.

⬜ **Confirmed incident site** (past events)
""")

    st.divider()
    st.caption(
        "Data: NASA FIRMS VIIRS 375 m · VNF Gas Flare Catalogue · "
        "WRI GPPD · OpenStreetMap  \n"
        "Model: RandomForest trained globally, India holdout.  \n"
        "Framing: *anomalous departure from known patterns*, "
        "not confirmed fire detection."
    )


# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("# 🔥 Industrial Fire & Thermal Anomaly Detection")
st.caption(
    "**SIH26162** — AI-enabled geospatial system · "
    "NASA FIRMS NRT → AI Classifier → Risk Engine → Alert Feed + GIS Export  \n"
    "Integrates: thermal anomaly data · land-cover information · "
    "industrial infrastructure databases (OSM/GPPD) · satellite imagery (VIIRS 375 m)"
)

# ── Stats bar — PS output class counts ────────────────────────────────────────
scored_df = load_scored()
c = alert_store.counts()
now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Active alerts", c["active"])
col2.metric("🔴 Industrial Fires", (scored_df["output_class"]==OUTPUT_CLASS_INDUSTRIAL_FIRE).sum() if not scored_df.empty else "—")
col3.metric("🟠 Persistent Sources", (scored_df["output_class"]==OUTPUT_CLASS_PERSISTENT_SOURCE).sum() if not scored_df.empty else "—")
col4.metric("🟢 Natural Fires", (scored_df["output_class"]==OUTPUT_CLASS_NATURAL_FIRE).sum() if not scored_df.empty else "—")
col5.metric("🔴 CRITICAL alerts", c["CRITICAL"])
col6.metric("Last refreshed", now_str)

st.divider()

# ── Main layout: alerts + map ──────────────────────────────────────────────────
col_alert, col_map = st.columns([1, 1.6], gap="medium")

with col_alert:
    alerts = alert_store.get_alerts(
        severity=sev_filter or None,
        status=status_filter or None,
    )
    st.markdown(f"### Alert Feed — {len(alerts)} alerts")

    for sev in ["CRITICAL","HIGH","MEDIUM","LOW"]:
        if sev not in sev_filter:
            continue
        sev_alerts = [a for a in alerts if a["severity"] == sev]
        if not sev_alerts:
            continue
        with st.expander(
            f"{SEVERITY_EMOJI[sev]} **{sev}** — {len(sev_alerts)} alerts",
            expanded=(sev in ("CRITICAL","HIGH")),
        ):
            for a in sev_alerts[:20]:
                st.markdown(_alert_card(a), unsafe_allow_html=True)
                if sev in ("CRITICAL","HIGH") and a["status"] in ("ALERTED","ESCALATED"):
                    b1, b2, b3 = st.columns(3)
                    if b1.button("Acknowledge", key=f"ack_{a['alert_id']}"):
                        alert_store.update_status(a["alert_id"], "MONITORING"); st.rerun()
                    if b2.button("Escalate", key=f"esc_{a['alert_id']}"):
                        alert_store.update_status(a["alert_id"], "ESCALATED"); st.rerun()
                    if b3.button("Resolve", key=f"res_{a['alert_id']}"):
                        alert_store.update_status(a["alert_id"], "EXTINGUISHED"); st.rerun()
            if len(sev_alerts) > 20:
                st.caption(f"… and {len(sev_alerts)-20} more")

with col_map:
    st.markdown("### Live Detection Map — India")
    incidents = load_incidents()
    st.pydeck_chart(_build_map(scored_df, incidents, show_incidents, colour_by),
                    use_container_width=True, height=560)

    # Map legend
    lcols = st.columns(3)
    lcols[0].markdown("🔴 Industrial Fire")
    lcols[1].markdown("🟠 Persistent Source")
    lcols[2].markdown("🟢 Natural Fire")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_gis, tab_ps, tab_inc, tab_model, tab_limits = st.tabs([
    "📥 GIS Export", "📋 PS Classification", "📌 Confirmed Incidents",
    "🤖 Model Details", "⚠️ Limitations"
])

with tab_gis:
    st.markdown("### GIS Export — PS Deliverable ii")
    st.markdown(
        "Download alerts as **GeoJSON** for use in QGIS, ArcGIS, or any GIS platform. "
        "Each alert is a Point feature with full attribute table: output class, severity, "
        "land-cover context, facility hazard type, FRP, persistence, and narrative."
    )
    all_alerts = alert_store.get_alerts(severity=sev_filter or None)
    geojson_str = _alerts_to_geojson(all_alerts)

    col_dl1, col_dl2, col_dl3 = st.columns(3)
    col_dl1.download_button(
        "⬇️ Download GeoJSON (all alerts)",
        data=geojson_str,
        file_name=f"sih26162_alerts_{datetime.now().strftime('%Y%m%d_%H%M')}.geojson",
        mime="application/geo+json",
        use_container_width=True,
    )

    # CSV export
    if all_alerts:
        csv_df = pd.DataFrame(all_alerts)[[
            "alert_id","lat","lon","output_class","severity","status","risk_score",
            "land_cover_context","hazard_facility_type","frp_mw","persistence_count",
            "dist_nearest_facility_km","nearest_city","acq_date","narrative",
        ]]
        col_dl2.download_button(
            "⬇️ Download CSV",
            data=csv_df.to_csv(index=False),
            file_name=f"sih26162_alerts_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("#### GeoJSON preview (first 3 features)")
    preview = json.loads(geojson_str)
    preview["features"] = preview["features"][:3]
    st.code(json.dumps(preview, indent=2), language="json")

with tab_ps:
    st.markdown("### PS Deliverable i — Classification Output")
    st.markdown(
        "The system classifies every NASA FIRMS thermal hotspot into one of three categories "
        "aligned to the problem statement requirements:"
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        n = (scored_df["output_class"]==OUTPUT_CLASS_INDUSTRIAL_FIRE).sum() if not scored_df.empty else 0
        st.error(f"🔴 **Industrial Fire / Abnormal Thermal Event**\n\n{n} detections")
        st.markdown(
            "Hotspots whose thermal signature matches **neither** the persistent-flare pattern "
            "nor the natural-fire pattern. Candidates: accidental fires, gas leaks, explosions, "
            "abnormal process heat.  \n\n"
            "Facility types flagged: oil refineries, petrochemical complexes, chemical plants, "
            "pharmaceutical units, mining areas."
        )
    with c2:
        n = (scored_df["output_class"]==OUTPUT_CLASS_PERSISTENT_SOURCE).sum() if not scored_df.empty else 0
        st.warning(f"🟠 **Persistent Industrial Thermal Source**\n\n{n} detections")
        st.markdown(
            "Continuous thermal emissions matching known industrial-heat signatures. "
            "VNF gas-flare catalogue used as labeling oracle (1,500–2,000 K spectral temp). "
            "Includes: thermal power plants, steel smelters, brick kilns, gas flaring stacks, "
            "LNG terminals.  \n\n"
            "Persistent re-detection across the 5-day NRT window is a key discriminator."
        )
    with c3:
        n = (scored_df["output_class"]==OUTPUT_CLASS_NATURAL_FIRE).sum() if not scored_df.empty else 0
        st.success(f"🟢 **Forest / Agricultural Fire**\n\n{n} detections")
        st.markdown(
            "Thermal events consistent with natural or crop-residue burning patterns. "
            "Short-burst detections in forest/cropland land-cover zones, correlated with "
            "agricultural burning seasons (Oct–Nov Punjab/Haryana; Jul–Sep Africa/Amazon). "
            "Distinguished from industrial heat by low persistence and land-cover context."
        )

    st.divider()
    st.markdown("#### Land-Cover Distribution (PS: 'integrates land-cover information')")
    if not scored_df.empty:
        lc_df = (scored_df.groupby(["land_cover_context","output_class"])
                 .size().reset_index(name="count"))
        st.dataframe(lc_df.sort_values("count", ascending=False),
                     hide_index=True, use_container_width=True)

    st.divider()
    st.markdown("#### Facility Hazard Type Distribution (PS: oil refineries, power plants, steel, mining, LNG)")
    if not scored_df.empty:
        ht_df = (scored_df.groupby(["hazard_facility_type","output_class"])
                 .size().reset_index(name="count"))
        st.dataframe(ht_df.sort_values("count", ascending=False),
                     hide_index=True, use_container_width=True)

with tab_inc:
    st.markdown("### Confirmed India Industrial Incidents — Anomaly Scoring")
    st.caption(
        "30 curated major Indian industrial incidents (2019–2023) scored against the trained model. "
        "**21/30 (70%) flagged as Industrial Fire / Abnormal Thermal Event** — correctly identified "
        "as departing from both persistent-flare and natural-fire patterns."
    )
    incidents = load_incidents()
    if not incidents.empty:
        disp = incidents[[
            "incident_id","name","date","state","facility_type",
            "predicted_label","prob_A","prob_B_candidate","anomaly_flag",
            "dist_nearest_facility_km",
        ]].rename(columns={
            "predicted_label":"model_class",
            "prob_B_candidate":"prob_B",
            "dist_nearest_facility_km":"dist_fac_km",
            "anomaly_flag":"industrial_fire_flag",
        })
        st.dataframe(disp.sort_values("industrial_fire_flag", ascending=False),
                     hide_index=True, use_container_width=True)

    st.markdown("#### Case Studies")
    cs1, cs2, cs3 = st.columns(3)
    with cs1:
        st.error("🔴 Jharia Coalfield")
        st.markdown("Underground coal seam fire active since 1916. **Flagged as Industrial Fire / Abnormal Event.** 4 repeat FIRMS detections. Near Mining/Extraction facility. Land cover: Mining/Industrial Corridor.")
    with cs2:
        st.success("🟢 Punjab Stubble Burning (Oct–Nov)")
        st.markdown("Seasonal kharif-residue burning. **Correctly classified as Forest/Agricultural Fire.** Agri-season flag active. Land cover: Cropland — Kharif/Rabi (Punjab/Haryana).")
    with cs3:
        st.warning("🟠 Vizag LG Polymers Gas Leak")
        st.markdown("Styrene gas leak, 2020, 12 fatalities. **Flagged as Industrial Fire.** Near Oil Refinery/Petrochemical facility (1.2 km). Anomaly score 0.52.")

with tab_model:
    st.markdown("### AI Model — Architecture & Evaluation")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
**Data sources integrated (PS requirement):**
- 🛰️ **Satellite data:** NASA FIRMS VIIRS 375 m NRT (thermal anomaly data)
- 🌿 **Land-cover:** Coordinate-based India zone classification + agri-season flag
- 🏭 **Industrial databases:** WRI GPPD (34,936 power plants) + OSM industrial polygons (37,688 India features)
- 🔥 **VNF gas flare catalogue:** ORNL DAAC 2012–2019 (83,641 gas flare sites, 1,500–2,000 K spectral temp)

**Labeling approach:**
VNF used as spatial labeling oracle — FIRMS detections within 5 km of a known VNF flare site → Persistent Source.
Remaining global FIRMS → Natural Fire candidate.
Anomaly (max_prob < 0.55) → Industrial Fire / Abnormal Event.

**PS facility types covered:**
Oil Refinery ✅ · Thermal Power Plant ✅ · Mining ✅ · Steel/Metal ✅ · Brick Kiln ✅ · LNG/Gas Terminal ✅ · Chemical/Pharma ✅
""")
    with c2:
        st.markdown("""
**Three-way evaluation (anti-leakage design):**

| Evaluation | Accuracy | Class A F1 |
|---|---|---|
| Random split (inflated baseline) | 97.25% | 0.24 |
| Spatial holdout (honest) | 98.06% | 0.18 |
| India holdout (locked) | scored only | — |

**Training:** Global FIRMS NRT · India entirely withheld as test region · Spatial grid 80/20 split

**Feature importances:**
| Feature | Importance |
|---|---|
| Distance to industrial facility | 29.3% |
| Nighttime detection flag | 25.3% |
| Pixel brightness temperature | 21.4% |
| Persistence count (5-day) | 13.9% |
| Fire Radiative Power (FRP) | 10.1% |
""")

with tab_limits:
    st.markdown("""
### Limitations & Scientific Caveats

**Classification:**
- No confirmed industrial fire ground-truth dataset exists (India or global). The "Industrial Fire" output class is derived from the anomaly detection — hotspots matching neither the persistent-flare nor natural-fire patterns — not from direct supervised training on confirmed incidents.
- Class A (Persistent Source) training set: 1,901 FIRMS examples via VNF oracle. F1 = 0.18 on spatial holdout. Historical FIRMS archive would improve recall substantially.

**Land-cover:**
- Land-cover context is derived from coordinate-based India zone rules + agri-season flag. Full MODIS MCD12Q1 or ESA CCI Land Cover integration would improve precision, particularly for forest vs agricultural vs mixed land-cover discrimination.

**Facility coverage:**
- LNG terminals are present in the facility layer via OSM `port` tags but are a small fraction. Dedicated LNG infrastructure datasets (e.g., Global LNG Tracker) would improve coverage.
- Steel mills and petrochemical complexes are mapped via generic `landuse=industrial` OSM tag where specific sub-tags are absent.

**Temporal:**
- FIRMS NRT covers only the last 5 days. Historical incident matching (2019–2023 events) requires LAADS DAAC archive download.
- VNF persistence data is annual (2012–2019); NRT persistence counts are 5-day only.

**General:**
- All alerts require human verification before operational dispatch.
- Correct framing: *"anomalous departure from known persistent-industrial and natural-fire patterns"* — not confirmed fire detection.
""")
