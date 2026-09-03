"""
Fire Intelligence Agent panel — the natural-language interface.

Renders the AI assistant robot illustration (dashboard/static/agent-bot.webp)
in a styled iframe stage, with CSS animations for idle / thinking states.
Read-only: the agent applies filters / focus / navigation but never changes
incident state.

Visual states
  IDLE       collapsed card · robot static, hover scale
  OPEN       expanded · robot static with subtle hover animation
  THINKING   query in-flight · robot bobs + pulsing glow ring + dot indicator
"""
from __future__ import annotations

import datetime as _dt
import html as _html
import re
import time as _time

import streamlit as st

from dashboard import data, state
from dashboard.components import ui

_EXAMPLES = [
    "Show all critical alerts",
    "Which events are increasing in risk?",
    "Find persistent sources near thermal power plants",
    "Show the highest-risk thermal events",
    "What is the situation summary?",
    "Compare eastern india and central india",
    "Show industrial fire candidates in the last 3 days",
    "Generate report for high-risk incidents",
]

_AGENT_IMG = "/app/static/agent-bot.webp"
_STAGE_H = 214
_THINK_FLOOR_S = 0.85


def _stage_html(thinking: bool = False) -> str:
    """Build the iframe HTML. Two CSS variants: idle (hover scale) and thinking (bob + glow)."""
    bob = "animation:agent-bob 1s ease-in-out infinite;" if thinking else "transition:transform .2s ease,filter .2s ease;"
    glow = "animation:pulse-glow 1.4s ease-in-out infinite;" if thinking else "box-shadow:0 4px 18px rgba(0,0,0,.38);"
    hover_rule = "" if thinking else ".stage:hover .bot-card img{transform:scale(1.05) translateY(-4px);filter:brightness(1.03);}"
    ring = '<div class="ring"></div>' if thinking else ""
    return f"""
<style>
  html,body{{margin:0;padding:0;background:transparent;overflow:hidden;}}
  .stage{{
    width:100%;height:{_STAGE_H}px;
    background:linear-gradient(165deg,#0e1828 0%,#0b1119 55%);
    border-radius:10px;border:1px solid #1e2733;
    display:flex;align-items:center;justify-content:center;
    position:relative;overflow:hidden;
  }}
  /* ambient bottom glow */
  .stage::after{{
    content:"";position:absolute;bottom:0;left:50%;transform:translateX(-50%);
    width:80%;height:50%;
    background:radial-gradient(ellipse,rgba(61,125,200,.09) 0%,transparent 70%);
    pointer-events:none;
  }}
  .bot-card{{
    position:relative;z-index:1;
    background:#fff;border-radius:10px;padding:6px 8px 2px;
    {glow}
  }}
  @keyframes pulse-glow{{
    0%,100%{{box-shadow:0 4px 18px rgba(0,0,0,.38),0 0 0 0 rgba(61,125,200,.55);}}
    50%{{box-shadow:0 4px 18px rgba(0,0,0,.38),0 0 0 14px rgba(61,125,200,0);}}
  }}
  .bot-card img{{height:{_STAGE_H - 38}px;width:auto;display:block;{bob}}}
  @keyframes agent-bob{{0%,100%{{transform:translateY(0);}}50%{{transform:translateY(-8px);}}}}
  {hover_rule}
  /* pulsing ring shown only while thinking */
  .ring{{
    position:absolute;inset:4px;border-radius:8px;pointer-events:none;
    border:1.5px solid rgba(61,125,200,.5);
    animation:ring-pulse 1.4s ease-in-out infinite;
  }}
  @keyframes ring-pulse{{0%,100%{{opacity:.9;}}50%{{opacity:.1;}}}}
</style>
<div class="stage">
  {ring}
  <div class="bot-card">
    <img src="{_AGENT_IMG}" alt="Fire Intelligence Agent">
  </div>
</div>
"""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=5, minutes=30))).strftime("%H:%M")


def _agent_is_online() -> bool:
    try:
        from src.intelligence.agent import runtime
        return runtime.claude_available()
    except Exception:
        return False


def _queue(msg: str) -> None:
    """Record user turn and mark busy. Work runs next rerun so the UI paints first."""
    st.session_state["agent_history"].append({"role": "user", "text": msg, "ts": _now()})
    st.session_state["agent_pending"] = msg


def _process(msg: str, context: dict) -> None:
    hist = st.session_state["agent_history"]
    t0 = _time.monotonic()
    reply = data.agent_ask(msg, context)
    left = _THINK_FLOOR_S - (_time.monotonic() - t0)
    if left > 0:
        _time.sleep(left)
    hist.append({
        "role": "bot", "text": reply.text, "ts": _now(),
        "cards": reply.result_cards, "ui_action": reply.ui_action,
        "mode": reply.mode, "note": reply.note,
    })
    ua = dict(reply.ui_action or {})
    nav = ua.pop("nav", None)
    state.apply_ui_action(ua)
    if reply.result_cards or nav:
        hist[-1]["pending_nav"] = nav


def _render_message(m: dict, scope: str, idx: int) -> None:
    if m["role"] == "user":
        st.markdown(
            f'<div class="agent-msg-user">'
            f'<span class="agent-msg-meta">You · {m.get("ts", "")}</span>'
            f'{_html.escape(m["text"])}'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    # Render **bold** preserving tags through html.escape
    raw = m["text"]
    raw = re.sub(r'\*\*([^*\n]+)\*\*', r'\x00BOLD\x00\1\x00ENDBOLD\x00', raw)
    body = _html.escape(raw)
    body = body.replace('\x00BOLD\x00', '<strong>').replace('\x00ENDBOLD\x00', '</strong>')
    body = body.replace("\n", "<br>")

    mode_icon = "🔷" if m.get("mode") == "claude" else "💡"
    st.markdown(
        f'<div class="agent-msg-bot">'
        f'<span class="agent-msg-meta">{mode_icon} Agent · {m.get("ts", "")}</span>'
        f'{body}'
        f'</div>',
        unsafe_allow_html=True,
    )

    for j, card in enumerate(m.get("cards", []) or []):
        act = ui.result_card(card, key=f"{scope}_{idx}_{j}")
        if act == "open_investigation":
            state.focus_alert(card.get("alert_id")); state.request_nav("Investigation"); st.rerun()
        elif act == "show_on_map":
            state.focus_alert(card.get("alert_id")); state.request_nav("Map Explorer"); st.rerun()
        elif act == "generate_report":
            state.request_nav("Reports / GIS"); st.rerun()

    pend = m.get("pending_nav")
    if pend:
        c1, c2 = st.columns(2)
        lbl = "Show on Map" if pend == "Map Explorer" else f"Open {pend}"
        if c1.button(lbl, key=f"{scope}_pn_{idx}", use_container_width=True):
            state.request_nav(pend); st.rerun()
        if c2.button("View Alerts", key=f"{scope}_pn2_{idx}", use_container_width=True):
            state.request_nav("Alerts"); st.rerun()


def _thinking_dots() -> None:
    """Animated dot indicator shown below the stage while a query is in flight."""
    st.markdown(
        '<div class="agent-thinking">'
        '<span class="agent-dot"></span>'
        '<span class="agent-dot"></span>'
        '<span class="agent-dot"></span>'
        '<span class="agent-thinking-label">ANALYSING</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def render(context: dict | None = None, *, scope: str = "dock",
           collapsible: bool = True) -> None:
    """Docked panel (collapsible=True) collapses to compact card; dialog always expanded."""
    state.init()
    context = context or {}
    ss = st.session_state
    hist = ss["agent_history"]
    pending = ss.get("agent_pending")
    is_open = ss.get("agent_open", False) or not collapsible
    online = _agent_is_online()

    # ── header: name + status pill ─────────────────────────────────────────
    name = ('<span class="agent-h-name">Fire Intelligence Agent</span>'
            if collapsible else "<span></span>")
    if online:
        dot = '<i style="background:#3d7dc8;box-shadow:0 0 0 3px rgba(61,125,200,0.22)"></i>'
        label = "CLAUDE"
    else:
        dot = '<i style="background:#f59e0b;box-shadow:0 0 0 3px rgba(245,158,11,0.18)"></i>'
        label = "LOCAL"
    st.markdown(
        f'<div class="agent-head">{name}<span class="agent-status">{dot}{label}</span></div>',
        unsafe_allow_html=True,
    )

    # ── robot stage — renders fresh HTML; lightweight image re-mounts instantly ──
    st.components.v1.html(_stage_html(thinking=bool(pending)), height=_STAGE_H)
    if pending:
        _thinking_dots()

    from src.intelligence.agent.claude import _MODEL as _claude_model
    mode_note = f"Claude {_claude_model} · tool-use" if online else "Deterministic parser · offline"
    st.markdown(
        f'<div class="agent-note">{mode_note} · read-only · same data as dashboard</div>',
        unsafe_allow_html=True,
    )

    # ── collapse / expand ──────────────────────────────────────────────────
    if collapsible:
        label_btn = "Collapse  ▾" if is_open else "Open console  ▸"
        if st.button(label_btn, key=f"{scope}_toggle", use_container_width=True):
            ss["agent_open"] = not is_open
            st.rerun()

    if not is_open:
        st.markdown(
            '<div class="agent-tagline">Ask about alerts, events, risks, regions or facilities.</div>',
            unsafe_allow_html=True,
        )
        return

    # ── expanded: conversation ─────────────────────────────────────────────
    st.markdown('<div class="agent-sep">Conversation</div>', unsafe_allow_html=True)

    if not hist:
        st.markdown(
            '<div class="agent-msg-bot">I can query alerts and thermal events, compare '
            'regions, explain risk trajectories, open investigations, and prepare reports '
            '— all read-only. Try one of these:</div>',
            unsafe_allow_html=True,
        )
        with st.container(key=f"agent_chips_{scope}"):
            for i, ex in enumerate(_EXAMPLES):
                if st.button(ex, key=f"{scope}_ex_{i}", use_container_width=True):
                    _queue(ex); st.rerun()
    else:
        for i, m in enumerate(hist[-14:]):
            _render_message(m, scope, i)

    # THINKING → process inline; spinner visible to user while backend call runs
    if pending:
        ss["agent_pending"] = None
        with st.spinner("Analysing…"):
            _process(pending, context)
        st.rerun()

    prompt = st.chat_input("Ask about fire data, events, risks…", key=f"{scope}_input")
    if prompt:
        _queue(prompt); st.rerun()

    if hist:
        _, clr_col = st.columns([4, 1])
        with clr_col:
            if st.button("Clear", key=f"{scope}_clear", use_container_width=True):
                ss["agent_history"] = []
                st.rerun()

    st.markdown(
        '<div class="agent-note">Cannot acknowledge / escalate / resolve — '
        'those stay with the operator. Verify important results.</div>',
        unsafe_allow_html=True,
    )


@st.dialog("Fire Intelligence Agent", width="large")
def open_dialog(context: dict | None = None) -> None:
    render(context or {}, scope="dialog", collapsible=False)
