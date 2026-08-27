"""
Stage 2 — Facility / context layer ingestion.

Downloads and normalises:
  1. WRI Global Power Plant Database (already confirmed accessible)
  2. OSM industrial polygons via Overpass API (for India)
  3. GEM trackers (if CSV exports are available)

Output: /data/raw/facilities/ raw files + provenance metadata
        /data/processed/facilities.parquet — normalised facility table

Normalised schema:
    facility_id  str      e.g. "GPPD-WRI1020239", "OSM-123456"
    lat          float
    lon          float
    facility_type str     e.g. "Coal", "Oil", "Gas", "Refinery", "industrial"
    source       str      "GPPD", "OSM", "GEM"
    name         str      (best available)
    country      str      ISO 3166-1 alpha-3

IMPORTANT: facility proximity is a FEATURE, not a label.
This table is used only to compute distance/type features in Stage 4.
"""
from __future__ import annotations

import io
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from .config import FACILITIES_RAW, OVERPASS_URL, PROCESSED_DIR
from .utils import download_file, make_session, sha256, write_metadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

# ── WRI GPPD ─────────────────────────────────────────────────────────────────
_GPPD_URL = (
    "https://datasets.wri.org/private-admin/dataset/"
    "53623dfd-3df6-4f15-a091-67457cdb571f/resource/"
    "66bcdacc-3d0e-46ad-9271-a5a76b1853d2/download/"
    "globalpowerplantdatabasev130.zip"
)
_GPPD_ZIP = FACILITIES_RAW / "globalpowerplantdatabasev130.zip"
_GPPD_CSV = FACILITIES_RAW / "global_power_plant_database.csv"


def ingest_gppd(session: requests.Session | None = None) -> pd.DataFrame:
    """Download (if needed) and load the WRI GPPD."""
    sess = session or make_session()

    if not _GPPD_CSV.exists():
        log.info("Downloading WRI Global Power Plant Database …")
        FACILITIES_RAW.mkdir(parents=True, exist_ok=True)
        try:
            download_file(_GPPD_URL, _GPPD_ZIP, session=sess)
        except requests.HTTPError as exc:
            log.error("Failed to download GPPD: %s — trying cached file.", exc)
            if not _GPPD_ZIP.exists():
                raise

        with zipfile.ZipFile(_GPPD_ZIP) as zf:
            names = zf.namelist()
            csv_name = next((n for n in names if n.endswith(".csv")), None)
            if csv_name is None:
                raise RuntimeError(f"No CSV found in GPPD zip. Contents: {names}")
            zf.extract(csv_name, FACILITIES_RAW)
            extracted = FACILITIES_RAW / csv_name
            if extracted != _GPPD_CSV:
                extracted.rename(_GPPD_CSV)

    df = pd.read_csv(_GPPD_CSV)
    write_metadata(
        _GPPD_CSV,
        {
            "source": "WRI Global Power Plant Database v1.3.0",
            "url": _GPPD_URL,
            "row_count": len(df),
            "sha256": sha256(_GPPD_CSV),
            "download_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    log.info("GPPD: %d rows, %d columns", len(df), len(df.columns))
    return df


def normalise_gppd(df: pd.DataFrame) -> pd.DataFrame:
    """Select and rename GPPD columns into the normalised facility schema."""
    out = pd.DataFrame(
        {
            "facility_id": "GPPD-" + df["gppd_idnr"].astype(str),
            "lat": pd.to_numeric(df["latitude"], errors="coerce"),
            "lon": pd.to_numeric(df["longitude"], errors="coerce"),
            "facility_type": df["primary_fuel"].fillna("Unknown"),
            "source": "GPPD",
            "name": df["name"].fillna(""),
            "country": df["country"].fillna(""),
        }
    )
    before = len(out)
    out = out.dropna(subset=["lat", "lon"])
    dropped = before - len(out)
    if dropped:
        log.warning("Dropped %d GPPD rows with missing lat/lon", dropped)
    return out.reset_index(drop=True)


# ── OSM Overpass ──────────────────────────────────────────────────────────────
_OSM_RAW = FACILITIES_RAW / "osm_industrial_india.json"

# Overpass query: nodes+ways tagged landuse=industrial within India bbox
_OVERPASS_QUERY = """
[out:json][timeout:180];
(
  node["landuse"="industrial"](6.0,68.0,37.0,97.5);
  way["landuse"="industrial"](6.0,68.0,37.0,97.5);
);
out center;
"""


def ingest_osm(session: requests.Session | None = None) -> pd.DataFrame:
    """Fetch OSM industrial polygons for India via Overpass and return a DataFrame."""
    sess = session or make_session()

    if _OSM_RAW.exists():
        log.info("OSM cache hit: %s", _OSM_RAW)
        import json
        data = json.loads(_OSM_RAW.read_text())
    else:
        log.info("Querying Overpass API for OSM industrial features (India) …")
        try:
            resp = sess.post(
                OVERPASS_URL,
                data={"data": _OVERPASS_QUERY},
                timeout=200,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.error("Overpass request failed: %s", exc)
            log.warning("OSM data not available — skipping.")
            return pd.DataFrame(columns=["facility_id", "lat", "lon",
                                         "facility_type", "source", "name", "country"])
        import json
        data = resp.json()
        _OSM_RAW.parent.mkdir(parents=True, exist_ok=True)
        _OSM_RAW.write_text(json.dumps(data))
        write_metadata(
            _OSM_RAW,
            {
                "source": "OpenStreetMap via Overpass API",
                "query": _OVERPASS_QUERY.strip(),
                "element_count": len(data.get("elements", [])),
                "download_utc": datetime.now(timezone.utc).isoformat(),
            },
        )

    elements = data.get("elements", [])
    log.info("OSM returned %d elements", len(elements))

    rows = []
    for el in elements:
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            # way — Overpass returns center when `out center` is used
            center = el.get("center", {})
            lat, lon = center.get("lat"), center.get("lon")

        if lat is None or lon is None:
            continue

        tags = el.get("tags", {})
        rows.append(
            {
                "facility_id": f"OSM-{el['id']}",
                "lat": lat,
                "lon": lon,
                "facility_type": tags.get("industrial", tags.get("landuse", "industrial")),
                "source": "OSM",
                "name": tags.get("name", ""),
                "country": "IND",
            }
        )

    df = pd.DataFrame(rows)
    log.info("OSM normalised: %d industrial features", len(df))
    return df


# ── Merge ─────────────────────────────────────────────────────────────────────

def build_facility_table(
    include_osm: bool = True,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """
    Build the normalised facility table from all available sources.

    Returns a DataFrame with schema:
        facility_id, lat, lon, facility_type, source, name, country
    """
    parts: list[pd.DataFrame] = []

    log.info("=== Building facility table ===")

    # 1. GPPD
    try:
        raw_gppd = ingest_gppd(session=session)
        norm_gppd = normalise_gppd(raw_gppd)
        parts.append(norm_gppd)
        log.info("GPPD: %d normalised rows", len(norm_gppd))
    except Exception as exc:
        log.error("GPPD ingestion failed: %s", exc)

    # 2. OSM (optional — Overpass can time out)
    if include_osm:
        try:
            osm = ingest_osm(session=session)
            if len(osm):
                parts.append(osm)
                log.info("OSM: %d normalised rows", len(osm))
        except Exception as exc:
            log.error("OSM ingestion failed: %s", exc)

    if not parts:
        raise RuntimeError("No facility data could be loaded.")

    combined = pd.concat(parts, ignore_index=True)

    # Deduplicate exact lat/lon/source duplicates (shouldn't exist, but be safe)
    combined = combined.drop_duplicates(subset=["facility_id"])

    log.info("Facility table: %d total rows, sources: %s",
             len(combined), combined["source"].value_counts().to_dict())

    return combined


def save_facility_table(df: pd.DataFrame) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "facilities.parquet"
    df.to_parquet(out, index=False)
    write_metadata(
        out,
        {
            "description": "Normalised facility/context table",
            "row_count": len(df),
            "sources": df["source"].value_counts().to_dict(),
            "columns": list(df.columns),
            "note": "facility_proximity is a FEATURE only — not a label",
        },
    )
    log.info("Facility table saved → %s (%d rows)", out, len(df))
    return out


if __name__ == "__main__":
    sess = make_session()
    df = build_facility_table(session=sess)
    path = save_facility_table(df)

    # Quick sanity check
    print("\n=== Facility Table Summary ===")
    print(f"Total facilities: {len(df):,}")
    print(f"Sources:\n{df['source'].value_counts()}")
    print(f"\nIndia (IND) rows: {(df['country'] == 'IND').sum():,}")
    print(f"Top facility types:\n{df['facility_type'].value_counts().head(10)}")
    print(f"\nSaved to: {path}")
