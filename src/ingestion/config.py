"""
Centralised ingestion configuration — all paths, bounding boxes, and URLs.
Reads from .env if present; safe to import without a .env file.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Repository root ───────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.getenv("DATA_ROOT", REPO_ROOT / "data"))

RAW_DIR = DATA_ROOT / "raw"
PROCESSED_DIR = DATA_ROOT / "processed"
INCIDENTS_DIR = DATA_ROOT / "incidents"

FIRMS_RAW = RAW_DIR / "firms"
VNF_RAW = RAW_DIR / "vnf"
GIHS_RAW = RAW_DIR / "gihs"
FACILITIES_RAW = RAW_DIR / "facilities"

# ── API credentials ───────────────────────────────────────────────────────────
FIRMS_MAP_KEY: str | None = os.getenv("FIRMS_MAP_KEY") or None
EARTHDATA_USERNAME: str | None = os.getenv("EARTHDATA_USERNAME") or None
EARTHDATA_PASSWORD: str | None = os.getenv("EARTHDATA_PASSWORD") or None

# ── Geographic scope ──────────────────────────────────────────────────────────
# India approximate bounding box (lon_min, lat_min, lon_max, lat_max)
INDIA_BBOX = tuple(
    float(x)
    for x in os.getenv("INDIA_BBOX", "68.0,6.0,97.5,37.0").split(",")
)

# ── FIRMS endpoints ───────────────────────────────────────────────────────────
FIRMS_API_BASE = "https://firms.modaps.eosdis.nasa.gov/api"
FIRMS_NRT_DAYS = int(os.getenv("FIRMS_NRT_DAYS", "5"))  # FIRMS NRT max = 5 days

# Products we care about
FIRMS_PRODUCTS = [
    "VIIRS_SNPP_NRT",   # 375 m — preferred
    "MODIS_NRT",        # 1 km  — broader temporal archive
]

# ── WRI Global Power Plant Database ──────────────────────────────────────────
GPPD_ZIP_URL = (
    "https://datasets.wri.org/private-admin/dataset/"
    "53623dfd-3df6-4f15-a091-67457cdb271f/resource/"
    "66bcdacc-3d0e-46ad-9271-a5a76b1853d2/download/"
    "globalpowerplantdatabasev130.zip"
)
GPPD_FILENAME = "global_power_plant_database.csv"

# ── Overpass API ──────────────────────────────────────────────────────────────
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
