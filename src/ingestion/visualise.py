"""
Sanity-check maps for ingested data.
Run after each ingestion step to verify coordinates look correct.

Usage:
    python -m src.ingestion.visualise --facilities
    python -m src.ingestion.visualise --firms <parquet_path>
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def plot_facilities(out_path: Path | None = None) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    from .config import PROCESSED_DIR

    fac_path = PROCESSED_DIR / "facilities.parquet"
    if not fac_path.exists():
        log.error("Facility table not found at %s — run facilities.py first.", fac_path)
        return

    df = pd.read_parquet(fac_path)
    india = df[df["country"] == "IND"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Left: India facilities by source
    ax = axes[0]
    colours = {"GPPD": "#2196F3", "OSM": "#FF5722", "GEM": "#4CAF50"}
    for src, grp in india.groupby("source"):
        ax.scatter(
            grp["lon"], grp["lat"],
            s=2, alpha=0.4,
            c=colours.get(src, "#9E9E9E"),
            label=f"{src} ({len(grp):,})",
        )
    ax.set_xlim(68, 97.5)
    ax.set_ylim(6, 37)
    ax.set_title(f"India facilities ({len(india):,} total)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(markerscale=4)
    ax.grid(alpha=0.3)

    # Right: Global GPPD by fuel type (top-8 types)
    gppd = df[df["source"] == "GPPD"]
    top_types = gppd["facility_type"].value_counts().head(8).index.tolist()
    ax2 = axes[1]
    import matplotlib.pyplot as _plt
    cmap = _plt.get_cmap("tab10")
    for i, ft in enumerate(top_types):
        sub = gppd[gppd["facility_type"] == ft]
        ax2.scatter(sub["lon"], sub["lat"], s=1, alpha=0.3, c=[cmap(i)], label=ft)
    ax2.set_xlim(-180, 180)
    ax2.set_ylim(-60, 80)
    ax2.set_title(f"GPPD global power plants ({len(gppd):,} total)")
    ax2.set_xlabel("Longitude")
    ax2.legend(markerscale=4, fontsize=7)
    ax2.grid(alpha=0.3)

    fig.suptitle("Facility / Context Layer — Sanity Check", fontsize=13)
    fig.tight_layout()

    out = out_path or Path("reports/facility_sanity_check.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    print(f"Saved → {out}")
    plt.close()


def plot_firms(parquet_path: Path, out_path: Path | None = None) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    df = pd.read_parquet(parquet_path)
    if df.empty:
        log.warning("FIRMS file is empty — nothing to plot.")
        return

    lat_col = "latitude" if "latitude" in df.columns else "lat"
    lon_col = "longitude" if "longitude" in df.columns else "lon"
    bt_col = "brightness" if "brightness" in df.columns else None

    fig, ax = plt.subplots(figsize=(10, 7))

    if bt_col:
        sc = ax.scatter(
            df[lon_col], df[lat_col],
            c=df[bt_col], cmap="hot_r",
            s=5, alpha=0.6, vmin=300, vmax=500,
        )
        plt.colorbar(sc, ax=ax, label="Brightness Temperature (K)")
    else:
        ax.scatter(df[lon_col], df[lat_col], s=3, alpha=0.5, color="red")

    ax.set_xlim(68, 97.5)
    ax.set_ylim(6, 37)
    ax.set_title(f"FIRMS hotspots — {parquet_path.name} ({len(df):,} rows)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(alpha=0.3)

    out = out_path or Path(f"reports/{parquet_path.stem}_map.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    print(f"Saved → {out}")
    plt.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--facilities", action="store_true")
    parser.add_argument("--firms", type=Path, default=None)
    args = parser.parse_args()

    if args.facilities:
        plot_facilities()
    if args.firms:
        plot_firms(args.firms)
    if not args.facilities and not args.firms:
        print("Use --facilities or --firms <path>")
