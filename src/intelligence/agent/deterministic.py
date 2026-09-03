"""
Deterministic natural-language parser — the guaranteed offline baseline.

No API key, no network. Keyword + regex intent/entity extraction that maps a
message to one read-only tool call from src/intelligence/agent/tools.py plus an
optional UI action (navigate / apply filters / focus an alert).

Covers every documented example query in context.md (§13, §17) and the reference
UI's example prompts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.intelligence import geo, queries

# ── vocab ───────────────────────────────────────────────────────────────────
_SEVERITY_WORDS = {
    "critical": "CRITICAL", "criticals": "CRITICAL",
    "high": "HIGH", "high-risk": "HIGH", "high risk": "HIGH",
    "medium": "MEDIUM", "moderate": "MEDIUM",
    "low": "LOW",
}
_CLASS_WORDS = [
    (("industrial fire", "industrial fires", "abnormal thermal", "industrial-fire"),
     "Industrial Fire"),
    (("persistent source", "persistent sources", "persistent thermal", "persistent industrial",
      "flare", "flares", "gas flare"), "Persistent Source"),
    (("natural fire", "natural fires", "forest fire", "wildfire", "agricultural fire",
      "crop", "stubble"), "Natural Fire"),
]
_FACILITY_KEYWORDS = [
    "thermal power plant", "thermal power", "power plant", "power station",
    "refinery", "petrochemical", "oil refinery",
    "steel plant", "steel", "smelter", "metal",
    "chemical plant", "chemical", "pharma", "pharmaceutical",
    "coal mine", "mine", "mining", "colliery", "coalfield",
    "brick kiln", "kiln", "cement",
    "lng", "gas terminal",
]
_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
              "seven": 7, "eight": 8, "nine": 9, "ten": 10, "a": 1, "an": 1}
_STOPWORDS_FOR_NAME = {
    "the", "a", "an", "alert", "alerts", "incident", "incidents", "this", "that",
    "detection", "fire", "in", "at", "near", "of", "on", "for", "is", "was",
    "critical", "high", "medium", "low", "industrial", "persistent", "natural",
    "why", "show", "me", "open", "investigate", "investigation",
}


@dataclass
class Interpretation:
    understood: bool
    tool: str | None = None
    args: dict = field(default_factory=dict)
    filters: dict = field(default_factory=dict)
    nav: str | None = None            # target page for the UI
    focus_alert_id: str | None = None
    limit: int | None = None
    intent: str = "unknown"
    explain_why: bool = False         # attach 'why flagged' to the answer
    message: str = ""
    note: str | None = None           # e.g. a read-only refusal explanation


# ── helpers ─────────────────────────────────────────────────────────────────
def _severities(text: str) -> list[str]:
    found = []
    for w, canon in _SEVERITY_WORDS.items():
        if re.search(rf"\b{re.escape(w)}\b", text):
            if canon not in found:
                found.append(canon)
    return found


def _classes(text: str) -> list[str]:
    out = []
    for keys, canon in _CLASS_WORDS:
        if any(k in text for k in keys):
            out.append(canon)
    return out


def _facility_type(text: str) -> str | None:
    for kw in _FACILITY_KEYWORDS:
        if kw in text:
            return kw
    return None


_PLURAL_HINT = re.compile(r"\b(alerts|incidents|sources|fires|detections|hotspots|ones|"
                          r"which .* (have|are))\b")
_SINGULAR_HINT = re.compile(r"\b(the highest|what is the|which is the|single|"
                            r"top one|#?1|one incident|one alert)\b")


def _limit(text: str) -> int | None:
    m = re.search(r"\b(?:top|first|highest|best)\s+(\d+)\b", text)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(\d+)\s+(?:highest|top|most|biggest)\b", text)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(?:the\s+)?(one|two|three|four|five|six|seven|eight|nine|ten)\s+"
                  r"(?:highest|top|most|biggest|largest)\b", text)
    if m:
        return _NUM_WORDS[m.group(1)]
    if re.search(r"\bhighest[- ]risk\b|\btop\b|\bmost (?:severe|critical|risky|dangerous)\b"
                 r"|\brank\b|\bworst\b", text):
        if _SINGULAR_HINT.search(text) and not _PLURAL_HINT.search(text):
            return 1
        return 5
    return None


def _rank_metric(text: str) -> str:
    if "frp" in text or "radiative" in text or "intense" in text or "intensity" in text:
        return "frp_mw"
    if "persistent" in text and ("most" in text or "highest" in text):
        return "persistence_count"
    if "recent" in text or "latest" in text or "newest" in text:
        return "recent"
    return "risk_score"


def _timeframe(text: str) -> tuple[str | None, str | None]:
    for pat in (r"last\s+\d+\s*(?:days?|weeks?|d|w)", r"past\s+\d+\s*(?:days?|weeks?)",
                r"this week", r"last week", r"today", r"yesterday",
                r"all time", r"everything"):
        m = re.search(pat, text)
        if m:
            return queries.resolve_timeframe(m.group(0))
    return None, None


def _location_filters(text: str) -> dict:
    loc = geo.match_locations(text)
    out: dict = {}
    if loc["region"]:
        out["region"] = loc["region"]
    named_states = {s for s in loc["states"]
                    if not (loc["region"] and s in geo.states_in_region(loc["region"]))}
    if named_states:
        out["state"] = sorted(named_states)
    return out


def _guess_alert_by_place(text: str):
    """For 'why is the Surat alert critical' — find the top alert at that place."""
    loc = geo.match_locations(text)
    f: dict = {}
    if loc["region"]:
        f["region"] = loc["region"]
    if loc["states"]:
        f["state"] = sorted(loc["states"])
    # also try a bare city token
    if not f:
        tokens = [t for t in re.findall(r"[a-z]+", text) if t not in _STOPWORDS_FOR_NAME]
        for t in tokens:
            hits = queries.list_alerts({"search": t}, limit=1)
            if hits:
                return hits[0]["alert_id"]
        return None
    hits = queries.list_alerts(f, limit=1, sort_by="risk_score")
    return hits[0]["alert_id"] if hits else None


def _build_filters(text: str) -> dict:
    f: dict = {}
    sev = _severities(text)
    if sev:
        f["severity"] = sev
    cls = _classes(text)
    if cls:
        f["output_class"] = cls
    f.update(_location_filters(text))
    df, dt = _timeframe(text)
    if df:
        f["date_from"] = df
    if dt:
        f["date_to"] = dt
    ft = _facility_type(text)
    if ft and ("near" in text or "close to" in text or "around" in text):
        f["near_facility_type"] = ft
    if re.search(r"\b(close to|near|next to|beside|around)\b.*\b(industrial |"
                 r")facilit", text) or "close to industrial" in text:
        f.setdefault("max_dist_facility_km", 10.0)
    if "close to" in text:
        f["max_dist_facility_km"] = 5.0
    if re.search(r"\bactive\b", text):
        f["status"] = ["DETECTED", "VALIDATING", "ALERTED", "ESCALATED", "MONITORING"]
    return f


# ── main entry ──────────────────────────────────────────────────────────────
def parse(message: str, context: dict | None = None) -> Interpretation:
    context = context or {}
    raw = message or ""
    text = " ".join(raw.lower().split())
    I = Interpretation(understood=True, message=raw)

    if not text:
        return Interpretation(understood=False, message=raw, intent="empty")

    # --- refuse state changes (read-only) ---
    if re.search(r"\b(acknowledge|escalate|resolve|dismiss|delete|assign)\b"
                 r"|\bclose (?:this|the|out|it|that|alert|incident)\b"
                 r"|\bmark (?:as|this|it)\b|\bset (?:the )?status\b|\bchange (?:the )?status\b",
                 text):
        I.understood = True
        I.intent = "refused_state_change"
        I.tool = None
        # still try to open the relevant investigation so the human can act
        aid = context.get("focus_alert_id") or _guess_alert_by_place(text)
        if not aid:
            top = queries.rank_alerts("risk_score", _build_filters(text), limit=1)
            aid = top[0]["alert_id"] if top else None
        if aid:
            I.focus_alert_id = aid
            I.nav = "Investigation"
        I.note = ("The agent is read-only. Acknowledge / Escalate / Resolve are "
                  "done from the alert's manual controls — opening it for you.")
        return I

    # --- greeting / help / capability ---
    if re.fullmatch(r"(hi|hello|hey|yo|help|what can you do\??|\?)", text) or \
       ("what can you" in text and "do" in text):
        I.understood = True
        I.intent = "help"
        I.tool = "situation_summary"
        return I

    # ── EVENT INTENTS ─────────────────────────────────────────────────────────
    import re as _re
    _event_id_match = _re.search(r'\bevent\s+([0-9a-f]{8})\b', text, _re.I)
    _eid = _event_id_match.group(1).lower() if _event_id_match else None

    if _eid:
        if any(kw in text for kw in ("fingerprint", "behaviour", "behavior", "signature")):
            return Interpretation(understood=True, tool="get_event_fingerprint",
                                  args={"event_id": _eid}, intent="event_fingerprint",
                                  message=f"Fetching behaviour fingerprint for event {_eid}.")
        if any(kw in text for kw in ("deviation", "deviate", "baseline", "unusual",
                                     "abnormal", "vs normal", "compared to normal")):
            return Interpretation(understood=True, tool="get_event_deviation",
                                  args={"event_id": _eid}, intent="event_deviation",
                                  message=f"Comparing event {_eid} with its facility baseline.")
        if any(kw in text for kw in ("evidence", "why", "reason", "because", "support")):
            return Interpretation(understood=True, tool="get_event_evidence",
                                  args={"event_id": _eid}, intent="event_evidence",
                                  message=f"Fetching evidence stack for event {_eid}.")
        if any(kw in text for kw in ("evolv", "evolution", "timeline", "history")):
            return Interpretation(understood=True, tool="get_event_evolution",
                                  args={"event_id": _eid}, intent="event_evolution",
                                  message=f"Fetching evolution timeline for event {_eid}.")
        if any(kw in text for kw in ("replay", "play", "animate")):
            return Interpretation(understood=True, tool="get_event_evolution",
                                  args={"event_id": _eid}, intent="event_replay",
                                  nav="Investigation",
                                  message=f"Loading event replay for event {_eid}.")
        if any(kw in text for kw in ("trajector", "risk trend", "increasing", "warning")):
            return Interpretation(understood=True, tool="get_event_trajectory",
                                  args={"event_id": _eid}, intent="event_trajectory",
                                  message=f"Computing risk trajectory for event {_eid}.")
        # Default for bare event ID mention → event detail
        return Interpretation(understood=True, tool="get_event",
                              args={"event_id": _eid}, intent="event_detail",
                              nav="Investigation",
                              message=f"Fetching details for event {_eid}.")

    # ── Event list intents ────────────────────────────────────────────────────
    _is_event_list = any(kw in text for kw in (
        "event", "events", "thermal event", "thermal events", "cluster", "clusters"
    ))
    if _is_event_list and any(kw in text for kw in ("increasing", "rising", "growing")):
        return Interpretation(understood=True, tool="find_increasing_risk_events",
                              args={"limit": 10}, intent="event_trajectory",
                              message="Finding thermal events with increasing risk trajectory.")

    if _is_event_list:
        _ev_filters: dict = {}
        for sev in ("critical", "high", "medium", "low"):
            if sev in text:
                _ev_filters["severity"] = [sev.upper()]
                break
        for token in text.replace(",", " ").split():
            cs = geo.canonical_state(token.title())
            if cs:
                _ev_filters["state"] = cs
                break
        return Interpretation(understood=True, tool="list_events",
                              args={"filters": _ev_filters or None, "limit": 20},
                              intent="event_list",
                              filters=_ev_filters or None,
                              message="Listing thermal events by risk score.")

    lim = _limit(text)
    wants_why = bool(re.search(r"\bwhy\b|\bexplain\b", text))
    is_ranking = lim is not None or bool(
        re.search(r"\bhighest\b|\btop\b|\brank\b|\bworst\b|\bmost (risky|severe|"
                  r"dangerous|critical|intense)\b", text))
    plural_subject = bool(_PLURAL_HINT.search(text)) or bool(_classes(text))

    # --- why was this ONE alert flagged / classified ---
    if wants_why and re.search(
            r"\b(flag|flagged|classif|critical|risk|matter|alert|industrial fire|"
            r"anomal)\b", text) and not (is_ranking and plural_subject):
        aid = context.get("focus_alert_id")
        if aid is None or re.search(r"\bthe .* alert\b|\bthis (alert|incident|one)\b", text) \
                or geo.match_locations(text)["states"] or geo.match_locations(text)["region"]:
            aid = _guess_alert_by_place(text) or aid
        if aid is None:
            top = queries.rank_alerts("risk_score", _build_filters(text), limit=1)
            aid = top[0]["alert_id"] if top else None
        I.intent = "investigation"
        I.tool = "get_investigation"
        I.args = {"alert_id": aid} if aid else {}
        I.focus_alert_id = aid
        I.nav = "Investigation" if aid else None
        I.explain_why = True
        return I

    # --- compare regions ---
    m = re.search(r"compare\s+([a-z .]+?)\s+(?:and|vs|versus|with|to)\s+([a-z .]+)", text)
    if m:
        a = _clean_place(m.group(1)); b = _clean_place(m.group(2))
        I.intent = "compare"
        I.tool = "compare_regions"
        I.args = {"region_a": a, "region_b": b}
        return I

    # --- generate report ---
    if re.search(r"\b(generate|create|build|make|prepare)\b.*\breport\b|\breport for\b|"
                 r"\bincident report\b", text):
        I.intent = "report"
        I.tool = "build_incident_report"
        I.filters = _build_filters(text)
        I.args = {"filters": I.filters}
        I.nav = "Reports"
        return I

    # --- export ---
    if re.search(r"\bexport\b|\bdownload\b|\bgeojson\b|\bshapefile\b|\bcsv\b", text):
        fmt_geo = "geojson" in text or "shapefile" in text or "gis" in text
        I.intent = "export"
        I.tool = "export_geojson" if fmt_geo or "csv" not in text else "export_csv"
        I.filters = _build_filters(text)
        I.args = {"filters": I.filters}
        I.nav = "Reports"
        return I

    # --- facility thermal fingerprinting (baseline / deviation) ---
    if "facilit" in text and re.search(
            r"\babnormal\b|deviat|\bunusual\b|behaving", text):
        if re.search(r"\brank\b|\bsort\b|\border\b|by deviat|highest deviat", text):
            I.intent = "rank_facility_deviation"
            I.tool = "rank_facilities_by_deviation"
        else:
            I.intent = "abnormal_facilities"
            I.tool = "find_abnormal_facilities"
        I.args = {"limit": lim or 10}
        I.nav = "Facilities"
        return I
    if "facilit" in text and re.search(r"\bbaseline\b|\bfingerprint\b|\bthermal profile\b", text):
        I.intent = "fp_summary"
        I.tool = "facility_fingerprint_summary"
        I.nav = "Analytics"
        return I

    # --- facilities (subject is the facilities themselves) ---
    if ("facilit" in text or "infrastructure" in text) and \
            not re.search(r"\b(alerts?|incidents?|detections?|hotspots?|sources?|fires?)\b",
                          text):
        I.intent = "facilities"
        I.tool = "facilities_with_activity"
        I.filters = _build_filters(text)
        I.filters.pop("max_dist_facility_km", None)
        I.filters.pop("near_facility_type", None)
        I.args = {"filters": I.filters, "limit": lim or 40}
        I.nav = "Facilities"
        return I

    # --- ranking (highest risk / top N [near a facility type]) ---
    if is_ranking:
        I.intent = "rank"
        I.tool = "rank_alerts"
        I.filters = _build_filters(text)
        # "highest-risk" / "high-risk" is the ranking metric, not a severity filter
        if I.filters.get("severity") == ["HIGH"] and re.search(
                r"\bhighest[- ]risk\b|\bhigh[- ]risk\b", text) \
                and not re.search(r"\bhigh[- ](severity|priority)\b", text):
            I.filters.pop("severity", None)
        metric = _rank_metric(text)
        I.args = {"by": metric, "filters": I.filters, "limit": lim or 5}
        I.limit = lim or 5
        I.nav = "Map" if "map" in text else "Alerts"
        I.explain_why = wants_why
        return I

    # --- baseline / trend ---
    if re.search(r"\bbaseline\b|\bvs normal\b|\bcompared to normal\b|\banomal(y|ous) (level|amount)\b"
                 r"|\btrend\b|\bover time\b", text):
        I.intent = "analytics"
        I.tool = "baseline_comparison"
        I.filters = _build_filters(text)
        I.args = {"filters": I.filters}
        I.nav = "Analytics"
        return I

    # --- how many / count / situation summary ---
    if re.search(r"\bhow many\b|\bcount\b|\bnumber of\b|\bsummar(y|ise|ize)\b|"
                 r"\bsituation\b|\boverview\b|\bstatus\b", text):
        I.intent = "summary"
        I.tool = "situation_summary"
        I.filters = _build_filters(text)
        I.args = {"filters": I.filters}
        return I

    # --- incidents list ---
    if re.search(r"\bconfirmed incidents?\b|\b30 incidents?\b|\bhistorical incidents?\b", text):
        I.intent = "incidents"
        I.tool = "incidents"
        return I

    # --- default: list / filter alerts ---
    I.intent = "list"
    I.tool = "list_alerts"
    I.filters = _build_filters(text)
    I.args = {"filters": I.filters, "limit": _limit(text) or 25,
              "sort_by": _rank_metric(text)}
    if "map" in text:
        I.nav = "Map"
    elif I.filters:
        I.nav = "Alerts"
    I.explain_why = "explain" in text or "why" in text

    # if nothing at all was extracted, mark as low-confidence
    if not I.filters and not re.search(r"\b(alert|fire|source|detection|hotspot|thermal|"
                                       r"show|list|find)\b", text):
        I.understood = False
        I.intent = "unknown"
    return I


def _clean_place(s: str) -> str:
    s = re.sub(r"\b(alerts?|incidents?|fires?|region|state|the|situation|data)\b", "", s)
    return " ".join(s.split()).strip(" .,")


# alias for test compatibility
interpret = parse
