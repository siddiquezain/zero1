"""
Agent runtime — picks the runtime and returns an AgentReply.

    ANTHROPIC_API_KEY set + `anthropic` importable  ->  Claude tool-use loop
    otherwise (the default, guaranteed)             ->  deterministic parser

Both use the SAME read-only tool registry (src/intelligence/agent/tools.py).
Any failure in the Claude path falls back to the deterministic parser.
"""
from __future__ import annotations

import os

from src.intelligence.agent import deterministic, response, tools
from src.intelligence.agent.response import AgentReply


def _deterministic(message: str, context: dict | None) -> AgentReply:
    interp = deterministic.parse(message, context)
    if not interp.understood or interp.tool is None:
        if interp.intent == "refused_state_change":
            return response.build(interp, None, mode="deterministic")
        if interp.tool is None and interp.intent not in ("empty",):
            hint = AgentReply(
                text=("I didn't catch a query I can run. Try naming a severity, a "
                      "class (industrial fire / persistent source / natural fire), "
                      "a state, or a timeframe — e.g. \"critical persistent sources "
                      "in Jharkhand this week\"."),
                mode="deterministic",
            )
            return hint
        return response.build(interp, None, mode="deterministic")
    try:
        result = tools.dispatch(interp.tool, interp.args)
    except Exception as e:  # noqa: BLE001 — never crash the panel
        return AgentReply(text=f"Query failed: {e}", mode="deterministic",
                          tool=interp.tool)
    return response.build(interp, result, mode="deterministic")


def claude_available() -> bool:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False
    try:
        from src.intelligence.agent import claude  # noqa: F401
        return claude.available()
    except Exception:
        return False


def ask(message: str, context: dict | None = None) -> AgentReply:
    """Answer a natural-language question. Read-only. Never raises."""
    context = context or {}
    if claude_available():
        try:
            from src.intelligence.agent import claude
            reply = claude.ask(message, context)
            if reply is not None:
                return reply
        except Exception:
            pass  # fall through to deterministic
    return _deterministic(message, context)
