"""Tests for event-aware agent parser extensions."""
from src.intelligence.agent.deterministic import interpret


def test_list_events_intent():
    r = interpret("show me thermal events")
    assert r.intent in ("event_list", "list")


def test_critical_events_intent():
    r = interpret("show critical industrial events")
    assert r.intent == "event_list"
    filters = r.filters or r.args.get("filters") or {}
    assert filters.get("severity") == ["CRITICAL"]


def test_event_detail_by_id():
    r = interpret("tell me about event abcd1234")
    assert r.intent == "event_detail"
    assert r.args.get("event_id") == "abcd1234"


def test_event_fingerprint_intent():
    r = interpret("show behaviour fingerprint for event abcd1234")
    assert r.intent == "event_fingerprint"
    assert r.args.get("event_id") == "abcd1234"


def test_event_evidence_intent():
    r = interpret("show evidence for event abcd1234")
    assert r.intent == "event_evidence"
    assert r.args.get("event_id") == "abcd1234"


def test_event_evolution_intent():
    r = interpret("how has event abcd1234 evolved")
    assert r.intent == "event_evolution"
    assert r.args.get("event_id") == "abcd1234"


def test_event_replay_intent():
    r = interpret("replay event abcd1234")
    assert r.intent == "event_replay"
    assert r.args.get("event_id") == "abcd1234"


def test_increasing_risk_events_intent():
    r = interpret("which events are increasing in risk")
    assert r.intent == "event_trajectory"


def test_high_risk_events_intent():
    r = interpret("show high risk events")
    assert r.intent == "event_list"


def test_rank_events_intent():
    r = interpret("which event has the highest risk")
    assert r.intent in ("event_list", "rank", "event_detail")
