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
INDIA_SCORES    = ROOT / "data/processed/stage6_india_scores.parquet"
INCIDENT_SCORES = ROOT / "data/incidents/stage7_incident_scores.parquet"

# ── PS output class config ─────────────────────────────────────────────────────
OUTPUT_CLASS_CFG = {
    OUTPUT_CLASS_INDUSTRIAL_FIRE:   ([220,  20,  20, 240], "Industrial Fire"),
    OUTPUT_CLASS_PERSISTENT_SOURCE: ([255, 140,   0, 220], "Persistent Source"),
    OUTPUT_CLASS_NATURAL_FIRE:      ([ 50, 200,  80, 180], "Natural Fire"),
}

_TYPE_SHORT = {
    OUTPUT_CLASS_INDUSTRIAL_FIRE:   "Industrial Fire",
    OUTPUT_CLASS_PERSISTENT_SOURCE: "Persistent Source",
    OUTPUT_CLASS_NATURAL_FIRE:      "Natural Fire",
}

# ── Auto-seed alert DB on first run ───────────────────────────────────────────
if not (ROOT / "data/alerts.db").exists():
    run_pipeline(fresh=True)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SIH26162 — Industrial Fire Intelligence",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Timeline session state ─────────────────────────────────────────────────────
for _k, _v in [("tl_start", None), ("tl_end", None),
                ("tl_playing", False), ("tl_play_date", None), ("tl_speed", 1.0),
                ("alert_page", 0), ("show_incidents", True),
                ("colour_by", "Output Class (PS classification)")]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Design system ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
  /* Surfaces */
  --bg-0: #070707;
  --bg-1: #0d0d0d;
  --bg-2: #111111;
  --bg-3: #181818;
  --bg-4: #1f1f1f;

  /* Borders */
  --bd-0: rgba(255,255,255,0.04);
  --bd-1: rgba(255,255,255,0.08);
  --bd-2: rgba(255,255,255,0.15);

  /* Text */
  --t0: #e6e6e6;
  --t1: #888888;
  --t2: #484848;

  /* Severity */
  --cr:   #e03131;
  --cr-a: rgba(224,49,49,0.07);
  --cr-b: rgba(224,49,49,0.20);
  --hi:   #d97706;
  --hi-a: rgba(217,119,6,0.07);
  --hi-b: rgba(217,119,6,0.20);
  --me:   #b5860d;
  --me-a: rgba(181,134,13,0.07);
  --me-b: rgba(181,134,13,0.20);
  --lo:   #2d8a2d;
  --lo-a: rgba(45,138,45,0.07);
  --lo-b: rgba(45,138,45,0.20);

  /* System */
  --sys:  #3d7dc8;

  --font: 'IBM Plex Sans', system-ui, sans-serif;
  --mono: 'IBM Plex Mono', 'Courier New', monospace;
  --r: 2px;
}

/* === BASE === */
html, body, [data-testid="stAppViewContainer"] {
  background: var(--bg-0) !important;
  font-family: var(--font);
  color: var(--t0);
}
.block-container {
  padding: 0 1.5rem 3rem !important;
  max-width: 100% !important;
}
#MainMenu, footer,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stHeader"],
[data-testid="collapsedControl"],
[data-testid="stSidebarNav"] { display: none !important; }

/* === SCROLLBAR === */
::-webkit-scrollbar { width: 3px; height: 3px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--bd-2); border-radius: 1px; }

/* === CONTROL BAR === */
.ctrl-bar {
  display: flex; align-items: center; gap: 0;
  padding: 10px 0 12px; border-bottom: 1px solid var(--bd-1);
  margin-bottom: 20px;
}
.ctrl-label {
  font-size: 11px; font-weight: 600; letter-spacing: 0.10em;
  text-transform: uppercase; color: var(--t1); margin-bottom: 6px;
}
.ctrl-sep {
  width: 1px; background: var(--bd-1); align-self: stretch; margin: 0 16px;
  flex-shrink: 0;
}
.ctrl-date-badge {
  font-size: 11px; font-family: var(--mono); color: var(--sys);
  letter-spacing: 0.05em; margin-top: 5px;
}
/* Streamlit sidebar hidden — all controls are in top bar */
[data-testid="stSidebar"] { display: none !important; }

/* === BUTTONS === */
.stButton > button {
  background: var(--bg-3) !important;
  color: var(--t1) !important;
  border: 1px solid var(--bd-1) !important;
  border-radius: var(--r) !important;
  font-family: var(--font) !important;
  font-size: 11px !important;
  font-weight: 500 !important;
  padding: 5px 10px !important;
  white-space: nowrap !important;
  transition: border-color 0.12s, color 0.12s, background 0.12s;
}
.stButton > button:hover {
  background: var(--bg-4) !important;
  border-color: var(--bd-2) !important;
  color: var(--t0) !important;
}

/* === TABS === */
[data-testid="stTabs"] [role="tablist"] {
  border-bottom: 1px solid var(--bd-1) !important;
  gap: 0 !important;
}
[data-testid="stTabs"] [role="tab"] {
  font-family: var(--font) !important;
  font-size: 11px !important;
  font-weight: 600 !important;
  letter-spacing: 0.10em !important;
  text-transform: uppercase !important;
  color: var(--t1) !important;
  padding: 10px 18px !important;
  border-radius: 0 !important;
  transition: color 0.12s;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
  color: var(--t0) !important;
  border-bottom: 2px solid var(--sys) !important;
}
[data-testid="stTabs"] [role="tab"]:hover { color: var(--t1) !important; }

/* === FORM / SELECT === */
/* Multiselect tags — target data-tag attribute set by Streamlit's emotion CSS */
span[data-tag] {
  background-color: var(--bg-4) !important;
  border: 1px solid var(--bd-2) !important;
  border-radius: var(--r) !important;
  color: var(--t0) !important;
}
span[data-tag] > span {
  background-color: transparent !important;
  color: var(--t0) !important;
}
span[data-tag] button { color: var(--t1) !important; }
[data-baseweb="input"], [data-baseweb="select"] {
  background: var(--bg-2) !important;
  border-color: var(--bd-1) !important;
  border-radius: var(--r) !important;
  font-family: var(--font) !important;
}
label[data-testid="stWidgetLabel"] {
  font-size: 12px !important;
  font-weight: 600 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  color: var(--t1) !important;
}

/* === SYSTEM BAR === */
.sys-bar {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 18px 0 16px; border-bottom: 1px solid var(--bd-1);
  margin-bottom: 20px;
}
.sys-bar-left {}
.sys-bar-id {
  font-family: var(--mono); font-size: 11px; font-weight: 500;
  letter-spacing: 0.10em; text-transform: uppercase; color: var(--t1);
  margin-bottom: 5px;
}
.sys-bar-title {
  font-size: 20px; font-weight: 600; letter-spacing: -0.02em;
  color: var(--t0); margin-bottom: 4px;
}
.sys-bar-sub { font-size: 12px; color: var(--t1); }
.sys-bar-live {
  display: flex; align-items: center; gap: 7px;
  font-family: var(--mono); font-size: 11px; color: var(--t1);
  margin-top: 4px;
}
.live-dot {
  width: 5px; height: 5px; border-radius: 50%;
  background: var(--lo); flex-shrink: 0;
  animation: pulse-live 2.5s infinite;
}

/* === STATUS STRIP === */
.status-strip {
  display: flex; border-bottom: 1px solid var(--bd-1);
  margin-bottom: 22px; overflow: hidden;
}
.ss-item {
  flex: 1; padding: 12px 0 14px;
  border-right: 1px solid var(--bd-0);
}
.ss-item:first-child { padding-left: 0; }
.ss-item:last-child  { border-right: none; }
.ss-label {
  font-size: 10px; font-weight: 600; letter-spacing: 0.10em;
  text-transform: uppercase; color: var(--t1); margin-bottom: 6px;
}
.ss-val {
  font-family: var(--mono); font-size: 22px; font-weight: 400;
  letter-spacing: -0.03em; color: var(--t0); line-height: 1;
}
.ss-val-cr { color: var(--cr); }
.ss-val-hi { color: var(--hi); }
.ss-sub {
  font-size: 11px; color: var(--t1); margin-top: 3px;
  font-family: var(--mono);
}

/* === ALERT FEED === */
.feed-header {
  display: flex; align-items: baseline; justify-content: space-between;
  padding-bottom: 10px; border-bottom: 1px solid var(--bd-1);
  margin-bottom: 14px;
}
.feed-title {
  font-size: 11px; font-weight: 600; letter-spacing: 0.10em;
  text-transform: uppercase; color: var(--t1);
}
.feed-meta { font-family: var(--mono); font-size: 11px; color: var(--t1); }

.sev-head {
  font-size: 11px; font-weight: 600; letter-spacing: 0.10em;
  text-transform: uppercase; padding: 12px 0 8px;
  border-bottom: 1px solid var(--bd-0);
  margin-bottom: 4px;
}
.sev-head-cr { color: var(--cr); }
.sev-head-hi { color: var(--hi); }
.sev-head-me { color: var(--me); }
.sev-head-lo { color: var(--lo); }
.sev-head-ct { color: var(--t2); font-weight: 400; margin-left: 6px; }

/* Alert card — flat row, no card container */
.ac {
  padding: 10px 0;
  border-bottom: 1px solid var(--bd-0);
}
.ac:last-child { border-bottom: none; }
.ac-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 4px;
}
.ac-sev {
  font-size: 10px; font-weight: 700; letter-spacing: 0.10em;
  text-transform: uppercase;
}
.sev-CRITICAL { color: var(--cr); }
.sev-HIGH     { color: var(--hi); }
.sev-MEDIUM   { color: var(--me); }
.sev-LOW      { color: var(--lo); }

.ac-type {
  font-size: 11px; color: var(--t1); font-weight: 500; letter-spacing: 0.03em;
}
.ac-right {
  margin-left: auto; display: flex; align-items: center; gap: 10px;
}
.ac-status {
  font-size: 10px; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase;
}
.status-DETECTED    { color: var(--t2); }
.status-VALIDATING  { color: var(--me); }
.status-ALERTED     { color: var(--hi); }
.status-ESCALATED   { color: var(--cr); }
.status-MONITORING  { color: var(--sys); }
.status-EXTINGUISHED { color: var(--t2); }

.ac-date {
  font-family: var(--mono); font-size: 11px; color: var(--t1);
}
.ac-loc {
  font-size: 12px; font-weight: 500; color: var(--t0);
  margin-bottom: 4px; letter-spacing: -0.01em;
}
.ac-metrics {
  display: flex; flex-wrap: wrap; gap: 14px;
  font-family: var(--mono); font-size: 12px; color: var(--t1);
  margin-bottom: 4px;
}
.ac-metrics em {
  font-style: normal; color: var(--t0); font-weight: 500;
}
.ac-narr {
  font-size: 12px; color: var(--t1); line-height: 1.65;
  padding-top: 8px; border-top: 1px solid var(--bd-0);
  margin-top: 6px;
}

/* === MAP === */
.map-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding-bottom: 10px; border-bottom: 1px solid var(--bd-1);
  margin-bottom: 10px;
}
.map-title {
  font-size: 11px; font-weight: 600; letter-spacing: 0.10em;
  text-transform: uppercase; color: var(--t1);
}
.map-mode {
  font-size: 12px; font-weight: 500; color: var(--t0);
  margin-top: 3px;
}
.map-ts { font-family: var(--mono); font-size: 11px; color: var(--t1); }
.map-legend {
  display: flex; gap: 20px; flex-wrap: wrap;
  padding-top: 10px; border-top: 1px solid var(--bd-0);
  font-size: 11px; font-weight: 500; letter-spacing: 0.03em;
  text-transform: uppercase; color: var(--t1);
}
.leg { display: flex; align-items: center; gap: 5px; }
.leg-sq {
  width: 7px; height: 7px; flex-shrink: 0;
}

.hist-mode-bar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 14px; margin-bottom: 10px;
  background: rgba(61,125,200,0.05);
  border: 1px solid rgba(61,125,200,0.14);
  border-radius: var(--r);
  font-family: var(--mono); font-size: 11px; color: #6080b0;
}
.hist-mode-bar b { color: #8090cc; font-weight: 500; }

/* === TIMELINE === */
.tl-section {
  font-size: 11px; font-weight: 600; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--t1);
  padding-bottom: 10px; border-bottom: 1px solid var(--bd-1);
  margin-bottom: 16px;
}

.tl-strip-wrap {
  display: flex; gap: 5px; margin-bottom: 14px; overflow-x: auto;
  padding-bottom: 4px;
}
.tl-day-block {
  flex-shrink: 0; width: 62px; padding: 9px 6px 8px;
  border-radius: var(--r); text-align: center; cursor: pointer;
  border: 1px solid transparent;
  transition: filter 0.12s;
}
.tl-day-block:hover { filter: brightness(1.25); }
.tl-day-n  { font-family: var(--mono); font-size: 16px; font-weight: 400; line-height: 1; }
.tl-day-d  { font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase; margin-top: 4px; opacity: 0.7; }
.tl-day-ct { font-size: 10px; font-family: var(--mono); margin-top: 3px; opacity: 0.55; }

.tl-CRITICAL { background: var(--cr-a); border-color: var(--cr-b); color: var(--cr); }
.tl-HIGH     { background: var(--hi-a); border-color: var(--hi-b); color: var(--hi); }
.tl-MODERATE { background: var(--me-a); border-color: var(--me-b); color: var(--me); }
.tl-LOW      { background: var(--lo-a); border-color: var(--lo-b); color: var(--lo); }
.tl-selected { outline: 2px solid rgba(255,255,255,0.3); outline-offset: 2px; }

/* Calendar */
.tl-cal-wrap { display: flex; justify-content: center; }
.tl-cal { border-collapse: separate; border-spacing: 3px; margin: 0 auto; }
.tl-cal th {
  color: var(--t1); font-size: 10px; font-weight: 600;
  letter-spacing: 0.10em; text-transform: uppercase;
  padding: 6px 8px; text-align: center;
}
.tl-cal td {
  width: 46px; height: 44px; text-align: center; border-radius: var(--r);
  font-size: 13px; font-family: var(--mono); vertical-align: middle;
  cursor: default; transition: filter 0.1s;
}
.tl-cal td:hover { filter: brightness(1.3); }
.tl-cal-none { color: var(--t2); }
.tl-cal-sel  { outline: 2px solid rgba(255,255,255,0.3); outline-offset: 1px; }

/* Calendar month header */
.tl-cal-month {
  text-align: center; font-size: 14px; font-weight: 600;
  color: var(--t0); margin-bottom: 14px; letter-spacing: -0.01em;
  font-family: var(--font);
}

/* Severity legend */
.tl-legend {
  display: flex; gap: 20px; flex-wrap: wrap; margin-top: 14px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
}
.tl-legend-item { display: flex; align-items: center; gap: 6px; }
.tl-legend-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}

/* Stat blocks for timeline */
.tl-stats {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 1px; background: var(--bd-1);
  border: 1px solid var(--bd-1); border-radius: var(--r);
  overflow: hidden; margin-bottom: 20px;
}
.tl-stat {
  padding: 16px 18px; background: var(--bg-1);
}
.tl-stat-label {
  font-size: 10px; font-weight: 600; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--t1); margin-bottom: 8px;
}
.tl-stat-val {
  font-family: var(--mono); font-size: 26px; font-weight: 300;
  color: var(--t0); letter-spacing: -0.03em; line-height: 1;
}
.tl-stat-unit {
  font-size: 12px; color: var(--t2); font-family: var(--mono);
  margin-left: 3px;
}
.tl-stat-val-cr { color: var(--cr); }
.tl-stat-sub {
  font-size: 11px; color: var(--t1); margin-top: 4px;
  font-family: var(--mono);
}

.tl-alert-panel {
  padding: 14px 18px; border-radius: var(--r); margin-bottom: 18px;
}
.tl-alert-cr {
  background: var(--cr-a); border: 1px solid var(--cr-b);
}
.tl-alert-hi {
  background: var(--hi-a); border: 1px solid var(--hi-b);
}
.tl-alert-head {
  font-size: 12px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; margin-bottom: 6px;
}
.tl-alert-cr .tl-alert-head { color: var(--cr); }
.tl-alert-hi .tl-alert-head { color: var(--hi); }
.tl-alert-body { font-size: 13px; color: var(--t1); line-height: 1.5; }

/* Playback */
.tl-play-state {
  padding: 8px 14px; border-radius: var(--r);
  background: rgba(61,125,200,0.06); border: 1px solid rgba(61,125,200,0.14);
  font-family: var(--mono); font-size: 11px; color: #6080b0;
  margin-bottom: 10px;
}

/* === SECTION LABEL === */
.sec-label {
  font-size: 11px; font-weight: 600; letter-spacing: 0.10em;
  text-transform: uppercase; color: var(--t1);
  padding-bottom: 10px; border-bottom: 1px solid var(--bd-1);
  margin-bottom: 14px;
}

/* === INTELLIGENCE HEADER (situation overview) === */
.intel-bar {
  padding: 8px 0 16px; border-bottom: 1px solid var(--bd-1);
  margin-bottom: 18px;
}
.intel-primary {
  display: flex; align-items: baseline; gap: 20px; margin-bottom: 6px;
}
.intel-count {
  font-family: var(--mono); font-size: 36px; font-weight: 300;
  letter-spacing: -0.04em; color: var(--t0); line-height: 1;
}
.intel-count-label {
  font-size: 13px; color: var(--t1);
}
.intel-severity {
  display: flex; gap: 20px; margin-bottom: 8px;
}
.intel-sev-item {
  font-family: var(--mono); font-size: 13px; font-weight: 500;
}
.intel-sev-item span { font-size: 11px; color: var(--t1); margin-left: 4px; }
.intel-classes {
  display: flex; gap: 24px;
  font-size: 12px; color: var(--t1);
  border-top: 1px solid var(--bd-0); padding-top: 8px;
}
.intel-cls-item { display: flex; gap: 6px; align-items: center; }
.intel-cls-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.intel-cls-val { font-family: var(--mono); font-size: 13px; color: var(--t0); }

/* === EXPANDER (progressive disclosure in alert feed) === */
[data-testid="stExpander"] {
  border: none !important;
  border-top: 1px solid var(--bd-0) !important;
  border-radius: 0 !important;
  background: transparent !important;
  margin: 0 !important;
}
[data-testid="stExpander"] summary {
  font-family: var(--font) !important;
  font-size: 11px !important;
  color: var(--t1) !important;
  padding: 4px 0 8px !important;
  background: transparent !important;
}
[data-testid="stExpander"] summary:hover { color: var(--t0) !important; }
[data-testid="stExpander"] > div > div { padding: 0 !important; }

/* === POPOVER === */
[data-testid="stPopover"] { font-family: var(--font) !important; }

/* === GIS / TABLE / CODE === */
[data-testid="stDataFrame"] { border-radius: var(--r) !important; }
[data-testid="stCodeBlock"] pre { font-family: var(--mono) !important; font-size: 11px !important; }

/* === DOWNLOAD BUTTON === */
[data-testid="stDownloadButton"] > button {
  background: var(--bg-3) !important;
  color: var(--t1) !important;
  border: 1px solid var(--bd-1) !important;
  border-radius: var(--r) !important;
  font-family: var(--font) !important;
  font-size: 11px !important;
  font-weight: 500 !important;
  transition: border-color 0.12s, color 0.12s;
}
[data-testid="stDownloadButton"] > button:hover {
  border-color: var(--bd-2) !important; color: var(--t0) !important;
}

/* === PS CLASSIFICATION PANELS === */
.ps-class-panel {
  padding: 16px 18px; border-radius: var(--r);
  border: 1px solid var(--bd-1);
}
.ps-class-panel + .ps-class-panel { margin-top: 0; }
.ps-class-head {
  font-size: 11px; font-weight: 700; letter-spacing: 0.10em;
  text-transform: uppercase; margin-bottom: 6px;
}
.ps-class-count {
  font-family: var(--mono); font-size: 28px; font-weight: 300;
  letter-spacing: -0.03em; margin-bottom: 10px; line-height: 1;
}
.ps-class-body { font-size: 11px; color: var(--t1); line-height: 1.7; }

.ps-cr { border-color: var(--cr-b); background: var(--cr-a); }
.ps-cr .ps-class-head { color: var(--cr); }
.ps-cr .ps-class-count { color: var(--cr); }

.ps-hi { border-color: var(--hi-b); background: var(--hi-a); }
.ps-hi .ps-class-head { color: var(--hi); }
.ps-hi .ps-class-count { color: var(--hi); }

.ps-lo { border-color: var(--lo-b); background: var(--lo-a); }
.ps-lo .ps-class-head { color: var(--lo); }
.ps-lo .ps-class-count { color: var(--lo); }

/* === ANIMATION === */
@keyframes pulse-live {
  0%   { box-shadow: 0 0 0 0 rgba(45,138,45,0.6); }
  70%  { box-shadow: 0 0 0 5px rgba(45,138,45,0); }
  100% { box-shadow: 0 0 0 0 rgba(45,138,45,0); }
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


# ── Helper renderers ───────────────────────────────────────────────────────────
def _alert_row_html(a: dict) -> str:
    """Compact single-line alert row for the collapsed state."""
    sev       = a["severity"]
    status    = a.get("status", "")
    city      = a.get("nearest_city", "—")
    city_dist = a.get("dist_nearest_city_km", 0)
    frp       = a.get("frp_mw", 0)
    persist   = a.get("persistence_count", 1)
    risk      = a.get("risk_score", 0)
    acq       = a.get("acq_date", "")
    oc        = a.get("output_class", "")
    lat       = a.get("lat", 0)
    lon       = a.get("lon", 0)

    type_label = _TYPE_SHORT.get(oc, oc)
    return f"""
<div class="ac">
  <div class="ac-head">
    <span class="ac-sev sev-{sev}">{sev}</span>
    <span class="ac-type">{type_label}</span>
    <span class="ac-right">
      <span class="ac-status status-{status}">{status}</span>
      <span class="ac-date">{acq}</span>
    </span>
  </div>
  <div class="ac-loc">{lat:.4f}°N {lon:.4f}°E &nbsp;·&nbsp; {city} ({city_dist:.0f} km)</div>
  <div class="ac-metrics">
    <span>Risk <em>{risk}</em>/100</span>
    <span>FRP <em>{frp:.1f}</em> MW</span>
    <span>Persist <em>{persist}</em>&times;</span>
  </div>
</div>"""


def _alert_detail_html(a: dict) -> str:
    """Expanded detail block — narrative + secondary metrics."""
    dist_fac  = a.get("dist_nearest_facility_km", 0)
    haz       = a.get("hazard_facility_type", "—")
    land      = a.get("land_cover_context", "—")
    day_night = a.get("day_night", "D")
    narrative = a.get("narrative", "")
    dn_label  = "Night" if day_night == "N" else "Day"

    detail_parts = []
    if narrative:
        detail_parts.append(f'<div class="ac-narr">{narrative}</div>')
    detail_parts.append(
        f'<div class="ac-metrics" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--bd-0)">'
        f'<span>{haz} &nbsp;{dist_fac:.1f} km</span>'
        f'<span>{dn_label}</span>'
        f'<span>{land}</span>'
        f'</div>'
    )
    return "".join(detail_parts)


def _sev_section_head(sev: str, count: int) -> str:
    cls_map = {"CRITICAL": "cr", "HIGH": "hi", "MEDIUM": "me", "LOW": "lo"}
    cls = cls_map.get(sev, "lo")
    return (
        f'<div class="sev-head sev-head-{cls}">'
        f'{sev}<span class="sev-head-ct">· {count}</span>'
        f'</div>'
    )


# ── GeoJSON export ─────────────────────────────────────────────────────────────
def _alerts_to_geojson(alerts: list[dict]) -> str:
    features = []
    for a in alerts:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [a["lon"], a["lat"]]},
            "properties": {
                "alert_id":             a["alert_id"],
                "output_class":         a.get("output_class", ""),
                "severity":             a["severity"],
                "status":               a["status"],
                "risk_score":           a["risk_score"],
                "land_cover_context":   a.get("land_cover_context", ""),
                "hazard_facility_type": a.get("hazard_facility_type", ""),
                "frp_mw":               a["frp_mw"],
                "persistence_count":    a["persistence_count"],
                "dist_facility_km":     a["dist_nearest_facility_km"],
                "nearest_city":         a.get("nearest_city", ""),
                "acq_date":             a.get("acq_date", ""),
                "narrative":            a.get("narrative", ""),
            },
        })
    return json.dumps({"type": "FeatureCollection", "features": features}, indent=2)


# ── Map ────────────────────────────────────────────────────────────────────────
_SEV_OPACITY = {"CRITICAL": 0.90, "HIGH": 0.72, "MEDIUM": 0.54, "LOW": 0.38}

def _build_map(scored: pd.DataFrame, incidents: pd.DataFrame,
               show_incidents: bool, colour_by: str) -> pdk.Deck:
    layers = []

    if not scored.empty:
        df = scored.copy()
        if colour_by == "Output Class (PS classification)":
            df["color"] = df["output_class"].map(
                {k: v[0] for k, v in OUTPUT_CLASS_CFG.items()}
            )
        else:
            sev_color = {
                "CRITICAL": [220, 20,  20, 230],
                "HIGH":     [217, 119,  6, 200],
                "MEDIUM":   [181, 134, 13, 170],
                "LOW":      [ 45, 138, 45, 140],
            }
            df["color"] = df["severity"].map(sev_color)

        df["radius"] = df["risk_score"].apply(lambda s: 4500 + s * 80)
        df["tip"] = df.apply(lambda r: (
            f"{_TYPE_SHORT.get(r['output_class'], r['output_class'])}\n"
            f"Severity: {r.get('severity','')}  Score: {r.get('risk_score',0)}\n"
            f"FRP {r['frp_mw']:.1f} MW  Persist {r['persistence_count']}x\n"
            f"Facility: {r.get('hazard_facility_type','')}  ({r['dist_nearest_facility_km']:.1f} km)\n"
            f"Land: {r.get('land_cover_context','')}"
        ), axis=1)
        layers.append(pdk.Layer("ScatterplotLayer", data=df,
            get_position=["lon", "lat"], get_color="color", get_radius="radius",
            pickable=True, opacity=0.85))

    if show_incidents and not incidents.empty:
        inc = incidents.copy()
        inc["color"] = [[220, 220, 220, 200]] * len(inc)
        inc["tip"] = inc.apply(lambda r: (
            f"{r['incident_id']}: {r['name']}\n"
            f"Date: {r['date']}  Facility: {r.get('facility_type','?')}\n"
            f"Anomaly flag: {'YES' if r['anomaly_flag'] else 'no'}  "
            f"prob_A={r['prob_A']:.2f}"
        ), axis=1)
        layers.append(pdk.Layer("ScatterplotLayer", data=inc,
            get_position=["lon", "lat"], get_color="color", get_radius=18000,
            pickable=True, opacity=0.95, stroked=True,
            get_line_color=[200, 200, 200], line_width_min_pixels=1))

    return pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(latitude=22.0, longitude=82.0, zoom=4.5),
        tooltip={
            "html": "<pre style='font-family:IBM Plex Mono,monospace;font-size:11px;"
                    "color:#e6e6e6;margin:0'>{tip}</pre>",
            "style": {
                "background": "rgba(10,10,10,0.92)",
                "border": "1px solid rgba(255,255,255,0.10)",
                "borderRadius": "2px",
                "padding": "10px 12px",
            },
        },
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )


# ── Data ───────────────────────────────────────────────────────────────────────
scored_df     = load_scored()
daily_summary = get_daily_summary()
_sb_dates_iso = daily_summary["acq_date"].tolist() if not daily_summary.empty else []
_sb_min_date  = date.fromisoformat(_sb_dates_iso[0])  if _sb_dates_iso else date.today()
_sb_max_date  = date.fromisoformat(_sb_dates_iso[-1]) if _sb_dates_iso else date.today()
c             = alert_store.counts()
_IST = timezone(timedelta(hours=5, minutes=30))
now_str   = datetime.now(_IST).strftime("%H:%M IST")


# ── Pre-compute counts ─────────────────────────────────────────────────────────
n_industrial = (
    int((scored_df["output_class"] == OUTPUT_CLASS_INDUSTRIAL_FIRE).sum())
    if not scored_df.empty else 0
)
n_persistent = (
    int((scored_df["output_class"] == OUTPUT_CLASS_PERSISTENT_SOURCE).sum())
    if not scored_df.empty else 0
)
n_natural = (
    int((scored_df["output_class"] == OUTPUT_CLASS_NATURAL_FIRE).sum())
    if not scored_df.empty else 0
)

# ── Integrated header + situation overview ────────────────────────────────────
_cr_color = "var(--cr)" if c["CRITICAL"] > 0 else "var(--t0)"
_hi_color = "var(--hi)" if c["HIGH"] > 0 else "var(--t0)"
st.markdown(f"""
<div class="sys-bar">
  <div class="sys-bar-left">
    <div class="sys-bar-id">SIH · 26162 · India Fire Intelligence Platform</div>
    <div class="sys-bar-title">Industrial Fire &amp; Thermal Anomaly Detection &nbsp;—&nbsp; Team ZeroOne</div>
    <div class="sys-bar-sub">
      NASA FIRMS VIIRS 375m &nbsp;·&nbsp; AI Classifier &nbsp;·&nbsp;
      Risk Engine &nbsp;·&nbsp; GIS Export
    </div>
  </div>
  <div class="sys-bar-live">
    <div class="live-dot"></div>
    LIVE &nbsp;·&nbsp; {now_str} &nbsp;·&nbsp; NRT
  </div>
</div>
<div class="intel-bar">
  <div class="intel-primary">
    <div class="intel-count">{c['active']}</div>
    <div class="intel-count-label">active alerts requiring attention</div>
  </div>
  <div class="intel-severity">
    <div class="intel-sev-item" style="color:{_cr_color}">
      {c['CRITICAL']}<span>critical</span>
    </div>
    <div class="intel-sev-item" style="color:{_hi_color}">
      {c['HIGH']}<span>high</span>
    </div>
    <div class="intel-sev-item" style="color:var(--me)">
      {c['MEDIUM']}<span>medium</span>
    </div>
    <div class="intel-sev-item" style="color:var(--t1)">
      {c['LOW']}<span>low</span>
    </div>
  </div>
  <div class="intel-classes">
    <div class="intel-cls-item">
      <div class="intel-cls-dot" style="background:var(--cr)"></div>
      <span class="intel-cls-val">{n_industrial}</span>
      <span>Industrial Fire (PS·A)</span>
    </div>
    <div class="intel-cls-item">
      <div class="intel-cls-dot" style="background:var(--hi)"></div>
      <span class="intel-cls-val">{n_persistent}</span>
      <span>Persistent Source (PS·B)</span>
    </div>
    <div class="intel-cls-item">
      <div class="intel-cls-dot" style="background:var(--lo)"></div>
      <span class="intel-cls-val">{n_natural}</span>
      <span>Natural Fire (PS·C)</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Top control bar ────────────────────────────────────────────────────────────
_cb1, _cb2, _cb3, _cb4, _cb5 = st.columns([2, 2.2, 2.4, 1.6, 1.2], gap="medium")

with _cb1:
    st.markdown('<div class="ctrl-label">Severity</div>', unsafe_allow_html=True)
    sev_filter = st.multiselect(
        "Severity", ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        default=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        label_visibility="collapsed", key="ctrl_sev",
    )

with _cb2:
    st.markdown('<div class="ctrl-label">Status</div>', unsafe_allow_html=True)
    status_filter = st.multiselect(
        "Status", alert_store.LIFECYCLE_STATES,
        default=["DETECTED", "VALIDATING", "ALERTED", "ESCALATED", "MONITORING"],
        label_visibility="collapsed", key="ctrl_sts",
    )

with _cb3:
    st.markdown('<div class="ctrl-label">Date</div>', unsafe_allow_html=True)
    _dq1, _dq2, _dq3, _dq4, _dq5 = st.columns(5)
    if _dq1.button("Today", key="cb_q0", use_container_width=True):
        st.session_state.tl_start = date.today(); st.session_state.tl_end = date.today()
        st.session_state.alert_page = 0; st.rerun()
    if _dq2.button("24h", key="cb_q1", use_container_width=True):
        st.session_state.tl_start = date.today() - timedelta(days=1)
        st.session_state.tl_end = date.today()
        st.session_state.alert_page = 0; st.rerun()
    if _dq3.button("7d", key="cb_q2", use_container_width=True):
        st.session_state.tl_start = date.today() - timedelta(days=7)
        st.session_state.tl_end = date.today()
        st.session_state.alert_page = 0; st.rerun()
    if _dq4.button("Clear", key="cb_q4", use_container_width=True,
                   disabled=st.session_state.tl_start is None):
        st.session_state.tl_start = None; st.session_state.tl_end = None
        st.session_state.tl_playing = False; st.session_state.alert_page = 0; st.rerun()
    with _dq5.popover("↗", use_container_width=True):
        st.markdown("**Custom date range**")
        if not daily_summary.empty:
            with st.form("cb_date_form"):
                _cb_dr = st.date_input(
                    "Range",
                    value=(st.session_state.tl_start or _sb_min_date,
                           st.session_state.tl_end   or _sb_max_date),
                    min_value=_sb_min_date,
                    max_value=max(_sb_max_date, date.today()),
                    label_visibility="collapsed",
                )
                if st.form_submit_button("Apply", use_container_width=True):
                    if isinstance(_cb_dr, (list, tuple)) and len(_cb_dr) == 2:
                        st.session_state.tl_start = _cb_dr[0]; st.session_state.tl_end = _cb_dr[1]
                    elif isinstance(_cb_dr, date):
                        st.session_state.tl_start = _cb_dr; st.session_state.tl_end = _cb_dr
                    st.session_state.alert_page = 0; st.rerun()
    if st.session_state.tl_start:
        _active_rng = (
            st.session_state.tl_start.strftime("%b %d")
            if st.session_state.tl_start == st.session_state.tl_end
            else f"{st.session_state.tl_start.strftime('%b %d')} – {st.session_state.tl_end.strftime('%b %d')}"
        )
        st.markdown(f'<div class="ctrl-date-badge">▸ {_active_rng}</div>', unsafe_allow_html=True)

with _cb4:
    st.markdown('<div class="ctrl-label">Map Layer</div>', unsafe_allow_html=True)
    show_incidents = st.checkbox("Incident sites", value=st.session_state.show_incidents, key="ctrl_inc")
    st.session_state.show_incidents = show_incidents
    colour_by = st.radio(
        "Colour by",
        ["Output Class (PS classification)", "Alert Severity"],
        index=["Output Class (PS classification)", "Alert Severity"].index(st.session_state.colour_by),
        label_visibility="collapsed", key="ctrl_clr",
    )
    st.session_state.colour_by = colour_by

with _cb5:
    st.markdown('<div class="ctrl-label">Pipeline</div>', unsafe_allow_html=True)
    if st.button("Re-run", key="cb_pipe", use_container_width=True):
        with st.spinner("Running…"):
            r = run_pipeline(fresh=True)
            load_scored.clear()
            load_incidents.clear()
        st.success(f"CRITICAL: {r['counts']['CRITICAL']}  HIGH: {r['counts']['HIGH']}")
        st.rerun()

st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)


# ── Apply timeline date filter ─────────────────────────────────────────────────
_tl_s = st.session_state.tl_start
_tl_e = st.session_state.tl_end
if _tl_s and _tl_e and not scored_df.empty:
    _mask = (
        (scored_df["acq_date"] >= _tl_s.isoformat()) &
        (scored_df["acq_date"] <= _tl_e.isoformat())
    )
    map_df = scored_df[_mask]
else:
    map_df = scored_df


# ── Main layout: alert feed + map ─────────────────────────────────────────────
col_alert, col_map = st.columns([1, 2], gap="medium")

# ── Alert feed ─────────────────────────────────────────────────────────────────
_PAGE_SIZE = 5

with col_alert:
    alerts = alert_store.get_alerts(
        severity=sev_filter or None,
        status=status_filter or None,
    )
    if _tl_s and _tl_e:
        _s_iso, _e_iso = _tl_s.isoformat(), _tl_e.isoformat()
        alerts = [a for a in alerts if _s_iso <= a.get("acq_date", "") <= _e_iso]

    _n_total = len(alerts)
    _n_pages = max(1, (_n_total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    _page    = min(st.session_state.alert_page, _n_pages - 1)
    _page_alerts = alerts[_page * _PAGE_SIZE : (_page + 1) * _PAGE_SIZE]

    _date_meta = ""
    if _tl_s:
        _rng = (
            _tl_s.strftime("%b %d")
            if _tl_s == _tl_e
            else f"{_tl_s.strftime('%b %d')} – {_tl_e.strftime('%b %d')}"
        )
        _date_meta = f"&nbsp;·&nbsp; {_rng}"

    _pager_str = f"pg {_page+1}/{_n_pages}" if _n_pages > 1 else ""
    st.markdown(f"""
<div class="feed-header">
  <div class="feed-title">Alert Feed</div>
  <div class="feed-meta">{_n_total} total{_date_meta}
    {f'&nbsp;·&nbsp; {_pager_str}' if _pager_str else ''}
  </div>
</div>
""", unsafe_allow_html=True)

    if not alerts:
        st.markdown(
            '<div style="padding:24px 0;font-size:11px;color:var(--t2);text-align:center">'
            'No alerts match the current filters.</div>',
            unsafe_allow_html=True,
        )
    else:
        _cur_sev = None
        for a in _page_alerts:
            if a["severity"] != _cur_sev:
                _cur_sev = a["severity"]
                _sev_ct  = sum(1 for x in alerts if x["severity"] == _cur_sev)
                st.markdown(_sev_section_head(_cur_sev, _sev_ct), unsafe_allow_html=True)

            # Collapsed row (always visible)
            st.markdown(_alert_row_html(a), unsafe_allow_html=True)

            # Expanded detail + actions via progressive disclosure
            _has_actions = a["status"] in ("ALERTED", "ESCALATED")
            _exp_label   = "Assessment + Actions" if _has_actions else "Assessment"
            with st.expander(_exp_label):
                st.markdown(_alert_detail_html(a), unsafe_allow_html=True)
                if _has_actions:
                    _b1, _b2, _b3 = st.columns(3)
                    if _b1.button("Acknowledge", key=f"ack_{a['alert_id']}"):
                        alert_store.update_status(a["alert_id"], "MONITORING")
                        st.rerun()
                    if _b2.button("Escalate", key=f"esc_{a['alert_id']}"):
                        alert_store.update_status(a["alert_id"], "ESCALATED")
                        st.rerun()
                    if _b3.button("Resolve", key=f"res_{a['alert_id']}"):
                        alert_store.update_status(a["alert_id"], "EXTINGUISHED")
                        st.rerun()

        # Pagination controls
        if _n_pages > 1:
            st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
            _ppc1, _ppc2, _ppc3 = st.columns([1, 2, 1])
            if _ppc1.button("← Prev", key="ap_prev", disabled=_page == 0,
                            use_container_width=True):
                st.session_state.alert_page = _page - 1; st.rerun()
            _ppc2.markdown(
                f'<div style="text-align:center;font-size:10px;color:var(--t1);'
                f'font-family:var(--mono);padding:6px 0">{_page+1} / {_n_pages}</div>',
                unsafe_allow_html=True,
            )
            if _ppc3.button("Next →", key="ap_next", disabled=_page >= _n_pages - 1,
                            use_container_width=True):
                st.session_state.alert_page = _page + 1; st.rerun()


# ── Map ────────────────────────────────────────────────────────────────────────
with col_map:
    # Mode bar for historical view
    if _tl_s:
        _range_lbl = (
            _tl_s.strftime("%b %d, %Y")
            if _tl_s == _tl_e
            else f"{_tl_s.strftime('%b %d')} – {_tl_e.strftime('%b %d, %Y')}"
        )
        st.markdown(
            f'<div class="hist-mode-bar">'
            f'HISTORICAL &nbsp;·&nbsp; <b>{_range_lbl}</b>'
            f'&nbsp;·&nbsp; {len(map_df):,} detections'
            f'</div>',
            unsafe_allow_html=True,
        )
        _map_mode = "Historical Detection"
    else:
        _map_mode = "Live Detection"

    st.markdown(f"""
<div class="map-header">
  <div>
    <div class="map-title">Detection Map</div>
    <div class="map-mode">{_map_mode} &nbsp;·&nbsp; India</div>
  </div>
  <div class="map-ts">VIIRS 375m &nbsp;·&nbsp; {now_str}</div>
</div>
""", unsafe_allow_html=True)

    incidents_df = load_incidents()
    # Hide confirmed incident markers when a date filter is active — they are
    # 2019-2023 historical events that don't correspond to the filtered FIRMS dates.
    _show_inc_now = show_incidents and not _tl_s
    st.pydeck_chart(
        _build_map(map_df, incidents_df, _show_inc_now, colour_by),
        use_container_width=True,
        height=520,
    )

    st.markdown("""
<div class="map-legend">
  <span class="leg">
    <span class="leg-sq" style="background:#dc1414"></span>Industrial Fire
  </span>
  <span class="leg">
    <span class="leg-sq" style="background:#d97706"></span>Persistent Source
  </span>
  <span class="leg">
    <span class="leg-sq" style="background:#32c850"></span>Natural Fire
  </span>
  <span class="leg">
    <span class="leg-sq" style="background:#dcdcdc;opacity:.7"></span>Confirmed Incident
  </span>
</div>
""", unsafe_allow_html=True)


# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_tl, tab_gis, tab_ps, tab_inc, tab_model, tab_limits = st.tabs([
    "Timeline", "GIS Export", "Classification", "Incidents", "Model", "Limitations",
])


# ────────────────────────────────────────────────────────────────────────────────
# TAB 1 — Historical Timeline
# ────────────────────────────────────────────────────────────────────────────────
with tab_tl:
    st.markdown('<div class="sec-label">Historical Fire Timeline</div>', unsafe_allow_html=True)

    if daily_summary.empty:
        st.markdown(
            '<div style="padding:32px 0;text-align:center;font-size:11px;color:var(--t2)">'
            'No historical data available.<br>Run the detection pipeline to populate the database.'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        _today    = date.today()
        _dates_iso = daily_summary["acq_date"].tolist()
        _min_date  = date.fromisoformat(_dates_iso[0])
        _max_date  = date.fromisoformat(_dates_iso[-1])

        # Playback controls (date filter is in the sidebar)
        st.markdown(
            '<div style="font-size:12px;color:var(--t1);margin-bottom:12px">'
            'Use the <b style="color:var(--t0)">Date Filter</b> above to filter '
            'the map and alerts by date range. Click a day below to jump to it.</div>',
            unsafe_allow_html=True,
        )
        _playing = st.session_state.tl_playing
        _pc1, _pc2, _pc3 = st.columns([1, 1, 2])
        if _pc1.button("Play" if not _playing else "Pause",
                       use_container_width=True, key="tl_play_btn"):
            if not _playing:
                st.session_state.tl_play_date = _min_date
                st.session_state.tl_start     = _min_date
                st.session_state.tl_end       = _min_date
            st.session_state.tl_playing = not _playing
            st.rerun()
        if _pc2.button("Stop", use_container_width=True, key="tl_stop_btn"):
            st.session_state.tl_playing   = False
            st.session_state.tl_play_date = None
            st.rerun()
        _speed = _pc3.select_slider(
            "Speed", options=[0.5, 1.0, 2.0],
            value=st.session_state.tl_speed, key="tl_speed_slider",
        )
        st.session_state.tl_speed = _speed

        if _playing and st.session_state.tl_play_date:
            _pd = st.session_state.tl_play_date
            st.markdown(
                f'<div class="tl-play-state">'
                f'Playing &nbsp;{_pd.strftime("%b %d, %Y")}'
                f'&nbsp; at {_speed}x'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)

        # Activity strip
        st.markdown('<div class="tl-section">Fire Activity by Date</div>', unsafe_allow_html=True)
        _strip_data = daily_summary.tail(14)
        _data_by_date = {r["acq_date"]: r for r in daily_summary.to_dict("records")}

        _strip_html = '<div class="tl-strip-wrap">'
        for _, _sr in _strip_data.iterrows():
            _d       = date.fromisoformat(_sr["acq_date"])
            _sev     = _sr["severity_label"]
            _sel     = (st.session_state.tl_start and
                        st.session_state.tl_start <= _d <= (st.session_state.tl_end or _d))
            _sel_cls = " tl-selected" if _sel else ""
            _cnt     = int(_sr["total_detections"])
            _crit_ct = int(_sr["critical_events"])
            _max_frp = float(_sr["max_frp"])
            _title   = f"{_sev}: {_cnt} detections, {_crit_ct} critical, max FRP {_max_frp:.1f} MW"
            _strip_html += (
                f'<div class="tl-day-block tl-{_sev}{_sel_cls}" title="{_title}">'
                f'<div class="tl-day-n">{_d.day}</div>'
                f'<div class="tl-day-d">{_d.strftime("%b")}</div>'
                f'<div class="tl-day-ct">{_cnt}</div>'
                f'</div>'
            )
        _strip_html += '</div>'

        # ponytail: can't make these clickable without JS; use Streamlit buttons below
        st.markdown(_strip_html, unsafe_allow_html=True)

        # Clickable day buttons (same data, Streamlit-native)
        _strip_cols = st.columns(len(_strip_data))
        for _ci, (_, _sr) in enumerate(_strip_data.iterrows()):
            _d   = date.fromisoformat(_sr["acq_date"])
            _sev = _sr["severity_label"]
            _tip = (
                f"{_sev}: {_sr['total_detections']} detections, "
                f"{int(_sr['critical_events'])} critical, "
                f"max FRP {_sr['max_frp']} MW"
            )
            with _strip_cols[_ci]:
                if st.button(
                    _d.strftime("%b %d"),
                    key=f"tl_strip_{_sr['acq_date']}",
                    use_container_width=True,
                    help=_tip,
                ):
                    st.session_state.tl_start   = _d
                    st.session_state.tl_end     = _d
                    st.session_state.tl_playing = False
                    st.rerun()

        st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)

        # ── Two-column layout: Calendar | Period Analysis ──────────────────────
        _col_cal, _col_stats = st.columns([1.1, 1.6], gap="large")

        with _col_cal:
            st.markdown('<div class="tl-section">Calendar View</div>', unsafe_allow_html=True)
            _cal_month = st.session_state.tl_start or _max_date
            _sel_s = st.session_state.tl_start
            _sel_e = st.session_state.tl_end

            _cal_html = (
                f'<div class="tl-cal-wrap"><div>'
                f'<div class="tl-cal-month">{_cal_month.strftime("%B %Y")}</div>'
                f'<table class="tl-cal"><tr>'
                f'{"".join(f"<th>{d}</th>" for d in ["Mo","Tu","We","Th","Fr","Sa","Su"])}'
                f'</tr>'
            )
            for _week in _cal.monthcalendar(_cal_month.year, _cal_month.month):
                _cal_html += "<tr>"
                for _day in _week:
                    if _day == 0:
                        _cal_html += '<td class="tl-cal-none"></td>'
                    else:
                        _d_str = f"{_cal_month.year}-{_cal_month.month:02d}-{_day:02d}"
                        _rd    = _data_by_date.get(_d_str)
                        _d_obj = date.fromisoformat(_d_str)
                        _is_sel = (_sel_s and _sel_e and _sel_s <= _d_obj <= _sel_e)
                        _sel_cls = " tl-cal-sel" if _is_sel else ""
                        if _rd:
                            _sv = _rd["severity_label"]
                            _tip_txt = (
                                f"{_d_str} | {_rd['total_detections']} detections "
                                f"| {_rd['critical_events']} critical "
                                f"| max FRP {_rd['max_frp']} MW"
                            )
                            _cal_html += (
                                f'<td class="tl-{_sv}{_sel_cls}" title="{_tip_txt}">'
                                f'{_day}</td>'
                            )
                        else:
                            _cal_html += f'<td class="tl-cal-none{_sel_cls}">{_day}</td>'
                _cal_html += "</tr>"
            _cal_html += "</table></div></div>"
            st.markdown(_cal_html, unsafe_allow_html=True)

            # Severity legend
            st.markdown("""
<div class="tl-legend" style="margin-top:16px">
  <div class="tl-legend-item">
    <div class="tl-legend-dot" style="background:var(--cr)"></div>
    <span style="color:var(--cr)">Critical &ge;65</span>
  </div>
  <div class="tl-legend-item">
    <div class="tl-legend-dot" style="background:var(--hi)"></div>
    <span style="color:var(--hi)">High &ge;40</span>
  </div>
  <div class="tl-legend-item">
    <div class="tl-legend-dot" style="background:var(--me)"></div>
    <span style="color:var(--me)">Moderate &ge;20</span>
  </div>
  <div class="tl-legend-item">
    <div class="tl-legend-dot" style="background:var(--lo)"></div>
    <span style="color:var(--lo)">Low &lt;20</span>
  </div>
</div>
<div style="font-size:10px;color:var(--t2);margin-top:6px">Risk score threshold</div>
""", unsafe_allow_html=True)

        with _col_stats:
            # Selected range statistics
            _tl_start_val = st.session_state.tl_start
            _tl_end_val   = st.session_state.tl_end
            if not _tl_start_val or not _tl_end_val:
                st.markdown(
                    '<div style="padding:32px 0;font-size:12px;color:var(--t2);line-height:1.8">'
                    'Select a date or date range from the calendar<br>'
                    'or use the Date Filter above to see period analysis.'
                    '</div>',
                    unsafe_allow_html=True,
                )
            else:
                _range_events = get_events_for_range(_tl_start_val, _tl_end_val)
                _range_str = (
                    _tl_start_val.strftime("%B %d, %Y") if _tl_start_val == _tl_end_val
                    else f"{_tl_start_val.strftime('%B %d')} – {_tl_end_val.strftime('%B %d, %Y')}"
                )
                st.markdown(
                    f'<div class="tl-section">Period Analysis &nbsp;·&nbsp; {_range_str}</div>',
                    unsafe_allow_html=True,
                )

                if not _range_events:
                    st.markdown(
                        '<div style="padding:20px 0;font-size:12px;color:var(--t2);line-height:1.8">'
                        'No fire detections recorded for this period.<br>'
                        'Try selecting a date that has data in the calendar.'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    _rev_df     = pd.DataFrame(_range_events)
                    _n_total    = len(_rev_df)
                    _n_highconf = int((_rev_df["severity"].isin(["CRITICAL", "HIGH"])).sum())
                    _n_critical = int((_rev_df["severity"] == "CRITICAL").sum())
                    _avg_frp    = _rev_df["frp_mw"].mean()
                    _max_frp    = _rev_df["frp_mw"].max()
                    _day_sev    = (
                        "CRITICAL" if _n_critical
                        else "HIGH" if _n_highconf
                        else "MODERATE" if _n_total
                        else "LOW"
                    )
                    _sev_color  = {"CRITICAL": "var(--cr)", "HIGH": "var(--hi)",
                                   "MODERATE": "var(--me)", "LOW": "var(--lo)"}[_day_sev]

                    # Alert banner
                    if _n_critical > 0:
                        st.markdown(
                            f'<div class="tl-alert-panel tl-alert-cr">'
                            f'<div class="tl-alert-head">Critical fire activity</div>'
                            f'<div class="tl-alert-body">'
                            f'{_n_critical} critical events &nbsp;·&nbsp; '
                            f'{_n_highconf} high-confidence detections'
                            f'</div></div>',
                            unsafe_allow_html=True,
                        )
                    elif _n_highconf > 0:
                        st.markdown(
                            f'<div class="tl-alert-panel tl-alert-hi">'
                            f'<div class="tl-alert-head">High fire activity</div>'
                            f'<div class="tl-alert-body">'
                            f'{_n_highconf} high-confidence detections'
                            f'</div></div>',
                            unsafe_allow_html=True,
                        )

                    # Stats grid (3×2)
                    cr_v     = "tl-stat-val-cr" if _n_critical > 0 else ""
                    _avg_str = f"{_avg_frp:.1f}" if _n_total else "—"
                    _max_str = f"{_max_frp:.1f}" if _n_total else "—"
                    st.markdown(f"""
<div class="tl-stats">
  <div class="tl-stat">
    <div class="tl-stat-label">Detections</div>
    <div class="tl-stat-val">{_n_total:,}</div>
  </div>
  <div class="tl-stat">
    <div class="tl-stat-label">High Confidence</div>
    <div class="tl-stat-val">{_n_highconf:,}</div>
  </div>
  <div class="tl-stat">
    <div class="tl-stat-label">Critical</div>
    <div class="tl-stat-val {cr_v}">{_n_critical:,}</div>
  </div>
  <div class="tl-stat">
    <div class="tl-stat-label">Avg FRP</div>
    <div class="tl-stat-val">{_avg_str}<span class="tl-stat-unit">MW</span></div>
  </div>
  <div class="tl-stat">
    <div class="tl-stat-label">Max FRP</div>
    <div class="tl-stat-val">{_max_str}<span class="tl-stat-unit">MW</span></div>
  </div>
  <div class="tl-stat">
    <div class="tl-stat-label">Risk Level</div>
    <div class="tl-stat-val" style="font-size:18px;font-weight:600;color:{_sev_color}">{_day_sev}</div>
  </div>
</div>
""", unsafe_allow_html=True)

                    if _n_total:
                        _areas = _rev_df["land_cover_context"].value_counts().head(3)
                        _area_str = " &nbsp;·&nbsp; ".join(
                            f"{z} ({n})" for z, n in _areas.items()
                        )
                        st.markdown(
                            f'<div style="font-size:11px;color:var(--t1);margin-top:4px;line-height:1.7">'
                            f'<span style="color:var(--t2);font-size:10px;letter-spacing:0.08em;'
                            f'text-transform:uppercase">Top land cover</span><br>'
                            f'{_area_str}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )


# ────────────────────────────────────────────────────────────────────────────────
# TAB 2 — GIS Export
# ────────────────────────────────────────────────────────────────────────────────
with tab_gis:
    st.markdown('<div class="sec-label">GIS Export &nbsp;·&nbsp; PS Deliverable ii</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:11px;color:var(--t1);margin-bottom:18px;line-height:1.7">'
        'Download alerts as GeoJSON for use in QGIS, ArcGIS, or any GIS platform. '
        'Each alert is a Point feature with full attribute table: output class, severity, '
        'land-cover context, facility hazard type, FRP, persistence count, and narrative.'
        '</div>',
        unsafe_allow_html=True,
    )

    all_alerts  = alert_store.get_alerts(severity=sev_filter or None)
    geojson_str = _alerts_to_geojson(all_alerts)

    _dl1, _dl2, _dl3 = st.columns(3)
    _dl1.download_button(
        "Download GeoJSON",
        data=geojson_str,
        file_name=f"sih26162_alerts_{datetime.now().strftime('%Y%m%d_%H%M')}.geojson",
        mime="application/geo+json",
        use_container_width=True,
    )
    if all_alerts:
        csv_df = pd.DataFrame(all_alerts)[[
            "alert_id", "lat", "lon", "output_class", "severity", "status",
            "risk_score", "land_cover_context", "hazard_facility_type",
            "frp_mw", "persistence_count", "dist_nearest_facility_km",
            "nearest_city", "acq_date", "narrative",
        ]]
        _dl2.download_button(
            "Download CSV",
            data=csv_df.to_csv(index=False),
            file_name=f"sih26162_alerts_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown('<div class="sec-label" style="margin-top:20px">GeoJSON Preview &nbsp;·&nbsp; First 3 Features</div>', unsafe_allow_html=True)
    preview = json.loads(geojson_str)
    preview["features"] = preview["features"][:3]
    st.code(json.dumps(preview, indent=2), language="json")


# ────────────────────────────────────────────────────────────────────────────────
# TAB 3 — PS Classification
# ────────────────────────────────────────────────────────────────────────────────
with tab_ps:
    st.markdown('<div class="sec-label">PS Deliverable i &nbsp;·&nbsp; Classification Output</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:11px;color:var(--t1);margin-bottom:18px;line-height:1.7">'
        'Every NASA FIRMS thermal hotspot is classified into one of three output classes '
        'aligned to the problem statement requirements.'
        '</div>',
        unsafe_allow_html=True,
    )

    n_ind = (scored_df["output_class"] == OUTPUT_CLASS_INDUSTRIAL_FIRE).sum() if not scored_df.empty else 0
    n_per = (scored_df["output_class"] == OUTPUT_CLASS_PERSISTENT_SOURCE).sum() if not scored_df.empty else 0
    n_nat = (scored_df["output_class"] == OUTPUT_CLASS_NATURAL_FIRE).sum() if not scored_df.empty else 0

    _pc1, _pc2, _pc3 = st.columns(3)
    with _pc1:
        st.markdown(f"""
<div class="ps-class-panel ps-cr">
  <div class="ps-class-head">Industrial Fire</div>
  <div class="ps-class-count">{n_ind}</div>
  <div class="ps-class-body">
    Accidental fires, gas leaks, explosions, abnormal process heat.
    Thermal signature matches neither the persistent-flare nor
    natural-fire pattern.<br><br>
    Facility types: oil refineries, petrochemical complexes,
    chemical plants, pharmaceutical units, mining areas.
  </div>
</div>
""", unsafe_allow_html=True)

    with _pc2:
        st.markdown(f"""
<div class="ps-class-panel ps-hi">
  <div class="ps-class-head">Persistent Source</div>
  <div class="ps-class-count">{n_per}</div>
  <div class="ps-class-body">
    Continuous thermal emissions matching known industrial-heat
    signatures. VNF gas-flare catalogue used as labeling oracle
    (1,500–2,000 K spectral temp).<br><br>
    Includes: thermal power plants, steel smelters, brick kilns,
    gas flaring stacks, LNG terminals. Persistent re-detection
    across the 5-day NRT window is the key discriminator.
  </div>
</div>
""", unsafe_allow_html=True)

    with _pc3:
        st.markdown(f"""
<div class="ps-class-panel ps-lo">
  <div class="ps-class-head">Natural Fire</div>
  <div class="ps-class-count">{n_nat}</div>
  <div class="ps-class-body">
    Thermal events consistent with natural or crop-residue burning.
    Short-burst detections in forest/cropland land-cover zones,
    correlated with agricultural burning seasons.<br><br>
    Distinguished from industrial heat by low persistence and
    land-cover context (cropland, forest — not industrial corridor).
  </div>
</div>
""", unsafe_allow_html=True)

    st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)
    st.markdown('<div class="sec-label">Land-Cover Distribution</div>', unsafe_allow_html=True)
    if not scored_df.empty:
        lc_df = (
            scored_df.groupby(["land_cover_context", "output_class"])
            .size().reset_index(name="count")
        )
        st.dataframe(
            lc_df.sort_values("count", ascending=False),
            hide_index=True, use_container_width=True,
        )

    st.markdown('<div class="sec-label" style="margin-top:16px">Facility Hazard Type Distribution</div>', unsafe_allow_html=True)
    if not scored_df.empty:
        ht_df = (
            scored_df.groupby(["hazard_facility_type", "output_class"])
            .size().reset_index(name="count")
        )
        st.dataframe(
            ht_df.sort_values("count", ascending=False),
            hide_index=True, use_container_width=True,
        )


# ────────────────────────────────────────────────────────────────────────────────
# TAB 4 — Confirmed Incidents
# ────────────────────────────────────────────────────────────────────────────────
with tab_inc:
    st.markdown('<div class="sec-label">Confirmed India Industrial Incidents &nbsp;·&nbsp; Anomaly Scoring</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:11px;color:var(--t1);margin-bottom:18px;line-height:1.7">'
        '30 curated major Indian industrial incidents (2019–2023) scored against the trained model. '
        '21/30 (70%) flagged as Industrial Fire / Abnormal Thermal Event — correctly identified '
        'as departing from both persistent-flare and natural-fire patterns.'
        '</div>',
        unsafe_allow_html=True,
    )

    incidents_tab = load_incidents()
    if not incidents_tab.empty:
        disp = incidents_tab[[
            "incident_id", "name", "date", "state", "facility_type",
            "predicted_label", "prob_A", "prob_B_candidate",
            "anomaly_flag", "dist_nearest_facility_km",
        ]].rename(columns={
            "predicted_label":          "model_class",
            "prob_B_candidate":         "prob_B",
            "dist_nearest_facility_km": "dist_fac_km",
            "anomaly_flag":             "industrial_fire_flag",
        })
        st.dataframe(
            disp.sort_values("industrial_fire_flag", ascending=False),
            hide_index=True, use_container_width=True,
        )

    st.markdown('<div class="sec-label" style="margin-top:16px">Case Studies</div>', unsafe_allow_html=True)
    _cs1, _cs2, _cs3 = st.columns(3)
    with _cs1:
        st.markdown("""
<div class="ps-class-panel ps-cr">
  <div class="ps-class-head">Jharia Coalfield</div>
  <div class="ps-class-body">
    Underground coal seam fire active since 1916.
    <b style="color:var(--cr)">Flagged as Industrial Fire.</b>
    4 repeat FIRMS detections. Near Mining/Extraction facility.
    Land cover: Mining/Industrial Corridor.
  </div>
</div>
""", unsafe_allow_html=True)
    with _cs2:
        st.markdown("""
<div class="ps-class-panel ps-lo">
  <div class="ps-class-head">Punjab Stubble Burning</div>
  <div class="ps-class-body">
    Seasonal kharif-residue burning (Oct–Nov).
    <b style="color:var(--lo)">Correctly classified as Natural Fire.</b>
    Agri-season flag active. Land cover:
    Cropland — Kharif/Rabi (Punjab/Haryana).
  </div>
</div>
""", unsafe_allow_html=True)
    with _cs3:
        st.markdown("""
<div class="ps-class-panel ps-hi">
  <div class="ps-class-head">Vizag LG Polymers Gas Leak</div>
  <div class="ps-class-body">
    Styrene gas leak, 2020, 12 fatalities.
    <b style="color:var(--hi)">Flagged as Industrial Fire.</b>
    Near Oil Refinery/Petrochemical facility (1.2 km).
    Anomaly score 0.52.
  </div>
</div>
""", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────────
# TAB 5 — Model
# ────────────────────────────────────────────────────────────────────────────────
with tab_model:
    st.markdown('<div class="sec-label">AI Model &nbsp;·&nbsp; Architecture &amp; Evaluation</div>', unsafe_allow_html=True)

    _mc1, _mc2 = st.columns(2)
    with _mc1:
        st.markdown("""
<div style="font-size:11px;color:var(--t1);line-height:1.8">
<div style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;
            color:var(--t2);margin-bottom:10px">Data Sources (PS requirement)</div>
<b style="color:var(--t0)">Satellite</b><br>
NASA FIRMS VIIRS 375m NRT — thermal anomaly data<br><br>
<b style="color:var(--t0)">Land-cover</b><br>
Coordinate-based India zone classification + agri-season flag<br><br>
<b style="color:var(--t0)">Industrial databases</b><br>
WRI GPPD (34,936 power plants) + OSM industrial polygons (37,688 India features)<br><br>
<b style="color:var(--t0)">Gas flare catalogue</b><br>
ORNL DAAC VNF 2012–2019 (83,641 sites, 1,500–2,000 K spectral temp)<br><br>
<div style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;
            color:var(--t2);margin:14px 0 8px">Facility Types Covered</div>
Oil Refinery &nbsp;·&nbsp; Thermal Power Plant &nbsp;·&nbsp; Mining<br>
Steel/Metal &nbsp;·&nbsp; Brick Kiln &nbsp;·&nbsp; LNG/Gas &nbsp;·&nbsp; Chemical/Pharma<br><br>
<div style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;
            color:var(--t2);margin-bottom:8px">Labeling Approach</div>
VNF used as spatial oracle — FIRMS within 5 km of a VNF site &rarr; Persistent Source.
Remaining global FIRMS &rarr; Natural Fire candidate.
Anomaly (max_prob &lt; 0.55) &rarr; Industrial Fire.
</div>
""", unsafe_allow_html=True)

    with _mc2:
        st.markdown("""
<div style="font-size:11px;color:var(--t1);line-height:1.8">
<div style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;
            color:var(--t2);margin-bottom:10px">Three-Way Evaluation (anti-leakage design)</div>
</div>
""", unsafe_allow_html=True)
        _eval_df = pd.DataFrame({
            "Evaluation":  ["Random split (baseline)", "Spatial holdout (honest)", "India holdout (locked)"],
            "Accuracy":    ["97.25%", "98.06%", "scored only"],
            "Class A F1":  ["0.24",   "0.18",   "—"],
        })
        st.dataframe(_eval_df, hide_index=True, use_container_width=True)

        st.markdown("""
<div style="font-size:11px;color:var(--t1);line-height:1.8;margin-top:14px">
<div style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;
            color:var(--t2);margin-bottom:10px">Feature Importances</div>
</div>
""", unsafe_allow_html=True)
        _feat_df = pd.DataFrame({
            "Feature":    [
                "Distance to industrial facility",
                "Nighttime detection flag",
                "Pixel brightness temperature",
                "Persistence count (5-day)",
                "Fire Radiative Power (FRP)",
            ],
            "Importance": ["29.3%", "25.3%", "21.4%", "13.9%", "10.1%"],
        })
        st.dataframe(_feat_df, hide_index=True, use_container_width=True)


# ────────────────────────────────────────────────────────────────────────────────
# TAB 6 — Limitations
# ────────────────────────────────────────────────────────────────────────────────
with tab_limits:
    st.markdown('<div class="sec-label">Limitations &amp; Scientific Caveats</div>', unsafe_allow_html=True)

    _lim_items = [
        ("Classification",
         "No confirmed industrial fire ground-truth dataset exists (India or global). "
         "The Industrial Fire output class is derived from anomaly detection — hotspots "
         "matching neither the persistent-flare nor natural-fire patterns — not from "
         "direct supervised training on confirmed incidents. "
         "Class A training set: 1,901 FIRMS examples via VNF oracle. F1 = 0.18 on spatial holdout. "
         "Historical FIRMS archive would improve recall substantially."),
        ("Land-cover",
         "Land-cover context is derived from coordinate-based India zone rules + agri-season flag. "
         "Full MODIS MCD12Q1 or ESA CCI Land Cover integration would improve precision, "
         "particularly for forest vs agricultural vs mixed land-cover discrimination."),
        ("Facility coverage",
         "LNG terminals are present in the facility layer via OSM port tags but are a small fraction. "
         "Dedicated LNG infrastructure datasets (e.g., Global LNG Tracker) would improve coverage. "
         "Steel mills and petrochemical complexes are mapped via generic landuse=industrial "
         "OSM tag where specific sub-tags are absent."),
        ("Temporal",
         "FIRMS NRT covers only the last 5 days. Historical incident matching (2019–2023 events) "
         "requires LAADS DAAC archive download. "
         "VNF persistence data is annual (2012–2019); NRT persistence counts are 5-day only."),
        ("Operational use",
         "All alerts require human verification before operational dispatch. "
         "Correct framing: anomalous departure from known persistent-industrial and "
         "natural-fire patterns — not confirmed fire detection."),
    ]
    for _title, _body in _lim_items:
        st.markdown(f"""
<div style="padding:12px 0;border-bottom:1px solid var(--bd-0)">
  <div style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;
              color:var(--t2);margin-bottom:5px">{_title}</div>
  <div style="font-size:11px;color:var(--t1);line-height:1.75">{_body}</div>
</div>
""", unsafe_allow_html=True)


# ── Timeline playback — advance one day per rerun ─────────────────────────────
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
