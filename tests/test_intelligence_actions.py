"""Tests for src/intelligence/actions.py (read-only exporters + report)."""
import json

import pytest

from src.alerting import alert_store, pipeline
from src.intelligence import actions, queries


@pytest.fixture(scope="module", autouse=True)
def _seed():
    if not alert_store.DB_PATH.exists() or alert_store.counts()["total"] == 0:
        pipeline.run(fresh=True)
    queries.clear_caches()
    yield


def test_export_geojson_is_valid_featurecollection():
    doc = json.loads(actions.export_geojson({"severity": ["CRITICAL"]}))
    assert doc["type"] == "FeatureCollection"
    assert doc["metadata"]["feature_count"] == len(doc["features"])
    for f in doc["features"]:
        assert f["geometry"]["type"] == "Point"
        assert len(f["geometry"]["coordinates"]) == 2
        assert f["properties"]["severity"] == "CRITICAL"


def test_export_csv_has_header_and_rows():
    csv = actions.export_csv({"severity": ["HIGH"]})
    lines = [l for l in csv.splitlines() if l.strip()]
    assert lines[0].startswith("alert_id,")
    assert len(lines) > 1


def test_incident_report_markdown():
    md = actions.build_incident_report({"severity": ["CRITICAL", "HIGH"]})
    assert md.startswith("# SIH26162")
    assert "not confirmed fires" in md.lower()
    assert "| Rank |" in md


def test_report_empty_scope_is_honest():
    md = actions.build_incident_report({"state": "Sikkim", "severity": ["CRITICAL"]})
    assert "nothing to report" in md.lower() or "0 alert" in md.lower()
