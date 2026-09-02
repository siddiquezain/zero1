"""Shared India detection map (pydeck). Used by Command Center and Map Explorer."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pydeck as pdk

from dashboard import theme as T

_OUTLINE_PATH = Path(__file__).resolve().parents[2] / "data/geo/india_outline.json"
try:
    _INDIA_OUTLINE = json.loads(_OUTLINE_PATH.read_text())["polygon"]
except Exception:
    _INDIA_OUTLINE = []


def _s(v) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return ""
    s = str(v)
    return "" if s.lower() in ("nan", "none") else s

_VIEW_INDIA = pdk.ViewState(latitude=22.5, longitude=81.5, zoom=3.85, bearing=0, pitch=0)
# CARTO dark basemap (Streamlit's default, MapLibre, no Mapbox token needed).
# The bundled India outline is drawn as a thin emphasis border on top.
_MAP_STYLE = "dark"


def build_deck(alerts: list[dict], *, colour_by: str = "class",
               incidents: list[dict] | None = None,
               facilities: list[dict] | None = None,
               outside: list[dict] | None = None,
               focus_alert_id: str | None = None,
               view: pdk.ViewState | None = None) -> pdk.Deck:
    layers = []

    if _INDIA_OUTLINE:
        layers.append(pdk.Layer(
            "PolygonLayer",
            data=[{"polygon": _INDIA_OUTLINE}],
            get_polygon="polygon", stroked=True, filled=False,
            get_line_color=[90, 108, 128, 150], line_width_min_pixels=1, pickable=False,
        ))

    # regional context: FIRMS points inside the ingestion bbox but OUTSIDE India.
    # Plotted at their true coordinates, dimmed, explicitly labelled — not moved,
    # not dropped.
    if outside:
        odf = pd.DataFrame(outside)
        odf["tip"] = odf.apply(lambda r: (
            f"OUTSIDE INDIA — {_s(r.get('zone')) or 'neighbouring region'}\n"
            f"{_s(r['output_class_short'])} · not part of the India monitoring dataset\n"
            f"{r['lat']:.3f}, {r['lon']:.3f}"
        ), axis=1)
        layers.append(pdk.Layer(
            "ScatterplotLayer", data=odf, get_position=["lon", "lat"],
            get_fill_color=[120, 130, 145, 70], get_line_color=[150, 160, 175, 90],
            get_radius=9000, stroked=True, line_width_min_pixels=0.5, pickable=True,
            radius_min_pixels=1.5, radius_max_pixels=6,
        ))

    if alerts:
        df = pd.DataFrame(alerts)
        if colour_by == "severity":
            df["color"] = df["severity"].map(T.SEV_RGBA)
        else:
            df["color"] = df["output_class_short"].map(T.CLASS_RGBA)
        df["color"] = df["color"].apply(lambda v: v if isinstance(v, list) else [150, 150, 150, 160])
        df["radius"] = df["risk_score"].apply(lambda s: 6000 + int(s) * 260)
        df["tip"] = df.apply(lambda r: (
            f"{_s(r['output_class_short'])}  -  {_s(r['severity'])}  -  Risk {r['risk_score']}/100\n"
            f"{_s(r.get('place')) or _s(r.get('state')) or _s(r.get('zone')) or '-'}\n"
            f"FRP {r['frp_mw'] if pd.notna(r['frp_mw']) else '-'} MW  -  "
            f"Persist {int(r['persistence_count'])}x  -  {_s(r['acq_date'])}"
        ), axis=1)
        layers.append(pdk.Layer(
            "ScatterplotLayer", data=df, get_position=["lon", "lat"],
            get_fill_color="color", get_radius="radius", pickable=True,
            opacity=0.75, stroked=True, get_line_color=[10, 14, 21, 120],
            line_width_min_pixels=0.5, radius_min_pixels=2, radius_max_pixels=26,
        ))
        if focus_alert_id:
            f = df[df["alert_id"] == focus_alert_id]
            if not f.empty:
                layers.append(pdk.Layer(
                    "ScatterplotLayer", data=f, get_position=["lon", "lat"],
                    get_fill_color=[0, 0, 0, 0], get_line_color=[232, 234, 237, 230],
                    get_radius=42000, stroked=True, line_width_min_pixels=2, pickable=False,
                ))

    if facilities:
        fdf = pd.DataFrame(facilities)
        fdf["tip"] = fdf.apply(lambda r: (
            f"{_s(r['name'])}\n{_s(r['hazard_type'])}  {_s(r.get('state'))}\n"
            f"{r['nearby_detections']} nearby detections  -  max risk {r['max_risk']}"
        ), axis=1)
        layers.append(pdk.Layer(
            "ScatterplotLayer", data=fdf, get_position=["lon", "lat"],
            get_fill_color=[61, 125, 200, 40], get_line_color=[61, 125, 200, 180],
            get_radius=22000, stroked=True, line_width_min_pixels=1, pickable=True,
        ))

    if incidents:
        idf = pd.DataFrame(incidents)
        idf["tip"] = idf.apply(lambda r: (
            f"{r['incident_id']}: {_s(r['name'])}\n{_s(r.get('state'))}  {_s(r['date'])}\n"
            f"anomaly: {'yes' if r['anomaly_flag'] else 'no'}"
        ), axis=1)
        layers.append(pdk.Layer(
            "ScatterplotLayer", data=idf, get_position=["lon", "lat"],
            get_fill_color=[154, 164, 178, 90], get_line_color=[200, 205, 212, 200],
            get_radius=16000, stroked=True, line_width_min_pixels=1, pickable=True,
        ))

    return pdk.Deck(
        layers=layers,
        initial_view_state=view or _VIEW_INDIA,
        map_provider="carto",
        map_style=_MAP_STYLE,
        tooltip={"html": "<pre style='font-family:IBM Plex Mono,monospace;font-size:10.5px;"
                         "color:#e8eaed;margin:0'>{tip}</pre>",
                 "style": {"background": "rgba(10,14,21,0.95)",
                           "border": "1px solid #2a3644", "borderRadius": "6px",
                           "padding": "8px 10px"}},
    )
