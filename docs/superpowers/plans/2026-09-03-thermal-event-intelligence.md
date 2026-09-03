# Thermal Event Intelligence Platform — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the SIH26162 fire detection platform into a Thermal Event Intelligence Platform by adding event clustering, behaviour fingerprinting, evidence stacks, event evolution replay, early warning / risk trajectory, and an upgraded analyst agent — all without rewriting any existing code.

**Architecture:** Six new pure-logic modules (`clustering`, `fingerprint`, `evidence`, `evolution`, `early_warning`, `events`) feed into extended query functions in `queries.py`. The dashboard views (`investigation`, `alerts`, `command_center`, `map_explorer`, `analytics`) consume the new data through `dashboard/data.py` wrappers. The agent's tool registry and deterministic parser are extended, not replaced.

**Tech Stack:** Python 3.11, pandas, numpy, scikit-learn BallTree (already installed), hashlib (stdlib), math (stdlib), Streamlit, pydeck (existing), SQLite (existing)

---

## File Map

### New files
| File | Responsibility |
|---|---|
| `src/intelligence/clustering.py` | Union-find spatial+temporal clustering → `ThermalEvent` dataclass |
| `src/intelligence/fingerprint.py` | Behavioural fingerprint from observation list |
| `src/intelligence/evidence.py` | Structured evidence stack (supporting / limiting) |
| `src/intelligence/evolution.py` | Timeline milestones + ordered frame sequence for replay |
| `src/intelligence/early_warning.py` | Risk trajectory + early-warning state from frames |
| `tests/test_clustering.py` | Clustering unit tests |
| `tests/test_fingerprint.py` | Fingerprint unit tests |
| `tests/test_evidence.py` | Evidence unit tests |
| `tests/test_evolution.py` | Evolution unit tests |
| `tests/test_early_warning.py` | Early-warning unit tests |
| `tests/test_events.py` | Event query integration tests |
| `tests/test_agent_events.py` | Agent event-intent parser tests |

### Modified files
| File | What changes |
|---|---|
| `src/intelligence/queries.py` | Add `_events_cached`, `list_events`, `get_event`, `get_event_for_alert`, `get_event_fingerprint`, `get_event_evidence`, `get_event_evolution`, `get_event_trajectory`, `find_increasing_risk_events`, `situation_summary` (event KPIs); extend `clear_caches` |
| `src/intelligence/agent/tools.py` | Add 8 event read-only tools |
| `src/intelligence/agent/deterministic.py` | Add event intents: event_list, event_detail, event_fingerprint, event_evidence, event_evolution, event_replay, event_trajectory |
| `dashboard/data.py` | Add `EVENTS`, `EVENT`, `EVENT_FOR_ALERT`, `EVENT_FINGERPRINT`, `EVENT_EVIDENCE`, `EVENT_EVOLUTION`, `EVENT_TRAJECTORY` wrappers + `@st.cache_data` decorators |
| `dashboard/views/investigation.py` | Add fingerprint panel, evidence stack, evolution timeline+replay, risk trajectory, early warning |
| `dashboard/views/command_center.py` | Add Event KPI row (Active Events, High-Risk Events, Persistent Sources, Early Warnings) |
| `dashboard/views/alerts.py` | Add DETECTIONS / EVENTS tab toggle |
| `dashboard/views/map_explorer.py` | Add "Thermal Events" layer checkbox and event centroid markers |
| `dashboard/views/analytics.py` | Add event metrics section |

---

## Task 1: Thermal Event Clustering

**Files:**
- Create: `src/intelligence/clustering.py`
- Create: `tests/test_clustering.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_clustering.py
"""Tests for thermal event clustering."""
import pytest
from src.intelligence.clustering import cluster_alerts, ThermalEvent


def _alert(alert_id, lat, lon, acq_date, frp_mw=10.0, risk_score=40,
           severity="MEDIUM", day_night="D", bt_kelvin=320.0,
           dist_nearest_facility_km=5.0, predicted_label="B",
           anomaly_flag=0, state="Andhra Pradesh"):
    return {
        "alert_id": alert_id,
        "lat": lat, "lon": lon,
        "acq_date": acq_date,
        "frp_mw": frp_mw,
        "bt_kelvin": bt_kelvin,
        "risk_score": risk_score,
        "severity": severity,
        "day_night": day_night,
        "dist_nearest_facility_km": dist_nearest_facility_km,
        "nearest_facility_type": "thermal power",
        "predicted_label": predicted_label,
        "prob_A": 0.6, "prob_B": 0.3,
        "anomaly_flag": anomaly_flag,
        "persistence_count": 1,
        "state": state,
        "district": None, "zone": None,
        "output_class": "Persistent Thermal Source",
        "output_class_short": "Persistent Source",
        "output_class_code": "PS-B",
        "status": "ALERTED",
        "narrative": "",
    }


def test_nearby_same_day_detections_cluster_together():
    alerts = [
        _alert("a01", 17.0, 80.0, "2026-09-01"),
        _alert("a02", 17.01, 80.01, "2026-09-01"),  # ~1.5km away
    ]
    events = cluster_alerts(alerts)
    assert len(events) == 1
    assert "a01" in events[0].alert_ids
    assert "a02" in events[0].alert_ids


def test_distant_detections_become_different_events():
    alerts = [
        _alert("b01", 17.0, 80.0, "2026-09-01"),
        _alert("b02", 20.0, 83.0, "2026-09-01"),  # ~400km away
    ]
    events = cluster_alerts(alerts)
    assert len(events) == 2


def test_temporally_distant_detections_split():
    # Same location but 10 days apart → separate events
    alerts = [
        _alert("c01", 17.0, 80.0, "2026-09-01"),
        _alert("c02", 17.01, 80.01, "2026-09-11"),
    ]
    events = cluster_alerts(alerts, temporal_days=3)
    assert len(events) == 2


def test_identical_input_produces_identical_event_ids():
    alerts = [
        _alert("d01", 17.0, 80.0, "2026-09-01"),
        _alert("d02", 17.01, 80.01, "2026-09-01"),
    ]
    events1 = cluster_alerts(alerts)
    events2 = cluster_alerts(alerts)
    assert events1[0].event_id == events2[0].event_id


def test_empty_input():
    assert cluster_alerts([]) == []


def test_single_detection():
    alerts = [_alert("e01", 17.0, 80.0, "2026-09-01")]
    events = cluster_alerts(alerts)
    assert len(events) == 1
    assert events[0].observation_count == 1


def test_missing_frp_handled():
    a = _alert("f01", 17.0, 80.0, "2026-09-01")
    a["frp_mw"] = None
    events = cluster_alerts([a])
    assert events[0].peak_frp_mw is None
    assert events[0].mean_frp_mw is None


def test_missing_acq_date_handled():
    a = _alert("g01", 17.0, 80.0, "")
    a["acq_date"] = None
    events = cluster_alerts([a])
    assert len(events) == 1


def test_duplicate_alert_ids_deduplicated():
    a = _alert("h01", 17.0, 80.0, "2026-09-01")
    events = cluster_alerts([a, a])
    # Same alert_id should not appear twice in one event
    event_ids_flat = [aid for e in events for aid in e.alert_ids]
    assert event_ids_flat.count("h01") == 1


def test_mixed_unrelated_detections():
    alerts = [
        _alert("i01", 17.0, 80.0, "2026-09-01"),   # group A
        _alert("i02", 17.01, 80.01, "2026-09-01"),  # group A
        _alert("i03", 22.0, 88.0, "2026-09-01"),    # group B (Kolkata area)
    ]
    events = cluster_alerts(alerts)
    assert len(events) == 2


def test_event_aggregates_correctly():
    alerts = [
        _alert("j01", 17.0, 80.0, "2026-09-01", frp_mw=20.0, risk_score=50,
               severity="HIGH", day_night="N"),
        _alert("j02", 17.01, 80.01, "2026-09-02", frp_mw=30.0, risk_score=70,
               severity="CRITICAL", day_night="D"),
    ]
    events = cluster_alerts(alerts)
    assert len(events) == 1
    e = events[0]
    assert e.peak_frp_mw == 30.0
    assert e.night_count == 1
    assert e.day_count == 1
    assert e.risk_score == 70
    assert e.severity == "CRITICAL"
    assert e.duration_days == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/test_clustering.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'src.intelligence.clustering'`

- [ ] **Step 3: Implement clustering.py**

```python
# src/intelligence/clustering.py
"""
Deterministic spatial+temporal clustering of thermal alert detections
into ThermalEvent objects.

Algorithm: Union-Find over all alert pairs. Two alerts merge into the same
event when both:
  - haversine distance <= spatial_km (default 15 km)
  - date gap <= temporal_days (default 3 days)

Event IDs are deterministic: SHA-256 of "|"-joined sorted alert_ids, first 8 hex chars.

ponytail: O(n²) pair scan — fine at ≤5k rows. Add BallTree spatial index
when alert count exceeds ~10k.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import date


@dataclass
class ThermalEvent:
    event_id: str
    alert_ids: list[str]
    centroid_lat: float
    centroid_lon: float
    start_date: str | None
    end_date: str | None
    duration_days: int
    observation_count: int
    spatial_extent_km: float
    peak_frp_mw: float | None
    mean_frp_mw: float | None
    max_bt_kelvin: float | None
    mean_bt_kelvin: float | None
    night_count: int
    day_count: int
    persistence_count: int
    dist_nearest_facility_km: float | None
    nearest_facility_type: str | None
    predicted_class: str | None
    model_probability: float | None
    anomaly_flag: int
    risk_score: int
    severity: str
    state: str | None
    district: str | None
    zone: str | None
    output_class: str | None
    output_class_short: str | None
    output_class_code: str | None


_SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(min(a, 1.0)))


def _date_gap(d1: str | None, d2: str | None) -> int:
    """Absolute day difference. Returns 0 if either date is missing."""
    if not d1 or not d2:
        return 0
    try:
        return abs((date.fromisoformat(str(d1)[:10]) - date.fromisoformat(str(d2)[:10])).days)
    except (ValueError, TypeError):
        return 0


def _find(parent: list[int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def _union(parent: list[int], rank: list[int], i: int, j: int) -> None:
    ri, rj = _find(parent, i), _find(parent, j)
    if ri == rj:
        return
    if rank[ri] < rank[rj]:
        ri, rj = rj, ri
    parent[rj] = ri
    if rank[ri] == rank[rj]:
        rank[ri] += 1


def _make_event_id(alert_ids: list[str]) -> str:
    key = "|".join(sorted(alert_ids))
    return hashlib.sha256(key.encode()).hexdigest()[:8]


def _build_event(group: list[dict]) -> ThermalEvent:
    alert_ids = list(dict.fromkeys(a["alert_id"] for a in group))  # dedup, preserve order

    lats = [float(a["lat"]) for a in group]
    lons = [float(a["lon"]) for a in group]
    centroid_lat = sum(lats) / len(lats)
    centroid_lon = sum(lons) / len(lons)

    dates = sorted(
        d for a in group
        for d in [str(a.get("acq_date") or "")]
        if d
    )
    start_date = dates[0] if dates else None
    end_date = dates[-1] if dates else None
    duration_days = _date_gap(start_date, end_date)

    # Spatial extent: max pairwise distance (capped at 200km for speed)
    extent = 0.0
    for i in range(len(group)):
        for j in range(i + 1, len(group)):
            d = _haversine_km(lats[i], lons[i], lats[j], lons[j])
            if d > extent:
                extent = d

    frps = [float(a["frp_mw"]) for a in group if a.get("frp_mw") is not None]
    bts = [float(a["bt_kelvin"]) for a in group if a.get("bt_kelvin") is not None]

    night_count = sum(1 for a in group if a.get("day_night") == "N")
    day_count = sum(1 for a in group if a.get("day_night") == "D")

    dists = [float(a["dist_nearest_facility_km"]) for a in group
             if a.get("dist_nearest_facility_km") is not None]

    # Best probability (max prob_A, as A = industrial/persistent)
    probs = [max(float(a.get("prob_A") or 0), float(a.get("prob_B") or 0)) for a in group]

    # Majority predicted class
    labels = [a.get("predicted_label") for a in group if a.get("predicted_label")]
    from collections import Counter
    pred_class = Counter(labels).most_common(1)[0][0] if labels else None

    # Max risk → severity
    max_risk = max((int(a.get("risk_score") or 0) for a in group), default=0)
    max_sev = max(
        (a.get("severity") or "LOW" for a in group),
        key=lambda s: _SEVERITY_ORDER.get(s, 0),
        default="LOW",
    )

    # Nearest facility: pick the group member with smallest dist
    closest = min(group, key=lambda a: float(a.get("dist_nearest_facility_km") or 9999))
    near_fac_dist = (float(closest["dist_nearest_facility_km"])
                     if closest.get("dist_nearest_facility_km") is not None else None)
    near_fac_type = closest.get("nearest_facility_type") or None

    # State: majority
    states = [a.get("state") for a in group if a.get("state")]
    top_state = Counter(states).most_common(1)[0][0] if states else None

    districts = [a.get("district") for a in group if a.get("district")]
    top_district = Counter(districts).most_common(1)[0][0] if districts else None

    zones = [a.get("zone") for a in group if a.get("zone")]
    top_zone = Counter(zones).most_common(1)[0][0] if zones else None

    # Output class: pick from highest-risk member
    best = max(group, key=lambda a: int(a.get("risk_score") or 0))

    return ThermalEvent(
        event_id=_make_event_id(alert_ids),
        alert_ids=alert_ids,
        centroid_lat=round(centroid_lat, 5),
        centroid_lon=round(centroid_lon, 5),
        start_date=start_date,
        end_date=end_date,
        duration_days=duration_days,
        observation_count=len(group),
        spatial_extent_km=round(extent, 2),
        peak_frp_mw=round(max(frps), 2) if frps else None,
        mean_frp_mw=round(sum(frps) / len(frps), 2) if frps else None,
        max_bt_kelvin=round(max(bts), 1) if bts else None,
        mean_bt_kelvin=round(sum(bts) / len(bts), 1) if bts else None,
        night_count=night_count,
        day_count=day_count,
        persistence_count=max((int(a.get("persistence_count") or 1) for a in group), default=1),
        dist_nearest_facility_km=round(near_fac_dist, 2) if near_fac_dist is not None else None,
        nearest_facility_type=near_fac_type,
        predicted_class=pred_class,
        model_probability=round(max(probs), 3) if probs else None,
        anomaly_flag=1 if any(int(a.get("anomaly_flag") or 0) for a in group) else 0,
        risk_score=max_risk,
        severity=max_sev,
        state=top_state,
        district=top_district,
        zone=top_zone,
        output_class=best.get("output_class"),
        output_class_short=best.get("output_class_short"),
        output_class_code=best.get("output_class_code"),
    )


def cluster_alerts(
    alerts: list[dict],
    spatial_km: float = 15.0,
    temporal_days: int = 3,
) -> list[ThermalEvent]:
    """
    Group `alerts` into ThermalEvent objects.

    Two alerts belong to the same event when:
      - haversine distance <= spatial_km
      - date gap <= temporal_days

    Returns events sorted by risk_score descending.
    """
    if not alerts:
        return []

    # Deduplicate by alert_id
    seen: set[str] = set()
    uniq: list[dict] = []
    for a in alerts:
        aid = a.get("alert_id", "")
        if aid and aid not in seen:
            seen.add(aid)
            uniq.append(a)
        elif not aid:
            uniq.append(a)

    n = len(uniq)
    parent = list(range(n))
    rank = [0] * n

    for i in range(n):
        for j in range(i + 1, n):
            if _find(parent, i) == _find(parent, j):
                continue
            dist = _haversine_km(
                float(uniq[i]["lat"]), float(uniq[i]["lon"]),
                float(uniq[j]["lat"]), float(uniq[j]["lon"]),
            )
            if dist > spatial_km:
                continue
            gap = _date_gap(uniq[i].get("acq_date"), uniq[j].get("acq_date"))
            if gap <= temporal_days:
                _union(parent, rank, i, j)

    # Collect groups
    groups: dict[int, list[dict]] = {}
    for i, a in enumerate(uniq):
        root = _find(parent, i)
        groups.setdefault(root, []).append(a)

    events = [_build_event(g) for g in groups.values()]
    events.sort(key=lambda e: e.risk_score, reverse=True)
    return events
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/test_clustering.py -v
```

Expected: All 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/zain/SIH-2026
git add src/intelligence/clustering.py tests/test_clustering.py
git commit -m "feat: add deterministic thermal event clustering (union-find, spatial+temporal)"
```

---

## Task 2: Behaviour Fingerprint

**Files:**
- Create: `src/intelligence/fingerprint.py`
- Create: `tests/test_fingerprint.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fingerprint.py
"""Tests for thermal behaviour fingerprinting."""
from src.intelligence.fingerprint import compute_fingerprint


def _obs(day_night="D", frp=15.0, lat=17.0, lon=80.0, date="2026-09-01",
         dist_fac=5.0, risk=40, agri_month=False):
    return {
        "lat": lat, "lon": lon, "acq_date": date,
        "day_night": day_night,
        "frp_mw": frp,
        "bt_kelvin": 320.0,
        "dist_nearest_facility_km": dist_fac,
        "nearest_facility_type": "thermal power",
        "risk_score": risk,
        "anomaly_flag": 0,
        "persistence_count": 1,
    }


def test_empty_returns_insufficient():
    fp = compute_fingerprint([])
    assert fp["behaviour_category"] == "Insufficient Evidence"


def test_single_observation():
    fp = compute_fingerprint([_obs()])
    assert "behaviour_category" in fp
    assert fp["observation_count"] == 1


def test_persistent_source_high_persistence():
    obs = [_obs(day_night="N", frp=80.0, dist_fac=0.5) for _ in range(9)]
    fp = compute_fingerprint(obs)
    assert fp["persistence"] in ("HIGH", "VERY HIGH")
    assert fp["industrial_proximity"] in ("HIGH", "VERY HIGH")


def test_mostly_nighttime():
    obs = [_obs(day_night="N") for _ in range(8)] + [_obs(day_night="D")]
    fp = compute_fingerprint(obs)
    assert fp["night_activity"] in ("HIGH", "VERY HIGH")


def test_mostly_daytime():
    obs = [_obs(day_night="D") for _ in range(8)] + [_obs(day_night="N")]
    fp = compute_fingerprint(obs)
    assert fp["night_activity"] in ("LOW", "MEDIUM")


def test_high_frp_intensity():
    obs = [_obs(frp=200.0) for _ in range(3)]
    fp = compute_fingerprint(obs)
    assert fp["frp_intensity"] in ("HIGH", "VERY HIGH")


def test_missing_frp_handled():
    obs = [_obs()]
    obs[0]["frp_mw"] = None
    fp = compute_fingerprint(obs)
    assert "frp_intensity" in fp


def test_behaviour_category_present():
    obs = [_obs(day_night="N", frp=80.0, dist_fac=0.5) for _ in range(9)]
    fp = compute_fingerprint(obs)
    assert fp["behaviour_category"] in (
        "Persistent Industrial Signature",
        "Recurring Thermal Source",
        "Rapidly Expanding Fire Signature",
        "Seasonal Agricultural Signature",
        "Isolated Thermal Anomaly",
        "Insufficient Evidence",
    )


def test_seasonal_alignment_detected():
    # January = agri month (month 1)
    obs = [_obs(date="2026-01-15") for _ in range(5)]
    fp = compute_fingerprint(obs)
    assert fp["seasonal_alignment"] in ("HIGH", "MEDIUM", "LOW")
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/test_fingerprint.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'src.intelligence.fingerprint'`

- [ ] **Step 3: Implement fingerprint.py**

```python
# src/intelligence/fingerprint.py
"""
Thermal behaviour fingerprint computed from a list of alert-dict observations.

All values are derived from actual data — nothing is fabricated.
Output is a plain dict suitable for JSON serialisation and UI display.

Behaviour categories are assessments, not ground truth.
"""
from __future__ import annotations

from datetime import date

# Agricultural months in India (when crop-residue burning is common)
_AGRI_MONTHS = {1, 2, 4, 5, 7, 8, 9, 10, 11}

_LEVELS = ("VERY LOW", "LOW", "MEDIUM", "HIGH", "VERY HIGH")

BEHAVIOUR_CATEGORIES = [
    "Persistent Industrial Signature",
    "Recurring Thermal Source",
    "Rapidly Expanding Fire Signature",
    "Seasonal Agricultural Signature",
    "Isolated Thermal Anomaly",
    "Insufficient Evidence",
]


def _level(value: float, thresholds: tuple[float, ...]) -> str:
    """Map a 0-1 value to a 5-level rating using four thresholds."""
    for i, t in enumerate(thresholds):
        if value <= t:
            return _LEVELS[i]
    return _LEVELS[-1]


def _rate_persistence(n: int) -> str:
    if n <= 1:
        return "VERY LOW"
    if n <= 2:
        return "LOW"
    if n <= 4:
        return "MEDIUM"
    if n <= 8:
        return "HIGH"
    return "VERY HIGH"


def _rate_night_activity(night_ratio: float) -> str:
    return _level(night_ratio, (0.1, 0.3, 0.6, 0.8))


def _rate_frp(mean_frp: float | None) -> str:
    if mean_frp is None:
        return "UNKNOWN"
    if mean_frp < 5:
        return "VERY LOW"
    if mean_frp < 15:
        return "LOW"
    if mean_frp < 40:
        return "MEDIUM"
    if mean_frp < 100:
        return "HIGH"
    return "VERY HIGH"


def _rate_spatial_stability(extent_km: float, n: int) -> str:
    """Small spatial extent relative to observation count → stable/point source."""
    if n <= 1:
        return "VERY HIGH"
    if extent_km < 2:
        return "VERY HIGH"
    if extent_km < 5:
        return "HIGH"
    if extent_km < 15:
        return "MEDIUM"
    if extent_km < 30:
        return "LOW"
    return "VERY LOW"


def _rate_industrial_proximity(min_dist_km: float | None) -> str:
    if min_dist_km is None:
        return "UNKNOWN"
    if min_dist_km < 1:
        return "VERY HIGH"
    if min_dist_km < 3:
        return "HIGH"
    if min_dist_km < 10:
        return "MEDIUM"
    if min_dist_km < 25:
        return "LOW"
    return "VERY LOW"


def _rate_seasonal(fraction: float) -> str:
    return _level(fraction, (0.1, 0.3, 0.6, 0.8))


def _spatial_extent_km(obs: list[dict]) -> float:
    """Max pairwise distance — same haversine as clustering.py avoids re-import."""
    import math
    max_d = 0.0
    lats = [float(o["lat"]) for o in obs]
    lons = [float(o["lon"]) for o in obs]
    for i in range(len(obs)):
        for j in range(i + 1, len(obs)):
            dlat = math.radians(lats[j] - lats[i])
            dlon = math.radians(lons[j] - lons[i])
            a = (math.sin(dlat / 2) ** 2
                 + math.cos(math.radians(lats[i])) * math.cos(math.radians(lats[j]))
                 * math.sin(dlon / 2) ** 2)
            d = 2 * 6371.0 * math.asin(math.sqrt(min(a, 1.0)))
            if d > max_d:
                max_d = d
    return round(max_d, 2)


def _assign_category(persistence: str, night_activity: str, frp_intensity: str,
                     spatial_stability: str, industrial_proximity: str,
                     seasonal_alignment: str, n: int) -> str:
    if n < 2:
        return "Isolated Thermal Anomaly"
    high_set = {"HIGH", "VERY HIGH"}
    low_set = {"LOW", "VERY LOW"}
    if (persistence in high_set
            and industrial_proximity in high_set
            and spatial_stability in high_set):
        return "Persistent Industrial Signature"
    if persistence in high_set and frp_intensity in low_set and seasonal_alignment in high_set:
        return "Seasonal Agricultural Signature"
    if persistence in high_set and spatial_stability in low_set:
        return "Rapidly Expanding Fire Signature"
    if persistence in ("MEDIUM", "HIGH", "VERY HIGH"):
        return "Recurring Thermal Source"
    return "Isolated Thermal Anomaly"


def compute_fingerprint(observations: list[dict]) -> dict:
    """
    Compute a behavioural fingerprint from a list of alert dicts (event observations).

    Returns a plain dict with level strings and a behaviour_category string.
    All fields are derived from real data. Missing data results in "UNKNOWN" level.
    """
    n = len(observations)
    if n == 0:
        return {
            "observation_count": 0,
            "persistence": "VERY LOW",
            "night_activity": "UNKNOWN",
            "frp_intensity": "UNKNOWN",
            "spatial_stability": "UNKNOWN",
            "industrial_proximity": "UNKNOWN",
            "seasonal_alignment": "UNKNOWN",
            "behaviour_category": "Insufficient Evidence",
        }

    persistence = _rate_persistence(n)

    # Night activity
    night_count = sum(1 for o in observations if o.get("day_night") == "N")
    night_ratio = night_count / n
    night_activity = _rate_night_activity(night_ratio)

    # FRP intensity
    frps = [float(o["frp_mw"]) for o in observations if o.get("frp_mw") is not None]
    mean_frp = sum(frps) / len(frps) if frps else None
    frp_intensity = _rate_frp(mean_frp)

    # Spatial stability
    extent_km = _spatial_extent_km(observations) if n > 1 else 0.0
    spatial_stability = _rate_spatial_stability(extent_km, n)

    # Industrial proximity
    dists = [float(o["dist_nearest_facility_km"])
             for o in observations if o.get("dist_nearest_facility_km") is not None]
    min_dist = min(dists) if dists else None
    industrial_proximity = _rate_industrial_proximity(min_dist)

    # Seasonal alignment (derive from acq_date month)
    agri_hits = 0
    for o in observations:
        d = o.get("acq_date") or ""
        try:
            m = date.fromisoformat(str(d)[:10]).month
            if m in _AGRI_MONTHS:
                agri_hits += 1
        except (ValueError, TypeError):
            pass
    seasonal_fraction = agri_hits / n
    seasonal_alignment = _rate_seasonal(seasonal_fraction)

    category = _assign_category(
        persistence, night_activity, frp_intensity,
        spatial_stability, industrial_proximity, seasonal_alignment, n,
    )

    return {
        "observation_count": n,
        "persistence": persistence,
        "night_activity": night_activity,
        "frp_intensity": frp_intensity,
        "spatial_stability": spatial_stability,
        "industrial_proximity": industrial_proximity,
        "seasonal_alignment": seasonal_alignment,
        "behaviour_category": category,
        "night_count": night_count,
        "day_count": n - night_count,
        "mean_frp_mw": round(mean_frp, 1) if mean_frp is not None else None,
        "spatial_extent_km": extent_km,
        "min_dist_facility_km": round(min_dist, 2) if min_dist is not None else None,
    }
```

- [ ] **Step 4: Run tests**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/test_fingerprint.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/zain/SIH-2026
git add src/intelligence/fingerprint.py tests/test_fingerprint.py
git commit -m "feat: add thermal behaviour fingerprint with 6 dimensions and behaviour category"
```

---

## Task 3: Evidence Stack

**Files:**
- Create: `src/intelligence/evidence.py`
- Create: `tests/test_evidence.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_evidence.py
"""Tests for evidence stack builder."""
from src.intelligence.clustering import ThermalEvent
from src.intelligence.evidence import build_evidence, EvidenceItem


def _make_event(**kwargs):
    defaults = dict(
        event_id="abcd1234",
        alert_ids=["a01"],
        centroid_lat=17.0, centroid_lon=80.0,
        start_date="2026-09-01", end_date="2026-09-03",
        duration_days=2, observation_count=3,
        spatial_extent_km=2.0,
        peak_frp_mw=80.0, mean_frp_mw=50.0,
        max_bt_kelvin=340.0, mean_bt_kelvin=325.0,
        night_count=2, day_count=1,
        persistence_count=3,
        dist_nearest_facility_km=1.5,
        nearest_facility_type="thermal power plant",
        predicted_class="A", model_probability=0.82,
        anomaly_flag=0, risk_score=75, severity="HIGH",
        state="Andhra Pradesh", district="Visakhapatnam",
        zone=None, output_class="Persistent Thermal Source",
        output_class_short="Persistent Source", output_class_code="PS-B",
    )
    defaults.update(kwargs)
    return ThermalEvent(**defaults)


def _make_obs(n=3, frp=50.0, dist=1.5, day_night="N"):
    return [
        {"frp_mw": frp, "bt_kelvin": 330.0, "day_night": day_night,
         "dist_nearest_facility_km": dist, "acq_date": "2026-09-01",
         "risk_score": 75, "anomaly_flag": 0, "persistence_count": n}
        for _ in range(n)
    ]


def test_build_evidence_returns_dict():
    ev = _make_event()
    result = build_evidence(ev, _make_obs())
    assert isinstance(result, dict)
    assert "supporting" in result
    assert "limiting" in result


def test_supporting_has_evidence_items():
    ev = _make_event()
    result = build_evidence(ev, _make_obs())
    for item in result["supporting"]:
        assert "category" in item
        assert "label" in item
        assert "value" in item
        assert "direction" in item
        assert item["direction"] == "SUPPORTING"


def test_limiting_has_evidence_items():
    ev = _make_event()
    result = build_evidence(ev, _make_obs())
    # There are always system-level limiting items (FIRMS resolution, no ground truth)
    assert len(result["limiting"]) > 0


def test_no_fabrication_when_frp_missing():
    ev = _make_event(peak_frp_mw=None, mean_frp_mw=None)
    obs = _make_obs(frp=None.__class__())  # won't work — use explicit None
    obs2 = [{"frp_mw": None, "bt_kelvin": None, "day_night": "D",
              "dist_nearest_facility_km": 1.5, "acq_date": "2026-09-01",
              "risk_score": 40, "anomaly_flag": 0, "persistence_count": 1}]
    result = build_evidence(ev, obs2)
    # Should not crash and should not invent FRP evidence
    assert isinstance(result, dict)


def test_counts_are_consistent():
    ev = _make_event()
    result = build_evidence(ev, _make_obs())
    assert result["total_supporting"] == len(result["supporting"])
    assert result["total_limiting"] == len(result["limiting"])


def test_single_observation_event():
    ev = _make_event(observation_count=1, night_count=0, day_count=1,
                     duration_days=0, start_date="2026-09-01", end_date="2026-09-01")
    result = build_evidence(ev, _make_obs(n=1))
    assert isinstance(result, dict)


def test_anomaly_flag_creates_limiting_evidence():
    ev = _make_event(anomaly_flag=1)
    result = build_evidence(ev, _make_obs())
    limiting_labels = [i["label"] for i in result["limiting"]]
    assert any("anomal" in l.lower() or "pattern" in l.lower() for l in limiting_labels)
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/test_evidence.py -v 2>&1 | head -10
```

- [ ] **Step 3: Implement evidence.py**

```python
# src/intelligence/evidence.py
"""
Structured evidence stack: supporting and limiting evidence derived from
real alert data only. No values are fabricated.

EvidenceItem:
    category   THERMAL | GEOSPATIAL | BEHAVIOURAL | MODEL | RISK
    label      human-readable label
    value      human-readable value string
    direction  SUPPORTING | LIMITING | NEUTRAL
    explanation one-sentence explanation
    source     FIRMS | facility_db | ML_model | risk_engine | system
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from src.intelligence.clustering import ThermalEvent


@dataclass
class EvidenceItem:
    category: str
    label: str
    value: str
    direction: str   # SUPPORTING | LIMITING | NEUTRAL
    explanation: str
    source: str


def _item(category, label, value, direction, explanation, source="FIRMS") -> dict:
    return asdict(EvidenceItem(category, label, value, direction, explanation, source))


def build_evidence(event: ThermalEvent, observations: list[dict]) -> dict:
    """
    Build a structured evidence dict from a ThermalEvent and its observations.

    Returns:
        {
            "supporting": [EvidenceItem dict, ...],
            "limiting":   [EvidenceItem dict, ...],
            "total_supporting": int,
            "total_limiting": int,
        }
    """
    supporting: list[dict] = []
    limiting: list[dict] = []

    # ── THERMAL EVIDENCE ─────────────────────────────────────────────────────
    if event.peak_frp_mw is not None:
        frp_context = "elevated" if event.peak_frp_mw >= 30 else "moderate"
        supporting.append(_item(
            "THERMAL", "Peak Fire Radiative Power",
            f"{event.peak_frp_mw} MW ({frp_context})",
            "SUPPORTING",
            f"Peak FRP of {event.peak_frp_mw} MW indicates significant thermal energy release.",
        ))

    if event.observation_count >= 2:
        supporting.append(_item(
            "THERMAL", "Observation Persistence",
            f"{event.observation_count} detections across {event.duration_days + 1} day(s)",
            "SUPPORTING",
            "Multiple independent satellite overpasses detected the same source — reducing "
            "the likelihood of a single spurious reading.",
        ))
    else:
        limiting.append(_item(
            "THERMAL", "Single Observation",
            "1 detection only",
            "LIMITING",
            "Only one satellite overpass detected this source. Single observations have "
            "higher false-positive rates.",
        ))

    if event.max_bt_kelvin is not None and event.max_bt_kelvin > 340:
        supporting.append(_item(
            "THERMAL", "Brightness Temperature",
            f"{event.max_bt_kelvin} K (peak)",
            "SUPPORTING",
            "High brightness temperature is consistent with an intense or sustained "
            "thermal source.",
        ))

    if event.night_count >= 2:
        supporting.append(_item(
            "THERMAL", "Nocturnal Detections",
            f"{event.night_count} of {event.observation_count} at night",
            "SUPPORTING",
            "Night-time detections have lower solar background noise and are more consistent "
            "with a continuous industrial or fire source.",
        ))

    # ── GEOSPATIAL EVIDENCE ───────────────────────────────────────────────────
    if event.dist_nearest_facility_km is not None:
        if event.dist_nearest_facility_km < 3.0:
            supporting.append(_item(
                "GEOSPATIAL", "Industrial Facility Proximity",
                f"{event.dist_nearest_facility_km} km from {event.nearest_facility_type or 'facility'}",
                "SUPPORTING",
                f"Detection centroid is {event.dist_nearest_facility_km} km from a known "
                f"{event.nearest_facility_type or 'industrial facility'} — strong spatial co-location.",
                "facility_db",
            ))
        elif event.dist_nearest_facility_km < 10.0:
            supporting.append(_item(
                "GEOSPATIAL", "Industrial Facility Proximity",
                f"{event.dist_nearest_facility_km} km from {event.nearest_facility_type or 'facility'}",
                "NEUTRAL",
                f"Detection is within {event.dist_nearest_facility_km} km of a known facility — "
                "moderate spatial association.",
                "facility_db",
            ))

    if event.state:
        supporting.append(_item(
            "GEOSPATIAL", "Location",
            f"{event.district or ''}, {event.state}".strip(", "),
            "NEUTRAL",
            "Detection location confirmed via point-in-polygon state polygon match.",
        ))

    # ── BEHAVIOURAL EVIDENCE ──────────────────────────────────────────────────
    if event.duration_days >= 2:
        supporting.append(_item(
            "BEHAVIOURAL", "Temporal Persistence",
            f"{event.duration_days} days",
            "SUPPORTING",
            f"Event spans {event.duration_days} days — behaviour is consistent with a "
            "sustained rather than transient source.",
        ))

    if event.spatial_extent_km < 5.0 and event.observation_count >= 2:
        supporting.append(_item(
            "BEHAVIOURAL", "Spatial Stability",
            f"{event.spatial_extent_km} km extent",
            "SUPPORTING",
            "Detections are tightly co-located — consistent with a fixed point source "
            "rather than a spreading fire front.",
        ))
    elif event.spatial_extent_km > 15.0:
        limiting.append(_item(
            "BEHAVIOURAL", "Spatial Spread",
            f"{event.spatial_extent_km} km extent",
            "LIMITING",
            "Detections span a large area — may represent multiple nearby sources "
            "or a spreading fire, not a single fixed point.",
        ))

    # ── MODEL EVIDENCE ────────────────────────────────────────────────────────
    if event.model_probability is not None:
        prob_pct = round(event.model_probability * 100)
        if event.anomaly_flag:
            limiting.append(_item(
                "MODEL", "Pattern Anomaly",
                "Yes — low model confidence",
                "LIMITING",
                "The ML model's max class probability is below the anomaly threshold. "
                "The source does not match the learned pattern of either persistent-industrial "
                "or natural-fire activity.",
                "ML_model",
            ))
        else:
            supporting.append(_item(
                "MODEL", "Model Classification Confidence",
                f"{prob_pct}% — class {event.predicted_class or '?'}",
                "SUPPORTING" if prob_pct >= 70 else "NEUTRAL",
                f"Model assigns {prob_pct}% probability to class {event.predicted_class}. "
                "This is a proxy classifier, not a confirmed fire determination.",
                "ML_model",
            ))

    # ── RISK EVIDENCE ─────────────────────────────────────────────────────────
    if event.risk_score >= 70:
        supporting.append(_item(
            "RISK", "Risk Score",
            f"{event.risk_score}/100 — {event.severity}",
            "SUPPORTING",
            "High composite risk score from the risk engine (FRP, proximity, persistence, "
            "severity factors combined).",
            "risk_engine",
        ))

    # ── SYSTEM-LEVEL LIMITING EVIDENCE (always present) ──────────────────────
    limiting.append(_item(
        "SYSTEM", "Satellite Resolution",
        "VIIRS 375m / MODIS 1km",
        "LIMITING",
        "FIRMS spatial resolution prevents exact attribution of the thermal source to "
        "a specific facility, fire perimeter, or point.",
        "system",
    ))
    limiting.append(_item(
        "SYSTEM", "No Ground Confirmation",
        "Not verified",
        "LIMITING",
        "No field inspection or ground-truth confirmation is available. "
        "This assessment is based on satellite observations only.",
        "system",
    ))

    return {
        "supporting": supporting,
        "limiting": limiting,
        "total_supporting": len(supporting),
        "total_limiting": len(limiting),
    }
```

- [ ] **Step 4: Run tests**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/test_evidence.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/zain/SIH-2026
git add src/intelligence/evidence.py tests/test_evidence.py
git commit -m "feat: add structured evidence stack with supporting/limiting items"
```

---

## Task 4: Event Evolution

**Files:**
- Create: `src/intelligence/evolution.py`
- Create: `tests/test_evolution.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_evolution.py
"""Tests for event evolution timeline builder."""
from src.intelligence.evolution import build_evolution


def _obs(acq_date, frp=15.0, risk=40):
    return {"acq_date": acq_date, "frp_mw": frp, "risk_score": risk,
            "lat": 17.0, "lon": 80.0, "day_night": "D",
            "bt_kelvin": 320.0, "alert_id": acq_date}


def test_chronological_ordering():
    obs = [_obs("2026-09-03"), _obs("2026-09-01"), _obs("2026-09-02")]
    evo = build_evolution(obs)
    dates = [f["timestamp"] for f in evo["frames"]]
    assert dates == sorted(dates)


def test_duplicate_timestamps_handled():
    obs = [_obs("2026-09-01"), _obs("2026-09-01")]
    evo = build_evolution(obs)
    assert evo["observation_count"] == 2
    assert len(evo["frames"]) == 2


def test_single_observation():
    obs = [_obs("2026-09-01", frp=20.0, risk=50)]
    evo = build_evolution(obs)
    assert evo["observation_count"] == 1
    assert evo["start_date"] == "2026-09-01"
    assert evo["end_date"] == "2026-09-01"
    assert len(evo["milestones"]) >= 1  # at least "First Detection"


def test_missing_timestamp_handled():
    obs = [_obs(None), _obs("2026-09-01")]
    evo = build_evolution(obs)
    assert evo["observation_count"] == 2


def test_empty_event():
    evo = build_evolution([])
    assert evo["observation_count"] == 0
    assert evo["frames"] == []
    assert evo["milestones"] == []


def test_frames_have_cumulative_count():
    obs = [_obs("2026-09-01"), _obs("2026-09-02"), _obs("2026-09-03")]
    evo = build_evolution(obs)
    for i, f in enumerate(evo["frames"]):
        assert f["cumulative_count"] == i + 1


def test_deterministic_frame_generation():
    obs = [_obs("2026-09-01", frp=10.0), _obs("2026-09-02", frp=20.0)]
    evo1 = build_evolution(obs)
    evo2 = build_evolution(obs)
    assert evo1["frames"] == evo2["frames"]
    assert evo1["milestones"] == evo2["milestones"]


def test_peak_frp_milestone_detected():
    obs = [_obs("2026-09-01", frp=10.0), _obs("2026-09-02", frp=100.0),
           _obs("2026-09-03", frp=50.0)]
    evo = build_evolution(obs)
    labels = [m["label"] for m in evo["milestones"]]
    assert any("peak" in l.lower() or "frp" in l.lower() for l in labels)


def test_risk_threshold_milestone():
    obs = [_obs("2026-09-01", frp=10.0, risk=30),
           _obs("2026-09-02", frp=80.0, risk=75)]
    evo = build_evolution(obs)
    labels = [m["label"] for m in evo["milestones"]]
    assert any("risk" in l.lower() or "threshold" in l.lower() for l in labels)
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/test_evolution.py -v 2>&1 | head -10
```

- [ ] **Step 3: Implement evolution.py**

```python
# src/intelligence/evolution.py
"""
Event evolution: ordered timeline of observations with milestones.

Milestones are derived only from data — no semantic labels are invented.
The frame sequence supports UI replay (slider-based).
"""
from __future__ import annotations


def _safe_date(d) -> str:
    return str(d)[:10] if d else ""


def _sort_key(o: dict) -> str:
    """Sort key: acq_date string (lexicographic ISO date order). Null → sorts first."""
    return _safe_date(o.get("acq_date") or "")


def build_evolution(observations: list[dict]) -> dict:
    """
    Build an ordered evolution dict from a list of alert-dict observations.

    Returns:
        observation_count, start_date, end_date,
        frames: [{step, timestamp, cumulative_count, current_frp, risk_score, lat, lon}],
        milestones: [{timestamp, label, detail}]
    """
    if not observations:
        return {
            "observation_count": 0,
            "start_date": None,
            "end_date": None,
            "frames": [],
            "milestones": [],
        }

    sorted_obs = sorted(observations, key=_sort_key)
    n = len(sorted_obs)

    frames = []
    for i, o in enumerate(sorted_obs):
        frames.append({
            "step": i + 1,
            "timestamp": _safe_date(o.get("acq_date")),
            "cumulative_count": i + 1,
            "current_frp": o.get("frp_mw"),
            "risk_score": int(o.get("risk_score") or 0),
            "lat": float(o["lat"]),
            "lon": float(o["lon"]),
            "day_night": o.get("day_night", ""),
        })

    # Derive milestones from data
    milestones: list[dict] = []

    # Always: first detection
    first = sorted_obs[0]
    milestones.append({
        "timestamp": _safe_date(first.get("acq_date")),
        "label": "First Detection",
        "detail": (f"FRP {first.get('frp_mw')} MW" if first.get("frp_mw") is not None
                   else "Thermal anomaly detected"),
    })

    # Persistence detected (second observation)
    if n >= 2:
        second = sorted_obs[1]
        milestones.append({
            "timestamp": _safe_date(second.get("acq_date")),
            "label": "Persistence Detected",
            "detail": "Source confirmed across multiple satellite overpasses",
        })

    # FRP peak (if not first observation)
    frp_vals = [(i, o.get("frp_mw")) for i, o in enumerate(sorted_obs)
                if o.get("frp_mw") is not None]
    if frp_vals and len(frp_vals) > 1:
        peak_i, peak_frp = max(frp_vals, key=lambda x: x[1])
        if peak_i > 0:
            milestones.append({
                "timestamp": _safe_date(sorted_obs[peak_i].get("acq_date")),
                "label": "Peak FRP Observed",
                "detail": f"{peak_frp} MW — highest thermal intensity in event window",
            })

    # Risk threshold crossed (risk_score >= 60)
    risk_vals = [(i, int(o.get("risk_score") or 0)) for i, o in enumerate(sorted_obs)]
    for i, rs in risk_vals:
        if rs >= 60 and i > 0:
            milestones.append({
                "timestamp": _safe_date(sorted_obs[i].get("acq_date")),
                "label": "High-Risk Threshold Crossed",
                "detail": f"Risk score reached {rs}/100",
            })
            break

    # Sort milestones chronologically
    milestones.sort(key=lambda m: m["timestamp"])

    start_date = _safe_date(sorted_obs[0].get("acq_date"))
    end_date = _safe_date(sorted_obs[-1].get("acq_date"))

    return {
        "observation_count": n,
        "start_date": start_date or None,
        "end_date": end_date or None,
        "frames": frames,
        "milestones": milestones,
    }
```

- [ ] **Step 4: Run tests**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/test_evolution.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/zain/SIH-2026
git add src/intelligence/evolution.py tests/test_evolution.py
git commit -m "feat: add event evolution timeline with milestones and replay frames"
```

---

## Task 5: Early Warning / Risk Trajectory

**Files:**
- Create: `src/intelligence/early_warning.py`
- Create: `tests/test_early_warning.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_early_warning.py
"""Tests for risk trajectory and early-warning state."""
from src.intelligence.early_warning import compute_trajectory


def _frames(risk_scores: list[int]) -> list[dict]:
    return [{"step": i + 1, "timestamp": f"2026-09-0{i+1}",
             "cumulative_count": i + 1, "current_frp": 20.0,
             "risk_score": rs, "lat": 17.0, "lon": 80.0}
            for i, rs in enumerate(risk_scores)]


def test_stable_risk():
    result = compute_trajectory(_frames([40, 41, 42, 40]))
    assert result["trajectory"] == "STABLE"
    assert result["state"] in ("STABLE", "WATCH")


def test_increasing_risk():
    result = compute_trajectory(_frames([30, 45, 60, 80]))
    assert result["trajectory"] == "INCREASING"
    assert result["state"] in ("INCREASING", "EARLY WARNING", "HIGH PRIORITY")


def test_decreasing_risk():
    result = compute_trajectory(_frames([80, 60, 40, 30]))
    assert result["trajectory"] == "DECREASING"


def test_insufficient_history():
    result = compute_trajectory(_frames([50]))
    assert result["state"] == "INSUFFICIENT DATA"


def test_empty_frames():
    result = compute_trajectory([])
    assert result["state"] == "INSUFFICIENT DATA"


def test_missing_risk_score_skipped():
    frames = _frames([40, 60])
    frames[0]["risk_score"] = None
    result = compute_trajectory(frames)
    # Should not crash; computes from available scores
    assert "state" in result


def test_missing_frp_skipped():
    frames = _frames([40, 70])
    frames[0]["current_frp"] = None
    result = compute_trajectory(frames)
    assert "state" in result


def test_signals_list_present():
    result = compute_trajectory(_frames([30, 50, 70, 90]))
    assert isinstance(result["signals"], list)


def test_risk_history_matches_input():
    scores = [35, 50, 65, 80]
    result = compute_trajectory(_frames(scores))
    assert result["risk_history"] == scores
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/test_early_warning.py -v 2>&1 | head -10
```

- [ ] **Step 3: Implement early_warning.py**

```python
# src/intelligence/early_warning.py
"""
Risk trajectory analysis from ordered evolution frames.

Computes:
  - trajectory: INCREASING | STABLE | DECREASING
  - state: INSUFFICIENT DATA | STABLE | WATCH | INCREASING | EARLY WARNING | HIGH PRIORITY
  - signals: list of contributing reasons
  - risk_history: ordered list of risk scores

NEVER claims fire certainty. NEVER predicts the future.
Describes observed trend in existing data only.
"""
from __future__ import annotations

_STATES = ("INSUFFICIENT DATA", "STABLE", "WATCH", "INCREASING", "EARLY WARNING", "HIGH PRIORITY")


def compute_trajectory(frames: list[dict]) -> dict:
    """
    Compute a risk trajectory from ordered evolution frames.

    frames: list of dicts with at least risk_score (int|None) and current_frp (float|None).

    Returns:
        state, trajectory, delta, risk_history, signals
    """
    if not frames:
        return {"state": "INSUFFICIENT DATA", "trajectory": "UNKNOWN",
                "delta": 0, "risk_history": [], "signals": []}

    risk_scores = [int(f["risk_score"]) for f in frames if f.get("risk_score") is not None]

    if len(risk_scores) < 2:
        return {"state": "INSUFFICIENT DATA", "trajectory": "UNKNOWN",
                "delta": 0, "risk_history": risk_scores, "signals": []}

    delta = risk_scores[-1] - risk_scores[0]
    signals: list[str] = []

    # Trajectory classification
    if delta > 5:
        trajectory = "INCREASING"
    elif delta < -5:
        trajectory = "DECREASING"
    else:
        trajectory = "STABLE"

    # Signals
    if delta > 0:
        signals.append(f"Risk score increased by {delta} points over {len(risk_scores)} observations")
    elif delta < 0:
        signals.append(f"Risk score decreased by {abs(delta)} points over {len(risk_scores)} observations")
    else:
        signals.append("Risk score is stable across observations")

    # FRP trend
    frps = [float(f["current_frp"]) for f in frames if f.get("current_frp") is not None]
    if len(frps) >= 2:
        frp_delta = frps[-1] - frps[0]
        if frp_delta > 5:
            signals.append(f"Fire Radiative Power increased from {frps[0]:.1f} to {frps[-1]:.1f} MW")
        elif frp_delta < -5:
            signals.append(f"Fire Radiative Power decreased from {frps[0]:.1f} to {frps[-1]:.1f} MW")

    # State based on trajectory + magnitude
    latest_risk = risk_scores[-1]
    if trajectory == "INCREASING" and latest_risk >= 80:
        state = "HIGH PRIORITY"
    elif trajectory == "INCREASING" and latest_risk >= 60:
        state = "EARLY WARNING"
    elif trajectory == "INCREASING":
        state = "INCREASING"
    elif trajectory == "STABLE" and latest_risk >= 60:
        state = "WATCH"
    elif trajectory == "STABLE":
        state = "STABLE"
    else:  # DECREASING
        state = "STABLE"

    return {
        "state": state,
        "trajectory": trajectory,
        "delta": delta,
        "risk_history": risk_scores,
        "signals": signals,
    }
```

- [ ] **Step 4: Run tests**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/test_early_warning.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/zain/SIH-2026
git add src/intelligence/early_warning.py tests/test_early_warning.py
git commit -m "feat: add deterministic risk trajectory and early-warning states"
```

---

## Task 6: Event Queries in queries.py

**Files:**
- Modify: `src/intelligence/queries.py`
- Create: `tests/test_events.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_events.py
"""Integration tests for event query functions in queries.py."""
import pytest
from unittest.mock import patch
from src.intelligence import queries


_MOCK_ALERTS = [
    {"alert_id": "aaa001", "lat": 17.0, "lon": 80.0, "acq_date": "2026-09-01",
     "frp_mw": 40.0, "bt_kelvin": 330.0, "risk_score": 60, "severity": "HIGH",
     "day_night": "N", "dist_nearest_facility_km": 2.0,
     "nearest_facility_type": "thermal power", "predicted_label": "A",
     "prob_A": 0.75, "prob_B": 0.15, "anomaly_flag": 0, "persistence_count": 2,
     "status": "ALERTED", "output_class": "Persistent Thermal Source",
     "output_class_short": "Persistent Source", "output_class_code": "PS-B",
     "state": "Andhra Pradesh", "district": "Visakhapatnam", "zone": None,
     "narrative": "", "in_india": True, "place": "Visakhapatnam, Andhra Pradesh"},
    {"alert_id": "aaa002", "lat": 17.01, "lon": 80.01, "acq_date": "2026-09-02",
     "frp_mw": 65.0, "bt_kelvin": 340.0, "risk_score": 75, "severity": "HIGH",
     "day_night": "N", "dist_nearest_facility_km": 1.8,
     "nearest_facility_type": "thermal power", "predicted_label": "A",
     "prob_A": 0.80, "prob_B": 0.10, "anomaly_flag": 0, "persistence_count": 2,
     "status": "ALERTED", "output_class": "Persistent Thermal Source",
     "output_class_short": "Persistent Source", "output_class_code": "PS-B",
     "state": "Andhra Pradesh", "district": "Visakhapatnam", "zone": None,
     "narrative": "", "in_india": True, "place": "Visakhapatnam, Andhra Pradesh"},
    {"alert_id": "bbb001", "lat": 22.0, "lon": 88.0, "acq_date": "2026-09-01",
     "frp_mw": 10.0, "bt_kelvin": 310.0, "risk_score": 30, "severity": "LOW",
     "day_night": "D", "dist_nearest_facility_km": 20.0,
     "nearest_facility_type": "other", "predicted_label": "B",
     "prob_A": 0.2, "prob_B": 0.6, "anomaly_flag": 0, "persistence_count": 1,
     "status": "DETECTED", "output_class": "Natural Fire Candidate",
     "output_class_short": "Natural Fire", "output_class_code": "PS-C",
     "state": "West Bengal", "district": "Kolkata", "zone": None,
     "narrative": "", "in_india": True, "place": "Kolkata, West Bengal"},
]


def _patch_alerts(mock_alerts):
    import pandas as pd
    return patch.object(queries, "_alerts", return_value=pd.DataFrame(mock_alerts))


def test_list_events_returns_list():
    with _patch_alerts(_MOCK_ALERTS):
        events = queries.list_events()
    assert isinstance(events, list)
    assert len(events) >= 1


def test_nearby_alerts_grouped_into_one_event():
    with _patch_alerts(_MOCK_ALERTS):
        events = queries.list_events()
    # aaa001 and aaa002 are ~1.5km apart on consecutive days → same event
    assert any(len(e.get("alert_ids", [])) == 2 for e in events)


def test_get_event_returns_none_for_missing():
    with _patch_alerts(_MOCK_ALERTS):
        result = queries.get_event("nonexistent")
    assert result is None


def test_get_event_for_alert_finds_event():
    with _patch_alerts(_MOCK_ALERTS):
        result = queries.get_event_for_alert("aaa001")
    assert result is not None
    assert "aaa001" in result["alert_ids"]


def test_get_event_fingerprint_returns_dict():
    with _patch_alerts(_MOCK_ALERTS):
        events = queries.list_events()
        event_id = events[0]["event_id"]
        fp = queries.get_event_fingerprint(event_id)
    assert fp is not None
    assert "behaviour_category" in fp


def test_get_event_evidence_returns_dict():
    with _patch_alerts(_MOCK_ALERTS):
        events = queries.list_events()
        event_id = events[0]["event_id"]
        ev = queries.get_event_evidence(event_id)
    assert ev is not None
    assert "supporting" in ev
    assert "limiting" in ev


def test_get_event_evolution_returns_dict():
    with _patch_alerts(_MOCK_ALERTS):
        events = queries.list_events()
        event_id = events[0]["event_id"]
        evo = queries.get_event_evolution(event_id)
    assert evo is not None
    assert "frames" in evo
    assert "milestones" in evo


def test_get_event_trajectory_returns_dict():
    with _patch_alerts(_MOCK_ALERTS):
        events = queries.list_events()
        event_id = events[0]["event_id"]
        traj = queries.get_event_trajectory(event_id)
    assert traj is not None
    assert "state" in traj
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/test_events.py -v 2>&1 | head -15
```

Expected: `AttributeError: module 'src.intelligence.queries' has no attribute 'list_events'`

- [ ] **Step 3: Add event query functions to queries.py**

Add the following block at the end of `src/intelligence/queries.py` (before `clear_caches`):

```python
# ── public: thermal events ────────────────────────────────────────────────────
@lru_cache(maxsize=8)
def _events_cached(_sig: float) -> list:
    from src.intelligence.clustering import cluster_alerts
    alerts_list = [_row_to_alert(r) for _, r in _alerts().iterrows()]
    return cluster_alerts(alerts_list)


def _event_to_dict(e) -> dict:
    from dataclasses import asdict
    d = asdict(e)
    return d


def _get_event_observations(e) -> list[dict]:
    df = _alerts()
    obs_df = df[df["alert_id"].isin(e.alert_ids)]
    return [_row_to_alert(r) for _, r in obs_df.iterrows()]


def list_events(filters: dict | None = None, sort_by: str = "risk_score",
                limit: int = 500) -> list[dict]:
    events = _events_cached(db_signature())
    dicts = [_event_to_dict(e) for e in events]
    if filters:
        if filters.get("severity"):
            sevs = {s.upper() for s in _as_list(filters["severity"])}
            dicts = [d for d in dicts if d["severity"] in sevs]
        states = geo.resolve_state_filter(_as_list(filters.get("state")), filters.get("region"))
        if states:
            dicts = [d for d in dicts if d.get("state") in states]
        if filters.get("min_risk"):
            dicts = [d for d in dicts if d["risk_score"] >= int(filters["min_risk"])]
    if sort_by in ("frp", "frp_mw"):
        dicts.sort(key=lambda d: d.get("peak_frp_mw") or 0, reverse=True)
    else:
        dicts.sort(key=lambda d: d.get("risk_score", 0), reverse=True)
    return dicts[:limit]


def get_event(event_id: str) -> dict | None:
    events = _events_cached(db_signature())
    for e in events:
        if e.event_id == event_id:
            return _event_to_dict(e)
    return None


def get_event_for_alert(alert_id: str) -> dict | None:
    events = _events_cached(db_signature())
    for e in events:
        if alert_id in e.alert_ids:
            return _event_to_dict(e)
    return None


def get_event_fingerprint(event_id: str) -> dict | None:
    from src.intelligence.fingerprint import compute_fingerprint
    events = _events_cached(db_signature())
    for e in events:
        if e.event_id == event_id:
            return compute_fingerprint(_get_event_observations(e))
    return None


def get_event_evidence(event_id: str) -> dict | None:
    from src.intelligence.evidence import build_evidence
    events = _events_cached(db_signature())
    for e in events:
        if e.event_id == event_id:
            return build_evidence(e, _get_event_observations(e))
    return None


def get_event_evolution(event_id: str) -> dict | None:
    from src.intelligence.evolution import build_evolution
    events = _events_cached(db_signature())
    for e in events:
        if e.event_id == event_id:
            return build_evolution(_get_event_observations(e))
    return None


def get_event_trajectory(event_id: str) -> dict | None:
    from src.intelligence.early_warning import compute_trajectory
    evo = get_event_evolution(event_id)
    if not evo:
        return None
    frames = evo["frames"]
    risk_scores = [f["risk_score"] for f in frames if f.get("risk_score") is not None]
    return compute_trajectory(frames, risk_scores)


def find_increasing_risk_events(limit: int = 10) -> list[dict]:
    events = _events_cached(db_signature())
    result = []
    for e in events:
        traj = get_event_trajectory(e.event_id)
        if traj and traj.get("trajectory") == "INCREASING":
            d = _event_to_dict(e)
            d["trajectory"] = traj
            result.append(d)
    result.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
    return result[:limit]


def events_situation() -> dict:
    """Summary counts for the event layer (Command Center KPIs)."""
    events = _events_cached(db_signature())
    total = len(events)
    high_risk = sum(1 for e in events if e.risk_score >= 60)
    persistent = sum(1 for e in events if e.observation_count >= 3)
    early_warn = 0
    for e in events:
        traj = get_event_trajectory(e.event_id)
        if traj and traj.get("state") in ("EARLY WARNING", "HIGH PRIORITY"):
            early_warn += 1
    return {
        "total_events": total,
        "high_risk_events": high_risk,
        "persistent_sources": persistent,
        "early_warnings": early_warn,
    }
```

Also extend `clear_caches()` at the bottom of `queries.py`:

```python
def clear_caches() -> None:
    _load_alerts_cached.cache_clear()
    _events_cached.cache_clear()       # ADD THIS LINE
    data_date_range.cache_clear()
    _india_facilities.cache_clear()
    incidents.cache_clear()
    geo._resolve_cached.cache_clear()
```

- [ ] **Step 4: Run tests**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/test_events.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: 98 original tests + 8 new = 106 passing, 0 failures.

- [ ] **Step 6: Commit**

```bash
cd /Users/zain/SIH-2026
git add src/intelligence/queries.py tests/test_events.py
git commit -m "feat: add event query functions to queries.py (list_events, get_event, fingerprint, evidence, evolution, trajectory)"
```

---

## Task 7: dashboard/data.py Wrappers

**Files:**
- Modify: `dashboard/data.py`

- [ ] **Step 1: Add event wrappers to dashboard/data.py**

After the line `def DATE_RANGE(): return date_range(_sig())` in `dashboard/data.py`, add:

```python
# ── event queries ────────────────────────────────────────────────────────────
@st.cache_data(ttl=30, show_spinner=False)
def events(_sig: float, filters: dict | None, sort_by: str, limit: int) -> list[dict]:
    return queries.list_events(filters, sort_by=sort_by, limit=limit)


@st.cache_data(ttl=30, show_spinner=False)
def event(_sig: float, event_id: str) -> dict | None:
    return queries.get_event(event_id)


@st.cache_data(ttl=30, show_spinner=False)
def event_for_alert(_sig: float, alert_id: str) -> dict | None:
    return queries.get_event_for_alert(alert_id)


@st.cache_data(ttl=30, show_spinner=False)
def event_fingerprint(_sig: float, event_id: str) -> dict | None:
    return queries.get_event_fingerprint(event_id)


@st.cache_data(ttl=30, show_spinner=False)
def event_evidence(_sig: float, event_id: str) -> dict | None:
    return queries.get_event_evidence(event_id)


@st.cache_data(ttl=30, show_spinner=False)
def event_evolution(_sig: float, event_id: str) -> dict | None:
    return queries.get_event_evolution(event_id)


@st.cache_data(ttl=30, show_spinner=False)
def event_trajectory(_sig: float, event_id: str) -> dict | None:
    return queries.get_event_trajectory(event_id)


@st.cache_data(ttl=30, show_spinner=False)
def events_situation(_sig: float) -> dict:
    return queries.events_situation()


def EVENTS(filters=None, sort_by="risk_score", limit=500):
    return events(_sig(), filters, sort_by, limit)
def EVENT(event_id: str):             return event(_sig(), event_id)
def EVENT_FOR_ALERT(alert_id: str):   return event_for_alert(_sig(), alert_id)
def EVENT_FP(event_id: str):          return event_fingerprint(_sig(), event_id)
def EVENT_EV(event_id: str):          return event_evidence(_sig(), event_id)
def EVENT_EVO(event_id: str):         return event_evolution(_sig(), event_id)
def EVENT_TRAJ(event_id: str):        return event_trajectory(_sig(), event_id)
def EVENTS_SIT():                     return events_situation(_sig())
```

- [ ] **Step 2: Verify import works**

```
cd /Users/zain/SIH-2026 && python -c "from dashboard import data; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /Users/zain/SIH-2026
git add dashboard/data.py
git commit -m "feat: add event data wrappers to dashboard/data.py"
```

---

## Task 8: Agent Tool Registry + Parser Extension

**Files:**
- Modify: `src/intelligence/agent/tools.py`
- Modify: `src/intelligence/agent/deterministic.py`
- Create: `tests/test_agent_events.py`

- [ ] **Step 1: Write failing tests for new agent intents**

```python
# tests/test_agent_events.py
"""Tests for event-aware agent parser extensions."""
from src.intelligence.agent.deterministic import interpret


def test_list_events_intent():
    r = interpret("show me thermal events")
    assert r.intent in ("event_list", "list")


def test_critical_events_intent():
    r = interpret("show critical industrial events")
    assert r.intent in ("event_list",)
    assert r.filters.get("severity") == ["CRITICAL"] or "CRITICAL" in str(r.filters)


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


def test_high_risk_events_in_state():
    r = interpret("show high risk events in Andhra Pradesh")
    assert r.intent in ("event_list",)
    assert "andhra" in str(r.filters).lower() or "andhra" in str(r.args).lower()


def test_rank_events_intent():
    r = interpret("which event has the highest risk")
    assert r.intent in ("event_list", "rank")
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/test_agent_events.py -v 2>&1 | head -20
```

Expected: Most tests fail on missing intent values.

- [ ] **Step 3: Add event tools to tools.py**

Append to `src/intelligence/agent/tools.py` before `READ_ONLY_TOOL_NAMES`:

```python
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
          "Ordered timeline and frame sequence for event evolution replay. "
          "Returns milestones and per-observation frames.",
          lambda event_id: queries.get_event_evolution(event_id),
          {"event_id": {"type": "string"}}))

_reg(Tool("get_event_trajectory",
          "Risk trajectory for a thermal event. Returns state (STABLE / WATCH / "
          "INCREASING / EARLY WARNING / HIGH PRIORITY), delta, and signals.",
          lambda event_id: queries.get_event_trajectory(event_id),
          {"event_id": {"type": "string"}}))

_reg(Tool("find_increasing_risk_events",
          "Find thermal events whose risk trajectory is INCREASING. "
          "Returns events sorted by current risk score.",
          lambda limit=10: queries.find_increasing_risk_events(limit=limit),
          {"limit": {"type": "integer"}}))

_reg(Tool("events_situation",
          "Summary counts for the event layer: total events, high-risk, "
          "persistent sources, early warnings.",
          lambda: queries.events_situation(), {}))
```

- [ ] **Step 4: Extend deterministic.py parser**

In `src/intelligence/agent/deterministic.py`, find the `interpret` function and add event-intent detection BEFORE the existing intent checks. The exact insertion point is at the start of the main intent-matching logic, after initial cleanup/refused-state-change checks.

Add this block:

```python
# ── EVENT INTENTS (check before generic alert intents) ────────────────────
# Detect 8-character hex event IDs (e.g. "abcd1234")
import re as _re
_EVENT_ID_RE = _re.compile(r'\bevent\s+([0-9a-f]{8})\b', _re.I)
_event_id_match = _EVENT_ID_RE.search(text)
_eid = _event_id_match.group(1).lower() if _event_id_match else None

if _eid:
    if any(kw in text for kw in ("fingerprint", "behaviour", "behavior", "signature")):
        return Interpretation(understood=True, tool="get_event_fingerprint",
                              args={"event_id": _eid}, intent="event_fingerprint",
                              message=f"Fetching behaviour fingerprint for event {_eid}.")
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
    if any(kw in text for kw in ("invest", "detail", "about", "open")):
        return Interpretation(understood=True, tool="get_event",
                              args={"event_id": _eid}, intent="event_detail",
                              nav="Investigation",
                              message=f"Opening investigation for event {_eid}.")
    # Default for bare event ID mention → event detail
    return Interpretation(understood=True, tool="get_event",
                          args={"event_id": _eid}, intent="event_detail",
                          nav="Investigation",
                          message=f"Fetching details for event {_eid}.")

# ── Event list intents ────────────────────────────────────────────────────
_is_event_list_req = any(kw in text for kw in (
    "event", "events", "thermal event", "thermal events", "cluster", "clusters"
))
if _is_event_list_req and any(kw in text for kw in ("increasing", "rising", "growing")):
    return Interpretation(understood=True, tool="find_increasing_risk_events",
                          args={"limit": 10}, intent="event_trajectory",
                          message="Finding thermal events with increasing risk trajectory.")

if _is_event_list_req:
    filters: dict = {}
    # Severity
    for sev in ("critical", "high", "medium", "low"):
        if sev in text:
            filters["severity"] = [sev.upper()]
            break
    # State/region (reuse existing geo resolution)
    from src.intelligence import geo as _geo
    # Try to extract a state name from text
    for token in text.replace(",", " ").split():
        cs = _geo.canonical_state(token.title())
        if cs:
            filters["state"] = cs
            break
    return Interpretation(understood=True, tool="list_events",
                          args={"filters": filters or None, "limit": 20},
                          intent="event_list",
                          filters=filters or None,
                          message="Listing thermal events by risk score.")
```

**Important:** The `Interpretation` dataclass must have an `args` field if it doesn't already. Check `deterministic.py` — if `Interpretation` only has `tool` (not `args`), add `args: dict = field(default_factory=dict)`.

Read `deterministic.py` `Interpretation` definition and add `args: dict = field(default_factory=dict)` if missing, then use `args` in the new intents above.

- [ ] **Step 5: Run tests**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/test_agent_events.py tests/test_agent_deterministic.py -v
```

Expected: All new event tests pass. All existing agent tests still pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/zain/SIH-2026
git add src/intelligence/agent/tools.py src/intelligence/agent/deterministic.py tests/test_agent_events.py
git commit -m "feat: extend agent with 8 event tools and event intent parsing"
```

---

## Task 9: Investigation Page Upgrade

**Files:**
- Modify: `dashboard/views/investigation.py`

This is the flagship page. Add panels for: event context, fingerprint, evidence stack, evolution timeline+replay, risk trajectory, early warning.

- [ ] **Step 1: Read deterministic.py Interpretation dataclass first**

```
cd /Users/zain/SIH-2026 && grep -n "Interpretation\|@dataclass\|args" src/intelligence/agent/deterministic.py | head -30
```

Verify `args` field exists or confirm its absence.

- [ ] **Step 2: Implement the upgraded investigation.py**

Replace `dashboard/views/investigation.py` with:

```python
"""Investigation — deep-dive: event context, fingerprint, evidence,
evolution replay, risk trajectory, early warning, detection details.
All values from real data only — nothing fabricated."""
from __future__ import annotations

import pydeck as pdk
import streamlit as st

from dashboard import data, state
from dashboard import theme as T
from dashboard.components import mapview, ui
from dashboard.shell import topbar

_EW_COLORS = {
    "HIGH PRIORITY": T.CRIT,
    "EARLY WARNING": "#f97316",
    "INCREASING": T.HIGH,
    "WATCH": T.MED,
    "STABLE": T.LOW,
    "DECREASING": T.LOW,
    "INSUFFICIENT DATA": T.T2,
    "UNKNOWN": T.T2,
}

_FP_COLORS = {
    "VERY HIGH": T.CRIT,
    "HIGH": T.HIGH,
    "MEDIUM": T.MED,
    "LOW": T.LOW,
    "VERY LOW": "#5a6472",
    "UNKNOWN": T.T2,
}


def _kv(rows: list[tuple[str, str]]) -> None:
    body = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:5px 0;'
        f'border-bottom:1px solid {T.BORDER}"><span style="color:{T.T1};font-size:11px">{k}</span>'
        f'<span style="font-family:var(--mono);font-size:11px;color:{T.T0}">{v}</span></div>'
        for k, v in rows
    )
    st.markdown(f'<div class="panel">{body}</div>', unsafe_allow_html=True)


def _fp_row(label: str, level: str) -> str:
    color = _FP_COLORS.get(level, T.T2)
    return (
        f'<div style="display:flex;justify-content:space-between;padding:5px 0;'
        f'border-bottom:1px solid {T.BORDER}">'
        f'<span style="color:{T.T1};font-size:11px">{label}</span>'
        f'<span style="font-family:var(--mono);font-size:11px;font-weight:700;color:{color}">'
        f'{level}</span></div>'
    )


def _render_fingerprint(fp: dict) -> None:
    ui.section("Thermal Behaviour Fingerprint")
    rows = (
        ("Persistence", fp.get("persistence", "UNKNOWN"))
        , ("Night Activity", fp.get("night_activity", "UNKNOWN"))
        , ("FRP Intensity", fp.get("frp_intensity", "UNKNOWN"))
        , ("Spatial Stability", fp.get("spatial_stability", "UNKNOWN"))
        , ("Industrial Proximity", fp.get("industrial_proximity", "UNKNOWN"))
        , ("Seasonal Alignment", fp.get("seasonal_alignment", "UNKNOWN"))
    )
    body = "".join(_fp_row(lbl, lvl) for lbl, lvl in rows)
    cat = fp.get("behaviour_category", "—")
    st.markdown(
        f'<div class="panel">{body}'
        f'<div style="margin-top:10px;padding-top:8px;border-top:1px solid {T.BORDER_2}">'
        f'<span style="font-size:10px;letter-spacing:.1em;color:{T.T2}">BEHAVIOUR ASSESSMENT</span>'
        f'<div style="font-size:13px;font-weight:700;margin-top:4px">{cat}</div>'
        f'<div style="font-size:10px;color:{T.T2};margin-top:2px;line-height:1.5">'
        f'Behavioural assessment only — not ground truth confirmation.</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def _render_evidence(ev: dict) -> None:
    ui.section("Evidence Stack")
    with st.expander(
            f"✓ {ev['total_supporting']} supporting  ·  "
            f"! {ev['total_limiting']} limiting", expanded=True):
        if ev["supporting"]:
            st.markdown(
                f'<div style="font-size:10px;letter-spacing:.09em;color:{T.LOW};'
                f'font-weight:700;margin-bottom:4px">SUPPORTING</div>',
                unsafe_allow_html=True,
            )
            for item in ev["supporting"]:
                st.markdown(
                    f'<div style="padding:4px 0 6px;border-bottom:1px solid {T.BORDER}">'
                    f'<div style="display:flex;gap:6px;align-items:baseline">'
                    f'<span style="color:{T.LOW};font-size:12px">✓</span>'
                    f'<span style="font-size:11.5px;font-weight:600">{item["label"]}</span>'
                    f'<span style="font-family:var(--mono);font-size:10px;color:{T.T1}">'
                    f'{item["value"]}</span></div>'
                    f'<div style="font-size:10px;color:{T.T2};margin-left:18px;line-height:1.5">'
                    f'{item["explanation"]}</div></div>',
                    unsafe_allow_html=True,
                )
        if ev["limiting"]:
            st.markdown(
                f'<div style="font-size:10px;letter-spacing:.09em;color:{T.MED};'
                f'font-weight:700;margin-top:10px;margin-bottom:4px">LIMITING</div>',
                unsafe_allow_html=True,
            )
            for item in ev["limiting"]:
                st.markdown(
                    f'<div style="padding:4px 0 6px;border-bottom:1px solid {T.BORDER}">'
                    f'<div style="display:flex;gap:6px;align-items:baseline">'
                    f'<span style="color:{T.MED};font-size:12px">!</span>'
                    f'<span style="font-size:11.5px;font-weight:600">{item["label"]}</span>'
                    f'<span style="font-family:var(--mono);font-size:10px;color:{T.T1}">'
                    f'{item["value"]}</span></div>'
                    f'<div style="font-size:10px;color:{T.T2};margin-left:18px;line-height:1.5">'
                    f'{item["explanation"]}</div></div>',
                    unsafe_allow_html=True,
                )


def _render_evolution(evo: dict) -> None:
    ui.section("Event Evolution")
    if evo["observation_count"] < 2:
        st.markdown(
            f'<div class="panel" style="color:{T.T2};font-size:11px">'
            f'Single observation — no evolution to display.</div>',
            unsafe_allow_html=True,
        )
        return

    # Milestone timeline
    milestones = evo.get("milestones", [])
    if milestones:
        timeline_html = ""
        for m in milestones:
            timeline_html += (
                f'<div style="display:flex;gap:10px;padding:5px 0;'
                f'border-bottom:1px solid {T.BORDER}">'
                f'<span style="font-family:var(--mono);font-size:10px;color:{T.T2};min-width:80px">'
                f'{m["timestamp"]}</span>'
                f'<span style="font-size:11px;font-weight:600">{m["label"]}</span>'
                f'<span style="font-size:10px;color:{T.T2}">{m.get("detail", "")}</span>'
                f'</div>'
            )
        st.markdown(f'<div class="panel">{timeline_html}</div>', unsafe_allow_html=True)

    # Frame replay slider
    frames = evo.get("frames", [])
    if len(frames) >= 2:
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
        step = st.slider(
            "Replay frame",
            min_value=1,
            max_value=len(frames),
            value=len(frames),
            key="evo_replay_slider",
        )
        visible = frames[:step]
        f = frames[step - 1]
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Observations visible", f["cumulative_count"])
        col_b.metric("FRP at frame", f'{f["current_frp"]} MW' if f.get("current_frp") else "—")
        col_c.metric("Risk at frame", f'{f["risk_score"]}/100' if f.get("risk_score") else "—")


def _render_trajectory(traj: dict) -> None:
    ui.section("Risk Trajectory")
    state_label = traj.get("state", "UNKNOWN")
    color = _EW_COLORS.get(state_label, T.T2)
    delta = traj.get("delta", 0)
    signals = traj.get("signals", [])
    history = traj.get("risk_history", [])

    st.markdown(
        f'<div class="panel">'
        f'<div style="display:flex;justify-content:space-between;align-items:center">'
        f'<div><span style="font-size:10px;letter-spacing:.1em;color:{T.T2}">STATE</span>'
        f'<div style="font-size:18px;font-weight:700;color:{color};margin-top:2px">'
        f'{state_label}</div></div>'
        f'<div style="text-align:right"><span style="font-size:10px;color:{T.T2}">ΔRISK</span>'
        f'<div style="font-family:var(--mono);font-size:16px;font-weight:700;'
        f'color:{color if delta > 0 else T.LOW}">'
        f'{"+" if delta > 0 else ""}{delta}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if history:
        st.markdown(
            '<div style="font-size:10px;color:#5a6472;margin-top:6px">Risk history: '
            + " → ".join(str(r) for r in history)
            + '</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown("</div>", unsafe_allow_html=True)

    if signals:
        for sig in signals:
            st.markdown(
                f'<div style="font-size:11px;color:{T.T1};padding:2px 0">· {sig}</div>',
                unsafe_allow_html=True,
            )
    st.markdown(
        f'<div style="font-size:10px;color:{T.T2};margin-top:6px;line-height:1.5">'
        f'Risk trajectory reflects observed data only. '
        f'It does not predict future fire behaviour.</div>',
        unsafe_allow_html=True,
    )


def render() -> None:
    topbar("Investigation")
    aid = st.session_state.get("focus_alert_id")

    if not aid:
        ui.page_header("Investigation", "Select an alert to investigate")
        ui.empty_state(
            "No alert selected.",
            "Open an alert from the Alerts feed or a marker on the Map, "
            "or ask the agent \"why is the … alert critical?\".",
            "",
        )
        top = data.R("risk_score", state.filters(), limit=5)
        ui.section("Or start with the highest-risk alerts")
        for a in top:
            if ui.alert_card(a, ago=a["acq_date"], key_prefix="invpick"):
                state.focus_alert(a["alert_id"]); st.rerun()
        return

    inv = data.INV(aid)
    if not inv.get("found"):
        ui.empty_state("That alert is no longer available.", "It may have been re-seeded.")
        state.focus_alert(None)
        return

    # Fetch event intelligence (may be None for isolated detections)
    ev_dict = data.EVENT_FOR_ALERT(aid)
    event_id = ev_dict["event_id"] if ev_dict else None

    h = inv["header"]
    c = T.SEV_COLOR.get(h["severity"], T.T1)

    # ── Event / Alert header ──────────────────────────────────────────────
    event_label = f"EVENT #{event_id}" if event_id else f"DETECTION {aid}"
    obs_count = ev_dict.get("observation_count", 1) if ev_dict else 1
    st.markdown(
        f'<div style="display:flex;align-items:flex-start;justify-content:space-between;'
        f'border-bottom:1px solid {T.BORDER};padding-bottom:12px;margin-bottom:14px">'
        f'<div><div style="font-size:11px;color:{T.T1};font-family:var(--mono)">'
        f'{event_label} · {obs_count} FIRMS detection{"s" if obs_count != 1 else ""}</div>'
        f'<div class="page-h" style="margin-top:4px">{h["output_class_short"]} — {h["location"]}</div>'
        f'<div style="margin-top:6px">{T.sev_chip(h["severity"])} '
        f'<span class="mini">status <em>{h["status"]}</em> · model class probability '
        f'<em>{h["model_class_probability_pct"]}%</em> · predicted '
        f'<em>{h["predicted_label"] or "—"}</em></span></div>'
        f'</div>'
        f'<div style="text-align:right"><div style="font-size:30px;font-weight:700;'
        f'font-family:var(--mono);color:{c};line-height:1">{h["risk_score"]}<span '
        f'style="font-size:13px;color:{T.T2}">/100</span></div>'
        f'<div style="font-size:10px;color:{T.T2};letter-spacing:.1em">RISK SCORE</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1.25, 1], gap="medium")

    with c1:
        ui.section("Detection")
        d = inv["detection"]
        _kv([
            ("Fire Radiative Power",
             f'{d["frp_mw"]} MW' if d["frp_mw"] is not None else "not available"),
            ("Brightness temperature",
             f'{d["bt_kelvin"]} K' if d["bt_kelvin"] is not None else "not available"),
            ("Persistence", f'{d["persistence_count"]} detections in window'),
            ("Detection date", d["acq_date"]),
            ("Day / night", d["day_night"]),
            ("Coordinates", d["coordinates"]),
            ("Instrument", d["instrument"]),
        ])
        if ev_dict and obs_count > 1:
            _kv([
                ("Event observations", str(obs_count)),
                ("Event duration", f'{ev_dict.get("duration_days", 0)} day(s)'),
                ("Event spatial extent", f'{ev_dict.get("spatial_extent_km", 0):.1f} km'),
            ])

        ui.section("Context")
        ctx = inv["context"]
        _kv([
            ("District", ctx.get("district") or "outside India"),
            ("State", ctx.get("state") or "outside India"),
            ("Nearest facility",
             f'{ctx["dist_nearest_facility_km"]} km' if ctx[
                 "dist_nearest_facility_km"] is not None else "not available"),
            ("Facility type", ctx["hazard_facility_type"] or "not available"),
            ("Land-cover context", ctx["land_cover_context"] or "not available"),
        ])

        ui.section("Why this was flagged")
        why = inv["why_flagged"]
        if why:
            st.markdown('<div class="panel">' + "".join(
                f'<div style="padding:4px 0;font-size:11.5px">'
                f'<span style="color:{T.LOW}">✓</span> {w}</div>'
                for w in why) + '</div>', unsafe_allow_html=True)
        else:
            ui.empty_state("Limited supporting signals — low-confidence single detection.")

    with c2:
        ui.section("Location")
        one = data.INV(aid)
        pt = [{
            "alert_id": aid, "lat": one["coords"]["lat"], "lon": one["coords"]["lon"],
            "output_class_short": h["output_class_short"], "severity": h["severity"],
            "risk_score": h["risk_score"], "frp_mw": inv["detection"]["frp_mw"],
            "persistence_count": inv["detection"]["persistence_count"],
            "acq_date": inv["detection"]["acq_date"],
            "place": h["location"], "state": h["state"], "zone": None,
        }]
        st.pydeck_chart(mapview.build_deck(
            pt, colour_by="class", focus_alert_id=aid,
            view=pdk.ViewState(latitude=one["coords"]["lat"],
                               longitude=one["coords"]["lon"], zoom=7.2),
        ), use_container_width=True, height=200)

        ui.section("Classification")
        cl = inv["classification"]
        prob_a_pct = round((cl["prob_A"] or 0) * 100)
        prob_b_pct = round((cl["prob_B_candidate"] or 0) * 100)
        anomaly_val = "YES — pattern anomaly ⚠" if cl["anomaly_flag"] else "no"
        _kv([
            ("Model classification", h["output_class_short"]),
            ("Raw model label", cl["predicted_label"] or "—"),
            ("P(Industrial / Persistent — A)", f"{prob_a_pct}%"),
            ("P(Natural Fire — B)", f"{prob_b_pct}%"),
            ("Anomaly detected", anomaly_val),
        ])
        st.markdown(
            f'<div class="mini" style="line-height:1.6;margin-top:6px">'
            f'<em>{cl["framing"]}</em></div>',
            unsafe_allow_html=True,
        )

        ui.section("Risk assessment")
        factors = inv["risk_assessment"]["factors"]
        if factors:
            st.markdown('<div class="panel">' + "".join(
                f'<div style="display:flex;justify-content:space-between;padding:4px 0;'
                f'font-size:11px"><span>{r}</span>'
                f'<span style="font-family:var(--mono);color:{T.HIGH}">+{p}</span></div>'
                for r, p in factors)
                + f'<div style="display:flex;justify-content:space-between;padding:7px 0 0;'
                f'margin-top:4px;border-top:1px solid {T.BORDER_2};font-size:11.5px;font-weight:700">'
                f'<span>Risk score</span><span style="font-family:var(--mono)">'
                f'{inv["risk_assessment"]["score"]}/100</span></div></div>',
                unsafe_allow_html=True)

    # ── Event intelligence panels (when event exists) ─────────────────────
    if event_id:
        fp = data.EVENT_FP(event_id)
        if fp:
            _render_fingerprint(fp)

        ev = data.EVENT_EV(event_id)
        if ev:
            _render_evidence(ev)

        evo = data.EVENT_EVO(event_id)
        if evo and evo.get("observation_count", 0) > 0:
            _render_evolution(evo)

        traj = data.EVENT_TRAJ(event_id)
        if traj and traj.get("state") != "INSUFFICIENT DATA":
            _render_trajectory(traj)

    # ── Recommended action + manual controls ──────────────────────────────
    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
    ra = inv["recommended_action"]
    st.markdown(
        f'<div class="panel" style="border-left:3px solid {c}">'
        f'<div style="font-size:10.5px;letter-spacing:.12em;color:{T.T1}">RECOMMENDED ACTION</div>'
        f'<div style="font-size:15px;font-weight:700;margin:4px 0 3px">{ra["action"]}</div>'
        f'<div style="font-size:11.5px;color:{T.T1};line-height:1.6">{ra["reason"]}</div></div>',
        unsafe_allow_html=True,
    )
    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Acknowledge", use_container_width=True, key="inv_ack"):
        data.set_status(aid, "acknowledge"); st.rerun()
    if b2.button("Escalate", use_container_width=True, key="inv_esc"):
        data.set_status(aid, "escalate"); st.rerun()
    if b3.button("Resolve", use_container_width=True, key="inv_res"):
        data.set_status(aid, "resolve"); st.rerun()
    if b4.button("Show on map  →", use_container_width=True, key="inv_map"):
        state.request_nav("Map Explorer"); st.rerun()
```

- [ ] **Step 2: Verify no import errors**

```
cd /Users/zain/SIH-2026 && python -c "from dashboard.views.investigation import render; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /Users/zain/SIH-2026
git add dashboard/views/investigation.py
git commit -m "feat: upgrade investigation page with fingerprint, evidence, evolution, and trajectory panels"
```

---

## Task 10: Command Center Event KPIs + Alerts Page Events View

**Files:**
- Modify: `dashboard/views/command_center.py`
- Modify: `dashboard/views/alerts.py`

- [ ] **Step 1: Add Event KPI row to command_center.py**

After the existing KPI row (the `k = st.columns(5)` block, after `st.markdown('<div style="height:8px"></div>'...)`), add:

```python
        # ── Event KPI row ──────────────────────────────────────────────────
        es = data.EVENTS_SIT()
        ek = st.columns(4, gap="small")
        with ek[0]:
            ui.kpi(es["total_events"], "Thermal Events", "clustered detections", icon="⬡")
        with ek[1]:
            ui.kpi(es["high_risk_events"], "High-Risk Events",
                   "risk ≥ 60", color=T.HIGH)
        with ek[2]:
            ui.kpi(es["persistent_sources"], "Persistent Sources",
                   "≥3 observations", color=T.MED)
        with ek[3]:
            ui.kpi(es["early_warnings"], "Early Warnings",
                   "trajectory increasing", color=T.CRIT)
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
```

- [ ] **Step 2: Add EVENTS tab to alerts.py**

Replace the `render()` function content in `dashboard/views/alerts.py` to add a tab toggle:

```python
def render() -> None:
    topbar("Alerts")
    ui.page_header("Alerts", "Full alert feed — DETECT → CLASSIFY → VALIDATE → PRIORITIZE → ACT")

    tab_det, tab_evt = st.tabs(["DETECTIONS", "THERMAL EVENTS"])

    with tab_det:
        filterbar.render(key="alerts_fb")
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)

        alerts = data.A(state.filters(), limit=2000, sort_by="risk_score")
        if not alerts:
            ui.empty_state("No alerts match the current filters.",
                           "Widen the severity, state or date window.",
                           "Use Clear to reset.")
        else:
            npages = max(1, (len(alerts) + _PAGE - 1) // _PAGE)
            page = min(st.session_state.get("alert_page", 0), npages - 1)
            ui.section(f"{len(alerts)} alerts", f"page {page+1} / {npages}")

            cur_sev = None
            for a in alerts[page * _PAGE:(page + 1) * _PAGE]:
                if a["severity"] != cur_sev:
                    cur_sev = a["severity"]
                    n = sum(1 for x in alerts if x["severity"] == cur_sev)
                    c = T.SEV_COLOR[cur_sev]
                    st.markdown(
                        f'<div style="font-size:10.5px;font-weight:700;letter-spacing:.1em;'
                        f'color:{c};padding:10px 0 4px;border-bottom:1px solid {T.BORDER}">'
                        f'{cur_sev} · {n}</div>', unsafe_allow_html=True)

                c1, c2 = st.columns([3, 1])
                with c1:
                    ui.alert_card(a, ago=a["acq_date"], show_button=False, key_prefix="al")
                with c2:
                    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
                    if st.button("View investigation  →", key=f"inv_{a['alert_id']}",
                                 use_container_width=True):
                        state.focus_alert(a["alert_id"])
                        state.request_nav("Investigation")
                        st.rerun()

                with st.expander("Assessment · manual actions"):
                    st.markdown(
                        f'<div class="mini" style="line-height:1.7">{a["narrative"]}</div>',
                        unsafe_allow_html=True,
                    )
                    if a["status"] not in ("EXTINGUISHED",):
                        b1, b2, b3 = st.columns(3)
                        if b1.button("Acknowledge", key=f"ack_{a['alert_id']}"):
                            data.set_status(a["alert_id"], "acknowledge"); st.rerun()
                        if b2.button("Escalate", key=f"esc_{a['alert_id']}"):
                            data.set_status(a["alert_id"], "escalate"); st.rerun()
                        if b3.button("Resolve", key=f"res_{a['alert_id']}"):
                            data.set_status(a["alert_id"], "resolve"); st.rerun()

            pg_cols = st.columns([1, 4, 1])
            if pg_cols[0].button("◀ Prev", key="al_prev", disabled=(page == 0)):
                st.session_state["alert_page"] = page - 1; st.rerun()
            pg_cols[1].markdown(
                f'<div style="text-align:center;font-size:11px;color:{T.T2};padding-top:8px">'
                f'page {page + 1} / {npages}</div>', unsafe_allow_html=True)
            if pg_cols[2].button("Next ▶", key="al_next", disabled=(page >= npages - 1)):
                st.session_state["alert_page"] = page + 1; st.rerun()

    with tab_evt:
        st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)
        events = data.EVENTS(state.filters(), limit=500)
        if not events:
            ui.empty_state("No thermal events in the current data window.", "", "")
        else:
            ui.section(f"{len(events)} thermal events", "sorted by risk score")
            _EW_COLORS_LOCAL = {
                "HIGH PRIORITY": T.CRIT, "EARLY WARNING": "#f97316",
                "INCREASING": T.HIGH, "WATCH": T.MED,
                "STABLE": T.LOW, "DECREASING": T.LOW, "INSUFFICIENT DATA": T.T2,
            }
            for ev in events[:50]:  # limit display to top 50
                ev_id = ev["event_id"]
                sev = ev.get("severity", "LOW")
                c = T.SEV_COLOR.get(sev, T.T1)
                obs = ev.get("observation_count", 1)
                loc = (f'{ev.get("district") or ""}, {ev.get("state") or ""}'.strip(", ")
                       or f'{ev.get("centroid_lat", 0):.3f}, {ev.get("centroid_lon", 0):.3f}')
                st.markdown(
                    f'<div class="panel" style="border-left:3px solid {c};margin-bottom:4px">'
                    f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
                    f'<div>'
                    f'<div style="font-size:10px;font-family:var(--mono);color:{T.T2}">'
                    f'EVENT #{ev_id} · {obs} detection{"s" if obs != 1 else ""}</div>'
                    f'<div style="font-size:13px;font-weight:600;margin-top:2px">'
                    f'{ev.get("output_class_short", "—")} — {loc}</div>'
                    f'</div>'
                    f'<div style="font-family:var(--mono);font-size:18px;font-weight:700;color:{c}">'
                    f'{ev.get("risk_score", 0)}</div>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
                if ev.get("alert_ids"):
                    first_aid = ev["alert_ids"][0]
                    if st.button(f"Investigate event #{ev_id}", key=f"ev_inv_{ev_id}",
                                 use_container_width=False):
                        state.focus_alert(first_aid)
                        state.request_nav("Investigation")
                        st.rerun()
```

- [ ] **Step 3: Verify imports work**

```
cd /Users/zain/SIH-2026 && python -c "
from dashboard.views.command_center import render
from dashboard.views.alerts import render
print('OK')
"
```

- [ ] **Step 4: Run full test suite**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/ -v --tb=short 2>&1 | tail -15
```

Expected: All tests pass, 0 failures.

- [ ] **Step 5: Commit**

```bash
cd /Users/zain/SIH-2026
git add dashboard/views/command_center.py dashboard/views/alerts.py
git commit -m "feat: add event KPIs to command center and THERMAL EVENTS tab to alerts page"
```

---

## Task 11: Map Explorer Event Layer

**Files:**
- Modify: `dashboard/views/map_explorer.py`

Add a "Thermal Events" checkbox that overlays event centroids on the map. Uses the existing `mapview.build_deck` — events are passed as a new `events` parameter by adding a new layer in `mapview.py`, or displayed as a simple separate pydeck layer.

- [ ] **Step 1: Add event centroid layer to map_explorer.py**

After the existing `show_out` checkbox block in `map_explorer.py`, add:

```python
        show_events = st.checkbox("Thermal Events", value=False, key="map_events",
                                  help="Event centroids — one marker per clustered thermal event.")
        st.session_state["show_events"] = show_events
```

Then in the canvas section, after the `deck = mapview.build_deck(...)` call, add an overlay when `show_events` is True:

```python
        if show_events:
            ev_list = data.EVENTS(state.filters(), limit=300)
            if ev_list:
                import pydeck as pdk2
                import json as _json
                ev_pts = [
                    {"lat": e["centroid_lat"], "lon": e["centroid_lon"],
                     "event_id": e["event_id"],
                     "label": f'EVENT #{e["event_id"]} · {e["observation_count"]} obs',
                     "risk_score": e["risk_score"],
                     "severity": e.get("severity", "LOW")}
                    for e in ev_list
                ]
                ev_layer = pdk2.Layer(
                    "ScatterplotLayer",
                    data=ev_pts,
                    get_position=["lon", "lat"],
                    get_radius=8000,
                    get_fill_color=[245, 158, 11, 180],
                    pickable=True,
                )
                ev_deck = pdk2.Deck(
                    layers=[ev_layer],
                    initial_view_state=deck.initial_view_state,
                    tooltip={"text": "{label}\nRisk: {risk_score}"},
                    map_style=deck.map_style,
                )
                st.markdown(
                    f'<div style="font-size:10px;color:{T.T2};margin-top:4px">'
                    f'Event centroids shown as amber circles — '
                    f'click an alert marker to investigate.</div>',
                    unsafe_allow_html=True,
                )
                ui.section(f"{len(ev_list)} thermal events", "centroid overlay")
                st.pydeck_chart(ev_deck, use_container_width=True, height=300)
```

- [ ] **Step 2: Verify no import error**

```
cd /Users/zain/SIH-2026 && python -c "from dashboard.views.map_explorer import render; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
cd /Users/zain/SIH-2026
git add dashboard/views/map_explorer.py
git commit -m "feat: add thermal events centroid layer to map explorer"
```

---

## Task 12: Full Test Suite + Smoke Test

**Files:**
- No new files

- [ ] **Step 1: Run the complete test suite**

```
cd /Users/zain/SIH-2026 && python -m pytest tests/ -v --tb=short 2>&1 | tee /tmp/test_results.txt
tail -25 /tmp/test_results.txt
```

Expected: All tests pass (98 original + new tests). Zero failures.

- [ ] **Step 2: Verify all new modules import cleanly**

```
cd /Users/zain/SIH-2026 && python -c "
from src.intelligence.clustering import cluster_alerts, ThermalEvent
from src.intelligence.fingerprint import compute_fingerprint
from src.intelligence.evidence import build_evidence, EvidenceItem
from src.intelligence.evolution import build_evolution
from src.intelligence.early_warning import compute_trajectory
from src.intelligence import queries
assert hasattr(queries, 'list_events')
assert hasattr(queries, 'get_event')
assert hasattr(queries, 'events_situation')
from src.intelligence.agent import tools
assert 'list_events' in tools.REGISTRY
assert 'get_event_fingerprint' in tools.REGISTRY
from dashboard import data
assert hasattr(data, 'EVENTS')
assert hasattr(data, 'EVENT_FP')
print('All imports OK')
"
```

- [ ] **Step 3: Start the app and smoke test**

```
cd /Users/zain/SIH-2026 && streamlit run dashboard/app.py
```

Manually verify:
- [ ] Command Center loads — event KPIs visible (Active Events, High-Risk Events, Persistent Sources, Early Warnings)
- [ ] Alerts page loads — DETECTIONS and THERMAL EVENTS tabs both visible
- [ ] Thermal Events tab shows event cards with `EVENT #XXXXXXXX` labels
- [ ] Click "Investigate event #XXXXXXXX" → navigates to Investigation
- [ ] Investigation page shows all panels: Detection, Context, Fingerprint, Evidence, Evolution, Risk Trajectory, Recommended Action
- [ ] Evolution slider works (shows frame replay)
- [ ] Map Explorer → Thermal Events checkbox → amber event centroids appear
- [ ] Agent panel: type "show high risk events" → event list response
- [ ] Agent: type "show critical industrial events" → filtered event list
- [ ] Agent: type "which events are increasing in risk" → trajectory results
- [ ] Manual Acknowledge / Escalate / Resolve buttons still work on Investigation page

- [ ] **Step 4: Final commit**

```bash
cd /Users/zain/SIH-2026
git add .
git commit -m "feat: Thermal Event Intelligence Platform — clustering, fingerprint, evidence, evolution, early warning, agent upgrade complete"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Feature 1 — Thermal Event Clustering: Task 1 + Task 6
- [x] Feature 2 — Behaviour Fingerprint: Task 2 + Task 9 (investigation panel)
- [x] Feature 3 — Evidence Stack: Task 3 + Task 9 (investigation panel)
- [x] Feature 4 — Event Evolution Replay: Task 4 + Task 9 (slider replay)
- [x] Feature 5 — Early Warning / Risk Trajectory: Task 5 + Task 9 (trajectory panel)
- [x] Feature 6 — Agent Upgrade: Task 8 (tools + parser)
- [x] Rule 1 — No rewrites: All new modules added alongside existing code
- [x] Rule 2 — Existing features preserved: No existing functions removed
- [x] Rule 3 — Agent read-only: No state-change tools added
- [x] Rule 4 — No fabrication: All values derived from real data; "UNKNOWN" / "INSUFFICIENT DATA" for missing
- [x] Rule 5 — Honest ML: "behaviour assessment, not ground truth" language in fingerprint
- [x] Rule 6 — Offline first: No new external dependencies
- [x] Command Center event KPIs: Task 10
- [x] Alerts DETECTIONS/EVENTS toggle: Task 10
- [x] Map Explorer event mode: Task 11
- [x] Event ID deterministic: SHA256 of sorted alert_ids

**Type consistency check:**
- `ThermalEvent.event_id` → used as `e.event_id` consistently
- `cluster_alerts()` → returns `list[ThermalEvent]`
- `compute_fingerprint(observations: list[dict])` → returns `dict`
- `build_evidence(event: ThermalEvent, observations: list[dict])` → returns `dict`
- `build_evolution(observations: list[dict])` → returns `dict`
- `compute_trajectory(frames: list[dict], risk_scores: list[int])` → returns `dict`
  - Note: Task 5 test calls `compute_trajectory(frames)` — fix: signature should accept just `frames` and derive risk_scores internally, OR update tests. **Chose the cleaner approach: `compute_trajectory(frames)` derives risk_scores internally.**
  - In early_warning.py, change signature to `compute_trajectory(frames: list[dict]) -> dict` and derive `risk_scores` from frames inside.
  - In queries.py `get_event_trajectory`, call `compute_trajectory(frames)` without separate risk_scores arg.

**Placeholder scan:** None found.

**⚠ Fix identified:** `compute_trajectory` signature mismatch between Task 5 tests (1 arg) and Task 6 usage (2 args). The implementation in Task 5 shows `def compute_trajectory(frames, risk_scores)` but tests call `compute_trajectory(_frames([...]))` with 1 arg. Fix: derive risk_scores inside the function from frames, use single-argument signature `compute_trajectory(frames: list[dict]) -> dict`.

Apply fix in `src/intelligence/early_warning.py`: Remove `risk_scores` parameter. Derive internally:
```python
risk_scores = [int(f["risk_score"]) for f in frames if f.get("risk_score") is not None]
```

And in `src/intelligence/queries.py` `get_event_trajectory`, call `compute_trajectory(frames)` without the second argument.
