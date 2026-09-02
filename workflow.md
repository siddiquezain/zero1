# SIH26162 — End-to-End System Workflow

> The complete operational workflow, from satellite data to an analyst decision,
> plus the main user journeys. Derived from the approved plan and the existing
> codebase. Companion to `context.md`, `design_brief.md`, `architecture.md`.
>
> Each step is marked **[AUTOMATED]** (system does it), **[MANUAL]** (analyst does
> it), or **[AGENT-ASSISTED]** (analyst asks, agent helps — read-only).
> Legend also: **[IMPLEMENTED]** · **[PLANNED]** · **[OPTIONAL/FUTURE]**.

---

## Part 1 — Data → Intelligence pipeline

This is the offline pipeline that produces the data the dashboard serves. It is
**[IMPLEMENTED]** (Stages 1–8) and **not modified this round**; the committed
Parquet outputs are what the app reads.

### 1. Data acquisition **[AUTOMATED] [IMPLEMENTED]**

- NASA FIRMS NRT active-fire detections pulled for the India bounding box
  (`src/ingestion/firms.py`), plus 6 non-India regions for training.
- VIIRS Nightfire (VNF) global gas-flare catalogue (`src/ingestion/vnf.py`).
- WRI Global Power Plant Database + OSM `landuse=industrial` polygons
  (`src/ingestion/facilities.py`).
- Every row tagged with `split` (`train_global` / `validation_global` /
  `india_holdout`) **at ingest time**.
- Limitation: FIRMS NRT covers only ~5 days; no historical archive.

### 2. FIRMS / thermal-anomaly ingestion **[AUTOMATED] [IMPLEMENTED]**

- Raw CSV/Parquet written to `data/raw/`; row counts logged; leakage guard
  (`enforce_india_split`) run.

### 3. Data cleaning **[AUTOMATED] [IMPLEMENTED]**

- Column normalisation across MODIS/VIIRS products; brightness-temperature column
  resolution; datetime parsing; coordinate sanity checks.

### 4. Feature extraction **[AUTOMATED] [IMPLEMENTED]** (`src/features/engineer.py`)

Per detection: `bt_kelvin`, `bt_11_kelvin`, `frp_mw`, `persistence_count`
(same ~1 km cell re-lit within the window — the strongest discriminator),
`day_night`, `agri_season_flag`, `spatial_grid_id`, `grid_key_1km`, `confidence`.
These are **model inputs, never labels.**

### 5. Industrial / facility context enrichment **[AUTOMATED] [IMPLEMENTED]**

- BallTree (haversine) nearest-facility query against `facilities.parquet` →
  `dist_nearest_facility_km`, `nearest_facility_type`, `nearest_facility_source`.
- Facility proximity is a **feature, never a ground-truth label**.

### 6. Classification **[AUTOMATED] [IMPLEMENTED]** (`src/model/`)

- RandomForest, 7 features, trained on global data with India held out; spatial-
  grid split; VNF used as a labelling oracle only.
- Output per India detection: `predicted_label` (A / B_candidate), `prob_A`,
  `prob_B_candidate`.

### 7. Confidence calculation **[AUTOMATED] [IMPLEMENTED]**

- Model class probabilities per detection.
- **Anomaly rule:** `max(prob) < 0.55` → the detection matches neither learned
  pattern → **Industrial Fire / Abnormal Thermal Event** candidate.
- FIRMS's own `confidence` field is carried through as a secondary signal.
- The UI presents this as "model class probability", **not** as a fabricated
  detection-confidence percentage.

### 8. Persistent thermal-source detection **[AUTOMATED] [IMPLEMENTED]**

- `persistence_count` per ~1 km cell over the NRT window; high persistence + Class
  A + near facility → **Persistent Industrial Thermal Source**.

### 9. Alert generation **[AUTOMATED] [IMPLEMENTED]** (`src/alerting/`)

- `risk_engine.score_dataframe` derives, per detection:
  `output_class` (3-class), `risk_score` (0–100, transparent additive rule),
  `severity` (CRITICAL ≥ 65 / HIGH ≥ 40 / MEDIUM ≥ 20 / LOW), `land_cover_context`,
  `hazard_facility_type`, `narrative`, `nearest_city`, `dist_nearest_city_km`,
  `near_population`.
  - **[PLANNED additive]** `risk_factors` — the list of `(reason, +points)`
    components that produced the score (for the Investigation view).
- `pipeline.run()` inserts non-duplicate rows into `data/alerts.db` with an
  initial status by severity (CRITICAL/HIGH → `ALERTED`, MEDIUM → `VALIDATING`,
  else `DETECTED`).
- On first app launch the store auto-seeds if `alerts.db` is absent.

### Incident evaluation set **[AUTOMATED] [IMPLEMENTED]** (`src/scoring/`)

- 30 curated real Indian industrial incidents scored through the model →
  `stage7_incident_scores.parquet` (21/30 anomaly-flagged). Independent
  evaluation / demo only — **not a training class**.

---

## Part 2 — Serving & interaction workflow

Everything below runs in the Streamlit app against the committed data + `alerts.db`.

### 10. Geographic visualisation **[AUTOMATED render / [MANUAL] explore] [IMPLEMENTED map, PLANNED page]**

- The India detection map (pydeck + Carto dark) plots scored detections coloured
  by class (or severity), with the confirmed-incident overlay and an optional
  facility layer.
- **[PLANNED]** `geo.annotate_states` adds a `state` column so detections/alerts
  can be filtered and summarised by Indian state / region.
- **[MANUAL]** analyst pans/zooms, toggles layers and colour-by, hovers for
  metrics, clicks a detection to investigate it.

### 11. Investigation workflow **[MANUAL, system-assembled] [PLANNED]**

Entering Investigation for an alert (`queries.get_investigation(alert_id)`), the
analyst sees, assembled from real fields only:

1. **Incident header** — class, city + state, `RISK n/100`, model class
   probability, status.
2. **Detection** — FRP, persistence, detection date/time, day/night, coordinates,
   satellite/instrument (VIIRS 375 m), FIRMS confidence.
3. **Context** — distance to nearest facility + hazard type, land-cover context,
   nearest city + population (only when present).
4. **Why flagged** — the checklist of signals that actually fired (repeat
   detections, near industrial facility, industrial land-use match, elevated FRP,
   night-time detection, pattern anomaly). Absent/false signals are omitted.
5. **Classification** — 3-class output + `predicted_label` + class probabilities +
   the locked "anomalous departure, not a confirmed fire" framing.
6. **Risk assessment** — the real `risk_factors` breakdown summing to the score.
7. **Recommended action** — one operational recommendation derived from
   `(severity, class, anomaly_flag)`, e.g. "ESCALATE FOR FIELD VERIFICATION" with
   a one-line reason.

The analyst then decides — see journey B.

### 12. Analyst interaction (manual controls) **[MANUAL] [IMPLEMENTED]**

- **Filters** — severity, status, date (Today / 24h / 7d / custom), classification;
  **[PLANNED]** region/state. Shared across Command Center, Alerts, Map, Analytics.
- **Alert feed** — severity-grouped, paginated; expand for assessment.
- **Lifecycle actions** — **Acknowledge** (→ MONITORING), **Escalate**
  (→ ESCALATED), **Resolve** (→ EXTINGUISHED). These write to `alerts.db` via
  `alert_store.update_status`. **Manual only.**
- **Analytics** — activity strip, calendar, period analysis, playback;
  **[PLANNED]** baseline-vs-current FRP comparison.
- **Facilities [PLANNED]** — table of known facilities with nearby detection
  counts, repeat counts, max risk, historical activity.
- **Pipeline re-run** — manual "Re-run" reseeds `alerts.db` from the scored data.

### 13. Fire Intelligence Agent workflow **[AGENT-ASSISTED, READ-ONLY] [PLANNED / OPTIONAL]**

```
Analyst opens "⌘ Fire Intelligence" (command palette) on any page
        │
        ▼
Types a natural-language query
        │
        ▼
runtime.ask(query, {current_page, active_filters})
        │
        ├─ ANTHROPIC_API_KEY set  → Claude tool-use loop      [OPTIONAL/FUTURE]
        └─ otherwise              → deterministic parser       [PLANNED — baseline, always works]
        │
        ▼
Parser/LLM emits read-only tool call(s) from the fixed registry
   (queries.list_alerts / rank_alerts / situation_summary / compare_regions /
    get_investigation / facilities_with_activity / analytics_summary /
    baseline_comparison / incidents;
    actions.export_geojson / export_csv / build_incident_report)
        │
        ▼
Tools run against src/intelligence/ → src/alerting/ + committed data
        │
        ▼
response.py formats a grounded NL answer + result_cards + ui_action
        │
        ▼
Panel shows the answer and result cards:
   [Open Investigation]  → set focus_alert_id + navigate to Investigation
   [Show on Map]         → apply filters + navigate to Map (the existing map)
   [Generate Report]     → build_incident_report → download
        │
        ▼
ui_action applied through dashboard/state.py → st.rerun()
   (identical to the analyst having set those filters / navigated by hand)
```

What the agent **may** do this round: answer questions from real data; search /
filter / rank / aggregate; apply shared filters; navigate; focus the existing map;
open an investigation; generate a report.

What the agent **must not** do this round: acknowledge / escalate / resolve /
modify any incident state; fabricate a value (it says "not available"); issue SQL
or arbitrary code; open a second map; dominate the UI. A state-change request is
explained and redirected to the manual control (with an "Open Investigation"
card).

**[OPTIONAL/FUTURE]** agent state-changing actions behind an explicit confirmation
gate — deferred.

### 14. Reporting workflow **[MANUAL or AGENT-ASSISTED] [IMPLEMENTED export, PLANNED report]**

- **GIS export** — GeoJSON `FeatureCollection` (each alert a Point with the full
  attribute table) and CSV, both respecting the active filters
  (`actions.export_geojson` / `export_csv`).
- **Incident report [PLANNED]** — `actions.build_incident_report(filters)`
  produces a Markdown / CSV summary of the filtered critical / industrial-fire
  alerts for a period.
- Triggered from the Reports / GIS page, from Investigation ("generate a report
  for this"), or by the agent ("generate a report for critical industrial fires
  this week") — same underlying function.

### 15. Feedback / manual actions **[MANUAL] [IMPLEMENTED]**

- Lifecycle state changes (Acknowledge / Escalate / Resolve) are the analyst's
  feedback into the system and persist in `alerts.db`.
- The daily severity aggregation (`timeline.get_daily_summary`) reflects the
  current store, so Analytics updates as alerts are worked.
- No model-retraining feedback loop this round.

---

## Part 3 — User journeys

Notation: **[A]** automated system action · **[M]** manual analyst action ·
**[G]** agent-assisted (read-only).

### A. Analyst discovers new thermal activity

1. **[A]** Pipeline has scored the latest FIRMS India detections; alerts are in
   the store.
2. **[M]** Analyst opens the **Command Center**: reads the situation line
   (active alerts, criticals), scans the live map, sees the top-5 priority
   alerts and the 14-day activity strip.
3. **[M]** Something stands out (a red cluster, a spike on the strip) → clicks a
   priority-alert row or a map marker.
4. → journey B.

### B. Analyst investigates an alert

1. **[M]** From Alerts (row → "View Investigation") or the Map (marker) or the
   agent (result card), the analyst lands on **Investigation** for that alert.
2. **[A]** `get_investigation` assembles the sectioned view.
3. **[M]** Analyst reads **Why flagged** and **Risk assessment** — the real
   evidence — and the **Recommended action**.
4. **[M]** Analyst cross-checks on the map ("Show on Map") and, if useful,
   generates a report.
5. → journey F (decide).

### C. Analyst asks the Fire Intelligence Agent a question

1. **[M]** Opens "⌘ Fire Intelligence", asks e.g. *"Which persistent sources are
   close to industrial facilities in Odisha?"*
2. **[A/G]** Deterministic parser (or Claude, if a key is set) extracts
   `output_class = Persistent Source`, `state = Odisha`, `near_facility = true` →
   calls `queries.list_alerts` / `facilities_with_activity`.
3. **[A]** A grounded answer + result cards render. Values are real; anything
   missing is stated as "not available".
4. **[M]** Analyst clicks **Open Investigation** on the top result → journey B.

### D. Analyst filters the map using natural language

1. **[M]** Asks *"Show me critical alerts in eastern India from the last 7 days."*
2. **[A/G]** Parser → `ui_action = { nav: "map", filters: { severity:
   ["CRITICAL"], region: "eastern india", date_from: today-7, date_to: today } }`.
3. **[A]** `state.py` applies the filters; app reruns; the **Map** shows exactly
   that subset — the same result as setting those filters by hand.
4. **[M]** Analyst continues manually (zoom, click, toggle layers).

### E. Analyst generates a report

1. **[M]** On Reports / GIS (or via Investigation, or via the agent: *"Generate a
   report for critical industrial fires this week"*).
2. **[A]** `actions.build_incident_report(filters)` builds the Markdown / CSV
   summary from real alert fields; GeoJSON / CSV export is available alongside.
3. **[M]** Analyst downloads the artefact for a briefing or a GIS tool.

### F. Analyst manually acknowledges / escalates / resolves an alert

1. **[M]** From Alerts (expander) or Investigation, the analyst chooses
   **Acknowledge**, **Escalate**, or **Resolve**.
2. **[A]** `alert_store.update_status` writes the new lifecycle state (and
   `acknowledged_at` for Acknowledge) to `alerts.db`.
3. **[A]** The feed, counts, and daily aggregation reflect the change on the next
   rerun.
4. Note: **the agent cannot perform this step.** If asked, it explains the manual
   control and offers to open the Investigation.

---

## Automated vs manual vs agent-assisted — summary

| Action | Automated | Manual | Agent (read-only) |
|---|:--:|:--:|:--:|
| FIRMS ingestion, cleaning, feature extraction | ✅ | | |
| Facility-context enrichment | ✅ | | |
| Classification + anomaly flag | ✅ | | |
| Persistence detection | ✅ | | |
| Risk scoring + severity + alert creation | ✅ | | |
| Store seeding / auto-seed on first run | ✅ | ✅ (Re-run) | |
| Investigation assembly | ✅ | | |
| Browsing / filtering / navigating | | ✅ | ✅ |
| Focusing the map | | ✅ | ✅ |
| Opening an investigation | | ✅ | ✅ |
| Asking questions / ranking / comparing / summarising | | ✅ | ✅ |
| GIS export / incident report | | ✅ | ✅ |
| Acknowledge / Escalate / Resolve | | ✅ | ❌ (deferred) |
| Modifying incident state in any way | | ✅ | ❌ (deferred) |
| Model retraining | | | |
