"""
Shared utilities for ingestion: HTTP downloads with retries, metadata logging.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)


def make_session(retries: int = 3, backoff: float = 1.0) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers["User-Agent"] = "SIH26162-pipeline/1.0 (research project)"
    return session


def download_file(
    url: str,
    dest: Path,
    session: requests.Session | None = None,
    chunk_size: int = 1 << 20,
    timeout: int = 120,
) -> Path:
    """Download *url* to *dest*, streaming. Returns *dest* on success."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    sess = session or make_session()
    log.info("Downloading %s → %s", url, dest)
    with sess.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=chunk_size):
                fh.write(chunk)
    log.info("Saved %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
    return dest


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_metadata(path: Path, meta: dict[str, Any]) -> None:
    """Write provenance JSON next to *path*."""
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    meta["_recorded_utc"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, indent=2))
    log.debug("Metadata → %s", meta_path)


def load_metadata(path: Path) -> dict[str, Any]:
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {}
