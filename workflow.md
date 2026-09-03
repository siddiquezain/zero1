# SIH26162 — End-to-End System Workflow

> The complete operational workflow, from satellite data to an analyst decision,
> plus the main user journeys. Companion to `context.md`, `architecture.md`,
> `design_brief.md`, `modeltrain.md`. Reflects commit `ae61893` (Session 12).
>
> Each step is marked **[AUTOMATED]** (system), **[MANUAL]** (analyst), or
> **[AGENT-ASSISTED]** (analyst asks, agent helps — read-only). All steps below
> are **[IMPLEMENTED]** unless noted.

---

## Part 1 — Data → Intelligence pipeline (offline, Stages 1–8)

This produces the data the dashboard serves. The committed Parquet/CSV outputs
are what a fresh clone reads. `modeltrain.md` has every number with `path:line`
citations.

### 1. Data acquisition **[AUTOMATED]**

- NASA FIRMS NRT active-fire detections for the India bounding box
  (`src/ingestion/firms.py`), plus 6 non-India regions for training. Every row is
  tagged `split` (`train_global` / `validation_global` / `india_holdout`) **at
  ingest**; `enforce_india_split` retags any coordinate inside the India bbox to
  `india_holdout` regardless of which region was requested.
- VIIRS Nightfire (VNF) Global Gas Flare Survey, 2012–2019 (`src/ingestion/vnf.py`)
  — used as a **Class A labelling oracle only**, never as a feature.
- WRI Global Power Plant Database + OSM `landuse=industrial` polygons
  (`src/ingestion/facilities.py`) → normalised `facilities.parquet`
  (`facility_id, lat, lon, facility_type, source, name, country`; 72,624 rows,
  39,277 in India).
- **Limitation:** FIRMS NRT covers only ~5 days; there is no historical archive.

### 2. Data cleaning **[AUTOMATED]** (`src/features/engineer.py`)

- Column normalisation across MODIS/VIIRS products (brightness-temperature column
  resolution: `bright_ti4` for VIIRS, `brightness` for MODIS); datetime parsing;
  coordinate sanity checks.

### 3. Feature engineering **[AUTOMATED]** (`src/features/engineer.py`)

Per detection: `bt_kelvin`, `bt_11_kelvin`, `frp_mw`, `persistence_count`
(cross-file count of re-detections in the same ~1 km grid cell over the NRT
window), `day_night`, `agri_season_flag` (month ∈ `{10,11,4,5,7,8,9,1,2}`),
`spatial_grid_id` (1°), `grid_key_1km` (0.01°), `confidence`, and — via a
BallTree haversine query against `facilities.parquet` —
`dist_nearest_facility_km`, `nearest_facility_type`, `nearest_facility_source`.
**These are model inputs, never labels. Facility proximity is a feature, never
ground truth.**

### 4. Assemble & split **[AUTOMATED]** (`src/model/assemble.py`, `split.py`)

- **VNF oracle:** build a BallTree over VNF gas-flare sites; a global FIRMS row
  within `VNF_ORACLE_KM = 5` km of a VNF site → `label = "A"`, else
  `"B_candidate"`. VNF rows are excluded from training (their `avg_temp` 1500–2000 K
  is a different physical quantity from FIRMS `bt_kelvin` 300–500 K).
- **Spatial-grid split:** non-India rows grouped into 1° × 1° cells; cells
  shuffled with `seed=42` and assigned 80 % → `train_global`, 20 % →
  `validation_global`. A whole cell goes to one side — **never split at the row
  level**.
- **Leakage assertions must pass:** no India coordinate in train/val; disjoint
  grid cells; (facility overlap; label ↔ split correlation).

### 5. Classification **[AUTOMATED]** (`src/model/train.py`)

- `Pipeline(SimpleImputer(median), RandomForestClassifier(300 trees,
  min_samples_leaf=10, class_weight="balanced", random_state=42))`, **7
  features** (§Part 1.3, all FIRMS-native and available at India inference time).
- **Three-way evaluation, reported side by side:** random-split baseline
  (inflated), spatial-grid holdout (honest — this is the model that is saved and
  used), India geographic holdout (no labels — predicted distribution + anomaly
  rate only).
- Output per India detection: `predicted_label` (A / B_candidate), `prob_A`,
  `prob_B_candidate`, `max_prob`.

### 6. Anomaly flag **[AUTOMATED]**

- `max(prob) < 0.55` → the detection matches neither learned pattern →
  "Industrial Fire / Abnormal Thermal Event" candidate. **Not a model class — a
  post-hoc flag.** FIRMS's own `confidence` field is carried through as a
  secondary signal.
- The UI presents model probabilities as "model class probability", **never** as
  a fabricated detection-confidence percentage.

### 7. Risk scoring & alert generation **[AUTOMATED]** (`src/alerting/`)

- `risk_engine.score_dataframe` derives, per detection: `output_class` (the
  3-class label, from anomaly flag + `predicted_label`), `risk_score` (0–100,
  transparent additive rule), `severity` (≥65 CRITICAL / ≥40 HIGH / ≥20 MEDIUM /
  <20 LOW), `land_cover_context`, `hazard_facility_type`, `narrative`,
  `nearest_city`, `dist_nearest_city_km`, `near_population`, and `risk_factors`
  (the list of `(reason, +points)` components that produced the score).
- `pipeline.run()` inserts non-duplicate rows into `data/alerts.db` with an
  initial status by severity (CRITICAL/HIGH → `ALERTED`, MEDIUM → `VALIDATING`,
  else `DETECTED`).
- On first app launch the store auto-seeds if `alerts.db` is absent.

### 8. Incident evaluation set **[AUTOMATED]** (`src/scoring/score_incidents.py`)

- 30 curated real Indian industrial incidents (2019–2023) scored through the
  model → `stage7_incident_scores.parquet` (21/30 anomaly-flagged in the training
  run). Thermal features are NaN (no historical FIRMS archive) and imputed;
  scoring leans on `dist_nearest_facility_km` / `agri_season_flag` / `acq_month`.
  Independent evaluation / demo only — **not a training class**.
- `src/labeling/match_incidents.py` independently checks each incident for a FIRMS
  detection within 1 km / ±1 day: **0/30 match** (NRT vs 2019–2023). Unmatched
  incidents are kept as satellite-omission *findings*, not discarded.

### Live FIRMS NRT refresh **[AUTOMATED, runtime]** (`src/ingestion/refresh.py`)

When `FIRMS_MAP_KEY` is set **and** `data/processed/stage6_model.joblib` is
present locally, `maybe_refresh()` runs at dashboard startup (and on the sidebar
`↻ Refresh Data` button): if `today − MAX(acq_date)` in `alerts.db` exceeds the
threshold, it fetches fresh VIIRS+MODIS NRT for the India bbox, rebuilds the 7
feature columns, runs the joblib model, rewrites `stage6_india_scores.parquet`,
and reseeds `alerts.db` via `pipeline.run(fresh=True)`. **Any failure falls back
to the existing data silently** — the dashboard always has data. Without the key
or the model file, the committed snapshot is used and the status is `no_key` /
`no_model`.

---

## Part 2 — Serving & interaction

Everything below runs in the Streamlit app against `alerts.db` (committed-snapshot
seed, or live-refreshed).

### 9. Geographic visualisation **[AUTOMATED render / MANUAL explore]**

- **Map Explorer** and the **Command Center map** plot every scored India
  detection at its true lat/lon on the CARTO dark basemap, coloured by class
  (or severity), radius by risk. Neighbouring-country labels stay visible for
  context; a thin India outline is drawn on top.
- **Layers:** confirmed-incident overlay (default on), optional facility layer,
  optional "Regional context (outside India)" layer (dim, true coordinates),
  optional "Thermal Events" centroid overlay (amber, a separate deck below the
  main map).
- **Geography is authoritative:** `geo.resolve(lat, lon)` runs pure-Python
  point-in-polygon over a bundled 1.2 MB admin GeoJSON. A city name never implies
  a state; out-of-India points are flagged (`in_india=False`), never moved.
- **[MANUAL]** the analyst pans/zooms, toggles layers and colour-by, hovers for
  metrics, clicks a detection to investigate it, and can open the **Data
  validation** expander to verify the plotted layer (counts, lat/lon ranges,
  per-zone breakdown, sample rows).

### 10. Thermal-event clustering **[AUTOMATED, derived]**

- On any read of events, `queries._events_cached` runs
  `clustering.cluster_alerts(alerts, spatial_km=15, temporal_days=3)`: union-find
  over all pairs, merging two alerts when haversine ≤ 15 km AND |date gap| ≤ 3
  days. Deterministic event id = `sha256(sorted alert_ids)[:8]`.
- Cached by `alerts.db` mtime → auto-recomputes when the data changes. No DB
  table.
- Each event carries 29 fields (centroid, dates, duration, observation count,
  spatial extent, peak/mean FRP & BT, night/day counts, max persistence, nearest
  facility, predicted class, max model probability, anomaly flag, max risk, max
  severity, resolved state/district/zone, output class).

### 11. Event intelligence **[AUTOMATED, on demand]**

For a given event:

- **Fingerprint** (`fingerprint.compute_fingerprint`) — six behavioural
  dimensions (persistence, night activity, FRP intensity, spatial stability,
  industrial proximity, seasonal alignment), each rated VERY LOW … VERY HIGH,
  producing one of six behaviour categories.
- **Evidence stack** (`evidence.build_evidence`) — SUPPORTING / LIMITING /
  NEUTRAL items with category, value, explanation, and source; always includes
  the two SYSTEM limiting items (VIIRS/MODIS resolution; no ground confirmation).
- **Evolution** (`evolution.build_evolution`) — an ordered frame sequence
  (cumulative count, FRP, risk, lat/lon, day/night) plus milestones (First
  Detection; Persistence Detected; Peak FRP Observed; High-Risk Threshold
  Crossed).
- **Risk trajectory** (`early_warning.compute_trajectory`) — from the frame-level
  risk history: `trajectory` (INCREASING / STABLE / DECREASING) and `state`
  (STABLE / WATCH / INCREASING / EARLY WARNING / HIGH PRIORITY), with a signal
  breakdown. **Describes an observed trend — never predicts.**

### 12. Facility thermal baseline & deviation **[AUTOMATED, on demand]**

For a given event (`queries.get_event_deviation`):

1. The event centroid is matched to its nearest India facility via the shared
   BallTree (`queries._facility_index`). If the nearest facility is > 10 km away,
   there is no baseline (`NO_FACILITY`).
2. `facility_fingerprint.build_facility_baseline` derives a baseline from every
   India detection within 10 km of that facility: robust statistics
   (median / IQR / MAD) for FRP and brightness temperature, median persistence,
   day-night ratio, active months, and the observed window.
3. **Gate:** with fewer than 6 observations across fewer than 2 distinct dates →
   `baseline_quality = INSUFFICIENT_BASELINE` and no deviation is computed — an
   honest state, not an invented one. (With a ~5-day FIRMS window this is the
   common case.)
4. `facility_fingerprint.compare_event_to_baseline` scores each available signal
   0–100 (intensity, brightness, persistence, day/night, seasonal), combines them
   by a configurable weight map → `thermal_deviation_score` (0–100) and a level
   (NORMAL / ELEVATED / ABNORMAL / HIGHLY_ABNORMAL), with deterministic evidence
   strings citing the actual numbers.
5. This score is **surfaced separately** — on the Investigation "Facility Thermal
   Baseline" panel, the Facilities table, and the Analytics section — and is
   **never folded into `risk_score`** (`risk_engine.deviation_factor` exists as
   an opt-in helper but is not called by `score_row`).

### 13. Investigation workflow **[MANUAL, system-assembled]**

`queries.get_investigation(alert_id)` assembles the sectioned view (header,
detection, context, why-flagged, classification, risk assessment, recommended
action) from real alert fields only. `dashboard/views/investigation.py` adds the
event panels (fingerprint, evidence, evolution replay, trajectory, facility
baseline) when the alert belongs to a multi-detection event. The analyst reads
the "why", the comparisons, and the recommendation, then decides — journey F.

### 14. Analyst manual controls **[MANUAL]**

- **Filters** — severity, status, classification, state, window (All / Latest day
  / Last 3 days / Last 7 days). Shared across pages via `dashboard/state.py`.
- **Alert feed** — severity-grouped, paginated (12/page); expand for the
  narrative + actions.
- **Lifecycle actions** — **Acknowledge** (→ MONITORING), **Escalate**
  (→ ESCALATED), **Resolve** (→ EXTINGUISHED). Written to `alerts.db` via
  `alert_store.update_status`, with toast feedback. **Manual only — the agent
  cannot do this.**
- **Re-run pipeline** — the Command Center quick action reseeds `alerts.db` from
  the scored parquet.
- **↻ Refresh Data** — the sidebar button forces a live FIRMS refresh (when
  `FIRMS_MAP_KEY` is set).

### 15. Fire Intelligence Agent workflow **[AGENT-ASSISTED, READ-ONLY]**

The mode indicator shows **Claude-enhanced reasoning** when `ANTHROPIC_API_KEY`
is set, **Local intelligence mode** otherwise.

```
Analyst opens the agent (docked on Command Center, or ⌘ Ask Agent on any page)
        │
        ▼
Types a natural-language query
        │
        ▼
runtime.ask(query, {page, filters, focus_alert_id})       ← never raises
        │
        ├─ ANTHROPIC_API_KEY set + anthropic importable → Claude tool-use loop (≤4 rounds)
        │                                                  any failure → fall through
        └─ otherwise                                     → deterministic parser (baseline)
        │
        ▼
Emits read-only tool call(s) from the fixed 26-tool registry:
   alert/analytics (13): list_alerts, rank_alerts, get_alert, get_investigation,
     situation_summary, compare_regions, facilities_with_activity, analytics_summary,
     baseline_comparison, incidents, build_incident_report, export_geojson, export_csv
   thermal event (8): list_events, get_event, get_event_fingerprint, get_event_evidence,
     get_event_evolution, get_event_trajectory, find_increasing_risk_events, events_situation
   facility fingerprint (5): get_facility_fingerprint, get_event_deviation,
     rank_facilities_by_deviation, find_abnormal_facilities, facility_fingerprint_summary
        │
        ▼
Tools run against src/intelligence/ → src/alerting/ + committed data
        │
        ▼
response.build() → a grounded NL answer + result_cards + ui_action
        │
        ▼
Panel renders the answer and cards:
   [Open Investigation]  → focus_alert_id + navigate to Investigation
   [Show on Map]         → apply filters + navigate to Map Explorer
   [Generate Report]     → navigate to Reports / GIS (same build_incident_report)
        │
        ▼
ui_action applied via dashboard/state.py → st.rerun()
   (indistinguishable from the analyst having set those filters / navigated by hand)
```

**May:** answer from real data; search / filter / rank / aggregate over alerts,
events, and facilities; find increasing-risk events; find abnormal facilities;
apply shared filters; navigate; focus the map; open an investigation; generate a
report.

**Must not:** acknowledge / escalate / resolve / modify any incident state
(a state-change request is explained and redirected to the manual control with an
"Open Investigation" card); fabricate a value (says "not available"); issue SQL
or arbitrary code; open a second map; dominate the UI; crash the panel.

### 16. Reporting workflow **[MANUAL or AGENT-ASSISTED]**

- **GIS export** — filter-aware GeoJSON `FeatureCollection` (each alert a Point
  with the full attribute table) and CSV (`actions.export_geojson` /
  `export_csv`).
- **Incident report** — `actions.build_incident_report(filters)` → a Markdown /
  CSV summary of the filtered critical/high alerts for the current window.
- Triggered from Reports / GIS, or by the agent ("generate a report for critical
  industrial fires this week") — the same underlying function.

### 17. Feedback **[MANUAL]**

- Lifecycle state changes are the analyst's feedback; they persist in `alerts.db`
  and flow through to the counts and the daily aggregation on the next rerun.
- **No model-retraining feedback loop** this round.

---

## Part 3 — User journeys

Notation: **[A]** automated · **[M]** manual · **[G]** agent-assisted (read-only).

### A. Analyst discovers new thermal activity

1. **[A]** The pipeline has scored the latest FIRMS India detections; alerts are
   in the store (or a live refresh just reseeded it).
2. **[M]** Opens the **Command Center**: reads the KPI row (active alerts,
   criticals) and the event KPI row (thermal events, high-risk, persistent
   sources, early warnings), scans the live map, checks the top priority alerts
   and the activity timeline.
3. **[M]** Something stands out (a red cluster; a spike on the timeline; a
   non-zero "Early Warnings" count) → clicks a priority-alert card or a map
   marker → journey B.

### B. Analyst investigates an alert / event

1. **[M]** From Alerts (`View investigation →`), the Map (marker), the THERMAL
   EVENTS tab (`Investigate →`), or an agent result card → **Investigation** for
   that alert.
2. **[A]** `get_investigation` assembles the base view; the event panels
   (fingerprint, evidence, evolution, trajectory, **facility baseline**) render
   when the alert belongs to a multi-detection event.
3. **[M]** Reads **Why flagged**, **Risk assessment**, the **Risk Trajectory**,
   and the **Facility Thermal Baseline** — is this event unusual *for this site*?
4. **[M]** Cross-checks on the map ("Show on map →"); generates a report if
   useful → journey F.

### C. Analyst asks the agent a question

1. **[M]** *"Which persistent sources near industrial facilities in Odisha are
   unusual for their site?"* or *"How unusual is event `3ac7afa3`?"*
2. **[A/G]** Deterministic parser (or Claude) extracts the intent → calls
   `queries.list_alerts` / `get_event_deviation` / `rank_facilities_by_deviation`.
3. **[A]** A grounded answer + result cards render. Real values only; anything
   missing is stated as "not available" (e.g. INSUFFICIENT_BASELINE).
4. **[M]** Clicks **Open Investigation** on the top result → journey B.

### D. Analyst filters the map with natural language

1. **[M]** *"Show critical alerts in eastern India from the last 7 days."*
2. **[A/G]** Parser → `ui_action = {nav: "Map Explorer", filters: {severity:
   ["CRITICAL"], region: "eastern india", date_from: hi-7, date_to: hi}}`.
3. **[A]** `state.py` applies the filters; the app reruns; **Map Explorer** shows
   exactly that subset — identical to setting the filters by hand.
4. **[M]** Continues manually (zoom, click, toggle layers).

### E. Analyst generates a report

1. **[M]** On Reports / GIS, or via the agent (*"Generate a report for critical
   industrial fires this week"*).
2. **[A]** `build_incident_report(filters)` builds the Markdown / CSV summary from
   real alert fields; GeoJSON / CSV export is available alongside.
3. **[M]** Downloads the artefact for a briefing or a GIS tool.

### F. Analyst manually acknowledges / escalates / resolves

1. **[M]** From the Alerts expander or the Investigation page, chooses
   **Acknowledge**, **Escalate**, or **Resolve**.
2. **[A]** `alert_store.update_status` writes the new lifecycle state (and
   `acknowledged_at` for Acknowledge) to `alerts.db`; a toast confirms.
3. **[A]** The feed, counts, event clustering, and daily aggregation reflect the
   change on the next rerun (the DB-mtime cache key invalidates).
4. Note: **the agent cannot perform this step.** If asked, it explains the manual
   control and offers to open the Investigation.

---

## Automated vs manual vs agent-assisted — summary

| Action | Automated | Manual | Agent (read-only) |
|---|:--:|:--:|:--:|
| FIRMS ingestion, cleaning, feature engineering | ✅ | | |
| Facility-context enrichment (BallTree proximity) | ✅ | | |
| RandomForest classification + anomaly flag | ✅ | | |
| Persistence detection | ✅ | | |
| Risk scoring + severity + alert creation | ✅ | | |
| Store seeding / auto-seed on first run | ✅ | ✅ (Re-run) | |
| Live FIRMS NRT refresh | ✅ (startup) | ✅ (↻ Refresh Data) | |
| Thermal-event clustering | ✅ (derived) | | |
| Event fingerprint / evidence / evolution / trajectory | ✅ (on demand) | | |
| Facility thermal baseline + deviation | ✅ (on demand) | | |
| Investigation assembly | ✅ | | |
| Browsing / filtering / navigating / focusing the map | | ✅ | ✅ |
| Opening an investigation | | ✅ | ✅ |
| Asking questions / ranking / comparing / summarising | | ✅ | ✅ |
| GIS export / incident report | | ✅ | ✅ |
| Acknowledge / Escalate / Resolve; any state change | | ✅ | ❌ (deferred) |
| Model retraining | ❌ (offline pipeline, not in the app) | | ❌ |
