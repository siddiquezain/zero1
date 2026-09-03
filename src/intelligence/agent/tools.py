"""
The agent's READ-ONLY tool registry.

Every tool maps 1:1 to a function in src/intelligence/queries.py or the read-only
exporters in src/intelligence/actions.py. There is no state-changing tool here —
by construction the agent (deterministic OR Claude) cannot change anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.intelligence import actions, queries


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    fn: Callable
    parameters: dict  # JSON-schema-style {name: {"type","description"}}


_FILTERS_PARAM = {
    "type": "object",
    "description": "Optional filters: severity[], status[], output_class[], "
                   "state, region, date_from, date_to, near_facility_type, "
                   "max_dist_facility_km, min_risk, search",
}

REGISTRY: dict[str, Tool] = {}


def _reg(t: Tool) -> None:
    REGISTRY[t.name] = t


_reg(Tool("list_alerts",
          "List / filter alerts (detections). Returns alert rows sorted by the "
          "chosen metric.",
          lambda filters=None, limit=25, sort_by="risk_score":
              queries.list_alerts(filters, limit=limit, sort_by=sort_by),
          {"filters": _FILTERS_PARAM,
           "limit": {"type": "integer"},
           "sort_by": {"type": "string",
                       "enum": ["risk_score", "frp_mw", "persistence_count", "recent",
                                "severity"]}}))

_reg(Tool("rank_alerts",
          "Return the top-N alerts by a metric (default risk_score).",
          lambda by="risk_score", filters=None, limit=5:
              queries.rank_alerts(by=by, filters=filters, limit=limit),
          {"by": {"type": "string"}, "filters": _FILTERS_PARAM,
           "limit": {"type": "integer"}}))

_reg(Tool("get_alert", "Get a single alert by id.",
          lambda alert_id: queries.get_alert(alert_id),
          {"alert_id": {"type": "string"}}))

_reg(Tool("get_investigation",
          "Full assembled investigation for one alert: detection, context, "
          "why-flagged, classification, risk factors, recommended action.",
          lambda alert_id: queries.get_investigation(alert_id),
          {"alert_id": {"type": "string"}}))

_reg(Tool("situation_summary",
          "High-level counts: active alerts, severity breakdown, classification "
          "breakdown, top states. Accepts filters (e.g. region).",
          lambda filters=None: queries.situation_summary(filters),
          {"filters": _FILTERS_PARAM}))

_reg(Tool("compare_regions",
          "Side-by-side comparison of two states or regions.",
          lambda region_a, region_b, filters=None:
              queries.compare_regions(region_a, region_b, filters),
          {"region_a": {"type": "string"}, "region_b": {"type": "string"},
           "filters": _FILTERS_PARAM}))

_reg(Tool("facilities_with_activity",
          "Known Indian industrial facilities that have nearby thermal "
          "detections, with detection counts and max risk.",
          lambda filters=None, limit=40, radius_km=10.0:
              queries.facilities_with_activity(filters, limit=limit, radius_km=radius_km),
          {"filters": _FILTERS_PARAM, "limit": {"type": "integer"},
           "radius_km": {"type": "number"}}))

_reg(Tool("analytics_summary",
          "Daily activity + classification / severity / land-cover breakdowns "
          "for a date range.",
          lambda date_from=None, date_to=None:
              queries.analytics_summary(date_from, date_to),
          {"date_from": {"type": "string"}, "date_to": {"type": "string"}}))

_reg(Tool("baseline_comparison",
          "Normal FRP band vs the latest day. Returns null when history is "
          "insufficient (honest 'not available').",
          lambda filters=None: queries.baseline_comparison(filters),
          {"filters": _FILTERS_PARAM}))

_reg(Tool("incidents",
          "The 30 curated confirmed Indian industrial incidents scored by the model.",
          lambda: queries.incidents(), {}))

_reg(Tool("build_incident_report",
          "Build a read-only Markdown incident report for the filtered alerts.",
          lambda filters=None, fmt="markdown":
              actions.build_incident_report(filters, fmt=fmt),
          {"filters": _FILTERS_PARAM, "fmt": {"type": "string",
                                              "enum": ["markdown", "csv"]}}))

_reg(Tool("export_geojson", "Export filtered alerts as GeoJSON (string).",
          lambda filters=None: actions.export_geojson(filters),
          {"filters": _FILTERS_PARAM}))

_reg(Tool("export_csv", "Export filtered alerts as CSV (string).",
          lambda filters=None: actions.export_csv(filters),
          {"filters": _FILTERS_PARAM}))


_reg(Tool("list_events",
          "List thermal events (clustered groups of nearby detections). "
          "Returns events sorted by risk_score by default.",
          lambda filters=None, sort_by="risk_score", limit=20:
              queries.list_events(filters, sort_by=sort_by, limit=limit),
          {"filters": _FILTERS_PARAM,
           "sort_by": {"type": "string", "enum": ["risk_score", "frp_mw"]},
           "limit": {"type": "integer"}}))

_reg(Tool("get_event",
          "Get full details of a single thermal event by event_id.",
          lambda event_id: queries.get_event(event_id),
          {"event_id": {"type": "string"}}))

_reg(Tool("get_event_fingerprint",
          "Behavioural fingerprint for a thermal event: persistence, night activity, "
          "FRP intensity, spatial stability, industrial proximity, seasonal alignment.",
          lambda event_id: queries.get_event_fingerprint(event_id),
          {"event_id": {"type": "string"}}))

_reg(Tool("get_event_evidence",
          "Structured evidence stack for a thermal event: supporting and limiting "
          "evidence items with categories, values, and explanations.",
          lambda event_id: queries.get_event_evidence(event_id),
          {"event_id": {"type": "string"}}))

_reg(Tool("get_event_evolution",
          "Ordered timeline and frame sequence for event evolution replay.",
          lambda event_id: queries.get_event_evolution(event_id),
          {"event_id": {"type": "string"}}))

_reg(Tool("get_event_trajectory",
          "Risk trajectory for a thermal event. Returns state (STABLE / WATCH / "
          "INCREASING / EARLY WARNING / HIGH PRIORITY), delta, and signals.",
          lambda event_id: queries.get_event_trajectory(event_id),
          {"event_id": {"type": "string"}}))

_reg(Tool("find_increasing_risk_events",
          "Find thermal events whose risk trajectory is INCREASING.",
          lambda limit=10: queries.find_increasing_risk_events(limit=limit),
          {"limit": {"type": "integer"}}))

_reg(Tool("events_situation",
          "Summary counts: total events, high-risk, persistent sources, early warnings.",
          lambda: queries.events_situation(), {}))


# ── facility thermal fingerprinting (read-only) ─────────────────────────────
_reg(Tool("get_facility_fingerprint",
          "Facility thermal baseline: typical FRP / brightness temperature / "
          "persistence / day-night profile over the observed window, or "
          "INSUFFICIENT_BASELINE when history is too thin.",
          lambda facility_id, exclude_event_id=None:
              queries.get_facility_fingerprint(facility_id, exclude_event_id),
          {"facility_id": {"type": "string"},
           "exclude_event_id": {"type": "string"}}))

_reg(Tool("get_event_deviation",
          "How far a thermal event departs from its nearest facility's baseline: "
          "thermal_deviation_score (0-100), level (NORMAL / ELEVATED / ABNORMAL / "
          "HIGHLY_ABNORMAL), and deterministic evidence. Separate from risk_score "
          "and model probability.",
          lambda event_id: queries.get_event_deviation(event_id),
          {"event_id": {"type": "string"}}))

_reg(Tool("rank_facilities_by_deviation",
          "Facilities ranked by the deviation of their most unusual current event "
          "vs their own thermal baseline.",
          lambda limit=10: queries.rank_facilities_by_deviation(limit=limit),
          {"limit": {"type": "integer"}}))

_reg(Tool("find_abnormal_facilities",
          "Facilities whose current thermal behaviour is ABNORMAL or "
          "HIGHLY_ABNORMAL vs their baseline.",
          lambda limit=10, min_level="ABNORMAL":
              queries.find_abnormal_facilities(limit=limit, min_level=min_level),
          {"limit": {"type": "integer"}, "min_level": {"type": "string"}}))

_reg(Tool("facility_fingerprint_summary",
          "Counts: facilities with activity, baselines available, insufficient "
          "baselines, events assessed, abnormal events, by-level breakdown.",
          lambda: queries.facility_fingerprint_summary(), {}))


READ_ONLY_TOOL_NAMES = tuple(REGISTRY.keys())


def dispatch(name: str, args: dict | None = None):
    if name not in REGISTRY:
        raise KeyError(f"unknown tool {name!r}")
    return REGISTRY[name].fn(**(args or {}))


def anthropic_tool_schemas() -> list[dict]:
    """Tool definitions in Anthropic tool-use format (for the optional Claude path)."""
    out = []
    for t in REGISTRY.values():
        props = {}
        for pname, spec in t.parameters.items():
            props[pname] = {k: v for k, v in spec.items() if k != "description"}
            if "description" in spec:
                props[pname]["description"] = spec["description"]
        out.append({
            "name": t.name,
            "description": t.description,
            "input_schema": {"type": "object", "properties": props},
        })
    return out
