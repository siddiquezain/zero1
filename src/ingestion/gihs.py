"""
Stage 1 — GIHS (Global Industrial Heat Sources) ingestion.

Ma et al. 2024, Scientific Data, DOI 10.1038/s41597-024-03461-3
"Annual dynamics of global remote industrial heat sources dataset from 2012 to 2021"

GIHS is used as Class A positives (validated industrial heat sources).

STATUS: The exact download URL is unconfirmed — the paper cites a repository
but the direct download link must be manually located from the Scientific Data
article. This script will:
  1. Try several candidate URLs (Figshare, Zenodo, Pangaea).
  2. Log a clear blocker if none work.
  3. Load the file if already present.

UPDATE this file once the URL is confirmed from the journal article page.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import requests

from .config import GIHS_RAW
from .utils import download_file, make_session, write_metadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

# Candidate download URLs — try in order.
# The confirmed URL must be obtained from: https://doi.org/10.1038/s41597-024-03461-3
# and updated here once verified.
_CANDIDATE_URLS: list[tuple[str, str]] = [
    # (url, expected filename)
    # Placeholder — fill in once manually verified from the journal supplementary
    # e.g. ("https://figshare.com/ndownloader/files/XXXXX", "GIHS_2012_2021.csv"),
]

_GIHS_RAW_PATH = GIHS_RAW / "GIHS_raw.csv"


def find_and_download(session: requests.Session | None = None) -> Path | None:
    """Try candidate URLs; return local path if successful, else None."""
    if _GIHS_RAW_PATH.exists():
        log.info("GIHS already cached: %s", _GIHS_RAW_PATH)
        return _GIHS_RAW_PATH

    if not _CANDIDATE_URLS:
        log.warning(
            "GIHS download URL is unconfirmed.\n"
            "  → Open https://doi.org/10.1038/s41597-024-03461-3 in a browser.\n"
            "  → Find the data repository link (Figshare / Zenodo / Pangaea).\n"
            "  → Add the direct CSV download URL to _CANDIDATE_URLS in src/ingestion/gihs.py\n"
            "BLOCKER: GIHS Stage 1 contribution is skipped until URL is confirmed."
        )
        return None

    sess = session or make_session()
    GIHS_RAW.mkdir(parents=True, exist_ok=True)

    for url, filename in _CANDIDATE_URLS:
        dest = GIHS_RAW / filename
        log.info("Trying GIHS candidate URL: %s", url)
        try:
            download_file(url, dest, session=sess)
            log.info("GIHS download succeeded: %s", dest)
            return dest
        except requests.HTTPError as exc:
            log.warning("Candidate URL failed (%s): %s", url, exc)
            if dest.exists():
                dest.unlink()

    log.error(
        "All GIHS candidate URLs failed. Manual download required.\n"
        "BLOCKER: GIHS unavailable — Class A will rely solely on VNF until resolved."
    )
    return None


def load_gihs(path: Path | None = None) -> pd.DataFrame | None:
    """Load GIHS file (CSV or Parquet) as a DataFrame."""
    p = path or _GIHS_RAW_PATH
    if not p or not p.exists():
        log.warning("GIHS file not found at %s", p)
        return None

    if p.suffix in (".parquet",):
        df = pd.read_parquet(p)
    else:
        df = pd.read_csv(p)

    log.info("GIHS: %d rows, columns: %s", len(df), list(df.columns))

    write_metadata(
        p,
        {
            "source": (
                "GIHS — Ma et al. 2024, Scientific Data, "
                "DOI 10.1038/s41597-024-03461-3"
            ),
            "row_count": len(df),
            "columns": list(df.columns),
            "class": "A — validated industrial heat sources (DO NOT relabel)",
            "accuracy_reported": "90.95–93.46% user accuracy per paper",
        },
    )
    return df


def status() -> str:
    if _GIHS_RAW_PATH.exists():
        return f"PRESENT ({_GIHS_RAW_PATH})"
    return "MISSING — see BLOCKER note in src/ingestion/gihs.py"


if __name__ == "__main__":
    print(f"GIHS status: {status()}")
    path = find_and_download()
    if path:
        df = load_gihs(path)
        if df is not None:
            print(f"GIHS: {len(df):,} rows")
            print(df.head(3))
    else:
        print("\nBLOCKER: GIHS not available. Proceed with VNF for Class A only.")
