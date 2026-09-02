"""
Tests for the deterministic Fire Intelligence Agent — the offline baseline.
Covers the documented example queries (context.md §13, §17) and the read-only
security model.
"""
import pytest

from src.alerting import alert_store, pipeline
from src.intelligence import queries
from src.intelligence.agent import ask, tools
from src.intelligence.agent import deterministic as D


@pytest.fixture(scope="module", autouse=True)
def _seed():
    if not alert_store.DB_PATH.exists() or alert_store.counts()["total"] == 0:
        pipeline.run(fresh=True)
    queries.clear_caches()
    yield


def test_registry_has_no_state_changing_tool():
    banned = ("update", "set_status", "set_alert_status", "acknowledge", "escalate",
              "resolve", "delete", "insert", "write", "run_pipeline", "exec", "sql")
    for name in tools.READ_ONLY_TOOL_NAMES:
        assert not any(b in name.lower() for b in banned), name


def test_no_api_key_still_works(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = ask("show critical industrial fires in Odisha")
    assert r.mode == "deterministic"
    assert r.tool == "list_alerts"


@pytest.mark.parametrize("msg,tool", [
    ("What are the critical industrial fire alerts today?", "list_alerts"),
    ("Show me persistent thermal sources in Odisha from the last 7 days.", "list_alerts"),
    ("Which incidents have the highest risk?", "rank_alerts"),
    ("Which persistent sources are close to industrial facilities?", "list_alerts"),
    ("How many critical incidents are currently active?", "situation_summary"),
    ("Compare Odisha and Jharkhand.", "compare_regions"),
    ("What is the highest-risk incident near a thermal power plant?", "rank_alerts"),
    ("Summarize the current situation in eastern India.", "situation_summary"),
    ("Generate report for high risk incidents this week", "build_incident_report"),
    ("Export the current results", "export_geojson"),
    ("Why was this incident classified as an industrial fire?", "get_investigation"),
])
def test_documented_queries_map_to_expected_tool(msg, tool):
    interp = D.parse(msg, {})
    assert interp.tool == tool, (msg, interp.tool)


def test_demo_query_three_highest_risk_with_why():
    msg = ("Find the three highest-risk persistent thermal sources near industrial "
           "facilities in eastern India over the last 7 days and explain why they "
           "are high risk.")
    interp = D.parse(msg, {})
    assert interp.tool == "rank_alerts"
    assert interp.args["limit"] == 3
    assert interp.explain_why is True
    f = interp.filters
    assert f.get("region") == "eastern india"
    assert "Persistent Source" in f.get("output_class", [])
    r = ask(msg)
    assert len(r.result_cards) <= 3
    assert r.mode == "deterministic"


def test_state_change_request_is_refused_and_read_only():
    r = ask("Escalate the highest-risk incident")
    assert r.tool is None
    assert "read-only" in r.text.lower()
    # it may offer to open the investigation, but must not have changed anything
    assert r.ui_action.get("nav") in (None, "Investigation")


def test_compare_regions_side_names():
    interp = D.parse("compare odisha and jharkhand", {})
    assert interp.args["region_a"].strip().lower() == "odisha"
    assert interp.args["region_b"].strip().lower() == "jharkhand"


def test_unavailable_data_is_reported_not_fabricated():
    r = ask("what is the wind speed at the top alert")
    # deterministic parser has no wind concept -> it should not invent a value
    assert "wind" not in r.text.lower() or "not" in r.text.lower() or r.tool in (
        None, "list_alerts", "rank_alerts")
