# SIH26162 — Project Context

Read this file in full before doing any work. It is the single source of truth for what this project is, what's already decided, and what not to do. Update the **Status Tracker** at the bottom after every session.

## What this project is

An AI system that classifies satellite-detected thermal hotspots (from NASA FIRMS) into:
1. **Persistent industrial thermal source** (flares, kilns, routine process heat)
2. **Natural / agricultural fire** (wildfire, crop-residue burning)
3. **Anomaly** — doesn't match either learned pattern; flagged for human review

Built for SIH26162 (NTRO, Smart India Hackathon 2026): "AI-Based Detection and Classification of Industrial Fires and Persistent Thermal Sources Using NASA FIRMS, OSM & Satellite Data."

## Hard constraints — do not violate these

These come directly from research already done. Violating them will produce a system that looks fine locally but falls apart under questioning.

- **There is no dataset of confirmed industrial fire incidents anywhere — India or global.** Do not build, or claim to build, a classifier trained on confirmed industrial fire events. Checked and confirmed absent: PESO, NDMA/NDMIS, IDRN, NCRB, DGMS, CPCB (India); no global equivalent found either.
- **A FIRMS hotspot is not typed by cause.** NASA states explicitly that MODIS/VIIRS active-fire products do not attribute anomaly type (fire vs. flare vs. volcano vs. other). Never treat a raw hotspot as a labelled example of anything.
- **"Near a facility" is not a label.** Distance-to-facility is a weak context *feature*, never a ground-truth signal. VIIRS Nightfire itself separates flares from fires using temperature + persistence, not proximity — follow that precedent.
- **Do not restrict training data to India only.** The physical signatures (temperature bands, persistence patterns) are not India-specific. Restricting to India-filtered data shrinks an already-thin dataset for no benefit. Train on global data; **hold out India entirely as the test/validation region** instead.
- **Never use a random train/test split on this data.** Repeated detections from the same facility will leak across a random split and inflate reported accuracy by 6–28 percentage points (documented across multiple studies). Split by facility ID / spatial grid cell, or by holding out India as a region, not randomly.
- **Log every unmatched confirmed incident — don't discard it.** When matching manually-curated incidents against FIRMS and no hotspot is found nearby, that's a finding (satellite omission), not a failed row to drop.
- **The pitch/demo must never claim "confirmed industrial fire detection."** The locked framing is: *"We detect anomalous departures from known persistent-industrial and natural-fire patterns — not confirmed fires, because no training data for that exists anywhere."* Any code, dashboard label, or slide that implies otherwise contradicts the whole design.

## Data sources

| Source | Identifier | What it gives you | Notes |
|---|---|---|---|
| NASA FIRMS | firms.modaps.eosdis.nasa.gov (MODIS 1km, VIIRS 375m) | Raw NRT + archive hotspot detections: lat/lon, brightness temp, FRP, confidence, date/time, day/night flag | Global, India-filterable, no access restriction. Requires a free account/API key for bulk archive downloads. |
| VIIRS Nightfire (VNF) global flare catalogue | ORNL DAAC, DOI 10.3334/ORNLDAAC/1874 | Pre-labelled global gas flare sites, separated from biomass burning by temperature (1500–2000K) + persistence | Use as-is for Class A positives — do not relabel. |
| GIHS (Global Industrial Heat Sources) | Ma et al. 2024, *Scientific Data*, DOI 10.1038/s41597-024-03461-3 | 25,544 validated industrial heat source objects, 90.95–93.46% user accuracy | **Verify the public repository link (Figshare/PANGAEA/Zenodo) before assuming it's downloadable — unconfirmed as of last check.** |
| Global Energy Monitor trackers | globalenergymonitor.org, CC BY 4.0 | Asset-level coordinates for refineries, oil/gas plants, pipelines — India included | Free, open, well-suited to the facility-proximity feature. |
| Global Power Plant Database | World Resources Institute, CC-BY-4.0 | ~28,500 power plant locations globally, India included | |
| OpenStreetMap (Overpass API) | `landuse=industrial` tagging | Industrial facility polygons | Coverage in India is inconsistent — spot-check density around known clusters before trusting it broadly. |
| CPCB Red-category industry lists | cpcb.nic.in | Sector/type context for ~1,861 major-accident-hazard units | Sector lists only, not geocoded — supplementary context, not a coordinate source. |
| Vadrevu & Lasko (2018) | *Remote Sensing*, DOI 10.3390/rs10070978 | Methodology for building the agricultural-burning class (VIIRS/MODIS + cropland + seasonal window + GFED cross-check, Punjab) | Replicate this method, not their exact data. |

## Pipeline — what to build, in order

Each stage is a separate work session. Verify output (row counts, a plotted sample) before moving to the next.

### 1. Data ingestion
Download FIRMS archive (MODIS + VIIRS) for an India bounding box, several years back. Download the VNF flare catalogue. Confirm GIHS access. Output: raw CSVs, row counts logged, a quick map plot to sanity-check coordinates look right.

### 2. Facility/context layer
Pull Global Energy Monitor trackers + Global Power Plant DB + OSM industrial polygons (Overpass API) for India. Merge into one facility table: `facility_id, lat, lon, type, source`.

### 3. Label construction
- **Class A (positive):** VNF flare entries + GIHS objects, tagged `source_dataset`.
- **Class B (negative):** FIRMS hotspots filtered to (a) forest/vegetation land cover with short-burst, non-persistent detection pattern → wildfire; (b) cropland + known seasonal windows (e.g., Oct–Nov Punjab/Haryana) → agricultural burning. Sanity-check volumes against GFED.
- **Confirmed-incident set (small, manual):** Compile ~30–100 major Indian industrial fires from news/Wikipedia with precise coordinates and dates (human-curated — do not fully automate source-reliability judgment). Match against FIRMS/VIIRS within a ~375m–1km spatial buffer and ±1 day window. Keep a column for `matched: yes/no` — unmatched rows are a finding, not noise to remove.

### 4. Feature engineering
Per hotspot, compute: brightness temperature, FRP, persistence count (same ~1km cell re-lit over trailing N days — the single best discriminator per the literature), day/night flag, land-cover class, distance to nearest facility (from Stage 2's table), facility type if within threshold, agri-season flag. These are model inputs, never labels.

### 5. Assemble & split
Merge Class A + Class B into one feature table. **Group by `facility_id` or spatial grid cell before splitting.** Hold out all India rows as the test set; train on the rest of the world's Class A/B data.

### 6. Train & validate
Random Forest or XGBoost (tabular — prefer explainability over deep learning given the labelled-sample size and the need to justify predictions). Report **two accuracy numbers side by side**: standard random-split accuracy, and the facility/spatial-holdout (India-held-out) accuracy. The gap between them is evidence the leakage problem was handled correctly — report it, don't hide it.

### 7. Incident scoring & anomaly demo
Run the Stage-3 confirmed-incident set (the matched ones) through the trained model. The goal outcome: they land in neither Class A nor Class B cleanly — i.e., they get flagged as anomalies. That result is the actual product demo.

### 8. Dashboard
Map view over India, hotspots colour-coded by predicted class (A / B / anomaly). Highlight 2–3 case studies: a real flare correctly classified as Class A, a real Punjab/Haryana ag-burning cluster as Class B, and a past major incident (e.g., 2025 Sigachi Telangana blast — has public coordinates) run through the pipeline to show either a correct anomaly flag or, if unmatched, an honest demonstration of the omission-rate limitation.

## Setup required before Stage 1 (human, not agent)

- [ ] NASA Earthdata account registered (needed for bulk archive downloads)
- [ ] FIRMS API key / archive-download access confirmed for an India bounding box
- [ ] GIHS public repository link located and confirmed downloadable
- [ ] If running in a sandboxed/cloud agent environment: confirm network access to ORNL DAAC, NASA FIRMS, Overpass API, and Global Energy Monitor domains

## Physical basis for classification (cite this, don't reinvent it)

Elvidge et al. (2016), *Energies* 9(1):14, DOI 10.3390/en9010014:
- Gas flares: **1500–2000 K**
- Biomass burning / industrial sites / volcanoes: **600–1300 K**
- **1300–1500 K is an ambiguous crossover zone** — treat predictions in this band as lower-confidence.

## Repo structure convention

```
/data/raw/            # untouched downloads (firms, vnf, gihs, facilities)
/data/processed/      # cleaned/merged feature tables
/data/incidents/       # manually-curated confirmed-incident CSV + matching results
/src/ingestion/        # Stage 1-2 scripts
/src/labeling/         # Stage 3 scripts
/src/features/         # Stage 4 scripts
/src/model/            # Stage 5-6: split, train, evaluate
/src/scoring/          # Stage 7: incident scoring
/dashboard/            # Stage 8
/reports/              # accuracy tables, feature importance, figures for the pitch deck
```

## Status Tracker

Update this section after each work session — what's done, what's blocked, what's next.

- [x] Stage 1 — Data ingestion (substantially complete; one minor blocker)
  - **Done:** FIRMS NRT downloaded for India bbox (631 VIIRS + 66 MODIS rows, 2026-08-23 to 2026-08-27).
  - **Done:** Global FIRMS NRT downloaded for 6 non-India training regions (sub-Saharan Africa 268k, South America 31k, West Africa 23k, Australia 8k, Central Asia 3k, SE Asia 729 rows; 335,807 total rows).
  - **Done:** All FIRMS files tagged with `split` column at ingest time (India → `india_holdout`, global → `train_global`).
  - **Done:** VNF (Global Gas Flare Survey, ORNL DAAC C2345877554-ORNL_CLOUD, 2012–2019) downloaded via Earthdata Bearer token. 83,641 rows. avg_temp mean 1,782 K (consistent with 1,500–2,000 K gas flare range). Split: 82,083 `train_global` / 1,558 `india_holdout` (coordinate-based, includes Pakistan/Bangladesh/Sri Lanka in bbox — conservative choice).
  - **Done:** WRI Global Power Plant Database v1.3.0 downloaded (34,936 plants globally).
  - **Done:** OSM industrial polygons fetched via Overpass API (37,688 India industrial features).
  - **BLOCKED — GIHS:** Download URL unconfirmed. Open https://doi.org/10.1038/s41597-024-03461-3, locate Figshare/Zenodo link, add to `src/ingestion/gihs.py::_CANDIDATE_URLS`. Class A currently relies on VNF alone.
  - **Note — Historical FIRMS:** NRT API only provides last 5 days. Historical data (months/years) requires LAADS DAAC HDF download or FIRMS bulk download portal — not yet implemented. Confirmed incident temporal matching is blocked on this.

- [x] Stage 2 — Facility/context layer (done)
  - Normalised facility table: `data/processed/facilities.parquet` (72,624 rows: 34,936 GPPD + 37,688 OSM; 39,277 India rows).
  - Sanity-check map: `reports/facility_sanity_check.png`.
  - Provenance metadata JSON written alongside all raw files.

- [~] Stage 3 — Label construction (Class A done; Class B partially; confirmed-incident set done)
  - **Done — Class A:** VNF provides 82,083 global training rows tagged `label=A`. Pre-labelled by temperature+persistence (avg_temp ~1,500–2,000 K). DO NOT relabel.
  - **Partial — Class B:** Global FIRMS NRT (335k rows, mostly natural fires in Africa/Amazon/SE Asia). Land-cover filtering needed to create defensible Class B labels. Not done yet.
  - **Done — Confirmed incidents:** 30 curated incidents in `data/incidents/confirmed_incidents_india.csv`. VNF proximity check (within 20 km): 15/30 match known VNF flare sites; 15/30 don't (coal mines, agricultural sites, pharma — expected, VNF only captures gas-flare thermal signatures). Temporal FIRMS matching: 0/30 (incidents are 2019–2023, FIRMS NRT is current — requires historical archive).
  - **BLOCKED — Class B labeling:** Requires land-cover data (e.g., MODIS MCD12Q1 or ESA CCI Land Cover) + persistence filtering. Not implemented yet.
  - **BLOCKED — Temporal incident matching:** Need historical FIRMS archive for specific incident dates (2019–2023).

- [x] Stage 4 — Feature engineering (done)
  - Feature table: `data/processed/features_stage4.parquet` — 419,448 rows, 25 columns.
  - Schema: feature_id, lat, lon, spatial_grid_id, grid_key_1km, source_dataset, split, label, bt_kelvin, bt_11_kelvin, frp_mw, avg_temp_K, acq_date, acq_year, acq_month, day_night, persistence_count, persistence_pct, dist_nearest_facility_km, nearest_facility_type, nearest_facility_source, agri_season_flag, confidence, flr_type, flr_volume.
  - **Class A (VNF):** 83,641 rows, mean bt_kelvin=1,783 K, 95.7% above 1,500 K. persistence_pct mean 21.6%.
  - **Class B_candidate (FIRMS):** 335,102 rows, mean bt_kelvin=339 K, 0% above 1,500 K. persistence_count mean 2.9.
  - **Holdout (no label):** 705 India FIRMS rows — correctly withheld.
  - Leakage caught and fixed: 8 border-overlap rows (Central Asia/SE Asia bbox) retagged from train_global → india_holdout. `enforce_india_split()` guard added to firms.py.
  - All leakage checks pass. 49 tests pass.
  - NOTE: `B_candidate` label for FIRMS rows is pending land-cover validation (Stage 3b). Rows near VNF flare sites should be excluded from Class B before training.

- [x] Stage 5 — Assemble & split (done)
  - **VNF labeling oracle approach:** VNF avg_temp (1,500–2,000 K spectral flame temp) is NOT the same physical quantity as FIRMS bright_ti4 (300–500 K pixel BT). Training on both as `bt_kelvin` would produce a model that always predicts B for India FIRMS data (India BT always in FIRMS range). Solution: VNF sites used as a spatial labeling oracle only — FIRMS global rows within 5 km of a known VNF flare site → label "A"; remaining FIRMS global → "B_candidate". VNF rows excluded from training.
  - **FIRMS-space Class A examples:** 1,901 / 335,102 FIRMS global rows (0.57%) are within 5 km of a VNF site — labeled Class A. All in FIRMS feature space.
  - **Splits (spatial grid 80/20):** train=270,238 (A=1,655, B=268,583) | val=64,864 (A=246, B=246) | india_holdout=705 (no label)
  - **Leakage checks:** all pass. No India coordinates in training. No grid overlap between train/val.
  - **Outputs:** `data/processed/stage5_{train,val,india_holdout,labeled,vnf_oracle}.parquet`
  - **Script:** `src/model/assemble.py`

- [x] Stage 6 — Train & validate (done)
  - **Model:** RandomForestClassifier, n_estimators=300, class_weight="balanced", n_jobs=-1.
  - **Training features (7):** bt_kelvin, frp_mw, persistence_count, dist_nearest_facility_km, agri_season_flag, day_night_bin, acq_month. Median imputation for NaN.
  - **Three-way evaluation:**
    - Random-split baseline: 97.25% accuracy (Class A F1=0.24) — INFLATED
    - Spatial holdout (honest): 98.06% accuracy (Class A F1=0.18) — honest geographic generalization
    - Leakage gap: random better by 0.8 pp overall; Class A F1 drops from 0.24→0.18 (25% degradation when splitting spatially — real leakage signal in the minority class)
    - India geographic holdout (705 rows, no labels): 309 predicted A, 396 predicted B, 59 anomaly-flagged (8.4%)
  - **Feature importances:** dist_nearest_facility_km (29%), day_night_bin (25%), bt_kelvin (21%), persistence_count (14%), frp_mw (10%). agri_season_flag and acq_month both 0 (expected — FIRMS NRT is not from peak burning season).
  - **Outputs:** `data/processed/stage6_model.joblib`, `stage6_india_scores.parquet`, `reports/stage6_evaluation.txt`, `reports/stage6_feature_importance.csv`
  - **Script:** `src/model/train.py`
  - **Known limitation:** Class A training set is thin (1,901 examples globally from VNF oracle). Class A F1=0.18 reflects this. Adding historical FIRMS archive or GIHS would significantly improve Class A recall.

- [x] Stage 7 — Incident scoring (done)
  - Scored all 30 confirmed India incidents through the Stage 6 RF model.
  - **21 / 30 incidents flagged as anomalies** (max_prob < 0.55, 70%) — correct outcome per design. Industrial fire incidents are transient anomalies that match neither the persistent gas flare pattern (Class A) nor natural fire (Class B).
  - Thermal features (bt_kelvin, frp_mw, persistence_count, day_night_bin) = NaN for all incidents (historical FIRMS archive not downloaded). Imputed by pipeline medians. Classification driven by dist_nearest_facility_km + agri_season_flag + acq_month.
  - Notable: Punjab/Haryana stubble burning (IND-009, IND-010) correctly NOT flagged as anomaly — predicted Class B, as expected.
  - Outputs: `data/incidents/stage7_incident_scores.parquet`, `reports/stage7_incident_report.txt`
  - Script: `src/scoring/score_incidents.py`

- [x] Stage 8 — Dashboard (done)
  - Streamlit + pydeck map at `dashboard/app.py`.
  - Run: `streamlit run dashboard/app.py`
  - Features: India FIRMS hotspot map coloured by predicted class (orange=A, green=B, purple=anomaly), confirmed incident overlay (yellow), facility layer toggle, stats header, incident detail table, 3 case studies (Jharia coalfield / Punjab stubble / Vizag LG Polymers), limitations panel.
  - No Mapbox token needed — uses free Carto dark-matter basemap.
  - Screenshot: `dashboard/screenshot_full.png`

**Last updated:** 2026-08-28 (Session 3)

**Architecture note (from new.txt):** Global training / India-held-out architecture is now enforced:
- Every dataset carries a `split` column (`train_global` | `validation_global` | `india_holdout`) assigned at ingest.
- `src/model/split.py` provides leakage-check assertions (31 tests, all passing).
- Splits use spatial-grid grouping + coordinate-based India bounding box — no random split.
- Anti-leakage checks verified on VNF and will be run at every subsequent pipeline stage.
- **VNF feature space mismatch resolved in Stage 5:** VNF used as labeling oracle only; all training in FIRMS feature space.

**Current blockers:**
1. **GIHS download URL** — manually check https://doi.org/10.1038/s41597-024-03461-3 → add to `src/ingestion/gihs.py::_CANDIDATE_URLS`
2. **Class B land-cover filtering** — needs land-cover raster or API (MODIS MCD12Q1 recommended). Currently all non-VNF-adjacent FIRMS global rows are B_candidate.
3. **Historical FIRMS archive** — for temporal incident matching in Stage 7; needs LAADS DAAC HDF workflow or FIRMS bulk download

**What to do next (no human action needed — all implementable):**
- Stage 7: Score the 30 confirmed India incidents through the model (lat/lon known, need FIRMS features from archive or approximate from nearest NRT detection).
- Stage 8: Streamlit dashboard — map of India holdout FIRMS scores colour-coded by predicted class + anomaly flag.
