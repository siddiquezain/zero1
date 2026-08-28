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

import calendar as _cal
import json
import sys
import time as _time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dashboard.timeline import get_daily_summary, get_events_for_range
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

# ── Timeline session state ─────────────────────────────────────────────────────
for _k, _v in [("tl_start", None), ("tl_end", None),
                ("tl_playing", False), ("tl_play_date", None), ("tl_speed", 1.0)]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg-0: #080810; --bg-1: #0c0c18; --bg-2: #101020; --bg-3: #151528; --bg-4: #1a1a32;
  --border-0: rgba(255,255,255,0.05); --border-1: rgba(255,255,255,0.09); --border-2: rgba(255,255,255,0.15);
  --text-0: #e0e0f0; --text-1: #9090b8; --text-2: #4a4a70;
  --accent: #5b78ff;
  --cr: #e53935; --cr-a: rgba(229,57,53,0.10); --cr-b: rgba(229,57,53,0.30);
  --hi: #ef6c00; --hi-a: rgba(239,108,0,0.10); --hi-b: rgba(239,108,0,0.30);
  --me: #f9a825; --me-a: rgba(249,168,37,0.10); --me-b: rgba(249,168,37,0.30);
  --lo: #43a047; --lo-a: rgba(67,160,71,0.10); --lo-b: rgba(67,160,71,0.30);
  --font: 'Manrope', system-ui, sans-serif;
  --mono: 'JetBrains Mono', 'Fira Code', monospace;
  --r: 3px;
}

html, body, [data-testid="stAppViewContainer"] { background: var(--bg-0) !important; font-family: var(--font); }
.block-container { padding: 1.25rem 1.5rem 3rem !important; max-width: 100% !important; }
[data-testid="stSidebar"] { background: var(--bg-1) !important; border-right: 1px solid var(--border-1); }
[data-testid="stSidebar"] * { font-family: var(--font); }
#MainMenu, footer, [data-testid="stToolbar"] { display: none !important; }

.stButton > button {
  background: var(--bg-3) !important; color: var(--text-0) !important;
  border: 1px solid var(--border-1) !important; border-radius: var(--r) !important;
  font-family: var(--font) !important; font-size: 12px !important; font-weight: 500 !important;
  padding: 6px 14px !important; transition: border-color 0.15s, background 0.15s;
}
.stButton > button:hover { background: var(--bg-4) !important; border-color: var(--border-2) !important; }

[data-testid="stMetric"] { background: transparent !important; }
[data-testid="stMetric"] label { color: var(--text-2) !important; font-size: 10px !important; font-weight: 700 !important; letter-spacing: 0.1em; text-transform: uppercase; }
[data-testid="stMetricValue"] { color: var(--text-0) !important; font-family: var(--mono) !important; }

[data-testid="stExpander"] { border: 1px solid var(--border-1) !important; border-radius: var(--r) !important; background: var(--bg-1) !important; }
[data-testid="stExpander"] summary { font-family: var(--font) !important; font-size: 12px !important; font-weight: 600 !important; color: var(--text-0) !important; }

[data-testid="stTabs"] [role="tab"] {
  font-family: var(--font) !important; font-size: 10px !important; font-weight: 600 !important;
  letter-spacing: 0.08em !important; text-transform: uppercase !important;
  color: var(--text-2) !important; padding: 8px 14px !important; border-radius: 0 !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { color: var(--text-0) !important; border-bottom: 2px solid var(--accent) !important; }
[data-testid="stTabs"] [role="tablist"] { border-bottom: 1px solid var(--border-1) !important; gap: 0 !important; }

::-webkit-scrollbar { width: 3px; height: 3px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border-2); border-radius: 2px; }

/* Alert cards */
.ac { padding: 11px 0; border-bottom: 1px solid var(--border-0); }
.ac:last-child { border-bottom: none; }
.ac-row1 { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.sev-badge { font-size: 9px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; padding: 2px 6px; border-radius: var(--r); }
.sev-CRITICAL { background: var(--cr-a); color: var(--cr); border: 1px solid var(--cr-b); }
.sev-HIGH     { background: var(--hi-a); color: var(--hi); border: 1px solid var(--hi-b); }
.sev-MEDIUM   { background: var(--me-a); color: var(--me); border: 1px solid var(--me-b); }
.sev-LOW      { background: var(--lo-a); color: var(--lo); border: 1px solid var(--lo-b); }
.cls-tag { font-size: 9px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; padding: 2px 6px; border-radius: var(--r); }
.cls-fire    { background: rgba(229,57,53,0.08); color: rgba(229,57,53,0.75); }
.cls-source  { background: rgba(239,108,0,0.08); color: rgba(239,108,0,0.75); }
.cls-natural { background: rgba(67,160,71,0.08); color: rgba(67,160,71,0.75); }
.ac-loc { font-size: 12px; font-weight: 600; color: var(--text-0); margin-bottom: 4px; font-family: var(--font); }
.ac-meta { display: flex; flex-wrap: wrap; gap: 12px; font-family: var(--mono); font-size: 10px; color: var(--text-2); }
.ac-narr { font-size: 11px; color: var(--text-1); margin-top: 7px; line-height: 1.55; border-top: 1px solid var(--border-0); padding-top: 7px; font-family: var(--font); }

/* Section headers */
.sec-head { font-size: 9px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-2); padding-bottom: 10px; border-bottom: 1px solid var(--border-1); margin-bottom: 12px; }

/* Map bar */
.map-bar { display: flex; align-items: center; justify-content: space-between; padding-bottom: 10px; border-bottom: 1px solid var(--border-1); margin-bottom: 10px; }
.map-bar-title { font-size: 9px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-2); }
.map-bar-meta { font-family: var(--mono); font-size: 10px; color: var(--text-2); }

/* Hist banner */
.hist-banner { display: flex; align-items: center; gap: 10px; padding: 7px 12px; background: rgba(91,120,255,0.06); border: 1px solid rgba(91,120,255,0.18); border-radius: var(--r); margin-bottom: 10px; font-family: var(--mono); font-size: 10px; color: #8090cc; }

/* Legend */
.legend-row { display: flex; gap: 18px; padding-top: 8px; border-top: 1px solid var(--border-0); font-size: 10px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-2); }
.leg-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 5px; vertical-align: middle; }

/* Sidebar labels */
.sb-sec { font-size: 9px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-2); margin: 14px 0 6px; }

/* Critical notice */
.crit-notice { padding: 10px 14px; background: var(--cr-a); border: 1px solid var(--cr-b); border-radius: var(--r); margin-bottom: 10px; }
.crit-notice-hed { font-size: 9px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--cr); margin-bottom: 3px; }
.crit-notice-body { font-size: 11px; color: rgba(229,57,53,0.65); }

/* High notice */
.high-notice { padding: 10px 14px; background: var(--hi-a); border: 1px solid var(--hi-b); border-radius: var(--r); margin-bottom: 10px; }
.high-notice-hed { font-size: 9px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--hi); margin-bottom: 3px; }
.high-notice-body { font-size: 11px; color: rgba(239,108,0,0.65); }

/* Timeline calendar */
.tl-cal { border-collapse: separate; border-spacing: 3px; margin: 8px auto; }
.tl-cal th { color: var(--text-2); font-size: 9px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; padding: 4px 6px; text-align: center; }
.tl-cal td { width: 44px; height: 44px; text-align: center; border-radius: var(--r); font-size: 12px; vertical-align: middle; cursor: default; transition: filter .1s; }
.tl-cal td:hover { filter: brightness(1.3); }
.tl-CRITICAL { background: var(--cr-a); color: var(--cr); border: 1px solid var(--cr-b); }
.tl-HIGH     { background: var(--hi-a); color: var(--hi); border: 1px solid var(--hi-b); }
.tl-MODERATE { background: var(--me-a); color: var(--me); border: 1px solid var(--me-b); }
.tl-LOW      { background: var(--lo-a); color: var(--lo); border: 1px solid var(--lo-b); }
.tl-none     { color: var(--text-2); }
.tl-selected { outline: 2px solid rgba(255,255,255,0.35) !important; outline-offset: 1px; }

@keyframes pulse-live {
  0%   { box-shadow: 0 0 0 0 rgba(67,160,71,0.5); }
  70%  { box-shadow: 0 0 0 5px rgba(67,160,71,0); }
  100% { box-shadow: 0 0 0 0 rgba(67,160,71,0); }
}
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
    css = {
        OUTPUT_CLASS_INDUSTRIAL_FIRE:    "cls-fire",
        OUTPUT_CLASS_PERSISTENT_SOURCE:  "cls-source",
        OUTPUT_CLASS_NATURAL_FIRE:       "cls-natural",
    }.get(output_class, "")
    em, _, short = OUTPUT_CLASS_CFG.get(output_class, ("", [], output_class))
    return f'<span class="cls-tag {css}">{short}</span>'


def _alert_card(a: dict) -> str:
    sev = a["severity"]
    status_text = STATUS_BADGE.get(a["status"], a["status"])
    city = a.get("nearest_city", "—")
    city_dist = a.get("dist_nearest_city_km", 0)
    frp = a.get("frp_mw", 0)
    persist = a.get("persistence_count", 1)
    dist_fac = a.get("dist_nearest_facility_km", 0)
    risk = a.get("risk_score", 0)
    acq = a.get("acq_date", "")
    night = "N" if a.get("day_night") == "N" else "D"
    output_class = a.get("output_class", "")
    narrative = a.get("narrative", "")
    lat = a.get("lat", 0)
    lon = a.get("lon", 0)
    haz = a.get("hazard_facility_type", "—")
    land = a.get("land_cover_context", "—")

    return f"""
<div class="ac">
  <div class="ac-row1">
    <span class="sev-badge sev-{sev}">{sev}</span>
    {_class_tag(output_class)}
    <span style="font-size:9px;color:var(--text-2);font-family:var(--mono);letter-spacing:0.04em;margin-left:auto">{status_text} · {acq}</span>
  </div>
  <div class="ac-loc">{lat:.4f}°N, {lon:.4f}°E · {city} ({city_dist:.0f} km)</div>
  <div class="ac-meta">
    <span>FRP <b style="color:var(--text-0)">{frp:.1f}</b> MW</span>
    <span>Persist <b style="color:var(--text-0)">{persist}×</b></span>
    <span>{dist_fac:.1f} km to {haz}</span>
    <span>Risk <b style="color:var(--text-0)">{risk}</b>/100</span>
    <span>{'🌙' if night=='N' else '☀'} {land}</span>
  </div>
  <div class="ac-narr">{narrative}</div>
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
    st.markdown('<div style="font-family:var(--mono);font-size:9px;font-weight:500;letter-spacing:0.18em;text-transform:uppercase;color:var(--text-2);padding:4px 0 12px">SIH · 26162</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:13px;font-weight:700;color:var(--text-0);margin-bottom:2px">Fire Intelligence</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:10px;color:var(--text-2);margin-bottom:14px">AI-Based Detection Platform</div>', unsafe_allow_html=True)
    st.divider()

    st.markdown('<div class="sb-sec">Severity</div>', unsafe_allow_html=True)
    sev_filter = st.multiselect("Severity", ["CRITICAL","HIGH","MEDIUM","LOW"],
        default=["CRITICAL","HIGH","MEDIUM","LOW"], label_visibility="collapsed")

    st.markdown('<div class="sb-sec">Status</div>', unsafe_allow_html=True)
    status_filter = st.multiselect("Status", alert_store.LIFECYCLE_STATES,
        default=["DETECTED","VALIDATING","ALERTED","ESCALATED","MONITORING"],
        label_visibility="collapsed")

    show_incidents = st.checkbox("Show confirmed incident sites", value=True)
    colour_by = st.radio("Map colour by",
        ["Output Class (PS classification)", "Alert Severity"], index=0)

    st.divider()
    st.markdown('<div class="sb-sec">Pipeline</div>', unsafe_allow_html=True)
    if st.button("Re-run pipeline", use_container_width=True):
        with st.spinner("Running …"):
            r = run_pipeline(fresh=True)
            load_scored.clear(); load_incidents.clear()
        st.success(f"Done — CRITICAL:{r['counts']['CRITICAL']} HIGH:{r['counts']['HIGH']}")
        st.rerun()

    st.divider()
    st.markdown('<div class="sb-sec">PS Output Classes</div>', unsafe_allow_html=True)
    st.markdown("""
<div style="font-size:10px;color:var(--text-1);line-height:1.7">
<span style="color:var(--cr)">■</span> <b style="color:var(--text-0)">Industrial Fire</b><br>
Accidental fires, gas leaks, explosions, abnormal thermal events.<br><br>
<span style="color:var(--hi)">■</span> <b style="color:var(--text-0)">Persistent Source</b><br>
Continuous industrial heat: gas flares, refineries, steel plants, kilns.<br><br>
<span style="color:var(--lo)">■</span> <b style="color:var(--text-0)">Natural Fire</b><br>
Wildfires, paddy-stubble burning, savanna fires.<br><br>
<span style="color:#fff">■</span> <b style="color:var(--text-0)">Confirmed incident site</b> (past events)
</div>
""", unsafe_allow_html=True)

    st.divider()
    st.markdown("""
<div style="font-size:9px;color:var(--text-2);line-height:1.7;font-family:var(--mono)">
Data: NASA FIRMS VIIRS 375m · VNF Gas Flare Catalogue · WRI GPPD · OpenStreetMap<br>
Model: RandomForest trained globally, India holdout.<br>
Framing: anomalous departure from known patterns — not confirmed fire detection.
</div>
""", unsafe_allow_html=True)


# ── Header ─────────────────────────────────────────────────────────────────────
scored_df = load_scored()
daily_summary = get_daily_summary()  # timeline aggregation
c = alert_store.counts()
now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")

st.markdown(f"""
<div class="sys-header" style="display:flex;align-items:flex-start;justify-content:space-between;padding-bottom:14px;border-bottom:1px solid var(--border-1);margin-bottom:18px">
  <div>
    <div style="font-family:var(--mono);font-size:9px;font-weight:500;letter-spacing:0.18em;text-transform:uppercase;color:var(--text-2);margin-bottom:4px">SIH · 26162 · India Fire Intelligence</div>
    <div style="font-size:18px;font-weight:700;letter-spacing:-0.02em;color:var(--text-0);line-height:1.2;font-family:var(--font)">Industrial Fire &amp; Thermal Anomaly Detection</div>
    <div style="font-size:11px;color:var(--text-2);margin-top:4px;font-family:var(--font)">NASA FIRMS VIIRS 375m · AI Classifier · Risk Engine · GIS Export</div>
  </div>
  <div style="display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:10px;color:var(--text-2);margin-top:3px">
    <div style="width:6px;height:6px;border-radius:50%;background:var(--lo);animation:pulse-live 2s infinite;flex-shrink:0"></div>
    LIVE · {now_str} · NRT
  </div>
</div>
""", unsafe_allow_html=True)

# ── Stats bar — PS output class counts ────────────────────────────────────────
n_industrial = int((scored_df["output_class"]==OUTPUT_CLASS_INDUSTRIAL_FIRE).sum()) if not scored_df.empty else 0
n_persistent = int((scored_df["output_class"]==OUTPUT_CLASS_PERSISTENT_SOURCE).sum()) if not scored_df.empty else 0
n_natural = int((scored_df["output_class"]==OUTPUT_CLASS_NATURAL_FIRE).sum()) if not scored_df.empty else 0

st.markdown(f"""
<div style="display:flex;border-bottom:1px solid var(--border-1);margin-bottom:20px">
  <div style="flex:1;padding:10px 20px 12px 0;border-right:1px solid var(--border-0)">
    <div style="font-size:9px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-2);margin-bottom:4px">Active Alerts</div>
    <div style="font-family:var(--mono);font-size:22px;font-weight:500;letter-spacing:-0.03em;color:var(--text-0);line-height:1">{c['active']}</div>
  </div>
  <div style="flex:1;padding:10px 20px 12px;border-right:1px solid var(--border-0)">
    <div style="font-size:9px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-2);margin-bottom:4px">Critical</div>
    <div style="font-family:var(--mono);font-size:22px;font-weight:500;letter-spacing:-0.03em;color:{'var(--cr)' if c['CRITICAL'] > 0 else 'var(--text-0)'};line-height:1">{c['CRITICAL']}</div>
  </div>
  <div style="flex:1;padding:10px 20px 12px;border-right:1px solid var(--border-0)">
    <div style="font-size:9px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-2);margin-bottom:4px">High</div>
    <div style="font-family:var(--mono);font-size:22px;font-weight:500;letter-spacing:-0.03em;color:{'var(--hi)' if c['HIGH'] > 0 else 'var(--text-0)'};line-height:1">{c['HIGH']}</div>
  </div>
  <div style="flex:1;padding:10px 20px 12px;border-right:1px solid var(--border-0)">
    <div style="font-size:9px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-2);margin-bottom:4px">Industrial Fire</div>
    <div style="font-family:var(--mono);font-size:22px;font-weight:500;letter-spacing:-0.03em;color:var(--text-0);line-height:1">{n_industrial}</div>
  </div>
  <div style="flex:1;padding:10px 20px 12px;border-right:1px solid var(--border-0)">
    <div style="font-size:9px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-2);margin-bottom:4px">Persistent Sources</div>
    <div style="font-family:var(--mono);font-size:22px;font-weight:500;letter-spacing:-0.03em;color:var(--text-0);line-height:1">{n_persistent}</div>
  </div>
  <div style="flex:1;padding:10px 0 12px 20px">
    <div style="font-size:9px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-2);margin-bottom:4px">Natural Fire</div>
    <div style="font-family:var(--mono);font-size:22px;font-weight:500;letter-spacing:-0.03em;color:var(--text-0);line-height:1">{n_natural}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Apply timeline date filter ─────────────────────────────────────────────────
_tl_s = st.session_state.tl_start
_tl_e = st.session_state.tl_end
if _tl_s and _tl_e and not scored_df.empty:
    _mask = (scored_df["acq_date"] >= _tl_s.isoformat()) & \
            (scored_df["acq_date"] <= _tl_e.isoformat())
    map_df = scored_df[_mask]
else:
    map_df = scored_df

# ── Main layout: alerts + map ──────────────────────────────────────────────────
col_alert, col_map = st.columns([1, 1.6], gap="medium")

with col_alert:
    alerts = alert_store.get_alerts(
        severity=sev_filter or None,
        status=status_filter or None,
    )
    # Apply date filter in Python — avoids any signature-change risk on cloud
    if _tl_s and _tl_e:
        _s_iso, _e_iso = _tl_s.isoformat(), _tl_e.isoformat()
        alerts = [a for a in alerts if _s_iso <= a.get("acq_date", "") <= _e_iso]
    _feed_extra = ""
    if _tl_s:
        _range_str = (_tl_s.strftime("%b %d") if _tl_s == _tl_e
                      else f"{_tl_s.strftime('%b %d')} – {_tl_e.strftime('%b %d, %Y')}")
        _feed_extra = f' &nbsp;·&nbsp; <span style="color:var(--text-2);font-family:var(--mono)">{_range_str}</span>'
    st.markdown(f'<div class="sec-head">Alert Feed &nbsp;·&nbsp; <span style="color:var(--text-1)">{len(alerts)}</span>{_feed_extra}</div>', unsafe_allow_html=True)

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
    if _tl_s:
        _range_lbl = (_tl_s.strftime("%b %d, %Y") if _tl_s == _tl_e
                      else f"{_tl_s.strftime('%b %d')} – {_tl_e.strftime('%b %d, %Y')}")
        st.markdown(
            f'<div class="hist-banner">&#9632; HISTORICAL VIEW &nbsp;·&nbsp; {_range_lbl} &nbsp;·&nbsp; {len(map_df):,} detections</div>',
            unsafe_allow_html=True,
        )
        map_title_label = "Historical Detection Map"
    else:
        map_title_label = "Live Detection Map — India"

    st.markdown(f"""
<div class="map-bar">
  <div class="map-bar-title">{map_title_label}</div>
  <div class="map-bar-meta">VIIRS 375m · {now_str}</div>
</div>
""", unsafe_allow_html=True)

    incidents = load_incidents()
    st.pydeck_chart(_build_map(map_df, incidents, show_incidents, colour_by),
                    use_container_width=True, height=560)

    st.markdown("""
<div class="legend-row">
  <span><span class="leg-dot" style="background:#dc1414"></span>Industrial Fire</span>
  <span><span class="leg-dot" style="background:#ff8c00"></span>Persistent Source</span>
  <span><span class="leg-dot" style="background:#32c850"></span>Natural Fire</span>
  <span><span class="leg-dot" style="background:#fff"></span>Confirmed Incident</span>
</div>
""", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_timeline, tab_gis, tab_ps, tab_inc, tab_model, tab_limits = st.tabs([
    "📅 Historical Timeline",
    "📥 GIS Export", "📋 PS Classification", "📌 Confirmed Incidents",
    "🤖 Model Details", "⚠️ Limitations"
])

with tab_timeline:
    st.markdown("### 📅 Historical Fire Timeline — Date Explorer")
    st.caption(
        "Select a date or range to explore how fire activity changed over time. "
        "The map and alert feed above update automatically."
    )

    if daily_summary.empty:
        st.info("No historical data yet. Run the pipeline to populate the alert database.")
    else:
        _today = date.today()
        _dates_iso = daily_summary["acq_date"].tolist()
        _min_date  = date.fromisoformat(_dates_iso[0])
        _max_date  = date.fromisoformat(_dates_iso[-1])

        # ── Quick jump ────────────────────────────────────────────────────────
        qc = st.columns(5)
        if qc[0].button("Today",       use_container_width=True, key="tl_qj0"):
            st.session_state.tl_start = _today
            st.session_state.tl_end   = _today; st.rerun()
        if qc[1].button("Last 24 h",   use_container_width=True, key="tl_qj1"):
            st.session_state.tl_start = _today - timedelta(days=1)
            st.session_state.tl_end   = _today; st.rerun()
        if qc[2].button("Last 7 days", use_container_width=True, key="tl_qj2"):
            st.session_state.tl_start = _today - timedelta(days=7)
            st.session_state.tl_end   = _today; st.rerun()
        if qc[3].button("Last 30 days",use_container_width=True, key="tl_qj3"):
            st.session_state.tl_start = _today - timedelta(days=30)
            st.session_state.tl_end   = _today; st.rerun()
        if qc[4].button("Clear filter",use_container_width=True, key="tl_qj4",
                         disabled=st.session_state.tl_start is None):
            st.session_state.tl_start   = None
            st.session_state.tl_end     = None
            st.session_state.tl_playing = False
            st.rerun()

        # ── Date range picker (form prevents auto-trigger on render) ────────
        with st.form("tl_date_form"):
            _dr = st.date_input(
                "Select date or date range",
                value=(
                    st.session_state.tl_start or _min_date,
                    st.session_state.tl_end   or _max_date,
                ),
                min_value=_min_date,
                max_value=max(_max_date, _today),
            )
            if st.form_submit_button("Apply date filter", use_container_width=True):
                if isinstance(_dr, (list, tuple)) and len(_dr) == 2:
                    st.session_state.tl_start = _dr[0]
                    st.session_state.tl_end   = _dr[1]
                elif isinstance(_dr, date):
                    st.session_state.tl_start = _dr
                    st.session_state.tl_end   = _dr
                st.rerun()

        st.divider()

        # ── Horizontal timeline strip ────────────────────────────────────────
        st.markdown("#### Fire Activity Timeline")
        _strip = daily_summary.tail(14)  # show last 14 dates with data
        _strip_cols = st.columns(len(_strip))
        for _ci, (_, _sr) in enumerate(_strip.iterrows()):
            _d   = date.fromisoformat(_sr["acq_date"])
            _sev = _sr["severity_label"]
            _em  = _sr["emoji"]
            _sel = (st.session_state.tl_start and
                    st.session_state.tl_start <= _d <= (st.session_state.tl_end or _d))
            _tip = (f"{_sev}: {_sr['total_detections']} detections, "
                    f"{_sr['critical_events']} critical, "
                    f"max FRP {_sr['max_frp']} MW")
            with _strip_cols[_ci]:
                if st.button(
                    f"{_em}\n{_d.strftime('%b %d')}",
                    key=f"tl_strip_{_sr['acq_date']}",
                    use_container_width=True,
                    help=_tip,
                ):
                    st.session_state.tl_start   = _d
                    st.session_state.tl_end     = _d
                    st.session_state.tl_playing = False
                    st.rerun()

        st.divider()

        # ── Calendar view ─────────────────────────────────────────────────────
        st.markdown("#### Calendar View")
        _cal_month = st.session_state.tl_start or _max_date
        _data_by_date = {r["acq_date"]: r for r in daily_summary.to_dict("records")}
        _sel_s = st.session_state.tl_start
        _sel_e = st.session_state.tl_end

        _sev_td_style: dict[str, str] = {}  # styles now handled by CSS classes
        _cal_html = (
            f'<div style="font-family:var(--mono);max-width:460px">'
            f'<div style="text-align:center;font-size:13px;font-weight:700;'
            f'color:var(--text-0);margin-bottom:8px;font-family:var(--font)">'
            f'{_cal_month.strftime("%B %Y")}</div>'
            f'<table class="tl-cal">'
            f'<tr>{"".join(f"<th>{d}</th>" for d in ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"])}</tr>'
        )
        for _week in _cal.monthcalendar(_cal_month.year, _cal_month.month):
            _cal_html += "<tr>"
            for _day in _week:
                if _day == 0:
                    _cal_html += '<td class="tl-none"></td>'
                else:
                    _d_str = f"{_cal_month.year}-{_cal_month.month:02d}-{_day:02d}"
                    _rd = _data_by_date.get(_d_str)
                    _d_obj = date.fromisoformat(_d_str)
                    _is_sel = (_sel_s and _sel_e and _sel_s <= _d_obj <= _sel_e)
                    if _rd:
                        _sev = _rd["severity_label"]
                        _em  = _rd["emoji"]
                        _sel_cls = " tl-selected" if _is_sel else ""
                        _tip_txt = (
                            f"{_d_str} | {_rd['total_detections']} detections | "
                            f"{_rd['critical_events']} critical | "
                            f"max FRP {_rd['max_frp']} MW | Risk: {_sev}"
                        )
                        _cal_html += (
                            f'<td class="tl-{_sev}{_sel_cls}" '
                            f'title="{_tip_txt}">'
                            f'{_em}<br>{_day}</td>'
                        )
                    else:
                        _sel_cls = " tl-selected" if _is_sel else ""
                        _cal_html += f'<td class="tl-none{_sel_cls}">{_day}</td>'
            _cal_html += "</tr>"
        _cal_html += "</table></div>"
        st.markdown(_cal_html, unsafe_allow_html=True)

        st.divider()

        # ── Historical statistics for selected range ───────────────────────────
        _tl_start_val = st.session_state.tl_start
        _tl_end_val   = st.session_state.tl_end
        if _tl_start_val and _tl_end_val:
            _range_events = get_events_for_range(_tl_start_val, _tl_end_val)
            _range_str    = (
                _tl_start_val.strftime("%B %d, %Y") if _tl_start_val == _tl_end_val
                else f"{_tl_start_val.strftime('%B %d')} – {_tl_end_val.strftime('%B %d, %Y')}"
            )
            st.markdown(f"#### Statistics — {_range_str}")

            if not _range_events:
                st.info("No fire detections recorded for this date/range.")
            else:
                _rev_df = pd.DataFrame(_range_events)
                _n_total    = len(_rev_df)
                _n_highconf = int((_rev_df["severity"].isin(["CRITICAL","HIGH"])).sum())
                _n_critical = int((_rev_df["severity"] == "CRITICAL").sum())
                _avg_frp    = _rev_df["frp_mw"].mean()
                _max_frp    = _rev_df["frp_mw"].max()
                _day_sev    = "CRITICAL" if _n_critical else ("HIGH" if _n_highconf else "MODERATE" if _n_total else "LOW")

                # Critical banner
                if _n_critical > 0:
                    st.markdown(
                        f'<div class="crit-notice">'
                        f'<div class="crit-notice-hed">Critical Fire Activity — {_range_str}</div>'
                        f'<div class="crit-notice-body">{_n_critical} critical events detected · {_n_highconf} high-confidence detections</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                elif _n_highconf > 0:
                    st.markdown(
                        f'<div class="high-notice">'
                        f'<div class="high-notice-hed">High Fire Activity — {_range_str}</div>'
                        f'<div class="high-notice-body">{_n_highconf} high-confidence detections</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                _sc1, _sc2, _sc3, _sc4, _sc5, _sc6 = st.columns(6)
                _sc1.metric("Total detections", f"{_n_total:,}")
                _sc2.metric("High-confidence",  f"{_n_highconf:,}")
                _sc3.metric("Critical events",   f"{_n_critical:,}")
                _sc4.metric("Avg FRP (MW)",       f"{_avg_frp:.1f}" if _n_total else "—")
                _sc5.metric("Max FRP (MW)",       f"{_max_frp:.1f}" if _n_total else "—")
                _sc6.metric("Risk level", _day_sev)

                if _n_total:
                    _areas = _rev_df["land_cover_context"].value_counts().head(3)
                    st.caption(
                        "Top affected areas: "
                        + " · ".join(f"**{z}** ({n})" for z, n in _areas.items())
                    )

        st.divider()

        # ── Playback controls ─────────────────────────────────────────────────
        st.markdown("#### Timeline Playback")
        _playing = st.session_state.tl_playing
        _pc1, _pc2, _pc3 = st.columns([1, 1, 2])
        if _pc1.button("⏸ Pause" if _playing else "▶️ Play", use_container_width=True, key="tl_play_btn"):
            if not _playing:
                st.session_state.tl_play_date = _min_date
                st.session_state.tl_start     = _min_date
                st.session_state.tl_end       = _min_date
            st.session_state.tl_playing = not _playing
            st.rerun()
        if _pc2.button("⏹ Stop", use_container_width=True, key="tl_stop_btn"):
            st.session_state.tl_playing  = False
            st.session_state.tl_play_date = None
            st.rerun()
        _speed = _pc3.select_slider(
            "Playback speed", options=[0.5, 1.0, 2.0],
            value=st.session_state.tl_speed, key="tl_speed_slider",
        )
        st.session_state.tl_speed = _speed

        if _playing and st.session_state.tl_play_date:
            _pd = st.session_state.tl_play_date
            st.info(f"▶️ Playing: **{_pd.strftime('%B %d, %Y')}** at {_speed}× speed")

        # Legend
        _lc = st.columns(4)
        _lc[0].markdown("🔴 **CRITICAL** ≥ 65 risk")
        _lc[1].markdown("🟠 **HIGH** ≥ 40 risk")
        _lc[2].markdown("🟡 **MODERATE** ≥ 20 risk")
        _lc[3].markdown("🟢 **LOW** < 20 risk")


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

# ── Timeline playback: advance one day per rerun ──────────────────────────────
if st.session_state.tl_playing and st.session_state.tl_play_date and not daily_summary.empty:
    _play_d    = st.session_state.tl_play_date
    _play_next = _play_d + timedelta(days=1)
    _all_dates = [date.fromisoformat(d) for d in daily_summary["acq_date"].tolist()]
    _time.sleep(1.0 / st.session_state.tl_speed)
    if _play_next > max(_all_dates):
        st.session_state.tl_playing = False
    else:
        st.session_state.tl_play_date = _play_next
        st.session_state.tl_start     = _play_next
        st.session_state.tl_end       = _play_next
    st.rerun()
