"""Shared analysis toolbar — writes the global filter model in dashboard/state.py."""
from __future__ import annotations

import streamlit as st

from dashboard import data, state

_SEV = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
_STATUS = ["DETECTED", "VALIDATING", "ALERTED", "ESCALATED", "MONITORING", "EXTINGUISHED"]
_CLASSES = ["Industrial Fire", "Persistent Source", "Natural Fire"]
_STATES = ["Odisha", "Jharkhand", "West Bengal", "Bihar", "Chhattisgarh", "Gujarat",
           "Maharashtra", "Andhra Pradesh", "Telangana", "Tamil Nadu", "Madhya Pradesh",
           "Uttar Pradesh", "Rajasthan", "Punjab", "Haryana", "Assam", "Karnataka", "Kerala"]


def render(*, show_status: bool = True, show_class: bool = True, key: str = "fb") -> None:
    f = state.raw_filters()
    lo, hi = data.DATE_RANGE()

    fields = ["severity"]
    if show_status:
        fields.append("status")
    if show_class:
        fields.append("class")
    fields += ["state", "window", "clear"]

    weights = {"severity": 1.3, "status": 1.3, "class": 1.4, "state": 1.3,
               "window": 1.1, "clear": 0.6}
    cols = st.columns([weights[x] for x in fields])
    col = dict(zip(fields, cols))

    sev = col["severity"].multiselect("Severity", _SEV, default=f["severity"], key=f"{key}_sev")
    sts = col["status"].multiselect("Status", _STATUS, default=f["status"],
                                    key=f"{key}_sts") if show_status else f["status"]
    cls = col["class"].multiselect("Classification", _CLASSES, default=f["output_class"],
                                   key=f"{key}_cls") if show_class else f["output_class"]
    stt = col["state"].multiselect("State", _STATES,
                                   default=[s for s in f["state"] if s in _STATES],
                                   key=f"{key}_state")
    quick = col["window"].selectbox("Window", ["All", "Latest day", "Last 3 days", "Last 7 days"],
                                    index=0, key=f"{key}_win")

    df_from, df_to = None, None
    if quick == "Latest day":
        df_from = df_to = hi
    elif quick in ("Last 3 days", "Last 7 days"):
        from src.intelligence.queries import resolve_timeframe
        df_from, df_to = resolve_timeframe(quick.lower())

    col["clear"].markdown('<div style="height:22px"></div>', unsafe_allow_html=True)
    if col["clear"].button("Clear", key=f"{key}_clear", use_container_width=True):
        state.clear_filters()
        st.rerun()

    state.set_filters({"severity": sev, "status": sts, "output_class": cls, "state": stt,
                       "date_from": df_from, "date_to": df_to})
    if stt:
        state.raw_filters()["region"] = None
