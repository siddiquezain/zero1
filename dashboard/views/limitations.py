"""Limitations — honest caveats. Important for technical credibility."""
from __future__ import annotations

import streamlit as st

from dashboard import theme as T
from dashboard.components import ui
from dashboard.shell import topbar

_ITEMS = [
    ("No 'confirmed fire' claim",
     "No dataset of confirmed industrial fires exists (India or global). The "
     "'Industrial Fire' class is an anomaly flag — a hotspot matching neither the "
     "persistent-industrial nor the natural-fire learned pattern — not a supervised "
     "detection. Every alert requires human verification."),
    ("FIRMS spatial resolution",
     "VIIRS pixels are 375 m, MODIS 1 km. Small or short-lived events can be missed "
     "or merged. We inherit the sensor's limits; our value is the interpretation layer."),
    ("Satellite revisit & cloud",
     "Polar-orbiting satellites pass a few times a day and cloud blocks the infrared "
     "view. Coverage is periodic; persistence is measured only over available passes."),
    ("Near-real-time only (~5 days)",
     "The FIRMS NRT API returns roughly the last 5 days. No historical archive is "
     "wired in, so timeline depth and 2019–2023 incident date-matching are limited. "
     "The archive is a known next step."),
    ("Proxy training labels",
     "Class A = a global FIRMS row within 5 km of a VIIRS Nightfire flare site; "
     "B_candidate = every other global FIRMS row (not land-cover validated). "
     "Defensible, and stated openly."),
    ("Thin industrial class",
     "~1,900 positive training rows → Class A F1 = 0.18 on the spatial holdout. "
     "Recall is limited by label scarcity; a historical archive or the GIHS dataset "
     "would help."),
    ("Land cover is a heuristic",
     "Derived from coordinate zone rules, not a MODIS / ESA land-cover raster. "
     "A pragmatic approximation; a real raster is a drop-in improvement."),
    ("State resolution is approximate",
     "lat/lon → Indian state uses a bounding-box + centroid method (offline, no "
     "dependency). Large well-separated states resolve reliably; border cells can "
     "be off by one state."),
    ("Agent is read-only",
     "The Fire Intelligence Agent can query, filter, navigate and prepare reports. "
     "It cannot acknowledge / escalate / resolve or change any record — those stay "
     "with the operator. A deliberate safety choice."),
]


def render() -> None:
    topbar("Limitations")
    ui.page_header("Limitations & Transparency",
                   "What the system does not do — and why we say so")
    for title, body in _ITEMS:
        st.markdown(
            f'<div class="panel" style="margin-bottom:8px">'
            f'<div style="font-size:11px;font-weight:700;letter-spacing:.06em;color:{T.T0}">{title}</div>'
            f'<div style="font-size:11.5px;color:{T.T1};line-height:1.7;margin-top:4px">{body}</div>'
            f'</div>', unsafe_allow_html=True)
