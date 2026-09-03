"""Model — the real pipeline, data sources, evaluation. Reference only."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import theme as T
from dashboard.components import ui
from dashboard.shell import topbar

_PIPELINE = ["NASA FIRMS", "Preprocessing", "Detection", "Classification",
             "Persistence analysis", "Industrial context", "Risk engine",
             "Alert / Investigation"]


def render() -> None:
    topbar("Model")
    ui.page_header("Model", "How a satellite detection becomes a prioritised, explained alert")

    st.markdown(
        '<div class="panel"><div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center">'
        + " ".join(
            f'<span style="font-family:var(--mono);font-size:11px;background:{T.PANEL_2};'
            f'border:1px solid {T.BORDER_2};border-radius:6px;padding:4px 8px">{s}</span>'
            + ('<span style="color:#5a6472">→</span>' if i < len(_PIPELINE) - 1 else '')
            for i, s in enumerate(_PIPELINE))
        + '</div></div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        ui.section("Data sources (actually used)")
        st.markdown(
            f'<div class="panel mini" style="line-height:1.9">'
            '<b>Satellite</b> — NASA FIRMS NRT (VIIRS 375 m / MODIS 1 km), India bounding box<br>'
            '<b>Flare labels</b> — VIIRS Nightfire (VNF) global gas-flare catalogue, used as a '
            'spatial labelling oracle only<br>'
            '<b>Facilities</b> — WRI Global Power Plant DB + OpenStreetMap industrial polygons '
            '(72,624 rows; 39,277 in India)<br>'
            '<b>Land cover</b> — coordinate-zone heuristic (no raster integrated yet)</div>',
            unsafe_allow_html=True)

        ui.section("Classifier")
        st.markdown(
            f'<div class="panel mini" style="line-height:1.9">'
            'RandomForestClassifier — 300 trees, class_weight="balanced", median imputation.<br>'
            'Trained on <b>270,238</b> non-India FIRMS rows; India held out entirely.<br>'
            'Predicts two classes: <b>A</b> (persistent industrial source) vs '
            '<b>B_candidate</b> (natural / agricultural fire).<br>'
            'Anomaly rule: <b>max(prob) &lt; 0.55</b> → "Industrial Fire / Abnormal Thermal Event".</div>',
            unsafe_allow_html=True)

    with c2:
        ui.section("Three-way evaluation")
        st.dataframe(pd.DataFrame({
            "Evaluation": ["Random split (inflated)", "Spatial holdout (honest)",
                           "India holdout (no labels)"],
            "Accuracy": ["0.9725", "0.9806", "—"],
            "Class A F1": ["0.24", "0.18", "—"],
        }), hide_index=True, use_container_width=True)
        st.markdown(f'<div class="mini" style="line-height:1.7">Overall accuracy is dominated '
                    f'by the easy majority class. The honest figure is <b>Class A F1 = 0.18</b> '
                    f'on the spatial holdout. India holdout: 309 predicted A, 396 B_candidate, '
                    f'59 (8.4%) anomaly-flagged.</div>', unsafe_allow_html=True)

        ui.section("Feature importance")
        st.dataframe(pd.DataFrame({
            "Feature": ["dist_nearest_facility_km", "day_night_bin", "bt_kelvin",
                        "persistence_count", "frp_mw", "agri_season_flag", "acq_month"],
            "Importance": [0.293, 0.253, 0.214, 0.139, 0.101, 0.0, 0.0],
        }), hide_index=True, use_container_width=True)

    ui.section("Risk engine (separate from the model)")
    st.markdown(
        f'<div class="panel mini" style="line-height:1.9">'
        'A transparent additive rule (0–100), <b>not</b> machine-learned: '
        '+30 anomaly · +25/15/8 FRP · +20/10 persistence · +20/12/6 facility proximity · '
        '+10 predicted A · +8 FIRMS confidence · +5 night · +10 near a city. '
        'Bands: ≥65 CRITICAL · ≥40 HIGH · ≥20 MEDIUM · &lt;20 LOW. '
        'The Investigation view shows exactly which components fired for each alert.</div>',
        unsafe_allow_html=True)

    ui.section("Three separate scores — not one number")
    st.markdown(
        f'<div class="panel mini" style="line-height:1.9">'
        '<b>Model class probability</b> — the Random Forest\'s confidence (prob_A / '
        'prob_B_candidate).<br>'
        '<b>Risk score</b> — the additive rule above; operational priority.<br>'
        '<b>Thermal deviation</b> — how far an event departs from its facility\'s own '
        'observed baseline (src/intelligence/facility_fingerprint.py; 0–100, '
        'NORMAL / ELEVATED / ABNORMAL / HIGHLY_ABNORMAL). Deterministic, baseline-relative, '
        'not machine-learned, and deliberately <b>not</b> folded into the risk score. '
        'INSUFFICIENT_BASELINE for facilities without enough history.</div>',
        unsafe_allow_html=True)
