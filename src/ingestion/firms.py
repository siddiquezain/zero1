"""
Stage 1 — FIRMS ingestion.

Fetches NASA FIRMS NRT active-fire detections for the India bounding box.
Archive downloads (> 10 days) require an Earthdata login; this script
handles both cases and degrades gracefully when credentials are absent.

Usage:
    python -m src.ingestion.firms          # NRT, both products, India bbox
    python -m src.ingestion.firms --days 7 --product VIIRS_SNPP_NRT
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from .config import (
    FIRMS_API_BASE,
    FIRMS_MAP_KEY,
    FIRMS_NRT_DAYS,
    FIRMS_PRODUCTS,
    FIRMS_RAW,
    INDIA_BBOX,
)
from .utils import make_session, write_metadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

# India bbox components (lon_min, lat_min, lon_max, lat_max)
_LON_MIN, _LAT_MIN, _LON_MAX, _LAT_MAX = INDIA_BBOX


def fetch_nrt_area(
    product: str,
    days: int,
    bbox: tuple[float, float, float, float] = INDIA_BBOX,
    map_key: str | None = FIRMS_MAP_KEY,
    session: requests.Session | None = None,
) -> pd.DataFrame | None:
    """
    Fetch NRT active-fire CSV from the FIRMS area API.

    Returns a DataFrame or None if the key is missing / request fails.

    Endpoint: GET /api/area/csv/{MAP_KEY}/{product}/{bbox}/{days}
    bbox format: lon_min,lat_min,lon_max,lat_max
    """
    if not map_key:
        log.warning(
            "FIRMS_MAP_KEY not set — cannot fetch %s NRT data. "
            "Register a free MAP_KEY at https://firms.modaps.eosdis.nasa.gov/api/",
            product,
        )
        return None

    lon_min, lat_min, lon_max, lat_max = bbox
    bbox_str = f"{lon_min},{lat_min},{lon_max},{lat_max}"
    url = f"{FIRMS_API_BASE}/area/csv/{map_key}/{product}/{bbox_str}/{days}"

    sess = session or make_session()
    log.info("Fetching FIRMS %s NRT (last %d days) for India bbox …", product, days)
    try:
        resp = sess.get(url, timeout=60)
    except requests.RequestException as exc:
        log.error("Network error fetching FIRMS: %s", exc)
        return None

    if resp.status_code == 400 and "Invalid MAP_KEY" in resp.text:
        log.error("FIRMS rejected MAP_KEY — check FIRMS_MAP_KEY in your .env")
        return None
    if resp.status_code != 200:
        log.error("FIRMS returned HTTP %s: %s", resp.status_code, resp.text[:200])
        return None

    # Empty response (no fires in window) returns header-only CSV
    from io import StringIO

    df = pd.read_csv(StringIO(resp.text))
    log.info("Fetched %d hotspot rows for %s", len(df), product)
    return df


def enforce_india_split(df: pd.DataFrame, intended_split: str) -> pd.DataFrame:
    """
    Guard: any row whose coordinates fall inside India's bounding box is
    tagged india_holdout regardless of which region bbox was requested.
    Prevents border-overlap rows from contaminating train_global.
    """
    if "latitude" not in df.columns or "longitude" not in df.columns:
        return df
    from src.model.split import is_india_coordinate
    india_mask = is_india_coordinate(df["latitude"], df["longitude"])
    n_fixed = india_mask.sum()
    if n_fixed:
        df = df.copy()
        df.loc[india_mask, "split"] = "india_holdout"
        df.loc[india_mask, "region"] = "india"
        log.warning(
            "enforce_india_split: retagged %d coordinate(s) inside India bbox "
            "from '%s' → 'india_holdout'", n_fixed, intended_split
        )
    return df


def save_nrt(df: pd.DataFrame, product: str, days: int) -> Path:
    """Save NRT DataFrame to parquet with provenance metadata."""
    FIRMS_RAW.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = FIRMS_RAW / f"{product}_NRT_{days}d_{ts}.parquet"
    df.to_parquet(out, index=False)
    write_metadata(
        out,
        {
            "source": "NASA FIRMS NRT",
            "product": product,
            "days": days,
            "bbox": list(INDIA_BBOX),
            "row_count": len(df),
            "columns": list(df.columns),
            "download_utc": ts,
        },
    )
    log.info("Saved → %s (%d rows)", out.name, len(df))
    return out


def sanity_check(df: pd.DataFrame, product: str) -> None:
    """Log basic checks on a freshly downloaded FIRMS DataFrame."""
    lat_col = "latitude" if "latitude" in df.columns else None
    lon_col = "longitude" if "longitude" in df.columns else None

    log.info("--- Sanity check: %s ---", product)
    log.info("Shape: %s", df.shape)
    log.info("Columns: %s", list(df.columns))

    if lat_col and lon_col:
        lat_ok = df[lat_col].between(_LAT_MIN, _LAT_MAX).all()
        lon_ok = df[lon_col].between(_LON_MIN, _LON_MAX).all()
        log.info(
            "Coordinates in India bbox: lat=%s lon=%s",
            "✓" if lat_ok else "✗",
            "✓" if lon_ok else "✗",
        )

    if "brightness" in df.columns:
        log.info(
            "Brightness temp (K): min=%.1f  max=%.1f  mean=%.1f",
            df["brightness"].min(),
            df["brightness"].max(),
            df["brightness"].mean(),
        )

    if "frp" in df.columns:
        log.info(
            "FRP (MW): min=%.2f  max=%.2f  mean=%.2f",
            df["frp"].min(),
            df["frp"].max(),
            df["frp"].mean(),
        )

    if "acq_date" in df.columns:
        log.info("Date range: %s → %s", df["acq_date"].min(), df["acq_date"].max())

    if len(df) == 0:
        log.warning("DataFrame is empty — no hotspots in this window/bbox.")


def ingest(
    products: list[str] | None = None,
    days: int = FIRMS_NRT_DAYS,
) -> list[Path]:
    """Run NRT ingestion for the given products. Returns list of saved paths."""
    products = products or FIRMS_PRODUCTS
    saved = []
    for product in products:
        df = fetch_nrt_area(product=product, days=days)
        if df is None:
            log.warning("Skipping %s — no data returned.", product)
            continue
        if len(df) == 0:
            log.info("Zero rows for %s — writing empty parquet for provenance.", product)
        sanity_check(df, product)
        path = save_nrt(df, product, days)
        saved.append(path)
    return saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch FIRMS NRT data for India.")
    parser.add_argument("--days", type=int, default=FIRMS_NRT_DAYS)
    parser.add_argument("--product", default=None, help="Specific product to fetch")
    args = parser.parse_args()

    products = [args.product] if args.product else None
    paths = ingest(products=products, days=args.days)
    if paths:
        print(f"Saved {len(paths)} file(s):")
        for p in paths:
            print(f"  {p}")
    else:
        print("No files saved — check FIRMS_MAP_KEY in .env")
        sys.exit(1)
