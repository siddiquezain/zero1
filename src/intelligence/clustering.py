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
from collections import Counter
from dataclasses import dataclass
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
    alert_ids = list(dict.fromkeys(a["alert_id"] for a in group))

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

    probs = [max(float(a.get("prob_A") or 0), float(a.get("prob_B") or 0)) for a in group]

    labels = [a.get("predicted_label") for a in group if a.get("predicted_label")]
    pred_class = Counter(labels).most_common(1)[0][0] if labels else None

    max_risk = max((int(a.get("risk_score") or 0) for a in group), default=0)
    max_sev = max(
        (a.get("severity") or "LOW" for a in group),
        key=lambda s: _SEVERITY_ORDER.get(s, 0),
        default="LOW",
    )

    closest = min(group, key=lambda a: float(a.get("dist_nearest_facility_km") or 9999))
    near_fac_dist = (float(closest["dist_nearest_facility_km"])
                     if closest.get("dist_nearest_facility_km") is not None else None)
    near_fac_type = closest.get("nearest_facility_type") or None

    states = [a.get("state") for a in group if a.get("state")]
    top_state = Counter(states).most_common(1)[0][0] if states else None

    districts = [a.get("district") for a in group if a.get("district")]
    top_district = Counter(districts).most_common(1)[0][0] if districts else None

    zones = [a.get("zone") for a in group if a.get("zone")]
    top_zone = Counter(zones).most_common(1)[0][0] if zones else None

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
    Group alerts into ThermalEvent objects.

    Two alerts belong to the same event when:
      - haversine distance <= spatial_km
      - date gap <= temporal_days

    Returns events sorted by risk_score descending.
    """
    if not alerts:
        return []

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

    groups: dict[int, list[dict]] = {}
    for i, a in enumerate(uniq):
        root = _find(parent, i)
        groups.setdefault(root, []).append(a)

    events = [_build_event(g) for g in groups.values()]
    events.sort(key=lambda e: e.risk_score, reverse=True)
    return events
