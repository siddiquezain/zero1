"""
Stage 8 — Dashboard.

Streamlit + pydeck map showing India FIRMS NRT hotspots scored by the
Stage 6 classifier, overlaid with confirmed incidents and facility locations.

Run:
    streamlit run dashboard/app.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
INDIA_SCORES = ROOT / "data/processed/stage6_india_scores.parquet"
INCIDENT_SCORES = ROOT / "data/incidents/stage7_incident_scores.parquet"
FACILITIES = ROOT / "data/processed/facilities.parquet"

# ── Colour map ────────────────────────────────────────────────────────────────
# [R, G, B, A]
COLOUR = {
    "A_confirmed":  [255, 140,   0, 200],  # orange — Class A (industrial/flare)
    "B_confirmed":  [ 50, 200,  80, 200],  # green  — Class B (natural/agri fire)
    "anomaly":      [180,   0, 255, 220],  # purple — anomaly flag
    "incident":     [255, 230,   0, 255],  # yellow — confirmed incidents
    "incident_A":   [255, 100,  20, 255],  # orange-red — incident predicted A
    "incident_B":   [ 80, 200,  80, 255],  # green  — incident predicted B
    "incident_anom":[180,   0, 255, 255],  # purple — incident anomaly
}

# ── Case studies (for sidebar panel) ─────────────────────────────────────────
CASE_STUDIES = [
    {
        "title": "Jharia Coalfield — Persistent Thermal Anomaly",
        "incident_id": "IND-012",
        "what": (
            "Jharia, Jharkhand has been burning underground since 1916. "
            "The classifier flags it as anomalous (max_prob=0.546) — not a gas flare "
            "pattern (no VNF record nearby) but also not a short-burst natural fire. "
            "Exactly the kind of chronic industrial thermal source this system is "
            "designed to surface."
        ),
        "finding": "Anomaly-flagged. Correct — no FIRMS NRT data can be matched without archive.",
    },
    {
        "title": "Punjab Paddy Stubble Burning (Oct–Nov cluster)",
        "incident_id": "IND-009",
        "what": (
            "Seasonal agricultural burning in Punjab/Haryana. The classifier correctly "
            "predicts Class B (natural/agricultural fire) with no anomaly flag. "
            "The agri_season_flag and acq_month drive this classification."
        ),
        "finding": "Correctly predicted Class B. Agri burning correctly NOT flagged as industrial.",
    },
    {
        "title": "Vizag LG Polymers Gas Leak — Industrial Incident",
        "incident_id": "IND-001",
        "what": (
            "Styrene gas leak at LG Polymers Visakhapatnam, May 2020. 12 fatalities. "
            "Flagged as anomalous (max_prob=0.52) — the site is near industrial "
            "facilities but doesn't match the persistent gas flare pattern (Class A) "
            "or a natural fire (Class B). This is the target detection case."
        ),
        "finding": "Anomaly-flagged. Correct — a transient industrial incident, not a persistent source.",
    },
]


@st.cache_data
def load_data():
    india = pd.read_parquet(INDIA_SCORES) if INDIA_SCORES.exists() else pd.DataFrame()
    incidents = pd.read_parquet(INCIDENT_SCORES) if INCIDENT_SCORES.exists() else pd.DataFrame()
    fac = pd.read_parquet(FACILITIES) if FACILITIES.exists() else pd.DataFrame()

    # India facility subset
    india_fac = fac[
        (fac["lat"] >= 6) & (fac["lat"] <= 37) &
        (fac["lon"] >= 68) & (fac["lon"] <= 97.5)
    ] if not fac.empty else fac

    return india, incidents, india_fac


def _colour_firms(row) -> list[int]:
    if row.get("anomaly_flag", 0) == 1:
        return COLOUR["anomaly"]
    return COLOUR["A_confirmed"] if row["predicted_label"] == "A" else COLOUR["B_confirmed"]


def _colour_incident(row) -> list[int]:
    if row.get("anomaly_flag", 0) == 1:
        return COLOUR["incident_anom"]
    return COLOUR["incident_A"] if row["predicted_label"] == "A" else COLOUR["incident_B"]


def _build_firms_layer(india: pd.DataFrame) -> pdk.Layer | None:
    if india.empty:
        return None

    india = india.copy()
    india["color"] = india.apply(_colour_firms, axis=1)
    india["radius"] = 8000
    india["tooltip_text"] = india.apply(
        lambda r: (
            f"Class: {r['predicted_label']} | Anomaly: {'yes' if r['anomaly_flag'] else 'no'}\n"
            f"prob_A={r['prob_A']:.3f}  prob_B={r['prob_B_candidate']:.3f}\n"
            f"bt_kelvin={r['bt_kelvin']:.1f}K  frp={r['frp_mw']:.1f}MW\n"
            f"persist={r['persistence_count']}  dist_fac={r['dist_nearest_facility_km']:.1f}km\n"
            f"date={r['acq_date']}"
        ),
        axis=1,
    )

    return pdk.Layer(
        "ScatterplotLayer",
        data=india,
        get_position=["lon", "lat"],
        get_color="color",
        get_radius="radius",
        pickable=True,
        opacity=0.7,
        stroked=True,
        line_width_min_pixels=1,
        id="firms_layer",
    )


def _build_incident_layer(incidents: pd.DataFrame) -> pdk.Layer | None:
    if incidents.empty:
        return None

    incidents = incidents.copy()
    incidents["color"] = incidents.apply(_colour_incident, axis=1)
    incidents["tooltip_text"] = incidents.apply(
        lambda r: (
            f"{r['incident_id']}: {r['name']}\n"
            f"Date: {r['date']}  Type: {r.get('facility_type', '?')}\n"
            f"Predicted: {r['predicted_label']} | Anomaly: {'YES' if r['anomaly_flag'] else 'no'}\n"
            f"prob_A={r['prob_A']:.3f}  prob_B={r['prob_B_candidate']:.3f}\n"
            f"dist_fac={r['dist_nearest_facility_km']:.1f}km"
        ),
        axis=1,
    )

    return pdk.Layer(
        "ScatterplotLayer",
        data=incidents,
        get_position=["lon", "lat"],
        get_color="color",
        get_radius=20000,
        pickable=True,
        opacity=0.9,
        stroked=True,
        get_line_color=[255, 255, 255],
        line_width_min_pixels=2,
        id="incident_layer",
    )


def _build_facility_layer(fac: pd.DataFrame) -> pdk.Layer | None:
    if fac.empty:
        return None
    sample = fac.sample(min(5000, len(fac)), random_state=42)
    return pdk.Layer(
        "ScatterplotLayer",
        data=sample,
        get_position=["lon", "lat"],
        get_color=[120, 120, 120, 100],
        get_radius=3000,
        pickable=False,
        id="facility_layer",
    )


def main():
    st.set_page_config(
        page_title="SIH26162 — Industrial Fire Detection",
        page_icon="🔥",
        layout="wide",
    )

    st.title("SIH26162 — Industrial Fire & Thermal Anomaly Detection")
    st.caption(
        "AI-based classification of satellite hotspots (NASA FIRMS NRT) into: "
        "**Class A** (persistent industrial/flare) · **Class B** (natural/agricultural fire) · **Anomaly** (neither)"
    )

    india, incidents, fac = load_data()

    # ── Sidebar ────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("Filters & Settings")

        show_firms = st.checkbox("Show India FIRMS hotspots", value=True)
        show_incidents = st.checkbox("Show confirmed incidents", value=True)
        show_facilities = st.checkbox("Show industrial facilities (sample)", value=False)

        st.divider()
        st.subheader("Legend")
        st.markdown(
            "🟠 **Class A** — Persistent industrial/flare  \n"
            "🟢 **Class B** — Natural/agricultural fire  \n"
            "🟣 **Anomaly** — Neither pattern (flagged for review)  \n"
            "🟡 **Incident** — Confirmed industrial incident site"
        )

        st.divider()
        st.subheader("Model")
        st.markdown(
            "**RandomForest** trained globally, India withheld as test.  \n"
            f"Training: 270,238 rows (global FIRMS NRT)  \n"
            f"Class A labelled via VNF oracle (5 km proximity)  \n"
            f"Spatial holdout accuracy: **98.1%** (Class A F1: 0.18)  \n"
            f"Anomaly threshold: max_prob < 0.55"
        )

        st.divider()
        st.subheader("Framing")
        st.info(
            "This system detects **anomalous departures from known patterns** — "
            "not confirmed fires. No dataset of confirmed industrial fires exists "
            "for training. Classification reflects departure from known persistent-"
            "industrial (gas flare) and natural-fire signatures."
        )

    # ── Stats row ─────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    if not india.empty:
        n_a = (india["predicted_label"] == "A").sum()
        n_b = (india["predicted_label"] == "B_candidate").sum()
        n_anom = india["anomaly_flag"].sum()
        col1.metric("India FIRMS hotspots", f"{len(india):,}")
        col2.metric("Predicted Class A (industrial)", f"{n_a:,}", f"{100*n_a/len(india):.1f}%")
        col3.metric("Predicted Class B (natural fire)", f"{n_b:,}", f"{100*n_b/len(india):.1f}%")
        col4.metric("Anomaly-flagged", f"{n_anom:,}", f"{100*n_anom/len(india):.1f}%")

    if not incidents.empty:
        with st.expander(f"Confirmed incidents — {incidents['anomaly_flag'].sum()}/30 anomaly-flagged"):
            st.dataframe(
                incidents[[
                    "incident_id", "name", "date", "state", "facility_type",
                    "predicted_label", "prob_A", "prob_B_candidate", "anomaly_flag",
                    "dist_nearest_facility_km"
                ]].sort_values("prob_A", ascending=False),
                hide_index=True,
                use_container_width=True,
            )

    # ── Map ────────────────────────────────────────────────────────────────────
    layers = []
    if show_firms and not india.empty:
        l = _build_firms_layer(india)
        if l:
            layers.append(l)
    if show_facilities and not fac.empty:
        l = _build_facility_layer(fac)
        if l:
            layers.append(l)
    if show_incidents and not incidents.empty:
        l = _build_incident_layer(incidents)
        if l:
            layers.append(l)

    view = pdk.ViewState(
        latitude=20.5,
        longitude=80.0,
        zoom=4.5,
        pitch=0,
    )

    tooltip = {
        "html": "<b>{tooltip_text}</b>",
        "style": {
            "backgroundColor": "rgba(0,0,0,0.85)",
            "color": "white",
            "fontSize": "12px",
            "padding": "8px",
            "borderRadius": "4px",
            "whiteSpace": "pre-line",
        },
    }

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view,
        tooltip=tooltip,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )

    st.pydeck_chart(deck, use_container_width=True, height=600)

    # ── Case studies ──────────────────────────────────────────────────────────
    st.subheader("Case Studies")
    tabs = st.tabs([cs["title"] for cs in CASE_STUDIES])
    for tab, cs in zip(tabs, CASE_STUDIES):
        with tab:
            inc_row = (
                incidents[incidents["incident_id"] == cs["incident_id"]].iloc[0]
                if not incidents.empty and cs["incident_id"] in incidents["incident_id"].values
                else None
            )
            col_a, col_b = st.columns([2, 1])
            with col_a:
                st.markdown(cs["what"])
                st.success(f"**Finding:** {cs['finding']}")
            with col_b:
                if inc_row is not None:
                    st.metric("prob_A", f"{inc_row['prob_A']:.3f}")
                    st.metric("prob_B", f"{inc_row['prob_B_candidate']:.3f}")
                    st.metric("Anomaly flag", "YES ✓" if inc_row["anomaly_flag"] else "no")
                    st.metric("Distance to facility", f"{inc_row['dist_nearest_facility_km']:.1f} km")

    # ── Limitations ───────────────────────────────────────────────────────────
    with st.expander("Limitations & scientific caveats"):
        st.markdown(
            """
            - **No confirmed industrial fire training data exists** (globally). Classification is trained on
              gas flares (VNF oracle) vs. natural fires (global FIRMS NRT). Industrial incident detection
              is demonstrated by *anomaly* output, not a trained class.
            - **Class A training set is thin** (1,901 FIRMS examples from VNF proximity). Spatial holdout
              Class A F1 = 0.18. Adding historical FIRMS archive or GIHS would improve substantially.
            - **Incident scores lack thermal features**. Historical FIRMS archive not yet downloaded.
              Incident classifications are driven by facility proximity + seasonality, not thermal measurements.
            - **FIRMS NRT is 5-day only**. Persistence counts reflect a 5-day window, not a full year.
              VNF persistence (dtc_freq, annual %) is a richer signal not yet available for current NRT.
            - **India holdout is locked** — not used during any training or model selection step.
              The 705 India hotspots scored here are genuine out-of-sample predictions.
            """
        )


if __name__ == "__main__":
    main()
