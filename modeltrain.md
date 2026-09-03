# SIH26162 — ML Pipeline, Precisely (training → India inference)

> Every number and name below is taken directly from the code or the committed
> reports. Sources are cited as `path:line`. Nothing here is inferred.
>
> Primary sources:
> - `src/model/split.py` — split rules, India bbox, leakage checks
> - `src/model/assemble.py` — Stage 5: VNF labelling oracle + spatial-grid split
> - `src/model/train.py` — Stage 6: Random Forest + three-way evaluation
> - `src/scoring/score_incidents.py` — Stage 7: scoring the 30 confirmed incidents
> - `src/features/engineer.py` — Stage 4: feature construction
> - `src/ingestion/refresh.py` — the runtime live-inference path
> - `reports/stage6_evaluation.txt`, `reports/stage6_feature_importance.csv`,
>   `reports/stage7_incident_report.txt` — committed evaluation outputs
>
> **Reproducibility caveat.** The trained model
> `data/processed/stage6_model.joblib` is git-ignored (`.gitignore:4`) and is
> **not in the repository**. The Stage 5 intermediates
> (`stage5_train/val/india_holdout.parquet`, `features_stage4.parquet`) are also
> git-ignored (`.gitignore:3`). What *is* committed: `stage6_india_scores.parquet`,
> `stage7_incident_scores.parquet`, `facilities.parquet`, the three `reports/`
> text files. The metrics below therefore come from the **committed report text**,
> which records the last full training run.
>
> **The committed `stage6_india_scores.parquet` is a moving artefact.** `.gitignore`
> un-ignores it (`.gitignore:8`), but `src/ingestion/refresh.py` overwrites it
> whenever a live FIRMS NRT refresh runs. At the time of writing it holds **1,213
> rows dated 2026-08-30 → 2026-09-03** (a live snapshot), while the training-run
> report describes **705 India rows dated 2026-08-23 → 2026-08-27**. The *model*
> and its evaluation are unchanged by a refresh — only the India rows it scores.

---

## 0. One-paragraph summary

A `RandomForestClassifier` is trained on **270,238 non-India NASA FIRMS hotspot
rows** to predict **exactly two classes**: `"A"` (persistent industrial thermal
source) and `"B_candidate"` (natural / agricultural fire). The labels are **not**
human incident labels — they come from a **VNF spatial oracle**: a global FIRMS
row within 5 km of a known VIIRS Nightfire gas-flare site is labelled `"A"`; every
other global FIRMS row is labelled `"B_candidate"`. The model uses **7 numeric
features**, all available at India inference time. It is evaluated three ways
(random split, spatial-grid holdout, India geographic holdout). The finalised
**spatial-holdout model** scores India FIRMS hotspots →
`stage6_india_scores.parquet`, adding `predicted_label`, `prob_A`,
`prob_B_candidate`, `max_prob`, and `anomaly_flag` (`max(prob) < 0.55`). The
dashboard's **third** class — "Industrial Fire / Abnormal Thermal Event" — is
**not a model output**; it is derived downstream from `anomaly_flag` by the
rule-based risk engine. Everything added after the training run (thermal-event
clustering, event fingerprinting, facility thermal baselines / deviation) is
**deterministic and non-ML** — no retraining has occurred.

---

## 1. Data lineage: training data → labels

### 1.1 Where the rows come from

| Split | Source | What it is |
|---|---|---|
| `train_global` + `validation_global` | NASA FIRMS NRT active-fire detections, non-India regions | Global FIRMS hotspots in FIRMS feature space |
| `india_holdout` | NASA FIRMS NRT, India bounding box | India hotspots, **no labels**, locked |
| **VNF (oracle only, excluded from training)** | VIIRS Nightfire (VNF) Global Gas Flare Survey, ORNL DAAC, 2012–2019 (`src/ingestion/vnf.py:39-43`) | Pre-labelled gas-flare **sites** (`avg_temp` ~1,500–2,200 K, `vnf.py:18`) |
| Facility / context layer (feature input only) | WRI Global Power Plant DB + OSM `landuse=industrial` → `facilities.parquet` (72,624 rows; 39,277 IND) | Coordinates for the `dist_nearest_facility_km` feature |

FIRMS NRT covers only ~5 days (`src/ingestion/config.py:41`,
`FIRMS_NRT_DAYS`; capped at 5 in `refresh.py:34`). There is **no historical FIRMS
archive** (`src/labeling/match_incidents.py:196-200`).

### 1.2 India bounding box (defines `india_holdout`)

`src/model/split.py:32-33`:
```
INDIA_LAT_MIN, INDIA_LAT_MAX = 6.0, 37.0
INDIA_LON_MIN, INDIA_LON_MAX = 68.0, 97.5
```
Any row inside this box → `india_holdout`, always excluded from train/val
(`split.py:45-50`, `assign_split_by_coords` `split.py:53-107`;
`src/ingestion/firms.py:93-112` `enforce_india_split` re-tags border rows). The
box is deliberately conservative — it also captures Pakistan / Bangladesh /
Sri Lanka border rows (`tests/test_split.py`).

> Note: this is a *different* box from the runtime `INDIA_BBOX`
> (`config.py:34-37`, `68.0,6.0,97.5,37.0`, lon-first) and from
> `geo.INDIA_BBOX` (`intelligence/geo.py`, `6.0,37.5,67.5,97.5`, lat-first). All
> three describe roughly the same region; only the training one gates the split.

### 1.3 How training labels are created — the VNF oracle

**There is no dataset of confirmed industrial fires** (`context.md` §6 hard
constraints). Labels are constructed, not observed.

`src/model/assemble.py:79-114` (`_vnf_oracle_label`):

1. Build a `BallTree` (haversine) over the lat/lon of **VNF global gas-flare
   sites** (`assemble.py:88-89`).
2. For each **global FIRMS row**, query radius = `VNF_ORACLE_KM / EARTH_RADIUS_KM`
   where `VNF_ORACLE_KM = 5.0` (`assemble.py:57`, `92-93`).
3. FIRMS row within 5 km of ≥ 1 VNF site → `label = "A"`; otherwise
   `label = "B_candidate"` (`assemble.py:96-100`).
4. **VNF rows themselves are excluded from training** — their `avg_temp`
   (1,500–2,000 K spectral flame temperature) is a different physical quantity
   from FIRMS `bright_ti4` (300–500 K pixel BT); training on both would produce a
   classifier that never predicts `A` for India NRT data (`assemble.py:4-16`).

**Why `B_candidate` and not `B`:** the natural/agricultural label is *not*
land-cover validated. All non-VNF-adjacent global FIRMS rows are provisionally
`B_candidate`, pending land-cover filtering that is **not implemented**
(`src/features/engineer.py:48-52`; `context.md` §3 Stage 3 `[PARTIAL]`).

### 1.4 Label counts actually used

`reports/stage6_evaluation.txt:7-13`:
```
Train (spatial holdout): 270238 rows
Val   (spatial holdout): 64864 rows
India (geographic holdout, no labels): 705 rows

Class distribution (train): {'B_candidate': 268583, 'A': 1655}
```

Validation-set support (`reports/stage6_evaluation.txt:56-62`): `A` = 246,
`B_candidate` = 64,618 (total 64,864).

**Total FIRMS rows labelled `"A"` by the oracle: 1,655 (train) + 246 (val) =
1,901** — ≈ 0.57 % of ~335,102 global FIRMS rows. This is a **severe class
imbalance** (~0.6 % positive), handled with `class_weight="balanced"`
(`train.py:79`). `assemble.py:108-113` explicitly warns when the Class A count is
low.

---

## 2. Features

### 2.1 The exact 7 features fed to the model

Identical list in `src/model/train.py:49-57`, `src/model/assemble.py:60-68`,
`src/scoring/score_incidents.py:48-56`, and `src/ingestion/refresh.py:47-55`:

```python
TRAIN_FEATURES = [
    "bt_kelvin",                # 4 µm pixel brightness temperature (K), FIRMS-native
    "frp_mw",                   # Fire Radiative Power (MW)
    "persistence_count",        # same ~1 km cell re-detections within the NRT window
    "dist_nearest_facility_km", # haversine distance to nearest facility (facilities.parquet)
    "agri_season_flag",         # 1 if acq month ∈ {10,11,4,5,7,8,9,1,2}, else 0
    "day_night_bin",            # 1 = daytime ('D'), 0 = nighttime ('N')
    "acq_month",                # 1–12
]
```

- `day_night_bin`: `assemble.py:71-76` — `{"D": 1.0, "N": 0.0}`.
- `agri_season_flag` months: `src/features/engineer.py:71-76`
  (`_AGRI_MONTHS = {10, 11, 4, 5, 7, 8, 9, 1, 2}`); re-listed in
  `score_incidents.py:58` and `refresh.py:45`.
- `persistence_count`: cross-file 1 km-cell count over the NRT window
  (`engineer.py:99-109`, `326-343`).
- `dist_nearest_facility_km`: `BallTree` haversine nearest-neighbour against
  `facilities.parquet` (`engineer.py:112-146`).

### 2.2 Features that exist in the feature table but are NOT model inputs

From `engineer.py:8-46` the Stage 4 table has ~25 columns including
`bt_11_kelvin`, `avg_temp_K`, `persistence_pct`, `nearest_facility_type`,
`nearest_facility_source`, `confidence`, `flr_type`, `flr_volume`, `acq_year`,
`spatial_grid_id`, `grid_key_1km`. **Only the 7 in §2.1 are model inputs.** In
particular:
- `avg_temp_K` (VNF spectral temp) is **deliberately not a feature**
  (`train.py:157-160`, `assemble.py:4-16`).
- Facility proximity is a **feature, never a label** (`engineer.py:33`, `51-52`).

### 2.3 Missing-value handling

`src/model/train.py:68-83` — the model is a `sklearn.pipeline.Pipeline`:
```
SimpleImputer(strategy="median")  →  RandomForestClassifier(...)
```
The imputer is fit on the training set and applied to val / India / incident
data. This matters for Stage 7 (§8), where all thermal features are missing.

---

## 3. Split construction (Stage 5)

`src/model/assemble.py:117-189`:

1. Load `data/processed/features_stage4.parquet` (`assemble.py:126`).
2. Separate **VNF rows** (oracle, excluded) from **FIRMS rows**
   (`assemble.py:130-135`).
3. Separate FIRMS **global** (`split != india_holdout`) from FIRMS **India
   holdout** (`assemble.py:141-144`).
4. Apply the VNF oracle to relabel FIRMS global rows (`assemble.py:147`).
5. Encode `day_night_bin` (`assemble.py:150-151`).
6. `assign_split_by_coords` (`split.py:53-107`):
   - India-bbox rows → `india_holdout`.
   - Non-India rows grouped into **1° × 1° spatial grid cells**
     (`split.py:41` `GRID_DEG = 1.0`, `split.py:75-80`).
   - Grid cells shuffled with `np.random.default_rng(seed=42)` and assigned
     **80 % of cells → `train_global`, 20 % of cells → `validation_global`**
     (`split.py:38` `GLOBAL_VAL_FRACTION = 0.20`, `split.py:83-96`). **A whole
     grid cell goes to one side — never split at the row level.**
7. Leakage checks run and must pass (`assemble.py:161-164`):
   - `check_no_india_in_training` — 0 India-bbox rows in train/val
     (`split.py:116-141`).
   - `check_no_grid_overlap` — train and val grid-cell sets are disjoint
     (`split.py:144-164`).
   - `run_all_checks` also runs `check_no_facility_overlap` and
     `check_no_label_leakage` (`split.py:167-226`).

Outputs (`assemble.py:179-186`, all git-ignored): `stage5_train.parquet`,
`stage5_val.parquet`, `stage5_india_holdout.parquet`, `stage5_labeled.parquet`,
`stage5_vnf_oracle.parquet`.

Resulting counts (`reports/stage6_evaluation.txt:7-13`):
`train = 270,238 (A=1,655, B_candidate=268,583) | val = 64,864 | india_holdout =
705`.

---

## 4. Random Forest training (Stage 6)

`src/model/train.py`.

### 4.1 Model

`src/model/train.py:68-83` (`_make_pipeline`):
```python
Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("clf", RandomForestClassifier(
        n_estimators=300,
        min_samples_leaf=10,
        class_weight="balanced",
        n_jobs=-1,
        random_state=42,
    )),
])
```
Rationale (`train.py:4`): "tabular data, explainability priority over accuracy."

### 4.2 Classes the model predicts — EXACTLY TWO

`src/model/train.py:17-20`, `train.py:143`; confirmed
`reports/stage6_evaluation.txt:4` (`Classes: ['A', 'B_candidate']`):
```
"A"           — persistent industrial thermal source (gas flare, kiln, …)
"B_candidate" — natural / agricultural fire
```

**There is no third model class.** The "anomaly" is not a class — it is a
post-hoc flag: `max(predict_proba) < ANOMALY_THRESHOLD`,
`ANOMALY_THRESHOLD = 0.55` (`train.py:59`, `101-109`).

### 4.3 What gets trained, three times

`train.py:164-240`:

1. **Random-split baseline** (`train.py:164-180`): concatenate train+val
   (`X_all, y_all`, `train.py:141-142`), `train_test_split(test_size=0.2,
   random_state=42)`, fit a fresh pipeline, evaluate on the random 20 %. The
   *inflated* benchmark that random splitting produces.
2. **Spatial holdout** (`train.py:182-196`): fit on `X_train` (stage5_train,
   270,238 rows) **only**, evaluate on `X_val` (stage5_val, 64,864 rows). This is
   the **honest** model and **the one that is saved and used for India scoring**
   (`pipe_sh`, `train.py:184-185`, `258`).
3. **India geographic holdout** (`train.py:209-240`): `pipe_sh` scores the 705
   India rows. No labels → no accuracy, only predicted-class distribution +
   anomaly rate.

### 4.4 Feature importance (from the saved spatial-holdout model)

`reports/stage6_feature_importance.csv` (verbatim):

| feature | importance |
|---|---|
| `dist_nearest_facility_km` | 0.2928 |
| `day_night_bin` | 0.2535 |
| `bt_kelvin` | 0.2139 |
| `persistence_count` | 0.1385 |
| `frp_mw` | 0.1014 |
| `agri_season_flag` | 0.0000 |
| `acq_month` | 0.0000 |

`agri_season_flag` and `acq_month` contribute **nothing** — expected, because
FIRMS NRT is a single narrow window, not a full annual cycle. The top two
features are **geographic/temporal, not thermal** — see §10.4.

---

## 5. Evaluation metrics obtained

All values verbatim from `reports/stage6_evaluation.txt`.

### 5.1 Random-split baseline (INFLATED) — `stage6_evaluation.txt:22-43`

- **Accuracy: 0.9725**
- Confusion matrix (rows=true, cols=pred), `['A', 'B_candidate']`:
  ```
  [[  289    72]
   [ 1770 64890]]
  ```
- Classification report:

  | class | precision | recall | f1 | support |
  |---|---|---|---|---|
  | A | 0.14 | 0.80 | 0.24 | 361 |
  | B_candidate | 1.00 | 0.97 | 0.99 | 66,660 |
  | macro avg | 0.57 | 0.89 | 0.61 | 67,021 |
  | weighted avg | 0.99 | 0.97 | 0.98 | 67,021 |

- Anomaly flag rate (`max_prob < 0.55`): **768 / 67,021 (1.1 %)**

### 5.2 Spatial holdout (HONEST — the saved model) — `stage6_evaluation.txt:45-66`

- **Accuracy: 0.9806**
- Confusion matrix:
  ```
  [[  139   107]
   [ 1150 63468]]
  ```
- Classification report:

  | class | precision | recall | f1 | support |
  |---|---|---|---|---|
  | A | 0.11 | 0.57 | 0.18 | 246 |
  | B_candidate | 1.00 | 0.98 | 0.99 | 64,618 |
  | macro avg | 0.55 | 0.77 | 0.59 | 64,864 |
  | weighted avg | 0.99 | 0.98 | 0.99 | 64,864 |

- Anomaly flag rate (`max_prob < 0.55`): **596 / 64,864 (0.9 %)**

### 5.3 Leakage gap — `stage6_evaluation.txt:68-72`

```
LEAKAGE GAP = 0.9725 (random) − 0.9806 (spatial) = -0.0081
```
Overall accuracy barely moves (the spatial-holdout val set is dominated by easy
`B_candidate` grid cells, so it is actually 0.8 pp *higher*). **The real leakage
signal is in the minority class:** Class A F1 drops **0.24 → 0.18** (a ~25 %
relative degradation) when the split respects spatial grouping.

### 5.4 India geographic holdout (NO LABELS) — `stage6_evaluation.txt:74-84`

- 705 India FIRMS hotspots scored.
- **Predicted class distribution: `{'B_candidate': 396, 'A': 309}`**
- **Anomaly flag (`max_prob < 0.55`): 59 / 705 (8.4 %)**
- No accuracy — India is a locked holdout with no ground truth.

The India anomaly rate (8.4 %) is ~9× the global validation rate (0.9 %),
consistent with the intended reading: Indian hotspots more often fall outside
both learned patterns.

---

## 6. India inference → `stage6_india_scores.parquet`

### 6.1 Batch path (the committed baseline)

`src/model/train.py:209-240`. Input: the 705 FIRMS rows in the India bbox carried
through Stage 4 features + `day_night_bin`.

```python
X_india      = india_df[TRAIN_FEATURES].values.astype(float)   # 7 features, may contain NaN
y_india_pred = pipe_sh.predict(X_india)                         # 'A' or 'B_candidate'
y_india_prob = pipe_sh.predict_proba(X_india)                   # [prob_A, prob_B_candidate]
anomaly_mask = y_india_prob.max(axis=1) < 0.55
```

Columns **added** and written to `data/processed/stage6_india_scores.parquet`
(`train.py:234-239`): `predicted_label`, `prob_A`, `prob_B_candidate`,
`anomaly_flag`. The rest of each row is the Stage 4 feature record.

### 6.2 Live path (dashboard runtime) — `src/ingestion/refresh.py`

When `FIRMS_MAP_KEY` **and** `stage6_model.joblib` are both present locally,
`maybe_refresh()` runs fresh inference at startup / on the sidebar button:

1. Fetch `VIIRS_SNPP_NRT` + `MODIS_NRT` for the India bbox, last `min(FIRMS_NRT_DAYS, 5)`
   days (`refresh.py:34`, `152-164`).
2. `_engineer()` (`refresh.py:83-129`) — rebuilds the 7 feature columns:
   `persistence_count` from a `round(lat/0.01)_round(lon/0.01)` grid-key groupby;
   `dist_nearest_facility_km` from a fresh `BallTree` over `facilities.parquet`;
   `agri_season_flag`; `day_night_bin`; `acq_month`; `bt_kelvin` from
   `bright_ti4` / `brightness`.
3. `joblib.load(stage6_model.joblib)` → `predict` + `predict_proba` →
   `max_prob` → `anomaly_flag = (max_prob < 0.55)` (`refresh.py:173-186`).
4. Write `stage6_india_scores.parquet` (`refresh.py:189-191`), then
   `pipeline.run(fresh=True)` reseeds `alerts.db` (`refresh.py:194-195`).
5. **Any exception → fall back to the existing data unchanged**
   (`refresh.py:204-206`).

Feature columns and the anomaly threshold are identical to the batch path, so the
two are consistent. The current committed parquet is a live snapshot (1,213 rows,
2026-08-30 → 2026-09-03).

---

## 7. Final classification (dashboard-facing 3-class output)

The model gives 2 classes + an anomaly flag. The **rule-based risk engine**
(`src/alerting/risk_engine.py:278-284`) maps that to the 3 PS-aligned output
classes:

```python
if anomaly_flag == 1:
    output_class = "Industrial Fire / Abnormal Thermal Event"     # OUTPUT_CLASS_INDUSTRIAL_FIRE
elif predicted_label == "A":
    output_class = "Persistent Industrial Thermal Source"         # OUTPUT_CLASS_PERSISTENT_SOURCE
else:
    output_class = "Forest / Agricultural Fire"                   # OUTPUT_CLASS_NATURAL_FIRE
```
(constants at `risk_engine.py:83-85`.)

The risk engine additionally derives, per row: `risk_score` (0–100 additive rule,
`score_row` `risk_engine.py:202-319`), `severity` (`≥65 CRITICAL / ≥40 HIGH / ≥20
MEDIUM / <20 LOW`, `risk_engine.py:267-275`), `land_cover_context`,
`hazard_facility_type`, `narrative`, `nearest_city` / `dist_nearest_city_km` /
`near_population`, and `factors` (the `(reason, +points)` breakdown). **None of
these come from the ML model.**

---

## 8. Stage 7 — the 30 confirmed incidents (separate, evaluation only)

`src/scoring/score_incidents.py`. **Not a training class** (`context.md` §6).

- Input: `data/incidents/confirmed_incidents_india.csv` — 30 curated real Indian
  industrial incidents, 2019–2023 (`score_incidents.py:79`).
- Only 3 features can be computed from a known lat/lon + date:
  `dist_nearest_facility_km`, `agri_season_flag`, `acq_month`
  (`score_incidents.py:88-98`).
- The 4 thermal features (`bt_kelvin`, `frp_mw`, `persistence_count`,
  `day_night_bin`) are **NaN** — no historical FIRMS archive for 2019–2023 — and
  are filled by the pipeline's median imputer (`score_incidents.py:100-104`,
  `train.py:75`).
- Scored with `stage6_model.joblib` (`score_incidents.py:86`).

Results — `reports/stage7_incident_report.txt`:
- Total incidents: 30.
- **Anomaly-flagged (`max_prob < 0.55`): 21 (70.0 %)**
- Predicted label distribution: `{'B_candidate': 30}` — all 30 predicted
  `B_candidate`, 21 with `max_prob < 0.55` → flagged anomalies → "Industrial Fire
  / Abnormal Thermal Event" downstream.
- Punjab/Haryana stubble-burning references are correctly **not** anomaly-flagged
  (`context.md`).

Independent match check (`data/incidents/match_summary.json`): **0/30** incidents
matched a FIRMS detection within 1 km / ±1 day — because FIRMS NRT is current and
the incidents are 2019–2023 (`src/labeling/match_incidents.py:39-42`, `196-200`).
Unmatched rows are retained as a satellite-omission *finding*, not discarded.

---

## 9. Precise answers to the questions usually asked

| Question | Answer (from code / reports) |
|---|---|
| **Exact classes the model predicts** | Two: `"A"` (persistent industrial thermal source) and `"B_candidate"` (natural / agricultural fire). `train.py:143`, `stage6_evaluation.txt:4`. The dashboard's third label ("Industrial Fire / Abnormal Thermal Event") is a downstream rule (`anomaly_flag = max(prob) < 0.55`), not a model class. |
| **Exact features used** | 7: `bt_kelvin`, `frp_mw`, `persistence_count`, `dist_nearest_facility_km`, `agri_season_flag`, `day_night_bin`, `acq_month`. `train.py:49-57`. |
| **Where training labels come from** | VNF spatial oracle: global FIRMS row ≤ 5 km from a VNF gas-flare site → `"A"`; otherwise → `"B_candidate"`. VNF rows themselves excluded from training. `assemble.py:79-114`. No confirmed-incident labels are used. `B_candidate` is not land-cover validated. |
| **How many samples** | Train **270,238** rows (`A`=1,655, `B_candidate`=268,583). Val **64,864** rows (`A`=246, `B_candidate`=64,618). India holdout scored **705** rows (no labels). Total FIRMS `"A"` labels: **1,901** (~0.57 %). `stage6_evaluation.txt:7-13, 56-62`. |
| **Evaluation metrics** | Random-split baseline: accuracy **0.9725**, Class A P/R/F1 **0.14/0.80/0.24**. Spatial holdout (the saved model): accuracy **0.9806**, Class A P/R/F1 **0.11/0.57/0.18**. Leakage gap −0.0081 overall; Class A F1 **0.24 → 0.18**. India holdout: predicted `{B_candidate: 396, A: 309}`, anomaly **59/705 (8.4 %)**. Incidents: **21/30 (70 %)** anomaly-flagged, all predicted `B_candidate`. |
| **Model + hyperparameters** | `Pipeline(SimpleImputer(strategy="median"), RandomForestClassifier(n_estimators=300, min_samples_leaf=10, class_weight="balanced", n_jobs=-1, random_state=42))`. `train.py:68-83`. |
| **Which model scores India** | The **spatial-holdout** model (`pipe_sh`), fit on `stage5_train` only — **not** retrained on train+val. `train.py:184-185`, `213-214`, `258`. |
| **Was the model retrained for the event / facility-fingerprint features?** | **No.** Thermal-event clustering (`clustering.py`), event fingerprinting (`fingerprint.py`), evidence/evolution/trajectory, and the facility thermal baseline / deviation (`facility_fingerprint.py`) are all **deterministic, non-ML** additions built on the *already-scored* rows. `risk_engine.deviation_factor` exists but is **not** called by `score_row`. |

---

## 10. Honest limitations of this pipeline

1. **No confirmed-fire ground truth anywhere.** The "industrial fire" output is an
   anomaly flag, not a trained detection. `context.md` §6.
2. **Labels are proxy labels.** `"A"` = "near a known gas flare"; `"B_candidate"`
   = "everything else global", not land-cover validated. `engineer.py:48-52`.
3. **Class A is tiny** (1,901 rows, ~0.57 %). Spatial-holdout Class A F1 = 0.18.
   `assemble.py:108-113`, `stage6_evaluation.txt:56-62`.
4. **Top features are geographic/temporal, not thermal.**
   `dist_nearest_facility_km` (0.29) + `day_night_bin` (0.25) dominate;
   persistence and brightness temperature — the physically meaningful
   discriminators — sit lower. `stage6_feature_importance.csv`.
5. **Stage 7 incidents are scored with imputed thermal features** — no historical
   FIRMS archive — so those predictions are "baseline geographic context, not a
   definitive classification". `score_incidents.py:100-104`,
   `stage7_incident_report.txt`.
6. **FIRMS NRT ≈ 5 days only.** `persistence_count` is a 5-day count;
   `agri_season_flag` / `acq_month` carry no signal in the current window
   (0.0 importance). This is also why **facility thermal baselines** are usually
   `INSUFFICIENT_BASELINE` (§9, last row) — a 5-day window rarely gives ≥ 6
   observations across ≥ 2 days for one facility.
7. **The trained model and Stage 5 parquets are not in the repo.** Re-running
   Stage 6 requires regenerating Stages 1–5 locally. The dashboard runs entirely
   off `stage6_india_scores.parquet` + the rule-based risk engine; when
   `stage6_model.joblib` is present locally it can also re-score live FIRMS data.
8. **The committed `stage6_india_scores.parquet` moves.** `src/ingestion/refresh.py`
   overwrites it on any live refresh; the row count and date window drift while
   the model and its evaluation stay fixed.
9. **Split shuffle uses a fixed seed (42)** but depends on regenerating the
   identical Stage 4 table; exact row counts are only guaranteed via the
   committed reports, not reproducible from the repo alone.

---

## 11. What is downstream of the model (and is NOT the model)

| Layer | ML? | Source |
|---|---|---|
| `predicted_label`, `prob_A`, `prob_B_candidate`, `max_prob`, `anomaly_flag` | **Yes** — RandomForest | `train.py` / `refresh.py` |
| `output_class` (3-class), `risk_score`, `severity`, `narrative`, `risk_factors`, land-cover / hazard / city context | No — deterministic rules | `src/alerting/risk_engine.py` |
| Thermal events (`ThermalEvent`, clustering) | No — union-find | `src/intelligence/clustering.py` |
| Event behaviour fingerprint (6 dimensions + category) | No — threshold rules | `src/intelligence/fingerprint.py` |
| Evidence stack, evolution frames + milestones, risk trajectory / early-warning state | No — deterministic | `evidence.py` / `evolution.py` / `early_warning.py` |
| **Facility thermal baseline + `thermal_deviation_score` (0–100)** | No — robust statistics (`statistics.median` / `quantiles` / MAD) + a saturating curve | `src/intelligence/facility_fingerprint.py` |

**Three distinct scores** are kept separate at every layer and must never be
merged: **model class probability** (RandomForest), **`risk_score`** (rule-based
priority), **`thermal_deviation_score`** (baseline-relative behaviour).
