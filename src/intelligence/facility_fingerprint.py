"""
Facility Thermal Fingerprinting — a facility-level behavioural baseline plus a
current-event deviation score.

This is DISTINCT from ``src/intelligence/fingerprint.py``, which fingerprints a
single thermal *event*'s behaviour (6 dimensions → a behaviour category). Here
the subject is an industrial *facility*: "what does this site's thermal activity
normally look like, and how far does the current event depart from it?"

Three scores are kept deliberately separate — never collapsed into one number:

    model class probability   src.alerting.risk_engine / the Random Forest
    risk_score                src.alerting.risk_engine (operational priority)
    thermal_deviation_score   THIS module (baseline-relative behaviour, 0–100)

Everything here is deterministic arithmetic over real observations. No value is
fabricated; where the data cannot support a field it is ``None`` /
``INSUFFICIENT_BASELINE``. No LLM is used to generate explanations.

Honest limitation: the FIRMS NRT feed is a ~5-day rolling window, so a facility
"baseline" is a short-window profile of observed activity, not a multi-month
archive. Facilities without enough observations are reported as
``INSUFFICIENT_BASELINE`` rather than given invented statistics.
"""
from __future__ import annotations

import math
import statistics

# ── tunables (transparent + configurable, per the additive-change brief) ──────
ASSOC_RADIUS_KM = 10.0          # detection ↔ facility association radius
MIN_OBS = 6                     # minimum detections for any baseline
MIN_ACTIVE_DAYS = 2             # ... spread across at least this many distinct dates
MIN_STAT_N = 3                  # minimum non-null values before a robust stat is reported
OK_OBS = 12                     # ≥ this (and ≥ 3 active days) upgrades LIMITED → OK

DEVIATION_LEVELS = ("NORMAL", "ELEVATED", "ABNORMAL", "HIGHLY_ABNORMAL")
BEHAVIOR_CLASSES = ("NORMAL", "ABNORMAL", "INSUFFICIENT_BASELINE")

# Per-signal weights for the combined deviation score. Only signals that can
# actually be computed for a given event contribute; weights are renormalised
# over whatever is available.
SIGNAL_WEIGHTS: dict[str, float] = {
    "intensity": 1.0,      # peak FRP vs facility baseline FRP
    "brightness": 0.8,     # peak brightness temperature vs baseline
    "persistence": 1.0,    # event persistence vs typical
    "day_night": 0.7,      # event timing vs the facility's typical timing
    "seasonal": 0.5,       # event month vs the facility's observed active months
}

# score → level thresholds
_LEVEL_BANDS = ((20, "NORMAL"), (45, "ELEVATED"), (70, "ABNORMAL"))


# ── small robust-statistics helpers ──────────────────────────────────────────
def _clean(values) -> list[float]:
    out: list[float] = []
    for v in values:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f != f:  # NaN
            continue
        out.append(f)
    return out


def _robust_stats(values) -> dict | None:
    """median / IQR / MAD / min / max over the non-null values, or None if there
    are fewer than MIN_STAT_N of them (never fabricate a distribution)."""
    vs = sorted(_clean(values))
    if len(vs) < MIN_STAT_N:
        return None
    med = statistics.median(vs)
    q1, _, q3 = statistics.quantiles(vs, n=4)
    mad = statistics.median([abs(x - med) for x in vs])
    return {
        "median": round(med, 2),
        "iqr": round(q3 - q1, 2),
        "mad": round(mad, 2),
        "min": round(vs[0], 2),
        "max": round(vs[-1], 2),
        "n": len(vs),
    }


def _month_of(day: str | None) -> int | None:
    if not day or len(str(day)) < 7:
        return None
    try:
        return int(str(day)[5:7])
    except ValueError:
        return None


def _x_times(value: float, ref: float) -> str:
    if ref <= 0:
        return "baseline near zero"
    r = value / ref
    if r >= 1.15:
        return f"{r:.1f}× the baseline"
    if r <= 0.85:
        return f"{r:.1f}× the baseline (lower)"
    return "comparable to the baseline"


def _dev_score(value: float, median: float, spread: float, *, floor: float) -> tuple[int, float]:
    """0–100 score for how far `value` sits ABOVE `median`, measured in robust
    spread units (IQR/MAD, floored). Saturating: z=1→33, z=2→55, z=3→70, z=5→86."""
    spread = max(float(spread or 0.0), floor)
    z = max(0.0, (float(value) - float(median)) / spread)
    return round(100 * (1 - math.exp(-z / 2.5))), round(z, 2)


def classify_deviation(score: int | float | None) -> str:
    if score is None:
        return "INSUFFICIENT_BASELINE"
    for threshold, level in _LEVEL_BANDS:
        if score < threshold:
            return level
    return "HIGHLY_ABNORMAL"


def behavior_class(level: str) -> str:
    if level in ("ABNORMAL", "HIGHLY_ABNORMAL"):
        return "ABNORMAL"
    if level in ("NORMAL", "ELEVATED"):
        return "NORMAL"
    return "INSUFFICIENT_BASELINE"


# ── baseline ─────────────────────────────────────────────────────────────────
def build_facility_baseline(facility: dict, observations: list[dict]) -> dict:
    """
    Derive a thermal baseline for one facility from the detections already
    associated with it (the caller does the spatial association and any
    leave-current-event-out exclusion).

    `facility`     : {facility_id, name, facility_type, lat, lon, ...}
    `observations` : alert dicts (keys used: frp_mw, bt_kelvin, persistence_count,
                     day_night, acq_date)

    Returns a plain dict. `baseline_quality` is INSUFFICIENT_BASELINE when the
    history is too thin; fields that the data cannot support stay None.
    """
    obs = list(observations or [])
    dates = sorted({str(o.get("acq_date"))[:10] for o in obs if o.get("acq_date")})
    n = len(obs)

    base: dict = {
        "facility_id": facility.get("facility_id"),
        "facility_name": facility.get("name"),
        "facility_type": facility.get("facility_type"),
        "observation_count": n,
        "active_days": len(dates),
        "baseline_start": dates[0] if dates else None,
        "baseline_end": dates[-1] if dates else None,
        "baseline_quality": "INSUFFICIENT_BASELINE",
        "assoc_radius_km": ASSOC_RADIUS_KM,
        "frp": None,
        "bt": None,
        "median_persistence": None,
        "max_persistence": None,
        "night_ratio": None,
        "day_ratio": None,
        "typical_day_night": None,
        "active_months": [],
        "notes": [],
    }

    if n < MIN_OBS or len(dates) < MIN_ACTIVE_DAYS:
        base["notes"].append(
            f"Only {n} observation(s) across {len(dates)} day(s) within "
            f"{ASSOC_RADIUS_KM:.0f} km — below the {MIN_OBS}-observation / "
            f"{MIN_ACTIVE_DAYS}-day minimum for a baseline."
        )
        return base

    base["baseline_quality"] = (
        "OK" if (n >= OK_OBS and len(dates) >= 3) else "LIMITED"
    )
    base["frp"] = _robust_stats(o.get("frp_mw") for o in obs)
    base["bt"] = _robust_stats(o.get("bt_kelvin") for o in obs)

    persist = [int(o.get("persistence_count") or 1) for o in obs]
    base["median_persistence"] = round(statistics.median(persist), 1)
    base["max_persistence"] = max(persist)

    dn = [o.get("day_night") for o in obs if o.get("day_night") in ("D", "N")]
    if dn:
        nr = sum(1 for x in dn if x == "N") / len(dn)
        base["night_ratio"] = round(nr, 2)
        base["day_ratio"] = round(1 - nr, 2)
        base["typical_day_night"] = "N" if nr >= 0.6 else "D" if nr <= 0.4 else "MIXED"

    base["active_months"] = sorted(
        {m for m in (_month_of(o.get("acq_date")) for o in obs) if m}
    )

    if base["frp"] is None and base["bt"] is None:
        base["notes"].append(
            "No FRP or brightness-temperature values in the window — "
            "intensity baseline unavailable."
        )
    if base["baseline_quality"] == "LIMITED":
        base["notes"].append(
            "Short-window baseline (FIRMS NRT is ~5 days) — treat as indicative, "
            "not a long-run profile."
        )
    return base


# ── current-event vs baseline deviation ──────────────────────────────────────
def compare_event_to_baseline(event: dict, baseline: dict | None) -> dict:
    """
    Compare a thermal event (dict from clustering.ThermalEvent) against a facility
    baseline. Returns a deviation dict. Never claims a confirmed fire.

    `event` keys used: peak_frp_mw, max_bt_kelvin, persistence_count,
                       night_count, day_count, start_date
    """
    out: dict = {
        "facility_id": (baseline or {}).get("facility_id"),
        "facility_name": (baseline or {}).get("facility_name"),
        "baseline_quality": (baseline or {}).get("baseline_quality", "INSUFFICIENT_BASELINE"),
        "thermal_deviation_score": None,
        "thermal_deviation_level": "INSUFFICIENT_BASELINE",
        "thermal_behavior_class": "INSUFFICIENT_BASELINE",
        "signals": [],
        "evidence": [],
        "interpretation": "",
        "note": (
            "Deviation from the facility's own observed baseline. Separate from the "
            "model class probability and the risk score; not a confirmed-fire "
            "determination."
        ),
    }

    if not baseline or baseline.get("baseline_quality") == "INSUFFICIENT_BASELINE":
        notes = (baseline or {}).get("notes") or []
        out["evidence"].append(
            notes[0] if notes else "Insufficient facility history for a baseline."
        )
        out["interpretation"] = "Insufficient baseline — deviation cannot be assessed."
        return out

    signals: list[tuple[str, int, str]] = []

    # ── intensity — peak FRP vs baseline FRP ────────────────────────────────
    b_frp = baseline.get("frp")
    ev_frp = event.get("peak_frp_mw")
    if b_frp and ev_frp is not None:
        if ev_frp > b_frp["median"]:
            sc, _ = _dev_score(ev_frp, b_frp["median"], b_frp["iqr"] or b_frp["mad"], floor=5.0)
            signals.append(("intensity", sc,
                            f"Peak FRP {ev_frp:g} MW vs facility baseline median "
                            f"{b_frp['median']:g} MW ({_x_times(ev_frp, b_frp['median'])})"))
        else:
            signals.append(("intensity", 0,
                            f"Peak FRP {ev_frp:g} MW is at or below the facility "
                            f"baseline median ({b_frp['median']:g} MW)"))

    # ── brightness temperature ─────────────────────────────────────────────
    b_bt = baseline.get("bt")
    ev_bt = event.get("max_bt_kelvin")
    if b_bt and ev_bt is not None:
        if ev_bt > b_bt["median"]:
            sc, _ = _dev_score(ev_bt, b_bt["median"], b_bt["iqr"] or b_bt["mad"], floor=3.0)
            signals.append(("brightness", sc,
                            f"Peak brightness temperature {ev_bt:g} K vs baseline "
                            f"median {b_bt['median']:g} K"))
        else:
            signals.append(("brightness", 0,
                            f"Brightness temperature {ev_bt:g} K is within the "
                            f"facility baseline"))

    # ── persistence ───────────────────────────────────────────────────────
    b_pers = baseline.get("median_persistence")
    ev_pers = event.get("persistence_count")
    if b_pers is not None and ev_pers:
        ev_pers = int(ev_pers)
        if ev_pers > b_pers:
            sc, _ = _dev_score(ev_pers, b_pers, max(b_pers * 0.5, 1.0), floor=1.0)
            signals.append(("persistence", sc,
                            f"Event persistence ({ev_pers}) exceeds the facility "
                            f"typical ({b_pers:g})"))
        else:
            signals.append(("persistence", 0,
                            f"Event persistence ({ev_pers}) is within the facility "
                            f"typical ({b_pers:g})"))

    # ── day / night timing ────────────────────────────────────────────────
    tdn = baseline.get("typical_day_night")
    ev_night = int(event.get("night_count") or 0)
    ev_day = int(event.get("day_count") or 0)
    if tdn in ("D", "N") and (ev_night + ev_day) > 0:
        ev_majority = "N" if ev_night >= ev_day else "D"
        if ev_majority != tdn:
            signals.append(("day_night", 60,
                            f"Event is mostly {'night' if ev_majority == 'N' else 'day'}-time; "
                            f"this facility is historically "
                            f"{'night' if tdn == 'N' else 'day'}-active"))
        else:
            signals.append(("day_night", 0,
                            "Event timing matches the facility's typical day/night pattern"))

    # ── seasonal (month membership) ───────────────────────────────────────
    months = baseline.get("active_months") or []
    ev_month = _month_of(event.get("start_date"))
    if months and ev_month and ev_month not in months:
        signals.append(("seasonal", 50,
                        f"Event month ({ev_month:02d}) is outside the facility's "
                        f"observed active months "
                        f"({', '.join(f'{m:02d}' for m in months)})"))

    if not signals:
        out["interpretation"] = "No comparable signals between the event and the baseline."
        return out

    num = sum(sc * SIGNAL_WEIGHTS.get(name, 1.0) for name, sc, _ in signals)
    den = sum(SIGNAL_WEIGHTS.get(name, 1.0) for name, _, _ in signals)
    score = round(num / den) if den else 0
    level = classify_deviation(score)

    out["thermal_deviation_score"] = score
    out["thermal_deviation_level"] = level
    out["thermal_behavior_class"] = behavior_class(level)
    out["signals"] = [{"name": n, "score": sc, "detail": d} for n, sc, d in signals]
    out["evidence"] = [d for _, sc, d in signals if sc >= 20]
    out["interpretation"] = _interpret(level)
    return out


def _interpret(level: str) -> str:
    return {
        "NORMAL": "Consistent with this facility's normal thermal behaviour — "
                  "monitor and keep as baseline.",
        "ELEVATED": "Somewhat above this facility's normal behaviour — worth a "
                    "look on the next satellite pass.",
        "ABNORMAL": "Materially different from this facility's observed baseline "
                    "— recommend operator validation.",
        "HIGHLY_ABNORMAL": "Strong departure from this facility's observed "
                           "baseline — prioritise for operator validation.",
    }.get(level, "Insufficient baseline — deviation cannot be assessed.")
