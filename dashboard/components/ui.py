"""Small HTML render helpers — no business logic."""
from __future__ import annotations

import html

import streamlit as st

from dashboard import theme as T


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def section(label: str, hint: str | None = None) -> None:
    h = f'<span class="hint">{_esc(hint)}</span>' if hint else ""
    st.markdown(f'<div class="sec">{_esc(label)}{h}</div>', unsafe_allow_html=True)


def page_header(title: str, subtitle: str | None = None) -> None:
    st.markdown(f'<div class="page-h">{_esc(title)}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="page-sub">{_esc(subtitle)}</div>', unsafe_allow_html=True)


def kpi(value, label: str, sub: str = "", *, icon: str = "", color: str = T.T0,
        trend: str | None = None, trend_color: str | None = None) -> None:
    ic = (f'<div class="kpi-ic" style="color:{color};border-color:{color}44;'
          f'background:{color}14">{icon}</div>') if icon else ""
    tr = (f'<div class="kpi-trend" style="color:{trend_color or T.T1}">{_esc(trend)}</div>'
          if trend else "")
    st.markdown(
        f'<div class="kpi"><div class="kpi-top">'
        f'<div class="kpi-num" style="color:{color}">{_esc(value)}</div>{ic}</div>'
        f'<div class="kpi-label">{_esc(label)}</div>'
        f'<div class="kpi-sub">{_esc(sub)}</div>{tr}</div>',
        unsafe_allow_html=True,
    )


def legend(items: list[tuple[str, str]]) -> None:
    inner = "".join(f'<span><i style="background:{c}"></i>{_esc(lbl)}</span>' for lbl, c in items)
    st.markdown(f'<div class="legend">{inner}</div>', unsafe_allow_html=True)


def alert_card(a: dict, *, ago: str = "", show_button: bool = True,
               key_prefix: str = "ac") -> bool:
    """Render a priority-alert card. Returns True if 'Investigate' was clicked."""
    sev = a["severity"]
    c = T.SEV_COLOR.get(sev, T.T1)
    loc = a.get("place") or a.get("state") or a.get("zone") or "—"
    frp = a["frp_mw"] if a["frp_mw"] is not None else "—"
    title = f"{a['output_class_short']} Detected"
    st.markdown(
        f'<div class="acard" style="border-left-color:{c}">'
        f'<div class="r1">{T.sev_chip(sev)}'
        f'<span class="title">{_esc(title)}</span>'
        f'<span style="margin-left:auto" class="ago">{_esc(ago)}</span></div>'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-end;margin-top:4px">'
        f'<div><div class="loc">{_esc(loc)}</div>'
        f'<div class="coord">{a["lat"]:.4f}°N, {a["lon"]:.4f}°E</div></div>'
        f'<div class="metrics">Risk <em>{a["risk_score"]}</em>/100<br>'
        f'FRP <em>{frp}</em> MW &nbsp; Persist <em>{a["persistence_count"]}</em>x</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    if show_button:
        return st.button("Investigate  →", key=f"{key_prefix}_{a['alert_id']}",
                         use_container_width=True)
    return False


def result_card(card: dict, key: str = "rc") -> str | None:
    """Render an agent result card. Returns the action key if a button was pressed."""
    st.markdown(
        f'<div class="rc"><div class="rc-t">{_esc(card["title"])}</div>'
        f'<div class="rc-s">{_esc(card["subtitle"])}</div></div>',
        unsafe_allow_html=True,
    )
    acts = card.get("actions", [])
    if not acts:
        return None
    cols = st.columns(len(acts))
    labels = {"open_investigation": "Investigation", "show_on_map": "Show on Map",
              "generate_report": "Report"}
    pressed = None
    for col, act in zip(cols, acts):
        if col.button(labels.get(act, act), key=f"{key}_{act}", use_container_width=True):
            pressed = act
    return pressed


def empty_state(what: str, why: str = "", action: str = "") -> None:
    st.markdown(
        f'<div class="panel" style="text-align:center;padding:30px 16px">'
        f'<div style="font-size:12.5px;font-weight:600;color:{T.T1}">{_esc(what)}</div>'
        + (f'<div style="font-size:11px;color:{T.T2};margin-top:6px;line-height:1.6">{_esc(why)}</div>' if why else "")
        + (f'<div style="font-size:11px;color:{T.T2};margin-top:4px">{_esc(action)}</div>' if action else "")
        + '</div>',
        unsafe_allow_html=True,
    )
