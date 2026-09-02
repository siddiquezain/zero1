"""
Offline lat/lon -> Indian state / district resolver.

No network, no geospatial runtime dependency. Uses a bundled, simplified
admin-boundary GeoJSON (`data/geo/india_admin.geojson`: dissolved state polygons
+ district polygons) and a pure-Python ray-casting point-in-polygon test with a
per-feature bounding-box pre-filter.

`resolve(lat, lon)` returns the authoritative geographic context for a point:
    {"state": str|None, "district": str|None, "in_india": bool, "zone": str}

A point that is not inside any Indian state polygon has `in_india=False` and a
coarse `zone` label ("Sri Lanka", "Bay of Bengal", ...). Coordinates are NEVER
transformed, swapped, or clipped here — this module only *classifies* points.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable

_GEO_PATH = Path(__file__).resolve().parents[2] / "data/geo/india_admin.geojson"

INDIA_BBOX = (6.0, 37.5, 67.5, 97.5)  # lat_min, lat_max, lon_min, lon_max (generous)

# region -> set of member states (lowercase region keys)
REGIONS: dict[str, set[str]] = {
    "eastern india": {"Odisha", "Jharkhand", "West Bengal", "Bihar"},
    "northern india": {"Punjab", "Haryana", "Delhi", "Uttar Pradesh", "Uttarakhand",
                       "Himachal Pradesh", "Jammu and Kashmir", "Rajasthan",
                       "Chandigarh", "Ladakh"},
    "southern india": {"Tamil Nadu", "Kerala", "Karnataka", "Andhra Pradesh",
                       "Telangana", "Puducherry"},
    "western india": {"Gujarat", "Maharashtra", "Goa"},
    "central india": {"Madhya Pradesh", "Chhattisgarh"},
    "northeastern india": {"Assam", "Meghalaya", "Manipur", "Mizoram", "Nagaland",
                           "Tripura", "Arunachal Pradesh", "Sikkim"},
}
_REGION_ALIASES = {
    "east india": "eastern india", "the east": "eastern india",
    "north india": "northern india", "south india": "southern india",
    "west india": "western india", "central india": "central india",
    "north east india": "northeastern india", "north-east india": "northeastern india",
    "northeast india": "northeastern india", "ne india": "northeastern india",
}
_STATE_ALIASES = {
    "orissa": "Odisha", "pondicherry": "Puducherry", "j&k": "Jammu and Kashmir",
    "jk": "Jammu and Kashmir", "up": "Uttar Pradesh", "mp": "Madhya Pradesh",
    "tn": "Tamil Nadu", "ap": "Andhra Pradesh", "wb": "West Bengal",
    "ncr": "Delhi", "new delhi": "Delhi", "bengal": "West Bengal",
    "bangalore": None,  # a city, not a state — guard against misuse
}

# Coarse zones for points that fall outside every Indian state polygon.
# lat_min, lat_max, lon_min, lon_max, label
_OUTSIDE_ZONES = [
    (5.7, 10.0, 79.5, 82.2, "Sri Lanka"),
    (23.6, 26.7, 88.0, 92.7, "Bangladesh"),
    (26.3, 30.6, 80.0, 88.3, "Nepal"),
    (26.6, 28.4, 88.7, 92.2, "Bhutan"),
    (9.0, 28.6, 92.2, 101.2, "Myanmar"),
    (23.6, 37.5, 60.0, 77.2, "Pakistan"),
    (28.0, 37.5, 77.0, 100.0, "China / Tibetan Plateau"),
    (5.5, 22.5, 80.5, 95.0, "Bay of Bengal"),
    (5.5, 24.0, 60.0, 71.8, "Arabian Sea"),
]


# ── geometry loading ─────────────────────────────────────────────────────────
def _rings_of(geom) -> list[list[list[tuple[float, float]]]]:
    """Normalise Polygon / MultiPolygon into list[ polygon ] where
    polygon = [exterior_ring, hole1, ...] and ring = [(lon, lat), ...]."""
    t = geom["type"]
    coords = geom["coordinates"]
    polys = coords if t == "MultiPolygon" else [coords]
    out = []
    for poly in polys:
        out.append([[(float(x), float(y)) for x, y in ring] for ring in poly])
    return out


def _bbox_of(polys) -> tuple[float, float, float, float]:
    xs = [x for poly in polys for ring in poly for (x, _) in ring]
    ys = [y for poly in polys for ring in poly for (_, y) in ring]
    return (min(xs), min(ys), max(xs), max(ys))  # lon_min, lat_min, lon_max, lat_max


@lru_cache(maxsize=1)
def _load():
    doc = json.loads(_GEO_PATH.read_text())
    states, districts = [], []
    for f in doc["features"]:
        p = f["properties"]
        polys = _rings_of(f["geometry"])
        rec = {"state": p["state"], "district": p.get("district"),
               "polys": polys, "bbox": _bbox_of(polys)}
        (states if p["kind"] == "state" else districts).append(rec)
    return states, districts


def _pt_in_ring(x: float, y: float, ring) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _pt_in_polys(x: float, y: float, polys) -> bool:
    for poly in polys:
        if not poly:
            continue
        if _pt_in_ring(x, y, poly[0]) and not any(_pt_in_ring(x, y, h) for h in poly[1:]):
            return True
    return False


def _in_bbox(x, y, bbox) -> bool:
    lo_x, lo_y, hi_x, hi_y = bbox
    return lo_x <= x <= hi_x and lo_y <= y <= hi_y


# ── public: point resolution ────────────────────────────────────────────────
def in_india_bbox(lat, lon) -> bool:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    la0, la1, lo0, lo1 = INDIA_BBOX
    return la0 <= lat <= la1 and lo0 <= lon <= lo1


def _zone_for(lat: float, lon: float) -> str:
    for la0, la1, lo0, lo1, label in _OUTSIDE_ZONES:
        if la0 <= lat <= la1 and lo0 <= lon <= lo1:
            return label
    return "outside India"


# Boundary tolerance: a point this far outside a state polygon is still counted
# as that state. Accounts for polygon simplification (~1 km) + the FIRMS pixel
# footprint (375 m - 1 km). NOT a coordinate clip — the point keeps its real
# lat/lon; only its state *classification* is snapped to the adjacent boundary.
_EDGE_TOL_DEG = 0.03


def _state_at(lon: float, lat: float, states) -> str | None:
    for s in states:
        if _in_bbox(lon, lat, s["bbox"]) and _pt_in_polys(lon, lat, s["polys"]):
            return s["state"]
    return None


@lru_cache(maxsize=20000)
def _resolve_cached(lat_r: float, lon_r: float) -> tuple[str | None, str | None, bool, str]:
    lat, lon = lat_r, lon_r
    states, districts = _load()

    hit_state = _state_at(lon, lat, states)
    on_edge = False
    if hit_state is None:
        # second pass: is the point within the boundary tolerance of a state?
        for dlon, dlat in ((_EDGE_TOL_DEG, 0), (-_EDGE_TOL_DEG, 0),
                           (0, _EDGE_TOL_DEG), (0, -_EDGE_TOL_DEG)):
            hit_state = _state_at(lon + dlon, lat + dlat, states)
            if hit_state:
                on_edge = True
                break

    if hit_state is None:
        return None, None, False, _zone_for(lat, lon)

    hit_district = None
    if not on_edge:
        for d in districts:
            if d["state"] != hit_state:
                continue
            if _in_bbox(lon, lat, d["bbox"]) and _pt_in_polys(lon, lat, d["polys"]):
                hit_district = d["district"]
                break
    return hit_state, hit_district, True, hit_state


def resolve(lat, lon) -> dict:
    """Authoritative geographic classification of a point. Never mutates coords."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return {"state": None, "district": None, "in_india": False, "zone": "unknown"}
    st, dist, ok, zone = _resolve_cached(round(lat, 4), round(lon, 4))
    return {"state": st, "district": dist, "in_india": ok, "zone": zone}


def state_for_point(lat, lon) -> str | None:
    return resolve(lat, lon)["state"]


def district_for_point(lat, lon) -> str | None:
    return resolve(lat, lon)["district"]


def place_label(lat, lon) -> str:
    """Human location string from coordinates alone (authoritative)."""
    r = resolve(lat, lon)
    if r["in_india"]:
        return f"{r['district']}, {r['state']}" if r["district"] else r["state"]
    return r["zone"]


# ── regions / names ─────────────────────────────────────────────────────────
def normalise_region(name: str | None) -> str | None:
    if not name:
        return None
    key = " ".join(str(name).strip().lower().split())
    key = _REGION_ALIASES.get(key, key)
    return key if key in REGIONS else None


def states_in_region(name: str | None) -> set[str]:
    key = normalise_region(name)
    return set(REGIONS.get(key, set())) if key else set()


@lru_cache(maxsize=1)
def all_states() -> tuple[str, ...]:
    states, _ = _load()
    return tuple(sorted({s["state"] for s in states}))


def canonical_state(name: str | None) -> str | None:
    if not name:
        return None
    q = " ".join(str(name).strip().lower().split())
    for canon in all_states():
        if canon.lower() == q:
            return canon
    alias = _STATE_ALIASES.get(q, "__missing__")
    return alias if alias != "__missing__" else None


def resolve_state_filter(states: Iterable[str] | None, region: str | None) -> set[str]:
    out: set[str] = set()
    known = set(all_states())
    for s in (states or []):
        c = canonical_state(s) or (s if s in known else None)
        if c:
            out.add(c)
    out |= states_in_region(region)
    return out


def match_locations(text: str) -> dict:
    if not text:
        return {"states": set(), "region": None}
    low = " ".join(str(text).lower().split())
    region = None
    for rk in list(REGIONS) + list(_REGION_ALIASES):
        if rk in low:
            region = normalise_region(rk)
            break
    states: set[str] = set()
    if region:
        states |= states_in_region(region)
    for canon in all_states():
        if canon.lower() in low:
            states.add(canon)
    for alias in ("orissa", "pondicherry", "bengal"):
        c = canonical_state(alias)
        if alias in low and c:
            states.add(c)
    return {"states": states, "region": region}


# ── dataframe helpers ───────────────────────────────────────────────────────
def annotate(df, lat_col: str = "lat", lon_col: str = "lon"):
    """Add `state`, `district`, `in_india`, `zone` columns from coordinates."""
    if df is None or len(df) == 0:
        return df
    df = df.copy()
    res = [resolve(la, lo) for la, lo in zip(df[lat_col], df[lon_col])]
    df["state"] = [r["state"] for r in res]
    df["district"] = [r["district"] for r in res]
    df["in_india"] = [r["in_india"] for r in res]
    df["zone"] = [r["zone"] for r in res]
    return df


# backwards-compatible alias
def annotate_states(df, lat_col: str = "lat", lon_col: str = "lon", out_col: str = "state"):
    return annotate(df, lat_col, lon_col)


def audit_points(df, lat_col: str = "lat", lon_col: str = "lon", sample: int = 6) -> dict:
    """Development validation report for a set of plotted points (requirement #10)."""
    if df is None or len(df) == 0:
        return {"plotted": 0}
    d = annotate(df, lat_col, lon_col)
    la0, la1, lo0, lo1 = INDIA_BBOX
    outside_bbox = d[(d[lat_col] < la0) | (d[lat_col] > la1) |
                     (d[lon_col] < lo0) | (d[lon_col] > lo1)]
    outside_india = d[~d["in_india"]]
    id_col = "alert_id" if "alert_id" in d.columns else (
        "feature_id" if "feature_id" in d.columns else None)
    samp_cols = [c for c in (id_col, lat_col, lon_col, "state", "district", "zone",
                             "nearest_city") if c and c in d.columns]
    return {
        "plotted": int(len(d)),
        "in_india": int(d["in_india"].sum()),
        "outside_india": int(len(outside_india)),
        "outside_india_bbox": int(len(outside_bbox)),
        "lat_min": round(float(d[lat_col].min()), 4),
        "lat_max": round(float(d[lat_col].max()), 4),
        "lon_min": round(float(d[lon_col].min()), 4),
        "lon_max": round(float(d[lon_col].max()), 4),
        "outside_zones": {k: int(v) for k, v in
                          outside_india["zone"].value_counts().items()},
        "sample_in_india": d[d["in_india"]][samp_cols].head(sample).to_dict("records"),
        "sample_outside": outside_india[samp_cols].head(sample).to_dict("records"),
    }
