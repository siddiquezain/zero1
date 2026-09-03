"""
Structured evidence stack: supporting and limiting evidence derived from
real alert data only. No values are fabricated.

EvidenceItem:
    category   THERMAL | GEOSPATIAL | BEHAVIOURAL | MODEL | RISK | SYSTEM
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
    neutral: list[dict] = []

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
            "High brightness temperature is consistent with an intense or sustained thermal source.",
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
            neutral.append(_item(
                "GEOSPATIAL", "Industrial Facility Proximity",
                f"{event.dist_nearest_facility_km} km from {event.nearest_facility_type or 'facility'}",
                "NEUTRAL",
                f"Detection is within {event.dist_nearest_facility_km} km of a known facility — "
                "moderate spatial association.",
                "facility_db",
            ))

    if event.state:
        neutral.append(_item(
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
            direction = "SUPPORTING" if prob_pct >= 70 else "NEUTRAL"
            item = _item(
                "MODEL", "Model Classification Confidence",
                f"{prob_pct}% — class {event.predicted_class or '?'}",
                direction,
                f"Model assigns {prob_pct}% probability to class {event.predicted_class}. "
                "This is a proxy classifier, not a confirmed fire determination.",
                "ML_model",
            )
            (supporting if direction == "SUPPORTING" else neutral).append(item)

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
        "neutral": neutral,
        "total_supporting": len(supporting),
        "total_limiting": len(limiting),
    }
