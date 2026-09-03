"""
Fire Intelligence Agent panel — the natural-language interface.

Renders the supplied BB-8 robot GLB via <model-viewer> (self-hosted from
dashboard/static/, so it works offline) plus a compact chat. Read-only: the
agent applies filters / focus / navigation but never changes incident state.

Interaction model — explicit visual states:

    IDLE       collapsed card · robot completely static
    OPEN       expanded card (robot on top, conversation below) · robot static
    THINKING / ANSWERING
               question submitted, backend call in flight — a restrained scan
               sweep is drawn *around* the static robot and a spinner sits in the
               conversation. Both are gone the moment the reply lands.

The robot model is loaded once and never re-mounted; the processing visual is a
plain CSS overlay that Python shows only while `agent_pending` is set, so motion
can never outlive the response.
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
    "Show all critical and high alerts",
    "Which alerts have anomaly flags?",
    "Find persistent sources near thermal power plants",
    "Show industrial fire candidates in the last 3 days",
    "Compare eastern india and central india",
    "What is the system summary?",
    "Why is the highest-risk alert flagged?",
    "Generate report for high-risk incidents",
]

_MODEL_JS = "/app/static/model-viewer.min.js"
_MODEL_GLB = "/app/static/bb-8.glb"
_STAGE_H = 206

# minimum time the THINKING state stays visible so it reads even when the offline
# parser answers in milliseconds (the Claude path already exceeds this)
_THINK_FLOOR_S = 0.85

_ROBOT_HTML = f"""
<script src="{_MODEL_JS}"></script>
<style>
  html,body{{margin:0;padding:0;background:transparent;overflow:hidden;}}
  .stage{{position:relative;width:100%;max-width:360px;margin:0 auto;height:{_STAGE_H - 10}px;
    border-radius:8px;border:1px solid #1e2733;overflow:hidden;
    background:radial-gradient(circle at 50% 38%, #16202f 0%, #0b1119 72%);}}
  model-viewer{{width:100%;height:100%;--poster-color:transparent;--progress-bar-height:0px;
    transition:transform .2s ease, filter .2s ease;}}
  .stage:hover model-viewer{{transform:scale(1.018);filter:brightness(1.07) saturate(1.04);}}
</style>
<div class="stage">
  <model-viewer src="{_MODEL_GLB}" alt="Fire Intelligence Agent"
    interaction-prompt="none" disable-zoom disable-pan disable-tap
    loading="eager" reveal="auto" environment-image="neutral"
    exposure="1.12" shadow-intensity="0.7" shadow-softness="1"
    camera-orbit="12deg 82deg 3.4m" field-of-view="26deg"></model-viewer>
</div>
<script>
  const mv = document.querySelector('model-viewer');
  // freeze any clip baked into the GLB — the robot is an interface, not a mascot
  mv.addEventListener('load', () => {{ try {{ mv.pause(); }} catch (e) {{}} }});
</script>
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
    """Record the question and mark the busy phase; the work runs on the next run
    so the busy overlay is painted before the backend call blocks."""
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
    state.apply_ui_action(ua)          # filters + focus land immediately
    if reply.result_cards or nav:
        hist[-1]["pending_nav"] = nav  # navigation waits for a button


def _render_message(m: dict, scope: str, idx: int) -> None:
    if m["role"] == "user":
        st.markdown(f'<div class="agent-msg-user">{_html.escape(m["text"])}</div>',
                    unsafe_allow_html=True)
        return
    # Render **bold** as <strong> in the HTML output.
    # Substitute placeholders before html.escape so the tags survive escaping.
    raw = m["text"]
    raw = re.sub(r'\*\*([^*\n]+)\*\*', r'\x00BOLD\x00\1\x00ENDBOLD\x00', raw)
    body = _html.escape(raw)
    body = body.replace('\x00BOLD\x00', '<strong>').replace('\x00ENDBOLD\x00', '</strong>')
    body = body.replace("\n", "<br>")
    st.markdown(f'<div class="agent-msg-bot">{body}</div>', unsafe_allow_html=True)

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


def render(context: dict | None = None, *, scope: str = "dock",
           collapsible: bool = True) -> None:
    """Docked panel (`collapsible=True`) collapses to a compact card; the dialog
    (`collapsible=False`) is always open."""
    state.init()
    context = context or {}
    ss = st.session_state
    hist = ss["agent_history"]
    pending = ss.get("agent_pending")
    is_open = ss.get("agent_open", False) or not collapsible
    online = _agent_is_online()

    # ── header: name (docked only — the dialog has its own title) + status ─
    name = ('<span class="agent-h-name">Fire Intelligence Agent</span>'
            if collapsible else "<span></span>")
    if online:
        status_dot = '<i style="background:#3d7dc8;box-shadow:0 0 0 3px rgba(61,125,200,0.22)"></i>'
        status_label = "CLAUDE"
    else:
        status_dot = '<i style="background:#f59e0b;box-shadow:0 0 0 3px rgba(245,158,11,0.18)"></i>'
        status_label = "LOCAL"
    st.markdown(f'<div class="agent-head">{name}'
                f'<span class="agent-status">{status_dot}{status_label}</span></div>',
                unsafe_allow_html=True)

    # ── robot stage — model mounts once; the busy state is a CSS overlay ─
    with st.container(key=f"agentstage_{scope}"):
        st.components.v1.html(_ROBOT_HTML, height=_STAGE_H)
        if pending:
            st.markdown('<div class="agent-scan"><span>ANALYSING</span></div>',
                        unsafe_allow_html=True)

    from src.intelligence.agent.claude import _MODEL as _claude_model
    mode_note = f"Claude {_claude_model} · tool-use reasoning" if online else "Deterministic parser · offline mode"
    st.markdown(
        f'<div class="agent-note">{mode_note}'
        f' · read-only · same data as the dashboard</div>',
        unsafe_allow_html=True,
    )

    # ── collapse / expand ───────────────────────────────────────────────
    if collapsible:
        label = "Collapse  ▾" if is_open else "Open console  ▸"
        if st.button(label, key=f"{scope}_toggle", use_container_width=True):
            ss["agent_open"] = not is_open
            st.rerun()

    if not is_open:
        st.markdown('<div class="agent-tagline">Ask about alerts, risks, regions '
                    'or facilities.</div>', unsafe_allow_html=True)
        return

    # ── expanded: conversation directly below the robot ─────────────────
    st.markdown('<div class="agent-sep">Conversation</div>', unsafe_allow_html=True)

    if not hist:
        st.markdown('<div class="agent-msg-bot">I can query alerts, compare regions, '
                    'open investigations, focus the map and prepare reports — all '
                    'read-only. Try one of these:</div>', unsafe_allow_html=True)
        for i, ex in enumerate(_EXAMPLES):
            if st.button(ex, key=f"{scope}_ex_{i}", use_container_width=True):
                _queue(ex); st.rerun()
    else:
        for i, m in enumerate(hist[-14:]):
            _render_message(m, scope, i)

    # THINKING → ANSWERING. The scan overlay + spinner are already streamed to the
    # browser; the backend call runs inline so the user watches it work, then the
    # rerun clears the busy visual and renders the reply from history.
    if pending:
        ss["agent_pending"] = None
        with st.spinner("Analysing…"):
            _process(pending, context)
        st.rerun()

    prompt = st.chat_input("Ask about the fire data…", key=f"{scope}_input")
    if prompt:
        _queue(prompt); st.rerun()

    if hist and st.button("Clear conversation", key=f"{scope}_clear"):
        ss["agent_history"] = []
        st.rerun()

    st.markdown('<div class="agent-note">Cannot acknowledge / escalate / resolve — '
                'those stay with the operator. Verify important results.</div>',
                unsafe_allow_html=True)


@st.dialog("Fire Intelligence Agent", width="large")
def open_dialog(context: dict | None = None) -> None:
    render(context or {}, scope="dialog", collapsible=False)
