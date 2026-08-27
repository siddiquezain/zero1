"""
Risk engine — converts a scored FIRMS hotspot into:
  - output_class      (PS-aligned 3-class output)
  - severity          (CRITICAL / HIGH / MEDIUM / LOW — for alert triage)
  - land_cover_context (land-cover integration per PS requirement)
  - hazard_facility_type (PS-specified facility categories)
  - narrative

OUTPUT CLASSES (aligned to PS deliverable i):
    Industrial Fire / Abnormal Thermal Event
        Hotspot anomalous: neither persistent-flare nor natural-fire pattern.
        Signals accidental fires, gas leaks, explosions, abnormal thermal events.
        (model anomaly_flag = 1, i.e. max class probability < 0.55)

    Persistent Industrial Thermal Source
        Continuous thermal signature matching known gas-flare / industrial-heat
        patterns: oil refineries, steel plants, thermal power plants, kilns.
        (model Class A, anomaly_flag = 0)

    Forest / Agricultural Fire
        Natural or crop-residue burning: wildfires, paddy-stubble, savanna.
        (model Class B, anomaly_flag = 0)

LAND-COVER CONTEXT (PS requirement: "integrates land-cover information"):
    Derived from coordinate-based India vegetation/land-use zones + seasonal
    agricultural burning flags + facility proximity. No MODIS raster needed.

FACILITY HAZARD TYPES (PS-specified):
    Oil Refinery / Petrochemical · Thermal Power Plant · Steel / Metal Industry
    Mining / Extraction · LNG / Gas Terminal · Chemical / Pharmaceutical
    Brick Kiln / Ceramic · Industrial Facility (generic)

SEVERITY TIERS (score 0–100):
    CRITICAL  ≥ 65   Anomalous + persistent + near facility/population
    HIGH      ≥ 40   Anomalous or high FRP or persistent near infrastructure
    MEDIUM    ≥ 20   Moderate signal — monitor
    LOW        < 20  Single low-confidence detection
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

# Major Indian population/industrial centres used for proximity context.
# Format: (name, lat, lon, approx_population)
_CITIES = [
    ("Mumbai",       19.0760, 72.8777, 20_000_000),
    ("Delhi",        28.7041, 77.1025, 32_000_000),
    ("Bangalore",    12.9716, 77.5946, 13_000_000),
    ("Hyderabad",    17.3850, 78.4867,  9_500_000),
    ("Chennai",      13.0827, 80.2707,  8_500_000),
    ("Kolkata",      22.5726, 88.3639, 15_000_000),
    ("Ahmedabad",    23.0225, 72.5714,  8_000_000),
    ("Pune",         18.5204, 73.8567,  7_400_000),
    ("Surat",        21.1702, 72.8311,  7_200_000),
    ("Jaipur",       26.9124, 75.7873,  4_000_000),
    ("Lucknow",      26.8467, 80.9462,  4_000_000),
    ("Nagpur",       21.1458, 79.0882,  3_000_000),
    ("Visakhapatnam",17.6868, 83.2185,  2_200_000),
    ("Kanpur",       26.4499, 80.3319,  3_000_000),
    ("Bhopal",       23.2599, 77.4126,  2_100_000),
    ("Patna",        25.5941, 85.1376,  2_000_000),
    ("Ludhiana",     30.9010, 75.8573,  2_000_000),
    ("Ranchi",       23.3441, 85.3096,  1_500_000),
    ("Guwahati",     26.1445, 91.7362,  1_100_000),
    ("Jamshedpur",   22.8046, 86.2029,  1_300_000),
    ("Dhanbad",      23.7957, 86.4304,  1_200_000),
    ("Bhilai",       21.2090, 81.4285,    620_000),
    ("Rourkela",     22.2270, 84.8536,    550_000),
    ("Korba",        22.3595, 82.7501,    400_000),
    ("Angul",        20.8409, 85.1012,    200_000),
    ("Talcher",      20.9466, 85.2309,    110_000),
    ("Jharia",       23.7617, 86.4122,    200_000),
    ("Numaligarh",   26.6683, 93.7135,     50_000),
    ("Jamnagar",     22.4707, 70.0577,    700_000),
    ("Haldia",       22.0667, 88.0833,    200_000),
]


# ── PS-required output class labels ───────────────────────────────────────────
OUTPUT_CLASS_INDUSTRIAL_FIRE = "Industrial Fire / Abnormal Thermal Event"
OUTPUT_CLASS_PERSISTENT_SOURCE = "Persistent Industrial Thermal Source"
OUTPUT_CLASS_NATURAL_FIRE = "Forest / Agricultural Fire"

# ── Facility hazard type mapping (PS-specified categories) ────────────────────
_HAZARD_TYPE_MAP: list[tuple[list[str], str]] = [
    (["refinery", "petroleum", "hpcl", "bpcl", "iocl", "petrochemical", "nrl"],
     "Oil Refinery / Petrochemical"),
    (["coal", "gas", "oil", "thermal", "ntpc", "biomass", "waste", "petcoke", "cogeneration"],
     "Thermal Power Plant"),
    (["steel", "metal", "nalco", "aluminium", "zinc", "iron", "smelter"],
     "Steel / Metal Industry"),
    (["mine", "mining", "quarry", "coalfield", "colliery"],
     "Mining / Extraction"),
    (["lng", "liquefied", "terminal", "port", "jetty"],
     "LNG / Gas Terminal"),
    (["chemical", "pharma", "pesticide", "fertiliser", "fertilizer", "chlor"],
     "Chemical / Pharmaceutical"),
    (["brickyard", "brickworks", "brick", "kiln", "ceramic", "tile"],
     "Brick Kiln / Ceramic"),
    (["nuclear"],
     "Nuclear Power Plant"),
]


def classify_hazard_type(raw_facility_type: str) -> str:
    """Map raw facility_type string to a PS-aligned hazard category."""
    ft = (raw_facility_type or "").lower()
    for keywords, label in _HAZARD_TYPE_MAP:
        if any(k in ft for k in keywords):
            return label
    return "Industrial Facility"


# ── Land-cover context (PS: "integrates land-cover information") ──────────────
# Derived without MODIS raster: coordinate-based Indian land-cover zones +
# agri_season_flag + persistence/facility context.
def _land_cover_context(lat: float, lon: float,
                        agri_flag: int, dist_fac_km: float,
                        persistence: int) -> str:
    # Persistent detection very close to industrial facility → industrial land use
    if dist_fac_km < 2 and persistence >= 2:
        return "Industrial Land Use"

    # Agricultural burning zones (seasonal flag + known crop belts)
    if agri_flag == 1:
        if 28 <= lat <= 32 and 73 <= lon <= 78:  # Punjab / Haryana wheat-rice belt
            return "Cropland — Kharif/Rabi (Punjab/Haryana)"
        if 15 <= lat <= 20 and 76 <= lon <= 81:  # Andhra/Telangana paddy
            return "Cropland — Paddy (Andhra/Telangana)"
        return "Cropland / Agricultural"

    # Dense forest zones (India's major forest belts)
    if 8 <= lat <= 13 and 75 <= lon <= 78:   # Western Ghats south (Kerala/TN)
        return "Dense Forest — Western Ghats"
    if 13 <= lat <= 20 and 73 <= lon <= 76:  # Western Ghats north (Goa/Karnataka)
        return "Dense Forest — Western Ghats"
    if lat >= 25 and lon >= 90:              # Northeast India (Assam, Arunachal, Meghalaya)
        return "Dense Forest — Northeast India"
    if 18 <= lat <= 24 and 80 <= lon <= 85:  # Central India (Chhattisgarh/Odisha forests)
        return "Forest / Savanna — Central India"
    if 21 <= lat <= 26 and 85 <= lon <= 88:  # Jharkhand/West Bengal forests
        return "Forest / Mixed — Jharkhand"

    # Mining / industrial corridors
    if 20 <= lat <= 24 and 83 <= lon <= 87:  # Jharkhand–Odisha coal/steel corridor
        return "Mining / Industrial Corridor"

    # Coastal / port industrial zones
    if lon < 72.5 or (lat < 12 and lon > 79):
        return "Coastal / Port Zone"

    return "Mixed / Unknown"


@dataclass
class RiskResult:
    score: int
    severity: str           # CRITICAL / HIGH / MEDIUM / LOW
    status: str             # DETECTED (initial state)
    output_class: str       # PS-aligned 3-class label
    land_cover_context: str # land-cover integration (PS requirement)
    hazard_facility_type: str  # PS-specified facility category
    narrative: str
    nearest_city: str
    dist_nearest_city_km: float
    near_population: int


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _nearest_city(lat: float, lon: float) -> tuple[str, float, int]:
    best_name, best_dist, best_pop = _CITIES[0][0], 1e9, 0
    for name, clat, clon, pop in _CITIES:
        d = _haversine_km(lat, lon, clat, clon)
        if d < best_dist:
            best_name, best_dist, best_pop = name, d, pop
    return best_name, best_dist, best_pop


def _confidence_high(conf) -> bool:
    if conf in ("h", "high"):
        return True
    try:
        return int(conf) >= 70
    except (TypeError, ValueError):
        return False


def score_row(row: dict | pd.Series) -> RiskResult:
    """Score a single FIRMS hotspot row. Returns a RiskResult."""
    lat = float(row["lat"])
    lon = float(row["lon"])
    frp = float(row.get("frp_mw", 0) or 0)
    persist = int(row.get("persistence_count", 1) or 1)
    dist_fac = float(row.get("dist_nearest_facility_km", 999) or 999)
    fac_type = str(row.get("nearest_facility_type", "unknown") or "unknown")
    anomaly = int(row.get("anomaly_flag", 0) or 0)
    pred = str(row.get("predicted_label", "B_candidate") or "B_candidate")
    conf = row.get("confidence", "n")
    day_night = str(row.get("day_night", "") or "")

    s = 0

    # Anomaly flag
    if anomaly:
        s += 30

    # FRP
    if frp >= 30:
        s += 25
    elif frp >= 15:
        s += 15
    elif frp >= 5:
        s += 8

    # Persistence
    if persist >= 4:
        s += 20
    elif persist >= 2:
        s += 10

    # Facility proximity
    if dist_fac < 1:
        s += 20
    elif dist_fac < 5:
        s += 12
    elif dist_fac < 15:
        s += 6

    # Classifier
    if pred == "A":
        s += 10

    # FIRMS confidence
    if _confidence_high(conf):
        s += 8

    # Nighttime (industrial flares burn continuously; nighttime detection reduces
    # natural-fire noise and increases confidence it's an industrial source)
    if day_night == "N":
        s += 5

    # Population proximity
    city, city_dist_km, city_pop = _nearest_city(lat, lon)
    if city_dist_km < 30:
        s += 10

    # Severity bands
    if s >= 65:
        severity = "CRITICAL"
    elif s >= 40:
        severity = "HIGH"
    elif s >= 20:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    # ── PS output class ───────────────────────────────────────────────────────
    agri_flag = int(row.get("agri_season_flag", 0) or 0)
    if anomaly:
        output_class = OUTPUT_CLASS_INDUSTRIAL_FIRE
    elif pred == "A":
        output_class = OUTPUT_CLASS_PERSISTENT_SOURCE
    else:
        output_class = OUTPUT_CLASS_NATURAL_FIRE

    # ── Land-cover context ────────────────────────────────────────────────────
    land_cover = _land_cover_context(lat, lon, agri_flag, dist_fac, persist)

    # ── Hazard facility type ──────────────────────────────────────────────────
    hazard_type = classify_hazard_type(fac_type)

    # ── Narrative ─────────────────────────────────────────────────────────────
    parts = []
    if anomaly:
        parts.append("Pattern anomaly — neither persistent flare nor natural fire")
    if frp > 0:
        parts.append(f"FRP {frp:.0f} MW")
    if persist > 1:
        parts.append(f"{persist} repeat detections in 5-day window")
    if dist_fac < 15:
        parts.append(f"≤{dist_fac:.1f} km from {hazard_type}")
    if city_dist_km < 50:
        parts.append(f"{city_dist_km:.0f} km from {city} (pop {city_pop:,})")
    parts.append(f"Land cover: {land_cover}")
    narrative = " · ".join(parts) if parts else "Low-confidence single detection"

    return RiskResult(
        score=s,
        severity=severity,
        status="DETECTED",
        output_class=output_class,
        land_cover_context=land_cover,
        hazard_facility_type=hazard_type,
        narrative=narrative,
        nearest_city=city,
        dist_nearest_city_km=round(city_dist_km, 1),
        near_population=city_pop if city_dist_km < 50 else 0,
    )


def score_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply risk scoring to every row. Returns df with new columns added."""
    results = [score_row(row) for _, row in df.iterrows()]
    out = df.copy()
    out["output_class"] = [r.output_class for r in results]
    out["risk_score"] = [r.score for r in results]
    out["severity"] = [r.severity for r in results]
    out["alert_status"] = [r.status for r in results]
    out["land_cover_context"] = [r.land_cover_context for r in results]
    out["hazard_facility_type"] = [r.hazard_facility_type for r in results]
    out["narrative"] = [r.narrative for r in results]
    out["nearest_city"] = [r.nearest_city for r in results]
    out["dist_nearest_city_km"] = [r.dist_nearest_city_km for r in results]
    out["near_population"] = [r.near_population for r in results]
    return out


if __name__ == "__main__":
    import pandas as pd
    df = pd.read_parquet("data/processed/stage6_india_scores.parquet")
    scored = score_dataframe(df)
    print("Severity distribution:")
    print(scored["severity"].value_counts())
    print("\nTop 5 CRITICAL rows:")
    crit = scored[scored["severity"] == "CRITICAL"].nlargest(5, "risk_score")
    print(crit[["lat", "lon", "risk_score", "frp_mw", "persistence_count",
                "dist_nearest_facility_km", "anomaly_flag", "narrative"]].to_string())
