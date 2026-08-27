"""
Stage 1 — VIIRS Nightfire (VNF) / Global Gas Flare Survey ingestion.

Dataset: "Global Gas Flare Survey by Infrared Imaging, VIIRS Nightfire, 2012-2019"
CMR concept_id: C2345877554-ORNL_CLOUD (ORNL CLOUD archive)
DOI: 10.3334/ORNLDAAC/1874

Files: eog_global_flare_survey_{year}_flare_list.csv (2012-2019)
Columns: cntry_name, cntry_iso, catalog_id, id_number, latitude, longitude,
         flr_volume, avg_temp, ellip, dtc_freq, clr_obs, flr_type

Requires NASA Earthdata credentials (EARTHDATA_USERNAME / EARTHDATA_PASSWORD in .env).
Auth: Bearer token via https://urs.earthdata.nasa.gov/api/users/tokens

IMPORTANT:
- VNF entries are pre-labelled global gas flare SITES (not per-detection).
- avg_temp range ~1500-2200 K, consistent with gas flare signature.
- DO NOT relabel these entries. They are Class A (persistent industrial flares).
- India entries (cntry_iso == IND) go to india_holdout; all others to train_global.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from .config import EARTHDATA_PASSWORD, EARTHDATA_USERNAME, VNF_RAW
from .utils import write_metadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

_BASE_URL = (
    "https://data.ornldaac.earthdata.nasa.gov/protected/cms/"
    "Methane_Flaring_Sites_VIIRS/data"
)
_YEARS = range(2012, 2020)  # 2012-2019 confirmed in CMR


def _get_token() -> str | None:
    if not EARTHDATA_USERNAME or not EARTHDATA_PASSWORD:
        log.warning(
            "VNF requires Earthdata credentials.\n"
            "  → Register at https://urs.earthdata.nasa.gov/\n"
            "  → Set EARTHDATA_USERNAME + EARTHDATA_PASSWORD in .env"
        )
        return None

    # Try to reuse an existing token before creating a new one
    r = requests.get(
        "https://urs.earthdata.nasa.gov/api/users/tokens",
        auth=(EARTHDATA_USERNAME, EARTHDATA_PASSWORD),
        timeout=30,
    )
    if r.status_code == 200 and r.json():
        return r.json()[0]["access_token"]

    # Create new token
    r2 = requests.post(
        "https://urs.earthdata.nasa.gov/api/users/token",
        auth=(EARTHDATA_USERNAME, EARTHDATA_PASSWORD),
        timeout=30,
    )
    if r2.status_code == 200:
        return r2.json()["access_token"]

    log.error("Failed to obtain Earthdata token: %s %s", r2.status_code, r2.text[:200])
    return None


def download_all(force: bool = False) -> list[Path]:
    """Download all available VNF annual flare-list CSVs. Returns list of saved paths."""
    token = _get_token()
    if token is None:
        return []

    VNF_RAW.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()
    sess.headers["Authorization"] = f"Bearer {token}"
    sess.headers["User-Agent"] = "SIH26162-pipeline/1.0"

    saved = []
    for year in _YEARS:
        fname = f"eog_global_flare_survey_{year}_flare_list.csv"
        dest = VNF_RAW / fname
        if dest.exists() and not force:
            log.info("VNF %d already cached: %s", year, dest)
            saved.append(dest)
            continue

        url = f"{_BASE_URL}/{fname}"
        log.info("Downloading VNF %d …", year)
        try:
            r = sess.get(url, timeout=120)
            r.raise_for_status()
            dest.write_bytes(r.content)
            log.info("VNF %d saved: %.2f MB", year, dest.stat().st_size / 1e6)
            saved.append(dest)
        except requests.HTTPError as exc:
            log.error("VNF %d download failed: %s", year, exc)

    return saved


def load_all() -> pd.DataFrame | None:
    """Load all downloaded VNF CSVs into a single DataFrame with split tags."""
    csvs = sorted(VNF_RAW.glob("eog_global_flare_survey_*_flare_list.csv"))
    if not csvs:
        log.warning("No VNF files found in %s — run download_all() first.", VNF_RAW)
        return None

    dfs = []
    for csv in csvs:
        year = int(csv.name.split("_")[4])
        df = pd.read_csv(csv)
        df["catalog_id"] = df["catalog_id"].astype(str)
        df["year"] = year
        df["source_dataset"] = "VNF"
        df["label"] = "A"  # Class A: persistent industrial flare
        # Use coordinate-based India bbox for holdout — more conservative than ISO code
        # only. Pakistan/Bangladesh/Sri Lanka rows within the bbox also go to holdout
        # since geographic proximity could cause leakage.
        from src.model.split import is_india_coordinate
        in_india_bbox = is_india_coordinate(df["latitude"], df["longitude"])
        df["split"] = in_india_bbox.map({True: "india_holdout", False: "train_global"})
        df["region"] = in_india_bbox.map({True: "india_bbox", False: "global"})
        dfs.append(df)

    combined = pd.concat(dfs, ignore_index=True)

    write_metadata(
        VNF_RAW / "vnf_combined.parquet",
        {
            "source": "Global Gas Flare Survey (VNF) — ORNL DAAC C2345877554-ORNL_CLOUD",
            "doi": "10.3334/ORNLDAAC/1874",
            "years": list(_YEARS),
            "row_count": len(combined),
            "india_rows": int((combined["split"] == "india_holdout").sum()),
            "train_global_rows": int((combined["split"] == "train_global").sum()),
            "avg_temp_mean_K": round(combined["avg_temp"].mean(), 1),
            "class": "A — persistent industrial flare — DO NOT relabel",
            "download_utc": datetime.now(timezone.utc).isoformat(),
        },
    )

    combined.to_parquet(VNF_RAW / "vnf_combined.parquet", index=False)
    log.info(
        "VNF combined: %d rows | train_global=%d | india_holdout=%d",
        len(combined),
        (combined["split"] == "train_global").sum(),
        (combined["split"] == "india_holdout").sum(),
    )
    return combined


def status() -> dict[str, bool]:
    return {str(y): (VNF_RAW / f"eog_global_flare_survey_{y}_flare_list.csv").exists()
            for y in _YEARS}


if __name__ == "__main__":
    print("VNF file status:")
    for year, present in status().items():
        print(f"  {year}: {'✓' if present else '✗'}")

    paths = download_all()
    if paths:
        df = load_all()
        if df is not None:
            print(f"\nVNF loaded: {len(df):,} rows")
            print(f"  train_global: {(df['split']=='train_global').sum():,}")
            print(f"  india_holdout: {(df['split']=='india_holdout').sum():,}")
            print(f"  avg_temp (K): mean={df['avg_temp'].mean():.1f} "
                  f"min={df['avg_temp'].min():.1f} max={df['avg_temp'].max():.1f}")
            print(f"  Top countries: {df['cntry_name'].value_counts().head(5).to_dict()}")
