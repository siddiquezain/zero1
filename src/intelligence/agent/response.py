"""
Turn a parsed Interpretation + tool result into an AgentReply
(natural-language text + result cards + a UI action).

Deterministic formatting — also used as the fallback formatter for the optional
Claude path.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.intelligence import queries
from src.intelligence.agent.deterministic import Interpretation


@dataclass
class AgentReply:
    text: str
    result_cards: list = field(default_factory=list)
    ui_action: dict = field(default_factory=dict)
    data: object = None
    mode: str = "deterministic"          # "deterministic" | "claude"
    tool: str | None = None
    note: str | None = None


_ACTIONS_FULL = ["open_investigation", "show_on_map", "generate_report"]


def _alert_card(a: dict, actions: list[str] | None = None) -> dict:
    loc = a.get("place") or a.get("state") or a.get("zone") \
          or f"{a['lat']:.3f}, {a['lon']:.3f}"
    sub = (f"{a['severity']} · Risk {a['risk_score']}/100 · "
           f"FRP {a['frp_mw'] if a['frp_mw'] is not None else '—'} MW · "
           f"Persist {a['persistence_count']}x · {a['acq_date']}")
    return {
        "title": f"{a['output_class_short']} — {loc}",
        "subtitle": sub,
        "alert_id": a["alert_id"],
        "lat": a["lat"], "lon": a["lon"],
        "severity": a["severity"],
        "actions": actions or _ACTIONS_FULL,
    }


def _fmt_int(n) -> str:
    return f"{int(n):,}"


def build(interp: Interpretation, result, mode: str = "deterministic") -> AgentReply:
    ui: dict = {}
    if interp.nav:
        ui["nav"] = interp.nav
    if interp.filters:
        ui["filters"] = interp.filters
    if interp.focus_alert_id:
        ui["focus_alert_id"] = interp.focus_alert_id

    reply = AgentReply(text="", ui_action=ui, data=result, mode=mode,
                       tool=interp.tool, note=interp.note)

    it = interp.intent

    if it == "empty":
        reply.text = "Ask me about alerts, risk, regions, facilities or reports — " \
                     "e.g. \"critical industrial fires in Odisha in the last 7 days\"."
        return reply

    if it == "refused_state_change":
        reply.text = (interp.note or
                      "I can't change alert state — that's a manual operator action.")
        if interp.focus_alert_id:
            a = queries.get_alert(interp.focus_alert_id)
            if a:
                reply.result_cards = [_alert_card(a, ["open_investigation"])]
        return reply

    if it == "help":
        s = result or queries.situation_summary()
        reply.text = (
            "I'm the Fire Intelligence Agent — a read-only, natural-language way to "
            "query this platform. Right now there are "
            f"**{_fmt_int(s['active'])} active alerts** "
            f"({s['severity']['CRITICAL']} critical, {s['severity']['HIGH']} high). "
            "Try: \"show critical industrial fires in Odisha\", "
            "\"highest-risk persistent sources near thermal power plants\", "
            "\"compare Odisha and Jharkhand\", or \"generate a report for high-risk "
            "incidents this week\"."
        )
        return reply

    if it == "summary":
        s = result
        if not s or s.get("total", 0) == 0:
            reply.text = "No alerts match that scope."
            return reply
        sev = s["severity"]; cls = s["classification"]
        scope = _scope_phrase(interp.filters)
        reply.text = (
            f"{_fmt_int(s['active'])} active alerts{scope} — "
            f"{sev['CRITICAL']} critical, {sev['HIGH']} high, {sev['MEDIUM']} medium, "
            f"{sev['LOW']} low. "
            f"By class: {cls['Industrial Fire']} industrial fire, "
            f"{cls['Persistent Source']} persistent source, "
            f"{cls['Natural Fire']} natural fire. "
            f"Detection window {s['data_window']['from']} to {s['data_window']['to']}."
        )
        if s.get("top_states"):
            top = ", ".join(f"{k} ({v})" for k, v in list(s["top_states"].items())[:3])
            reply.text += f" Most activity: {top}."
        return reply

    if it == "compare":
        c = result
        a, b = c["a"], c["b"]
        reply.text = (
            f"**{a['name']}**: {a['total']} alerts ({a['severity']['CRITICAL']} critical, "
            f"{a['severity']['HIGH']} high) · industrial fire {a['classification']['Industrial Fire']}, "
            f"persistent {a['classification']['Persistent Source']}, "
            f"natural {a['classification']['Natural Fire']}.\n\n"
            f"**{b['name']}**: {b['total']} alerts ({b['severity']['CRITICAL']} critical, "
            f"{b['severity']['HIGH']} high) · industrial fire {b['classification']['Industrial Fire']}, "
            f"persistent {b['classification']['Persistent Source']}, "
            f"natural {b['classification']['Natural Fire']}."
        )
        cards = []
        for side in (a, b):
            for t in side["top_alerts"][:1]:
                full = queries.get_alert(t["alert_id"])
                if full:
                    cards.append(_alert_card(full))
        reply.result_cards = cards
        return reply

    if it == "investigation":
        inv = result
        if not inv or not inv.get("found"):
            reply.text = ("I couldn't identify which alert you mean. Open an alert "
                          "from the feed or the map, then ask again.")
            return reply
        h = inv["header"]
        why = inv["why_flagged"]
        reply.text = (
            f"**{h['output_class_short']} near {h['location']}** — "
            f"risk {h['risk_score']}/100 ({h['severity']}), model class probability "
            f"{h['model_class_probability_pct']}%, status {h['status']}.\n\n"
            "Flagged because: " + ("; ".join(why) if why else "limited supporting signals") + ".\n\n"
            f"Recommended: **{inv['recommended_action']['action']}** — "
            f"{inv['recommended_action']['reason']}\n\n"
            f"_{inv['classification']['framing']}_"
        )
        a = queries.get_alert(inv["alert_id"])
        if a:
            reply.result_cards = [_alert_card(a, ["open_investigation", "show_on_map",
                                                  "generate_report"])]
        return reply

    if it == "facilities":
        facs = result or []
        if not facs:
            reply.text = "No known facilities have nearby detections for that scope."
            return reply
        top = facs[:5]
        lines = "; ".join(
            f"{f['name']} ({f['hazard_type']}, {f.get('state') or '—'}) — "
            f"{f['nearby_detections']} nearby, max risk {f['max_risk']}"
            for f in top
        )
        reply.text = (f"{len(facs)} facilit{'y' if len(facs)==1 else 'ies'} with nearby "
                      f"thermal activity{_scope_phrase(interp.filters)}. Top: {lines}.")
        return reply

    if it == "analytics":
        b = result
        if not b:
            reply.text = ("Not enough history for a baseline comparison — the FIRMS "
                          "NRT window is only a few days. (Honest 'insufficient data'.)")
            return reply
        reply.text = (
            f"Normal FRP band over {b['history_days']} prior day(s): "
            f"{b['baseline_low']}–{b['baseline_high']} MW (median {b['baseline_median']}). "
            f"Latest day ({b['current_date']}): median {b['current_median']} MW"
            + (f", {b['delta_pct']:+d}% vs baseline." if b['delta_pct'] is not None else ".")
        )
        return reply

    if it == "incidents":
        inc = result or []
        flagged = sum(1 for i in inc if i["anomaly_flag"])
        reply.text = (f"{len(inc)} curated confirmed Indian industrial incidents scored "
                      f"by the model; {flagged} flagged as anomalies "
                      f"(match neither learned pattern). These are an independent "
                      f"evaluation set, not training data.")
        return reply

    if it == "report":
        md = result if isinstance(result, str) else ""
        n = md.count("\n| ") - 1 if "| Rank |" in md else 0
        reply.text = (f"Incident report ready{_scope_phrase(interp.filters)} — "
                      f"{max(n,0)} alert(s). Open Reports / GIS to download it.")
        reply.ui_action.setdefault("nav", "Reports")
        return reply

    if it == "export":
        reply.text = (f"Export prepared{_scope_phrase(interp.filters)}. "
                      "Open Reports / GIS to download the file.")
        reply.ui_action.setdefault("nav", "Reports")
        return reply

    # rank / list
    alerts = result or []
    if not alerts:
        reply.text = f"No alerts match{_scope_phrase(interp.filters)}."
        return reply

    n = len(alerts)
    head = alerts[: (interp.limit or 3)]
    verb = "highest-risk" if interp.intent == "rank" else "matching"
    reply.text = f"Found {n} {verb} alert{'s' if n != 1 else ''}{_scope_phrase(interp.filters)}."
    if interp.explain_why:
        bits = []
        for a in head:
            inv = queries.get_investigation(a["alert_id"])
            why = inv.get("why_flagged", [])[:3]
            loc = a.get("place") or a.get("state") or a.get("zone")
            bits.append(f"**{loc or a['alert_id'][:6]}** (risk {a['risk_score']}): "
                        + ("; ".join(why) if why else "limited signals"))
        reply.text += "\n\n" + "\n\n".join(bits)
    reply.result_cards = [_alert_card(a) for a in head]
    return reply


def _scope_phrase(filters: dict | None) -> str:
    if not filters:
        return ""
    bits = []
    if filters.get("severity"):
        bits.append("/".join(filters["severity"]).lower())
    if filters.get("output_class"):
        bits.append(", ".join(str(c).lower() for c in filters["output_class"]))
    if filters.get("state"):
        st = filters["state"]
        bits.append("in " + (", ".join(st) if isinstance(st, list) else str(st)))
    if filters.get("region"):
        bits.append("in " + str(filters["region"]))
    if filters.get("near_facility_type"):
        bits.append("near " + str(filters["near_facility_type"]))
    if filters.get("date_from"):
        bits.append(f"{filters['date_from']}–{filters.get('date_to', '')}")
    return " " + " ".join(bits) if bits else ""
