"""
OPTIONAL Claude runtime for the Fire Intelligence Agent.

Active ONLY when ANTHROPIC_API_KEY is set and the `anthropic` package is
installed. It runs a tool-use loop over the SAME read-only tool registry as the
deterministic parser — it can do nothing the deterministic parser cannot.

The application does NOT depend on this module. Any import/availability failure
means the deterministic parser is used instead.
"""
from __future__ import annotations

import json
import os

from src.intelligence.agent import deterministic, response, tools
from src.intelligence.agent.response import AgentReply

_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
_MAX_TOOL_ROUNDS = 4

_SYSTEM = (
    "You are the Fire Intelligence Agent for the SIH26162 India Fire Intelligence "
    "Platform. You are READ-ONLY: you may query, rank, filter, summarise and "
    "prepare reports, but you must never claim to acknowledge, escalate, resolve "
    "or change any alert — those are manual operator actions. Answer only from the "
    "tool results. If data is unavailable, say so plainly; never invent values. "
    "Never claim a detection is a 'confirmed fire' — the platform detects "
    "anomalous departures from known thermal patterns that require human "
    "verification. Keep answers concise and operational."
)


def available() -> bool:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


def ask(message: str, context: dict | None = None) -> AgentReply | None:
    if not available():
        return None
    import anthropic

    client = anthropic.Anthropic()
    schemas = tools.anthropic_tool_schemas()
    msgs = [{"role": "user", "content": _with_context(message, context)}]
    last_tool = None
    last_result = None

    for _ in range(_MAX_TOOL_ROUNDS):
        resp = client.messages.create(
            model=_MODEL, max_tokens=1024, system=_SYSTEM,
            tools=schemas, messages=msgs,
        )
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            return _finalise(text, last_tool, last_result, message, context)

        msgs.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            if block.name not in tools.REGISTRY:
                payload = {"error": f"unknown/again read-only tool {block.name!r}"}
            else:
                try:
                    payload = tools.dispatch(block.name, dict(block.input or {}))
                    last_tool, last_result = block.name, payload
                except Exception as e:  # noqa: BLE001
                    payload = {"error": str(e)}
            tool_results.append({
                "type": "tool_result", "tool_use_id": block.id,
                "content": json.dumps(_truncate(payload))[:12000],
            })
        msgs.append({"role": "user", "content": tool_results})

    return _finalise("(Reached the tool-call limit.)", last_tool, last_result,
                     message, context)


def _finalise(text, tool_name, tool_result, message, context) -> AgentReply:
    # Reuse the deterministic formatter to build result cards + ui_action so the
    # Claude path drives the same UI state.
    interp = deterministic.parse(message, context)
    reply = response.build(interp, tool_result if tool_result is not None else None,
                           mode="claude")
    if text:
        reply.text = text
    reply.tool = tool_name or reply.tool
    return reply


def _with_context(message: str, context: dict | None) -> str:
    if not context:
        return message
    bits = []
    if context.get("page"):
        bits.append(f"current page: {context['page']}")
    if context.get("focus_alert_id"):
        bits.append(f"focused alert: {context['focus_alert_id']}")
    if context.get("filters"):
        bits.append(f"active filters: {json.dumps(context['filters'])}")
    return message + ("\n\n[" + "; ".join(bits) + "]" if bits else "")


def _truncate(obj, n=40):
    if isinstance(obj, list):
        return obj[:n]
    return obj
