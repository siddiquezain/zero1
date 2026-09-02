# SIH26162 — ML Pipeline, Precisely (training → India inference)

> Every number and name below is taken directly from the code and the committed
> reports. Sources are cited as `path:line`. Nothing here is inferred.
>
> Primary sources:
> - `src/model/split.py` — split rules, India bbox, leakage checks
> - `src/model/assemble.py` — Stage 5: VNF labeling oracle + spatial split
> - `src/model/train.py` — Stage 6: Random Forest training + 3-way evaluation
> - `src/scoring/score_incidents.py` — Stage 7: scoring the 30 confirmed incidents
> - `src/features/engineer.py` — Stage 4: feature construction
> - `reports/stage6_evaluation.txt`, `reports/stage6_feature_importance.csv`,
>   `reports/stage7_incident_report.txt` — committed evaluation outputs
> - `context.md` Status Tracker — session logs
>
> **Caveat on reproducibility:** the trained model file
> `data/processed/stage6_model.joblib` is git-ignored (`.gitignore:5`) and is
> **not in the repository**. The Stage 5 intermediate parquets
> (`stage5_train/val/india_holdout`) are also git-ignored
> (`.gitignore:3`). What *is* committed and drives the dashboard:
> `data/processed/stage6_india_scores.parquet`,
> `data/incidents/stage7_incident_scores.parquet`,
> `data/processed/facilities.parquet`. The numbers below therefore come from the
> **committed report text files**, which record the last training run
> (`context.md` Status Tracker, Session 3, dated 2026-08-28).

---

## 0. One-paragraph summary

A `RandomForestClassifier` is trained on **270,238 non-India NASA FIRMS hotspot
rows** to predict **exactly two classes**: `"A"` (persistent industrial thermal
source) and `"B_candidate"` (natural / agricultural fire). Labels are **not**
human incident labels — they are produced by a **VNF spatial oracle**: a FIRMS
row within 5 km of a known VIIRS Nightfire gas-flare site is labelled `"A"`, every
other global FIRMS row is labelled `"B_candidate"`. The model uses **7 numeric
features**, all available at India inference time. It is evaluated three ways
(random split, spatial-grid holdout, India geographic holdout). The finalised
**spatial-holdout model** then scores **705 held-out India FIRMS hotspots** →
`stage6_india_scores.parquet`, adding `predicted_label`, `prob_A`,
`prob_B_candidate`, and `anomaly_flag` (`max(prob) < 0.55`). The dashboard's
**third** class — "Industrial Fire / Abnormal Thermal Event" — is **not a model
output**; it is derived downstream from `anomaly_flag` by the rule-based risk
engine.

---

## 1. Data lineage: training data → labels

### 1.1 Where the rows come from

| Split | Source | What it is | Where |
|---|---|---|---|
| `train_global` + `validation_global` | **NASA FIRMS NRT active-fire detections**, 6 non-India regions | Global FIRMS hotspots in FIRMS feature space | `context.md` Status Tracker (Stage 1): "Global FIRMS NRT downloaded for 6 non-India training regions (sub-Saharan Africa 268k, South America 31k, West Africa 23k, Australia 8k, Central Asia 3k, SE Asia 729 rows; 335,807 total rows)" |
| `india_holdout` | **NASA FIRMS NRT**, India bounding box | India hotspots, **no labels**, locked | `context.md` Status Tracker (Stage 1): "FIRMS NRT downloaded for India bbox (631 VIIRS + 66 MODIS rows, 2026-08-23 to 2026-08-27)" |
| **VNF (oracle only, excluded from training)** | **VIIRS Nightfire (VNF) Global Gas Flare Survey**, ORNL DAAC, 2012–2019 | 83,641 pre-labelled gas-flare sites (avg_temp mean 1,782 K) | `context.md` Status Tracker (Stage 1) |
| Facility/context layer (feature input only) | WRI Global Power Plant DB (34,936) + OSM `landuse=industrial` (37,688 India) → `facilities.parquet` (72,624 rows) | Coordinates for the `dist_nearest_facility_km` feature | `context.md` Status Tracker (Stage 2); `facilities.parquet.meta.json` |

FIRMS NRT only covers ~5 days; there is **no historical FIRMS archive**
(`context.md` blockers).

### 1.2 India bounding box (defines `india_holdout`)

`src/model/split.py:32-33`:
```
INDIA_LAT_MIN, INDIA_LAT_MAX = 6.0, 37.0
INDIA_LON_MIN, INDIA_LON_MAX = 68.0, 97.5
```
Any row inside this box → `india_holdout`, always excluded from train/val
(`split.py:45-50`, `assign_split_by_coords` `split.py:53-107`). The box is
deliberately conservative — it also captures Pakistan/Bangladesh/Sri Lanka border
rows (`tests/test_split.py:26-28`).

### 1.3 How training labels are created — the VNF oracle

**There is no dataset of confirmed industrial fires** (`context.md` §"Hard
constraints"). Labels are constructed, not observed:

`src/model/assemble.py:79-114` (`_vnf_oracle_label`):

1. Build a `BallTree` (haversine) over the lat/lon of **VNF global gas-flare
   sites** (`assemble.py:88-89`).
2. For each **global FIRMS row**, query radius = `VNF_ORACLE_KM / EARTH_RADIUS_KM`
   where `VNF_ORACLE_KM = 5.0` (`assemble.py:57`, `92-93`).
3. FIRMS row within 5 km of ≥1 VNF site → `label = "A"`; otherwise
   `label = "B_candidate"` (`assemble.py:96-100`).
4. **VNF rows themselves are excluded from training** — their `avg_temp`
   (1,500–2,000 K spectral flame temperature) is a different physical quantity
   from FIRMS `bright_ti4` (300–500 K pixel BT); training on both would produce a
   classifier that never predicts `A` for India NRT data (`assemble.py:4-16`).

**Why `B_candidate` and not `B`:** the natural/agricultural-fire label is *not*
validated with land-cover data. All non-VNF-adjacent global FIRMS rows are
provisionally `B_candidate`, pending land-cover filtering that is **not
implemented** (`src/features/engineer.py:50-52`; `context.md` Stage 3 "BLOCKED —
Class B labeling").

### 1.4 Label counts actually used

From `reports/stage6_evaluation.txt:7-13`:

```
Train (spatial holdout): 270238 rows
Val   (spatial holdout): 64864 rows
India (geographic holdout, no labels): 705 rows

Class distribution (train): {'B_candidate': 268583, 'A': 1655}
```

Validation-set support (from the classification report,
`reports/stage6_evaluation.txt:56-62`): `A` = 246, `B_candidate` = 64618
(total 64864).

**Total FIRMS rows labelled `"A"` by the oracle: 1,655 (train) + 246 (val) =
1,901** — i.e. 1,901 / 335,102 global FIRMS rows ≈ 0.57 % (`context.md` Stage 5:
"1,901 / 335,102 FIRMS global rows (0.57%) are within 5 km of a VNF site").

This is a **severe class imbalance** (~0.6 % positive), handled with
`class_weight="balanced"` (`train.py:79`). `assemble.py:108-113` explicitly warns
when the Class A count is low.

---

## 2. Features

### 2.1 The exact 7 features fed to the model

`src/model/train.py:49-57` **and** `src/model/assemble.py:60-68` **and**
`src/scoring/score_incidents.py:48-56` — identical list in all three:

```python
TRAIN_FEATURES = [
    "bt_kelvin",              # 4 µm pixel brightness temperature (K), FIRMS-native
    "frp_mw",                 # Fire Radiative Power (MW)
    "persistence_count",      # same ~1 km cell re-detections within the NRT window
    "dist_nearest_facility_km", # haversine distance to nearest facility (facilities.parquet)
    "agri_season_flag",       # 1 if acq month ∈ {10,11,4,5,7,8,9,1,2}, else 0
    "day_night_bin",          # 1 = daytime ('D'), 0 = nighttime ('N')
    "acq_month",              # 1–12
]
```

- `day_night_bin` encoding: `assemble.py:71-76` — `{"D": 1.0, "N": 0.0}`.
- `agri_season_flag` months: `src/features/engineer.py:71-76`
  (`_AGRI_MONTHS = {10, 11, 4, 5, 7, 8, 9, 1, 2}`); re-listed in
  `score_incidents.py:58`.
- `persistence_count`: cross-file 1 km-cell count over the NRT window
  (`engineer.py:99-109`, `326-343`).
- `dist_nearest_facility_km`: `BallTree` haversine nearest-neighbour against
  `facilities.parquet` (`engineer.py:112-146`).

### 2.2 Features that exist in the feature table but are NOT used by the model

From `engineer.py:8-46` the Stage 4 table has 25 columns including
`bt_11_kelvin`, `avg_temp_K`, `persistence_pct`, `nearest_facility_type`,
`nearest_facility_source`, `confidence`, `flr_type`, `flr_volume`, `acq_year`,
`spatial_grid_id`, `grid_key_1km`. **Only the 7 listed in §2.1 are model
inputs.** In particular:
- `avg_temp_K` (VNF spectral temp) is **deliberately not a feature**
  (`train.py:157-160`, `assemble.py:4-16`).
- Facility proximity is used **as a feature, never as a label**
  (`engineer.py:33`, `51`; `context.md` hard constraints).

### 2.3 Missing-value handling

`src/model/train.py:68-83` — the model is a `sklearn.pipeline.Pipeline`:
```
SimpleImputer(strategy="median")  →  RandomForestClassifier(...)
```
The imputer is fit on the training set and applied to val / India / incident
data. This matters for Stage 7 (below), where all thermal features are missing.

---

## 3. Split construction (Stage 5)

`src/model/assemble.py:117-189`:

1. Load `data/processed/features_stage4.parquet` (`assemble.py:126`;
   419,448 rows per `context.md` Stage 4).
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
     (`split.py:38` `GLOBAL_VAL_FRACTION = 0.20`, `split.py:83-96`). A whole grid
     cell goes to one side — **never split randomly at the row level**.
7. Leakage checks run and must pass (`assemble.py:161-164`):
   - `check_no_india_in_training` — 0 India-bbox rows in train/val
     (`split.py:116-141`).
   - `check_no_grid_overlap` — train and val grid-cell sets are disjoint
     (`split.py:144-164`).
   - (`run_all_checks` also has `check_no_facility_overlap` and
     `check_no_label_leakage`, `split.py:167-226`.)

Outputs (`assemble.py:179-186`, all git-ignored):
`stage5_train.parquet`, `stage5_val.parquet`, `stage5_india_holdout.parquet`,
`stage5_labeled.parquet`, `stage5_vnf_oracle.parquet`.

`context.md` Stage 5 records the resulting counts:
`train = 270,238 (A=1,655, B=268,583) | val = 64,864 | india_holdout = 705`.

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
Choice rationale (`train.py:4`): "tabular data, explainability priority over
accuracy."

### 4.2 Classes the model predicts — EXACTLY TWO

`src/model/train.py:17-20`:
```
"A"           — Persistent industrial thermal source (gas flare, kiln, …)
"B_candidate" — Natural / agricultural fire
```
`classes = sorted(all_df["label"].dropna().unique())` → `['A', 'B_candidate']`
(`train.py:143`; confirmed `reports/stage6_evaluation.txt:4`:
`Classes: ['A', 'B_candidate']`).

**There is no third model class.** The "anomaly" is not a class — it is a
post-hoc flag: `max(predict_proba) < ANOMALY_THRESHOLD` where
`ANOMALY_THRESHOLD = 0.55` (`train.py:59`, `train.py:101-109`).

### 4.3 What gets trained, three times

`train.py:164-214`:

1. **Random-split baseline** (`train.py:164-180`): concatenate train+val
   (`X_all, y_all`, `train.py:141-142`), `train_test_split(test_size=0.2,
   random_state=42)`, fit a fresh pipeline, evaluate on the random 20 %. This is
   the *inflated* benchmark that random splitting produces.
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
| `dist_nearest_facility_km` | 0.29277 |
| `day_night_bin` | 0.25348 |
| `bt_kelvin` | 0.21387 |
| `persistence_count` | 0.13850 |
| `frp_mw` | 0.10138 |
| `agri_season_flag` | 0.00000 |
| `acq_month` | 0.00000 |

`agri_season_flag` and `acq_month` contribute nothing — expected, because FIRMS
NRT is not from peak burning season (`context.md` Stage 6).

---

## 5. Evaluation metrics obtained

All values verbatim from `reports/stage6_evaluation.txt`.

### 5.1 Random-split baseline (INFLATED) — `stage6_evaluation.txt:22-43`

- **Accuracy: 0.9725**
- Confusion matrix (rows=true, cols=pred), classes `['A', 'B_candidate']`:
  ```
  [[  289    72]
   [ 1770 64890]]
  ```
- Classification report:

  | class | precision | recall | f1 | support |
  |---|---|---|---|---|
  | A | 0.14 | 0.80 | 0.24 | 361 |
  | B_candidate | 1.00 | 0.97 | 0.99 | 66660 |
  | macro avg | 0.57 | 0.89 | 0.61 | 67021 |
  | weighted avg | 0.99 | 0.97 | 0.98 | 67021 |

- Anomaly flag rate (max_prob < 0.55): **768 / 67021 (1.1 %)**

### 5.2 Spatial holdout (HONEST) — `stage6_evaluation.txt:45-66`

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
  | B_candidate | 1.00 | 0.98 | 0.99 | 64618 |
  | macro avg | 0.55 | 0.77 | 0.59 | 64864 |
  | weighted avg | 0.99 | 0.98 | 0.99 | 64864 |

- Anomaly flag rate (max_prob < 0.55): **596 / 64864 (0.9 %)**

### 5.3 Leakage gap — `stage6_evaluation.txt:68-72`

```
LEAKAGE GAP = 0.9725 (random) − 0.9806 (spatial) = -0.0081
```
Overall accuracy barely moves (random is actually 0.8 pp *lower*, because the
spatial-holdout val set is dominated by easy `B_candidate` grid cells). **The
real leakage signal is in the minority class**: Class A F1 drops
**0.24 → 0.18** (a ~25 % relative degradation) when the split respects spatial
grouping (`context.md` Stage 6: "Class A F1 drops from 0.24→0.18 (25%
degradation when splitting spatially — real leakage signal in the minority
class)").

### 5.4 India geographic holdout (NO LABELS) — `stage6_evaluation.txt:74-84`

- 705 India FIRMS hotspots scored.
- **Predicted class distribution: `{'B_candidate': 396, 'A': 309}`**
- **Anomaly flag (max_prob < 0.55): 59 / 705 rows (8.4 %)**
- No accuracy — India is a locked holdout with no ground truth.

The India anomaly rate (8.4 %) is ~9× the global validation rate (0.9 %),
consistent with the intended reading: Indian hotspots more often fall outside
both learned patterns.

---

## 6. India inference → `stage6_india_scores.parquet`

`src/model/train.py:209-240`.

Input: `stage5_india_holdout.parquet` = the 705 FIRMS rows whose coordinates fall
in the India bbox, carried through Stage 4 features + `day_night_bin`.

Steps:
```python
X_india = india_df[TRAIN_FEATURES].values.astype(float)   # 7 features, may contain NaN
y_india_pred  = pipe_sh.predict(X_india)                   # 'A' or 'B_candidate'
y_india_prob  = pipe_sh.predict_proba(X_india)             # [prob_A, prob_B_candidate]
anomaly_mask  = y_india_prob.max(axis=1) < 0.55
```

Columns **added** to the India rows and written to
`data/processed/stage6_india_scores.parquet` (`train.py:234-239`):
- `predicted_label` — `"A"` or `"B_candidate"`
- `prob_A` — RF probability of class A
- `prob_B_candidate` — RF probability of class B_candidate
- `anomaly_flag` — `int(max(prob) < 0.55)` — 1 or 0

The rest of the row is the Stage 4 feature record (`lat`, `lon`, `bt_kelvin`,
`frp_mw`, `persistence_count`, `dist_nearest_facility_km`, `nearest_facility_type`,
`agri_season_flag`, `day_night` / `day_night_bin`, `acq_date`, `acq_month`,
`confidence`, `spatial_grid_id`, …).

**This committed parquet is the only model output the dashboard consumes.** The
dashboard never loads `stage6_model.joblib`.

---

## 7. Final classification (dashboard-facing 3-class output)

The model gives 2 classes + an anomaly flag. The **rule-based risk engine**
(`src/alerting/risk_engine.py:268-275`) maps that to the 3 PS-aligned output
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

So for the 705 India detections: **59** become "Industrial Fire / Abnormal
Thermal Event" (from `anomaly_flag`), and the remaining 646 are split into
"Persistent Industrial Thermal Source" (`predicted_label == "A"`) and
"Forest / Agricultural Fire" (`predicted_label == "B_candidate"`).

The risk engine additionally derives, per row, `risk_score` (0–100 additive
rule), `severity` (CRITICAL ≥ 65 / HIGH ≥ 40 / MEDIUM ≥ 20 / LOW,
`risk_engine.py:258-266`), `land_cover_context`, `hazard_facility_type`,
`narrative`, and city/population context — none of which come from the ML model.

---

## 8. Stage 7 — the 30 confirmed incidents (separate, evaluation only)

`src/scoring/score_incidents.py`. **Not a training class**
(`context.md` §"Critical distinction about labels").

- Input: `data/incidents/confirmed_incidents_india.csv` — 30 curated real Indian
  industrial incidents, 2019–2023 (`score_incidents.py:79`).
- Only 3 features can be computed from a known lat/lon + date:
  `dist_nearest_facility_km`, `agri_season_flag`, `acq_month`
  (`score_incidents.py:88-98`).
- The 4 thermal features (`bt_kelvin`, `frp_mw`, `persistence_count`,
  `day_night_bin`) are set to **NaN** — there is no historical FIRMS archive for
  2019–2023 — and are filled by the pipeline's median imputer
  (`score_incidents.py:100-104`, `train.py:75`).
- Scored with `stage6_model.joblib` (`score_incidents.py:86`).

Results — `reports/stage7_incident_report.txt:9-14`:
- Total incidents: 30
- **Anomaly-flagged (max_prob < 0.55): 21 (70.0 %)**
- Predicted label distribution: `{'B_candidate': 30}` — i.e. all 30 predicted
  `B_candidate`, but 21 of them with `max_prob < 0.55` → flagged anomalies
  ("Industrial Fire / Abnormal Thermal Event" downstream).
- Example rows (`stage7_incident_report.txt:18-20`): IND-001 Vizag LG Polymers
  `prob_A=0.479 prob_B=0.521 max=0.521` → ANOMALY; IND-003 HPCL Visakhapatnam
  `prob_A=0.440 prob_B=0.560 max=0.560` → not flagged.
- Punjab/Haryana stubble-burning references (IND-009, IND-010) are correctly
  **not** anomaly-flagged (`context.md` Stage 7).

Independent match check (`data/incidents/match_summary.json`): 0/30 incidents
matched a FIRMS detection within 1 km / ±1 day — because FIRMS NRT is current and
the incidents are 2019–2023. Unmatched rows are retained as a
satellite-omission finding, not discarded.

---

## 9. Precise answers to the questions asked

| Question | Answer (from code / reports) |
|---|---|
| **Exact classes the model predicts** | Two: `"A"` (persistent industrial thermal source) and `"B_candidate"` (natural/agricultural fire). `train.py:143`, `stage6_evaluation.txt:4`. The dashboard's third label ("Industrial Fire / Abnormal Thermal Event") is a downstream rule (`anomaly_flag = max(prob) < 0.55`), not a model class. |
| **Exact features used** | 7: `bt_kelvin`, `frp_mw`, `persistence_count`, `dist_nearest_facility_km`, `agri_season_flag`, `day_night_bin`, `acq_month`. `train.py:49-57`. |
| **Where training labels come from** | VNF spatial oracle: FIRMS global row ≤ 5 km from a VIIRS Nightfire gas-flare site → `"A"`; otherwise → `"B_candidate"`. VNF rows themselves excluded from training. `assemble.py:79-114`. No confirmed-incident labels are used. `B_candidate` is not land-cover-validated. |
| **How many samples** | Train: **270,238** rows (`A`=1,655, `B_candidate`=268,583). Val: **64,864** rows (`A`=246, `B_candidate`=64,618). India holdout scored: **705** rows (no labels). VNF oracle sites: 83,641 (not training samples). Total FIRMS `"A"` labels: 1,901 (~0.57 %). `stage6_evaluation.txt:7-13`, `56-62`; `context.md` Stage 5. |
| **Evaluation metrics obtained** | Random-split baseline: accuracy **0.9725**, Class A P/R/F1 **0.14/0.80/0.24**, B_candidate **1.00/0.97/0.99**. Spatial holdout (honest, the saved model): accuracy **0.9806**, Class A P/R/F1 **0.11/0.57/0.18**, B_candidate **1.00/0.98/0.99**. Leakage gap −0.0081 overall; Class A F1 0.24 → 0.18. India holdout (no labels): predicted `{B_candidate: 396, A: 309}`, anomaly 59/705 (**8.4 %**). Incidents (Stage 7): 21/30 (**70 %**) anomaly-flagged, all predicted `B_candidate`. `stage6_evaluation.txt`, `stage7_incident_report.txt`. |
| **Model + hyperparameters** | `Pipeline(SimpleImputer(strategy="median"), RandomForestClassifier(n_estimators=300, min_samples_leaf=10, class_weight="balanced", n_jobs=-1, random_state=42))`. `train.py:68-83`. |
| **Which model scores India** | The **spatial-holdout** model (`pipe_sh`), fit on `stage5_train` only, not retrained on train+val. `train.py:184-185`, `213-214`, `258`. |

---

## 10. Honest limitations of this pipeline (from code + reports + `context.md`)

1. **No confirmed-fire ground truth anywhere.** The "industrial fire" output is an
   anomaly flag, not a trained detection. `context.md` §"Hard constraints".
2. **Labels are proxy labels.** `"A"` = "near a known gas flare"; `"B_candidate"`
   = "everything else global", not land-cover-validated. `engineer.py:50-52`.
3. **Class A is tiny** (1,901 rows, ~0.57 %). Spatial-holdout Class A F1 = 0.18.
   `assemble.py:108-113`, `stage6_evaluation.txt:56-62`.
4. **Top features are geographic/temporal, not thermal.**
   `dist_nearest_facility_km` (0.29) + `day_night_bin` (0.25) dominate; the
   project's own literature says persistence and temperature should be the
   discriminators. `stage6_feature_importance.csv`.
5. **Stage 7 incidents are scored with imputed thermal features** — no historical
   FIRMS archive — so those predictions "should be treated as baseline geographic
   context, not a definitive classification". `score_incidents.py:100-104`,
   `stage7_incident_report.txt` interpretation section.
6. **FIRMS NRT ≈ 5 days only.** `persistence_count` is a 5-day count;
   `agri_season_flag` / `acq_month` carry no signal in the current window.
7. **The trained model and Stage 5 parquets are not in the repo.** Re-running
   Stage 6 requires regenerating Stages 1–5 locally. The dashboard runs entirely
   off `stage6_india_scores.parquet` + the rule-based risk engine.
8. **Split shuffle uses a fixed seed (42)** but depends on regenerating the
   identical Stage 4 table; exact row counts are only guaranteed via the
   committed reports, not reproducible from the repo alone.
