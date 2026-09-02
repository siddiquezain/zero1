"""
Shared session state: the global filter model + navigation / focus.

Manual controls and the Fire Intelligence Agent both write through here, so an
agent-applied filter is indistinguishable from a hand-set one downstream.
"""
from __future__ import annotations

import streamlit as st

_DEFAULT_FILTERS: dict = {
    "severity": [],          # [] = all
    "status": [],
    "output_class": [],
    "state": [],
    "region": None,
    "date_from": None,
    "date_to": None,
    "near_facility_type": None,
    "max_dist_facility_km": None,
    "min_risk": None,
    "search": None,
}

_PAGE_ROUTE = {
    "command center": "Command Center", "command_center": "Command Center",
    "alerts": "Alerts", "alert": "Alerts",
    "investigation": "Investigation", "investigations": "Investigation",
    "map": "Map Explorer", "map explorer": "Map Explorer", "map_explorer": "Map Explorer",
    "analytics": "Analytics",
    "facilities": "Facilities",
    "reports": "Reports / GIS", "reports / gis": "Reports / GIS", "gis": "Reports / GIS",
    "model": "Model",
    "limitations": "Limitations",
}


def init() -> None:
    ss = st.session_state
    ss.setdefault("filters", dict(_DEFAULT_FILTERS))
    ss.setdefault("focus_alert_id", None)
    ss.setdefault("agent_history", [])          # list[dict(role, text, cards, ui_action, ts, mode)]
    ss.setdefault("agent_open", False)           # dock panel expanded? (IDLE vs OPEN)
    ss.setdefault("agent_pending", None)         # queued question → robot "busy" until answered
    ss.setdefault("nav_request", None)          # a page name to switch to on next run
    ss.setdefault("alert_page", 0)
    ss.setdefault("map_colour_by", "class")
    ss.setdefault("show_incidents", True)
    ss.setdefault("show_facilities", False)


def filters() -> dict:
    init()
    return {k: v for k, v in st.session_state["filters"].items()
            if v not in (None, [], "")}


def raw_filters() -> dict:
    init()
    return st.session_state["filters"]


def set_filters(patch: dict, *, replace: bool = False) -> None:
    init()
    base = dict(_DEFAULT_FILTERS) if replace else st.session_state["filters"]
    for k, v in (patch or {}).items():
        if k in _DEFAULT_FILTERS:
            base[k] = v
    st.session_state["filters"] = base
    st.session_state["alert_page"] = 0


def clear_filters() -> None:
    init()
    st.session_state["filters"] = dict(_DEFAULT_FILTERS)
    st.session_state["alert_page"] = 0


def focus_alert(alert_id: str | None) -> None:
    init()
    st.session_state["focus_alert_id"] = alert_id


def request_nav(page: str | None) -> None:
    if not page:
        return
    st.session_state["nav_request"] = _PAGE_ROUTE.get(str(page).strip().lower(), page)


def take_nav_request() -> str | None:
    init()
    p = st.session_state.get("nav_request")
    st.session_state["nav_request"] = None
    return p


def apply_ui_action(ui_action: dict | None) -> bool:
    """Apply an agent ui_action ({nav, filters, focus_alert_id}). Returns True if a rerun is warranted."""
    if not ui_action:
        return False
    changed = False
    if ui_action.get("filters") is not None:
        set_filters(ui_action["filters"], replace=True)
        changed = True
    if ui_action.get("focus_alert_id"):
        focus_alert(ui_action["focus_alert_id"])
        changed = True
    if ui_action.get("nav"):
        request_nav(ui_action["nav"])
        changed = True
    return changed
