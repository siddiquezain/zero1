# SIH26162 — Project Context (Source of Truth)

> Read this file in full before doing any work. It describes what the project is,
> what is already built, what is planned, and what must not be done or claimed.
> Update the **Status Tracker** at the bottom after every work session.
>
> Companion documents at repo root:
> - `design_brief.md` — product identity + UI/UX blueprint per screen
> - `architecture.md` — technical architecture, modules, interfaces, agent design
> - `workflow.md` — end-to-end operational workflow and user journeys

---

## 1. Project identity

| | |
|---|---|
| **Project name** | India Thermal Event Intelligence Platform (Team ZeroOne) |
| **SIH problem statement** | SIH26162 |
| **Sponsor / context** | NTRO (National Technical Research Organisation), Smart India Hackathon 2026 |
| **Official PS title** | "AI-Based Detection and Classification of Industrial Fires and Persistent Thermal Sources Using NASA FIRMS, OSM & Satellite Data" |
| **Immediate milestone** | Internal hackathon demo — 5 September |

### Problem statement in our own words

Satellite thermal-anomaly feeds (NASA FIRMS MODIS/VIIRS) report *where* a hotspot
is, but never *what caused it*. Operators monitoring Indian industrial regions
cannot easily separate an accidental industrial fire from a routine gas flare,
a steel-plant thermal signature, or seasonal crop-residue burning — and the raw
feed offers no prioritisation, no context, and no explanation. There is also no
existing dataset of confirmed industrial fire incidents anywhere in the world to
train a direct classifier on.

Raw detections are also point-level: multiple FIRMS pixels from a single burning
location arrive as separate rows over hours or days, giving no event-level picture
of how a thermal source is evolving, how persistent it is, or what its behavioural
pattern implies.

### Why it matters

Industrial fires near refineries, chemical plants, power stations and mining
areas threaten life, infrastructure and the environment. Faster, better-prioritised
detection with clear supporting evidence lets disaster-management and monitoring
agencies investigate the right sites first. Persistent-thermal-source monitoring
also supports environmental compliance and industrial-activity intelligence.

### Core objective

Turn the raw NASA FIRMS thermal feed over India into a prioritised, explained,
GIS-based operational picture that:

1. Clusters detections into **thermal events** (multi-pixel, multi-day).
2. Characterises each event with a **behaviour fingerprint** (persistence,
   intensity, nocturnality, spatial stability, industrial proximity, seasonality).
3. Builds a structured **evidence stack** (supporting / limiting) for every event.
4. Replays how each event **evolved** over time (milestones + frame-by-frame).
5. Detects **early-warning trajectories** (risk trend, state: STABLE → HIGH PRIORITY).
6. Distinguishes detection classes:
   - **Industrial Fire / Abnormal Thermal Event** — anomalous departure from known patterns.
   - **Persistent Industrial Thermal Source** — continuous heat: gas flares, kilns, smelters.
   - **Forest / Agricultural Fire** — natural or crop-residue burning.

### What the system actually does

- Ingests NASA FIRMS NRT detections for the India bounding box.
- Enriches each detection with engineered features: brightness temperature, FRP,
  persistence count, day/night, distance to nearest industrial facility, facility
  type, agricultural-season flag, land-cover context.
- Classifies each detection into the 3 output classes above using a globally
  trained Random Forest (India held out of training) plus an anomaly rule.
- Scores each detection with a transparent rule-based **risk engine** (0–100) and
  assigns a severity (CRITICAL / HIGH / MEDIUM / LOW).
- Raises alerts into a SQLite store with a lifecycle
  (DETECTED → VALIDATING → ALERTED → ESCALATED → MONITORING → EXTINGUISHED).
- **Clusters alerts into thermal events** using union-find spatial+temporal
  grouping (≤15 km, ≤3 days). Each event has a deterministic SHA-256 ID.
- **Fingerprints** each event across 6 behavioural dimensions, assigning a
  behaviour category (Persistent Industrial Signature, Recurring Thermal Source,
  Rapidly Expanding Fire Signature, Seasonal Agricultural Signature, Isolated
  Thermal Anomaly, Insufficient Evidence).
- **Builds an evidence stack** — structured SUPPORTING / LIMITING / NEUTRAL items
  grounded in real observation values.
- **Replays event evolution** — ordered frame sequence + milestones (First Detection,
  Persistence Detected, Peak FRP, High-Risk Threshold Crossed).
- **Computes risk trajectory** — STABLE / WATCH / INCREASING / EARLY WARNING /
  HIGH PRIORITY from the frame-level risk history.
- Presents everything on a dark operations dashboard: situation overview, alert
  feed, event feed, India detection map with event centroid overlay, investigation
  with full event intelligence panels, and GIS export (GeoJSON / CSV).
- Scores a curated set of 30 real past Indian industrial incidents as an
  independent evaluation / demo set.
- Offers a **Fire Intelligence Agent** that reasons over events (not just raw
  alerts): list events, get fingerprint, evidence, evolution, trajectory, find
  increasing-risk events.

### Target users

- Disaster-management / emergency-monitoring analysts.
- Industrial-safety and environmental-compliance monitoring teams.
- Technical evaluators (SIH judges, NTRO/ISRO/NRSA-adjacent audiences).

### Core use cases

1. **Situational awareness** — "What thermal activity is happening over India
   right now, and how serious is it?"
2. **Triage** — "Which events need attention first?"
3. **Investigation** — "Why was this event flagged, what is its behaviour pattern,
   and what should we do?"
4. **Early warning** — "Which events are on an increasing risk trajectory?"
5. **Historical analysis** — "How does today compare to the recent baseline?"
6. **Facility monitoring** — "What is happening around known industrial sites?"
7. **Reporting / hand-off** — "Export the current picture for GIS tools or a
   briefing."
8. **Natural-language access** — "Ask the platform instead of manually driving
   filters." (Fire Intelligence Agent, read-only.)

---

## 2. Scope

### Approved scope (implemented — as of Session 10)

- **Thermal Event Clustering** — union-find algorithm groups FIRMS detections into
  events (≤15 km spatial, ≤3 days temporal). `ThermalEvent` dataclass with 29
  fields. Deterministic event IDs.
- **Thermal Behaviour Fingerprinting** — 6-dimension rating (persistence,
  night_activity, frp_intensity, spatial_stability, industrial_proximity,
  seasonal_alignment) + 6 behaviour categories.
- **Evidence Stack / Explainability** — `EvidenceItem` with direction
  SUPPORTING | LIMITING | NEUTRAL. Always includes system-level FIRMS-resolution
  and no-ground-truth limiting items. No fabrication.
- **Event Evolution Replay** — ordered frame sequence (cumulative count, FRP,
  risk score, lat/lon, day/night) + milestones. Dashboard replay slider.
- **Early Warning / Risk Trajectory** — STABLE / WATCH / INCREASING / EARLY
  WARNING / HIGH PRIORITY state from frame-level risk history. Shown on
  Investigation page with signal breakdown.
- **Fire Intelligence Agent upgrade** — 8 new event-level read-only tools +
  event intents in the deterministic parser.
- **Investigation page upgrade** — event header, fingerprint panel, evidence
  stack, evolution timeline + replay slider, risk trajectory; all existing panels
  and manual actions preserved.
- **Command Center event KPIs** — 4-column event row: Active Events, High-Risk
  Events, Persistent Sources, Early Warnings.
- **Alerts page event tab** — DETECTIONS / THERMAL EVENTS tab toggle.
- **Map Explorer event layer** — "Thermal Events" checkbox overlays amber event
  centroid ScatterplotLayer.
- **Information-architecture** — Command Center, Alerts, Investigation, Map,
  Analytics, Facilities, Reports / GIS, Model, Limitations pages.
- **`src/intelligence/` service layer** — framework-agnostic Python layer.
- **Offline lat/lon → Indian state / region resolver** (`src/intelligence/geo.py`).
- **Fire Intelligence Agent (READ-ONLY)** — deterministic offline parser baseline;
  optional Claude API enhancement.
- **Live FIRMS NRT refresh** — `src/ingestion/refresh.py` fetches fresh
  VIIRS+MODIS, re-scores via the joblib model, reseeds `alerts.db` when
  `FIRMS_MAP_KEY` is set and data is stale.

### Explicitly out of scope (this round)

- Agent-initiated **Acknowledge / Escalate / Resolve** or any incident-state
  change. (Manual controls stay fully available; the agent is read-only.)
- Any visual-identity rebuild. The current dark operations aesthetic is kept.
- React / FastAPI frontend. (The service layer is structured so this is possible
  later without touching logic.)
- Historical FIRMS archive download, GIHS integration, land-cover raster
  integration, model retraining.
- Real-time streaming ingestion, authentication / multi-user, notifications.

---

## 3. Implementation status

Legend: **[IMPLEMENTED]** works today · **[OPTIONAL/FUTURE]** may be added later · **[NOT SUPPORTED]** will not be built and must not be claimed.

### Data & ML pipeline

- **[IMPLEMENTED]** Stage 1 — FIRMS NRT ingestion for India + 6 global training
  regions; every row tagged `split` at ingest. VNF gas-flare catalogue (83,641
  rows). WRI Global Power Plant DB (34,936). OSM industrial polygons (37,688 India).
- **[IMPLEMENTED]** Stage 2 — normalised facility table
  `data/processed/facilities.parquet` (72,624 rows; columns: `facility_id, lat,
  lon, facility_type, source, name, country`).
- **[IMPLEMENTED / PARTIAL]** Stage 3 — Class A labels from VNF; Class B still
  `B_candidate` pending land-cover validation; 30 curated confirmed incidents in
  `data/incidents/confirmed_incidents_india.csv`.
- **[IMPLEMENTED]** Stage 4 — feature engineering (`src/features/engineer.py`).
- **[IMPLEMENTED]** Stage 5 — assemble & spatial-grid split (`src/model/assemble.py`,
  `src/model/split.py` with leakage assertions).
- **[IMPLEMENTED]** Stage 6 — Random Forest trained global, India held out.
  Outputs committed as `data/processed/stage6_india_scores.parquet` (1105 live
  India detections, Sep 2026; auto-refreshes via `src/ingestion/refresh.py` when
  `FIRMS_MAP_KEY` is set). Trained `.joblib` is git-ignored.
- **[IMPLEMENTED]** Stage 7 — 30 incidents scored →
  `data/incidents/stage7_incident_scores.parquet` (21/30 anomaly-flagged).
- **[IMPLEMENTED]** Stage 8 — multipage Streamlit dashboard.

### Alerting / intelligence

- **[IMPLEMENTED]** `src/alerting/risk_engine.py` — rule-based scoring →
  `output_class`, `risk_score`, `severity`, `land_cover_context`,
  `hazard_facility_type`, `narrative`, `nearest_city`, `dist_nearest_city_km`,
  `near_population`, `factors` (additive breakdown).
- **[IMPLEMENTED]** `src/alerting/alert_store.py` — SQLite store (`data/alerts.db`),
  lifecycle states, `get_alerts()` / `update_status()` / `counts()` / `clear_all()`.
- **[IMPLEMENTED]** `src/alerting/pipeline.py` — `run(fresh=…)` seeds the store
  from `stage6_india_scores.parquet`.
- **[IMPLEMENTED]** `dashboard/timeline.py` — daily severity aggregation and
  range queries over `alerts.db`.

### Thermal Event Intelligence (new in Session 10)

- **[IMPLEMENTED]** `src/intelligence/clustering.py` — `ThermalEvent` dataclass
  (29 fields), `cluster_alerts()`, union-find algorithm, deterministic SHA-256
  event IDs. LRU-cached via `queries._events_cached(_sig)`.
- **[IMPLEMENTED]** `src/intelligence/fingerprint.py` — `compute_fingerprint()`
  returning 6-dimension ratings + behaviour_category + 13 total keys.
- **[IMPLEMENTED]** `src/intelligence/evidence.py` — `EvidenceItem` dataclass,
  `build_evidence()` returning supporting[], limiting[], neutral[] lists. System-
  level FIRMS-resolution and no-ground-truth items always present in limiting[].
- **[IMPLEMENTED]** `src/intelligence/evolution.py` — `build_evolution()` returning
  frame sequence + milestones (First Detection, Persistence Detected, Peak FRP
  Observed, High-Risk Threshold Crossed).
- **[IMPLEMENTED]** `src/intelligence/early_warning.py` — `compute_trajectory(frames)`
  returning state, trajectory (INCREASING/STABLE/DECREASING), delta, risk_history,
  signals.
- **[IMPLEMENTED]** `src/intelligence/queries.py` — extended with 10 event query
  functions: `list_events`, `get_event`, `get_event_for_alert`,
  `get_event_fingerprint`, `get_event_evidence`, `get_event_evolution`,
  `get_event_trajectory`, `find_increasing_risk_events`, `events_situation`.
  LRU cache keyed on `db_signature()`.
- **[IMPLEMENTED]** `dashboard/data.py` — 8 `@st.cache_data(ttl=30)` event wrappers:
  `EVENTS`, `EVENT`, `EVENT_FOR_ALERT`, `EVENT_FP`, `EVENT_EV`, `EVENT_EVO`,
  `EVENT_TRAJ`, `EVENTS_SIT`.
- **[IMPLEMENTED]** `src/intelligence/agent/tools.py` — 8 new read-only event tools.
- **[IMPLEMENTED]** `src/intelligence/agent/deterministic.py` — event ID regex +
  event intents (event_list, event_detail, event_fingerprint, event_evidence,
  event_evolution, event_replay, event_trajectory, find_increasing_risk_events).
  `interpret = parse` alias.

### Dashboard (current)

- **[IMPLEMENTED]** Command Center — 5-column KPI row + 4-column event KPI row
  (Active Events, High-Risk Events, Persistent Sources, Early Warnings), live
  map, top priority alerts, activity strip, agent panel.
- **[IMPLEMENTED]** Alerts — DETECTIONS tab (existing feed) + THERMAL EVENTS tab
  (event cards with `EVENT #XXXXXXXX` labels, risk score, observation count).
- **[IMPLEMENTED]** Investigation — event header (`EVENT #<id>` vs `DETECTION <aid>`),
  fingerprint panel, evidence stack (supporting/limiting/neutral), evolution
  timeline + replay slider (per-frame FRP + risk), risk trajectory panel; all
  existing panels and manual Acknowledge/Escalate/Resolve preserved.
- **[IMPLEMENTED]** Map Explorer — detection layers + "Thermal Events" checkbox →
  amber event centroid ScatterplotLayer overlay.
- **[IMPLEMENTED]** Analytics, Facilities, Reports / GIS, Model, Limitations.
- **[IMPLEMENTED]** Fire Intelligence Agent — deterministic offline runtime (reads
  events, fingerprints, evidence, evolution, trajectories); optional Claude API.

### Existing features that must NOT be removed

Severity / status / date / classification filters · alert pagination · alert
detail / assessment · Acknowledge / Escalate / Resolve (manual) · lifecycle
states · India detection map with zoom, markers, classification colours,
incident overlay, facility layer, colour-by toggle, legend, tooltips · historical
timeline · activity strip · calendar view · period analysis · playback · GIS
export (GeoJSON + CSV) + preview · 3-class classification output + land-cover /
hazard distributions · confirmed-incident scoring + case studies · Model
transparency panel · Limitations panel · rule-based risk engine · global-training /
India-holdout methodology and leakage checks.

---

## 4. Final feature set

| Section | Contents | Status |
|---|---|---|
| **Command Center** | Situation KPIs, Event KPIs (4-col), live India map, top priority alerts, 14-day activity strip, quick actions, agent panel | IMPLEMENTED |
| **Alerts** | DETECTIONS tab (severity-grouped feed, pagination, manual actions) + THERMAL EVENTS tab (event cards) | IMPLEMENTED |
| **Investigation** | Event header, Detection, Context, Why Flagged, Fingerprint, Evidence Stack, Evolution + Replay, Risk Trajectory, Recommended Action, manual actions | IMPLEMENTED |
| **Map / GIS** | India detection map, all layers/controls, Thermal Events centroid overlay | IMPLEMENTED |
| **Analytics** | Timeline + calendar + period analysis + playback; classification + severity analysis; baseline-vs-current | IMPLEMENTED |
| **Facilities** | Known industrial facilities with nearby detections | IMPLEMENTED |
| **Reports / GIS** | GeoJSON + CSV export (filter-aware) + preview; incident report | IMPLEMENTED |
| **Model** | Real pipeline diagram, data sources, three-way evaluation, feature importance | IMPLEMENTED |
| **Limitations** | FIRMS resolution, satellite revisit, land-cover, temporal/NRT-only, false positives, operational framing | IMPLEMENTED |
| **Fire Intelligence Agent** | Event-aware NL queries, analysis, filtering, navigation — READ-ONLY | IMPLEMENTED (deterministic) + OPTIONAL (Claude) |

---

## 5. UI information architecture

Navigation follows the operator workflow:

```
DETECT → CLUSTER → FINGERPRINT → EVIDENCE → EVOLVE → ACT
```

```
Shell (system id · live clock · "⌘ Fire Intelligence")
│
├── Command Center      overview: what / how bad / where / what needs attention
│                       + event KPIs: active events / high-risk / persistent / early warnings
├── Alerts              DETECTIONS tab + THERMAL EVENTS tab
├── Investigation       event header + fingerprint + evidence + evolution replay + trajectory
├── Map / GIS           where the thermal anomalies are + event centroid overlay
├── Analytics           timeline, calendar, classification/severity, baseline
├── Facilities          activity around known industrial infrastructure
├── Reports / GIS       GeoJSON / CSV export + incident report
├── Model               real pipeline + evaluation + feature importance
└── Limitations         honest caveats
```

The Fire Intelligence Agent is a compact command palette available from the shell
on every page — never a full-screen chatbot.

---

## 6. Data sources

| Source | Role | Status |
|---|---|---|
| NASA FIRMS (MODIS 1 km, VIIRS 375 m) NRT | Primary thermal detections, India bbox | IMPLEMENTED (NRT only, last ~5 days) |
| VIIRS Nightfire (VNF) global flare catalogue (ORNL DAAC) | Class A labelling oracle | IMPLEMENTED |
| WRI Global Power Plant Database | Facility/context layer | IMPLEMENTED |
| OpenStreetMap `landuse=industrial` (Overpass) | Facility/context layer | IMPLEMENTED |
| Curated confirmed Indian incidents (news/Wikipedia) | Independent evaluation / demo set (30 rows) | IMPLEMENTED |
| Simplified India admin GeoJSON (`data/geo/india_admin.geojson`) | Offline lat/lon → state/district resolver | IMPLEMENTED (1.2 MB, 36 states + 760 districts) |
| GIHS (Global Industrial Heat Sources) | Additional Class A | NOT SUPPORTED yet |
| MODIS MCD12Q1 / ESA CCI Land Cover raster | Precise land-cover | NOT SUPPORTED yet |
| Historical FIRMS archive (LAADS DAAC) | Temporal incident matching | NOT SUPPORTED yet |

---

## 7. Data / ML approach

- **Global training, India held out.** The classifier learns physical/thermal
  patterns from non-India data; India is a locked geographic holdout for
  evaluation and deployment only.
- **No random split.** Splitting is by spatial grid / facility to avoid
  repeated-detection leakage. Three accuracy figures are reported side by side
  (random baseline, spatial holdout, India holdout).
- **VNF is a labelling oracle, not a feature.** FIRMS rows within 5 km of a known
  VNF flare site → Class A; remaining global FIRMS → `B_candidate`.
- **Model.** RandomForestClassifier, 7 features: `bt_kelvin`, `frp_mw`,
  `persistence_count`, `dist_nearest_facility_km`, `agri_season_flag`,
  `day_night_bin`, `acq_month`. Feature importance dominated by
  `dist_nearest_facility_km` (0.29), `day_night_bin` (0.25), `bt_kelvin` (0.21).
- **Anomaly rule.** `max(class probability) < 0.55` → Industrial Fire / Abnormal
  Thermal Event.
- **Risk engine is separate and rule-based** — transparent 0–100 additive score
  → severity bands → stored in `alerts.db`.
- **Event clustering is in-memory / derived** — no new DB table; events are
  recomputed from `alerts.db` on cache miss, keyed on DB mtime signature.

### Hard constraints — do not violate

- There is **no dataset of confirmed industrial fire incidents** anywhere. Do not
  build or claim a classifier trained on confirmed industrial fire events.
- A FIRMS hotspot is **not typed by cause**. Never treat a raw hotspot as a
  labelled example.
- "Near a facility" is a **weak context feature, never a label**.
- **Never use a random train/test split** as the primary evaluation.
- **Do not tune the model against the India holdout.**
- The pitch/demo must **never claim "confirmed industrial fire detection."**
  Locked framing: *"We detect anomalous departures from known persistent-industrial
  and natural-fire patterns — not confirmed fires, because no training data for
  that exists anywhere."*

---

## 8. Fire Intelligence Agent

### Concept

A natural-language operational intelligence layer over the fire detection and risk
system — **not** an "AI chatbot for fire detection." The platform has two
interaction modes over the *same* backend:

- **Manual** — the conventional dashboard and controls.
- **Agent** — ask questions / request views in natural language.

The agent is an additional interface, never a replacement. It calls the same
`src/intelligence/` service layer the manual UI uses.

### Capabilities (READ-ONLY)

- Answer questions from actual application data: alerts, events, fingerprints,
  evidence, evolution, trajectories, facilities, regions, incidents.
- Rank / filter / aggregate detections, alerts, and events.
- Find increasing-risk events and early warnings.
- Apply filters to the shared UI state.
- Navigate to a section; focus the map; open an Investigation.
- Generate a report via the existing report function.
- Offer result cards: **Open Investigation**, **Show on Map**, **Generate Report**.

### Limitations

- **Read-only.** The agent never acknowledges, escalates, resolves, or otherwise
  changes incident state.
- Answers only from real data. If a value is unavailable it says so — no
  fabrication.
- No free-text database access; the LLM never issues SQL or arbitrary code.

### Offline-first requirement

The deterministic keyword/intent parser (`src/intelligence/agent/deterministic.py`)
is the **guaranteed baseline** and must handle every documented example prompt.
The application — including the agent — must be fully functional with **no API key**.

### Optional Claude API architecture

If `ANTHROPIC_API_KEY` is present, `src/intelligence/agent/claude.py` provides a
tool-use loop over the same read-only tool registry (model `claude-sonnet-4-6`).
Any failure degrades to deterministic cleanly.

---

## 9. Technology stack

- **Language:** Python 3.11.
- **Frontend:** Streamlit (multipage via `st.navigation`), pydeck for the map,
  Carto dark-matter basemap (no Mapbox token).
- **Data:** pandas, pyarrow (Parquet), SQLite (`data/alerts.db`).
- **ML:** scikit-learn (RandomForest, BallTree), joblib.
- **Clustering:** hashlib (stdlib), math (stdlib) — no new dependency.
- **Geo:** bundled simplified admin GeoJSON + pure-Python point-in-polygon.
- **Agent LLM (optional):** `anthropic` SDK — optional, guarded import.
- **Config:** `python-dotenv`, `.env`.
- No React, no FastAPI, no external database, no auth layer.

---

## 10. Repository structure

```
context.md  design_brief.md  architecture.md  workflow.md   ← project docs
requirements.txt  .env.example  .gitignore

data/
  raw/                         # git-ignored downloads
  processed/
    facilities.parquet         # committed (72,624 rows)
    stage6_india_scores.parquet# committed (1105 rows, live-refreshable)
  incidents/
    confirmed_incidents_india.csv
    stage7_incident_scores.parquet
    match_summary.json
  geo/
    india_admin.geojson        # committed (1.2 MB — 36 states + 760 districts)
  alerts.db                    # git-ignored, auto-seeded on first run

src/
  ingestion/    # Stages 1–2: firms, vnf, facilities, config, utils
               # + refresh.py — live FIRMS NRT refresh at dashboard startup
  labeling/     # Stage 3: match_incidents
  features/     # Stage 4: engineer
  model/        # Stages 5–6: split, assemble, train
  scoring/      # Stage 7: score_incidents
  alerting/     # risk_engine, alert_store, pipeline
  intelligence/
    clustering.py       # ThermalEvent dataclass + union-find cluster_alerts()
    fingerprint.py      # compute_fingerprint() → 6-dimension ratings
    evidence.py         # EvidenceItem + build_evidence() → supporting/limiting/neutral
    evolution.py        # build_evolution() → frames + milestones
    early_warning.py    # compute_trajectory() → state + trajectory + signals
    queries.py          # list_alerts, get_alert, get_investigation, situation_summary,
                        # list_events, get_event, get_event_for_alert,
                        # get_event_fingerprint, get_event_evidence,
                        # get_event_evolution, get_event_trajectory,
                        # find_increasing_risk_events, events_situation, ...
    actions.py          # export_geojson, export_csv, build_incident_report, ...
    geo.py              # resolve(lat,lon) → {state, district, in_india, zone}
    agent/
      tools.py          # read-only tool registry (alert + event tools, no mutations)
      deterministic.py  # regex/intent parser; interpret = parse alias
      claude.py         # optional Anthropic SDK tool-use loop
      runtime.py        # selects runtime, dispatches, returns AgentReply
      response.py       # NL formatting of tool results

dashboard/
  app.py        # shell: st.navigation + auto-seed + maybe_refresh + st.toast
  theme.py      # CSS design system, injected once per page
  state.py      # session_state defaults + typed helpers
  data.py       # @st.cache_data wrappers: S, A, ALERTS, EVENTS, EVENT,
                # EVENT_FP, EVENT_EV, EVENT_EVO, EVENT_TRAJ, EVENTS_SIT, ...
  shell.py      # topbar (LIVE/SNAPSHOT badge, IST clock) + sidebar cards
  components/   # ui.py, mapview.py, charts.py, filterbar.py
  views/
    command_center.py   # 5-col KPI + 4-col event KPI + map + priority alerts
    alerts.py           # DETECTIONS tab + THERMAL EVENTS tab
    investigation.py    # event header + fingerprint + evidence + evolution + trajectory
    map_explorer.py     # detection layers + Thermal Events centroid overlay
    analytics.py        # timeline + baseline + class analysis
    facilities.py       # BallTree join → facility activity table
    reports.py          # GeoJSON/CSV/incident export
    model.py            # static pipeline + evaluation content
    limitations.py      # static caveats
  agent/
    panel.py            # command-palette dialog + chat + result-card rendering

tests/
  test_clustering.py    (11 tests)
  test_fingerprint.py   (9 tests)
  test_evidence.py      (7 tests)
  test_evolution.py     (9 tests)
  test_early_warning.py (9 tests)
  test_events.py        (8 tests)
  test_agent_events.py  (10 tests)
  test_intelligence_geo.py
  test_intelligence_queries.py
  test_intelligence_actions.py
  test_agent_deterministic.py
  test_ingestion.py  test_features.py  test_split.py  (original)
  # Total: 161 tests, all passing

reports/  # stage6_evaluation.txt, stage6_feature_importance.csv, stage7_incident_report.txt
```

---

## 11. Important architectural decisions

1. **Single service layer.** All data/logic lives in `src/intelligence/` (built on
   the existing `src/alerting/` engines). The Streamlit layer is presentation only.
2. **Events are derived, not stored.** Thermal events are computed in-memory from
   `alerts.db` via LRU-cached `_events_cached(_sig)` keyed on DB mtime. No new
   table; auto-invalidates when data changes.
3. **Deterministic event IDs.** SHA-256 of `"|".join(sorted(alert_ids))[:8 hex]` —
   stable across recomputation from the same alert set.
4. **Agent = fixed read-only tool registry.** The LLM (or deterministic parser)
   can only invoke named functions with typed arguments. No raw state access,
   no SQL, no mutation.
5. **Deterministic parser is primary, Claude is optional.** Offline-first.
6. **Investigation is assembled, not stored.** It is a view over existing alert
   fields + event intelligence; no new stored entity.
7. **Offline geo.** State/district resolution uses bundled GeoJSON +
   pure-Python ray-casting — no new dependency, no network.
8. **Preserve, relocate, don't rewrite.** Existing renderers and logic untouched;
   new intelligence panels layered on top.
9. **No dashboard module imports `src.alerting` directly** — only `src.intelligence`.

---

## 12. Known limitations & risks

- **FIRMS NRT only covers ~5 days.** No historical archive.
- **Land-cover is a coordinate-zone heuristic**, not a raster.
- **Class A training set is thin** (~1,901 FIRMS examples via VNF oracle); Class A
  F1 ≈ 0.18 on spatial holdout.
- **Trained model `.joblib` is not in the repo** — live NRT scoring requires it
  locally with `FIRMS_MAP_KEY` set. Otherwise, the dashboard runs off committed
  scored parquets.
- **Alert volume is ~1105 India detections** (Sep 2026 NRT snapshot).
- **Events are in-memory** — recomputation on cold cache takes O(n²) pair scan;
  fine at ≤5k rows; ponytail comment marks the ceiling.
- **Optional Claude path** adds cost/latency/network dependency; degrades
  to deterministic cleanly.

---

## 13. Hackathon constraints & demo priorities

- **Deadline:** internal hackathon 5 September.
- **Must run offline** on a single machine with no API keys.
- **Judge-facing clarity in ~10 seconds** on the Command Center.

### Demo priorities (in order)

1. Command Center reads instantly: active alerts, criticals, event KPIs, where, what to do.
2. Alerts → THERMAL EVENTS tab → "Investigate event #XXXXXXXX" → Investigation flow
   showing fingerprint, evidence, evolution replay, risk trajectory.
3. Map: detection layer + event centroid overlay.
4. Fire Intelligence Agent (offline): *"Which events are increasing in risk?"* →
   event list with risk trajectories + Open Investigation cards.
5. Analytics baseline comparison and Facilities view as differentiators.
6. Model + Limitations panels for technical credibility.

---

## 14. Future extensions (not in scope now)

- Agent state-changing actions (Acknowledge / Escalate / Resolve) behind a
  confirmation gate.
- Claude API runtime hardening and richer multi-step reasoning over events.
- React + FastAPI frontend on top of the unchanged service layer.
- Historical FIRMS archive ingestion → real temporal incident matching.
- GIHS and land-cover raster integration → better Class A / Class B precision.
- Analytics event metrics section (`analytics.py` event panel, planned but deferred).
- Notifications, multi-user, authentication.
- Persistent event storage (DB table) if in-memory clustering reaches scale limits.

---

## 15. Definition of "done" (this round) ✓

- [x] Every existing feature is reachable in the new IA; nothing regressed.
- [x] No module under `dashboard/` imports `src.alerting` directly — only `src.intelligence`.
- [x] `src/intelligence/` has unit tests; 161 tests pass, zero failures.
- [x] Investigation shows only real evidence; no fabricated confidence or metrics.
- [x] Manual Acknowledge / Escalate / Resolve work exactly as before.
- [x] Fire Intelligence Agent answers every documented example prompt with no API key.
- [x] Event clustering, fingerprinting, evidence, evolution, and trajectory all implemented.
- [x] The locked "not confirmed fire detection" framing appears wherever classification is presented.
- [x] `context.md` Status Tracker updated.

---

## Status Tracker

### Pipeline (unchanged this round)

- [x] Stage 1 — Data ingestion (FIRMS NRT India + 6 global regions; VNF; GPPD; OSM).
- [x] Stage 2 — Facility/context layer → `data/processed/facilities.parquet` (72,624 rows).
- [~] Stage 3 — Class A done (VNF); Class B still `B_candidate`; 30 confirmed incidents curated.
- [x] Stage 4 — Feature engineering.
- [x] Stage 5 — Assemble & spatial split.
- [x] Stage 6 — RF trained global / India held out; scores committed (1105 rows).
- [x] Stage 7 — 30 incidents scored (21/30 anomaly-flagged).
- [x] Stage 8 — Multipage Streamlit dashboard.

### Session 10 — Thermal Event Intelligence Platform

Implemented across 11 commits (Tasks 1–11 of `docs/superpowers/plans/2026-09-03-thermal-event-intelligence.md`):

- [x] **Task 1** (`820ceb7`) — `src/intelligence/clustering.py`: `ThermalEvent` (29 fields), `cluster_alerts()`, union-find, SHA-256 event IDs. 11 tests.
- [x] **Task 2** (`9fa93b4`) — `src/intelligence/fingerprint.py`: `compute_fingerprint()`, 6 dimensions, 6 behaviour categories. 9 tests.
- [x] **Task 3** (`4055166`) — `src/intelligence/evidence.py`: `EvidenceItem`, `build_evidence()`, SUPPORTING/LIMITING/NEUTRAL routing. 7 tests.
- [x] **Task 4** (`5cf55dd`) — `src/intelligence/evolution.py`: `build_evolution()`, ordered frames, 4 milestone types. 9 tests.
- [x] **Task 5** (`e2fd067`) — `src/intelligence/early_warning.py`: `compute_trajectory(frames)`, 5 risk states. 9 tests.
- [x] **Task 6** (`bf4c5e5`) — `queries.py` extended: `_events_cached` (LRU, DB-mtime key), 10 new event query functions, `events_situation()`. 8 integration tests.
- [x] **Task 7** (`83cde8b`) — `dashboard/data.py`: 8 `@st.cache_data(ttl=30)` event wrappers.
- [x] **Task 8** (`ce554fe`) — Agent tools (8 new) + deterministic parser (event ID regex + 8 event intents + `interpret = parse` alias). 10 tests.
- [x] **Task 9** (`b1730bd`) — `investigation.py` upgraded: event header, fingerprint panel, evidence stack, evolution replay slider, risk trajectory.
- [x] **Task 10** (`053606b`) — `command_center.py`: 4-col event KPI row. `alerts.py`: DETECTIONS / THERMAL EVENTS tabs.
- [x] **Task 11** (`9142dfa`) — `map_explorer.py`: "Thermal Events" checkbox + amber ScatterplotLayer centroid overlay.

**Test count:** 161 passing, 0 failing.

**Last updated:** 2026-09-03 (Session 10 — Thermal Event Intelligence Platform complete)
