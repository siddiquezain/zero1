"""
Design system for the SIH26162 dashboard.

Dark operations-centre aesthetic matching the approved UI reference:
neutral navy-black surfaces, hairline borders, restrained semantic colour
(red = critical is scarce), a strict type scale, ~8px radii. No gradients,
no glow, no glassmorphism.
"""
from __future__ import annotations

import streamlit as st

# ── palette ──────────────────────────────────────────────────────────────────
BG          = "#0a0e15"
BG_ELEV     = "#0f141d"
PANEL       = "#111823"
PANEL_2     = "#151d2a"
BORDER      = "#1e2733"
BORDER_2    = "#2a3644"
T0          = "#e8eaed"   # primary text
T1          = "#8b95a5"   # secondary
T2          = "#5a6472"   # muted
ACCENT      = "#3d7dc8"   # single system blue

CRIT        = "#ef4444"
HIGH        = "#f59e0b"
MED         = "#eab308"
LOW         = "#22c55e"
AGENT       = "#7c5cff"

CLS_INDUSTRIAL = "#ef4444"
CLS_PERSISTENT = "#f59e0b"
CLS_NATURAL    = "#22c55e"
CLS_INCIDENT   = "#9aa4b2"

SEV_COLOR = {"CRITICAL": CRIT, "HIGH": HIGH, "MEDIUM": MED, "LOW": LOW}
CLASS_COLOR = {
    "Industrial Fire": CLS_INDUSTRIAL,
    "Persistent Source": CLS_PERSISTENT,
    "Natural Fire": CLS_NATURAL,
    "Confirmed Incident": CLS_INCIDENT,
}

# pydeck RGBA
SEV_RGBA = {
    "CRITICAL": [239, 68, 68, 235],
    "HIGH":     [245, 158, 11, 210],
    "MEDIUM":   [234, 179, 8, 180],
    "LOW":      [34, 197, 94, 150],
}
CLASS_RGBA = {
    "Industrial Fire": [239, 68, 68, 235],
    "Persistent Source": [245, 158, 11, 215],
    "Natural Fire": [34, 197, 94, 175],
}

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {{
  --bg:{BG}; --panel:{PANEL}; --panel2:{PANEL_2}; --bd:{BORDER}; --bd2:{BORDER_2};
  --t0:{T0}; --t1:{T1}; --t2:{T2}; --accent:{ACCENT};
  --crit:{CRIT}; --high:{HIGH}; --med:{MED}; --low:{LOW}; --agent:{AGENT};
  --mono:'IBM Plex Mono',ui-monospace,monospace;
  --r:9px;
}}

html, body, [data-testid="stAppViewContainer"], .stApp {{
  background: var(--bg) !important;
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  color: var(--t0);
}}
[data-testid="stHeader"] {{ background: transparent; height: 0; }}
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer {{ display:none !important; }}
[data-testid="stMainBlockContainer"], .block-container {{
  padding: 0.4rem 1.4rem 3rem 1.4rem !important; max-width: 100% !important;
}}
[data-testid="stMain"] {{ background: var(--bg); }}
::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: var(--bd2); border-radius: 4px; }}

/* ── sidebar → operations rail ─────────────────────────────────────────────*/
[data-testid="stSidebar"] {{
  background: {BG_ELEV} !important;
  border-right: 1px solid var(--bd);
  width: 236px !important;
}}
[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {{ padding: 0; height: 0; }}
[data-testid="stSidebarUserContent"] {{ padding: 0.6rem 0.55rem 1rem; }}
[data-testid="stSidebarNav"] {{ padding-top: 4px; }}
[data-testid="stSidebarNav"] ul {{ gap: 1px; }}
[data-testid="stSidebarNav"] a {{
  border-radius: 7px; padding: 7px 10px !important; color: var(--t1) !important;
  font-size: 12.5px !important; font-weight: 500;
}}
[data-testid="stSidebarNav"] a:hover {{ background: var(--panel) !important; color: var(--t0) !important; }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{
  background: rgba(239,68,68,0.10) !important; color: var(--crit) !important;
  box-shadow: inset 2px 0 0 var(--crit);
}}
[data-testid="stSidebarNav"] a[aria-current="page"] span {{ color: var(--crit) !important; }}
[data-testid="stSidebarNav"] span[data-testid="stIconMaterial"] {{ font-size: 17px !important; }}

/* ── brand block (rendered into the sidebar top) ──────────────────────────*/
.brand {{ display:flex; gap:10px; align-items:center; padding: 12px 8px 12px; border-bottom:1px solid var(--bd); margin-bottom: 6px; }}
.brand-mark {{ width:34px; height:34px; border-radius:9px; background:{CRIT}1a; border:1px solid {CRIT}44;
  display:flex; align-items:center; justify-content:center; font-size:18px; flex:none; }}
.brand-id {{ font-family:var(--mono); font-size:9.5px; letter-spacing:.14em; color:var(--t2); }}
.brand-name {{ font-size:13px; font-weight:700; letter-spacing:.02em; line-height:1.15; }}
.brand-sub {{ font-size:9px; color:var(--t2); letter-spacing:.05em; margin-top:1px; }}

/* ── top status bar ──────────────────────────────────────────────────────*/
.topbar {{
  display:flex; align-items:center; justify-content:space-between;
  padding: 6px 2px 12px; border-bottom:1px solid var(--bd); margin-bottom: 16px;
}}
.tb-pills {{ display:flex; align-items:center; gap:0; border:1px solid var(--bd); border-radius:8px; overflow:hidden; }}
.tb-pill {{ padding:5px 11px; font-size:11px; color:var(--t1); font-family:var(--mono);
  border-right:1px solid var(--bd); display:flex; align-items:center; gap:6px; }}
.tb-pill:last-child {{ border-right:none; }}
.dot {{ width:6px; height:6px; border-radius:50%; background:var(--low); box-shadow:0 0 0 3px {LOW}22; }}
.tb-title {{ font-size:12px; color:var(--t1); }}
.tb-right {{ display:flex; align-items:center; gap:14px; color:var(--t1); font-size:11px; }}
.tb-badge {{ position:relative; }}
.tb-badge b {{ position:absolute; top:-6px; right:-8px; background:var(--crit); color:#fff; font-size:8px;
  font-weight:700; border-radius:8px; padding:1px 4px; }}

/* ── section labels ──────────────────────────────────────────────────────*/
.sec {{ font-size:10.5px; font-weight:700; letter-spacing:.12em; text-transform:uppercase;
  color:var(--t1); display:flex; align-items:center; justify-content:space-between; margin: 2px 0 10px; }}
.sec .hint {{ font-weight:500; letter-spacing:.02em; text-transform:none; color:var(--t2); font-size:11px; }}
.page-h {{ font-size:18px; font-weight:700; letter-spacing:-.01em; margin: 0 0 2px; }}
.page-sub {{ font-size:12px; color:var(--t1); margin-bottom:14px; }}

/* ── panels / cards ──────────────────────────────────────────────────────*/
.panel {{ background:var(--panel); border:1px solid var(--bd); border-radius:var(--r); padding:14px 16px; }}
.kpi {{ background:var(--panel); border:1px solid var(--bd); border-radius:var(--r); padding:13px 14px; height:100%; }}
.kpi-top {{ display:flex; align-items:flex-start; justify-content:space-between; }}
.kpi-num {{ font-size:26px; font-weight:700; letter-spacing:-.02em; line-height:1; font-family:var(--mono); }}
.kpi-label {{ font-size:11.5px; font-weight:600; margin-top:7px; }}
.kpi-sub {{ font-size:10.5px; color:var(--t2); margin-top:2px; }}
.kpi-ic {{ width:26px; height:26px; border-radius:7px; display:flex; align-items:center; justify-content:center;
  font-size:13px; border:1px solid var(--bd2); }}
.kpi-trend {{ font-size:10px; font-family:var(--mono); margin-top:6px; }}

/* ── alert row / priority card ───────────────────────────────────────────*/
.acard {{ border:1px solid var(--bd); border-left-width:3px; border-radius:8px; padding:10px 12px;
  margin-bottom:8px; background:var(--panel); }}
.acard .r1 {{ display:flex; align-items:center; gap:8px; }}
.chip {{ font-size:9px; font-weight:700; letter-spacing:.09em; padding:2px 6px; border-radius:4px; text-transform:uppercase; }}
.acard .title {{ font-size:12.5px; font-weight:600; }}
.acard .loc {{ font-size:11px; color:var(--t1); margin-top:3px; }}
.acard .coord {{ font-family:var(--mono); font-size:10px; color:var(--t2); }}
.acard .metrics {{ font-family:var(--mono); font-size:10.5px; color:var(--t1); text-align:right; line-height:1.5; }}
.acard .ago {{ font-size:10px; color:var(--t2); font-family:var(--mono); }}

.mini {{ font-family:var(--mono); font-size:11px; color:var(--t1); }}
.mini em {{ font-style:normal; color:var(--t0); }}

/* ── buttons ─────────────────────────────────────────────────────────────*/
.stButton > button {{
  background:var(--panel2); color:var(--t1); border:1px solid var(--bd2);
  border-radius:7px; font-size:11.5px; font-weight:600; padding:6px 12px;
  transition: all .12s;
}}
.stButton > button:hover {{ background:#1c2634; color:var(--t0); border-color:#374453; }}
.stButton > button[kind="primary"] {{ background:var(--crit); border-color:var(--crit); color:#fff; }}
.stButton > button[kind="primary"]:hover {{ background:#dc2f2f; border-color:#dc2f2f; }}
[data-testid="stDownloadButton"] > button {{ background:var(--panel2); color:var(--t1); border:1px solid var(--bd2);
  border-radius:7px; font-size:11.5px; font-weight:600; }}

/* ── inputs / selects / tabs ─────────────────────────────────────────────*/
[data-baseweb="select"] > div, [data-baseweb="input"] > div, .stTextInput input, .stDateInput input {{
  background:var(--panel2) !important; border-color:var(--bd2) !important; border-radius:7px !important;
  font-size:12px !important;
}}
[data-testid="stWidgetLabel"] p {{ font-size:10.5px !important; font-weight:600 !important;
  letter-spacing:.06em; text-transform:uppercase; color:var(--t1) !important; }}
[data-baseweb="tag"] {{ background:#26313f !important; border-radius:5px !important; }}
[data-testid="stTabs"] [role="tab"] {{ font-size:11px !important; font-weight:600 !important;
  letter-spacing:.08em; text-transform:uppercase; color:var(--t1) !important; }}
[data-testid="stTabs"] [aria-selected="true"] {{ color:var(--t0) !important; border-bottom-color:var(--accent) !important; }}
[data-testid="stExpander"] {{ border:1px solid var(--bd) !important; border-radius:8px !important; background:var(--panel) !important; }}
[data-testid="stExpander"] summary {{ font-size:11px !important; color:var(--t1) !important; }}
[data-testid="stMetric"] {{ background:var(--panel); border:1px solid var(--bd); border-radius:8px; padding:10px 12px; }}
[data-testid="stMetricValue"] {{ font-size:22px !important; font-family:var(--mono); }}
[data-testid="stDataFrame"] {{ border:1px solid var(--bd); border-radius:8px; }}

/* ── Fire Intelligence Agent ─────────────────────────────────────────────*/
.agent-head {{ display:flex; align-items:center; justify-content:space-between; padding:1px 2px 9px; }}
.agent-h-name {{ font-size:12.5px; font-weight:700; letter-spacing:.01em; }}
.agent-status {{ display:flex; align-items:center; gap:5px; font:600 9px/1 var(--mono);
  letter-spacing:.14em; color:var(--t1); }}
.agent-status i {{ width:5px; height:5px; border-radius:50%; background:var(--low); box-shadow:0 0 0 3px {LOW}22; }}
.agent-note {{ font-size:9.5px; color:var(--t2); text-align:center; padding:7px 2px 2px; letter-spacing:.02em; line-height:1.5; }}
/* processing overlay drawn around the (always-static) robot while a query runs */
[class*="st-key-agentstage"] {{ position:relative; }}
.agent-scan {{ position:absolute; left:0; right:0; top:0; margin:0 auto; max-width:360px; height:196px;
  pointer-events:none; border-radius:8px; overflow:hidden; box-shadow:inset 0 0 0 1px rgba(61,125,200,.42); }}
.agent-scan::before {{ content:""; position:absolute; inset:-45%;
  background:conic-gradient(from 0deg, transparent 205deg, rgba(61,125,200,.30) 320deg, transparent 360deg);
  animation:agent-sweep 3s linear infinite; }}
.agent-scan > span {{ position:absolute; left:12px; bottom:11px; font:600 9px/1 var(--mono);
  letter-spacing:.16em; color:#8fbce6; text-shadow:0 1px 3px rgba(0,0,0,.6); }}
.agent-scan > span::after {{ content:" …"; animation:agent-blink 1.1s steps(1,end) infinite; }}
@keyframes agent-sweep {{ to {{ transform:rotate(360deg); }} }}
@keyframes agent-blink {{ 50% {{ opacity:.25; }} }}
.agent-tagline {{ font-size:11px; color:var(--t1); text-align:center; padding:11px 6px 3px; line-height:1.55; }}
.agent-sep {{ display:flex; align-items:center; gap:8px; margin:13px 0 8px;
  font:700 9.5px/1 var(--mono); letter-spacing:.16em; text-transform:uppercase; color:var(--t2); }}
.agent-sep::after {{ content:""; flex:1; height:1px; background:var(--bd); }}
.agent-msg-user {{ background:var(--panel2); border:1px solid var(--bd2); border-right:2px solid var(--accent);
  color:var(--t0); padding:7px 10px; border-radius:6px; font-size:11.5px; line-height:1.5;
  margin:5px 0 5px auto; max-width:86%; width:fit-content; }}
.agent-msg-bot {{ background:var(--panel); border:1px solid var(--bd); color:var(--t0);
  padding:8px 11px; border-radius:6px; font-size:11.5px; line-height:1.55; margin:5px auto 8px 0; max-width:95%; }}
.rc {{ border:1px solid var(--bd2); border-left:2px solid var(--accent); border-radius:6px;
  padding:8px 11px; margin:6px 0 4px; background:var(--panel2); }}
.rc .rc-t {{ font-size:11.5px; font-weight:600; }}
.rc .rc-s {{ font-size:10px; color:var(--t1); font-family:var(--mono); margin-top:2px; }}

.legend {{ display:flex; gap:16px; flex-wrap:wrap; font-size:10.5px; color:var(--t1); }}
.legend span {{ display:flex; align-items:center; gap:5px; }}
.legend i {{ width:8px; height:8px; border-radius:2px; display:inline-block; }}

hr {{ border-color:var(--bd) !important; margin: 10px 0 !important; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: var(--r); }}
</style>
"""


def inject(page_title: str = "India Fire Intelligence") -> None:
    st.set_page_config(
        page_title=f"{page_title} · SIH26162",
        page_icon="🔥",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_CSS, unsafe_allow_html=True)


def sev_chip(sev: str) -> str:
    c = SEV_COLOR.get(sev, T1)
    return f'<span class="chip" style="background:{c}22;color:{c}">{sev}</span>'


def class_dot(cls_short: str) -> str:
    c = CLASS_COLOR.get(cls_short, T1)
    return f'<i style="width:8px;height:8px;border-radius:50%;background:{c};display:inline-block"></i>'
