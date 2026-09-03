# SIH26162 — Project Context (Source of Truth)

> Read this file in full before doing any work. It describes what the project is,
> what is already built, what is planned, and what must not be done or claimed.
> Update the **Status Tracker** at the bottom after every work session.
>
> Companion documents at repo root:
> - `design_brief.md` — product identity + UI/UX blueprint per screen
> - `architecture.md` — technical architecture, modules, interfaces, agent design
> - `workflow.md` — end-to-end operational workflow and user journeys
> - `.claude/plans/starry-rolling-pnueli.md` — the approved implementation plan

---

## 1. Project identity

| | |
|---|---|
| **Project name** | India Fire Intelligence Platform (Team ZeroOne) |
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

### Why it matters

Industrial fires near refineries, chemical plants, power stations and mining
areas threaten life, infrastructure and the environment. Faster, better-prioritised
detection with clear supporting evidence lets disaster-management and monitoring
agencies investigate the right sites first. Persistent-thermal-source monitoring
also supports environmental compliance and industrial-activity intelligence.

### Core objective

Turn the raw NASA FIRMS thermal feed over India into a prioritised, explained,
GIS-based operational picture that distinguishes:

1. **Industrial Fire / Abnormal Thermal Event** — anomalous: matches neither the
   persistent-industrial nor the natural-fire learned pattern (candidate for human
   review; *not* a confirmed fire).
2. **Persistent Industrial Thermal Source** — continuous industrial heat: gas
   flares, kilns, smelters, thermal power plants.
3. **Forest / Agricultural Fire** — natural or crop-residue burning.

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
- Presents everything on a dark operations dashboard: situation overview, alert
  feed, India detection map, historical timeline/calendar, classification and
  model transparency panels, and GIS export (GeoJSON / CSV).
- Scores a curated set of 30 real past Indian industrial incidents as an
  independent evaluation / demo set.

### Target users

- Disaster-management / emergency-monitoring analysts.
- Industrial-safety and environmental-compliance monitoring teams.
- Technical evaluators (SIH judges, NTRO/ISRO/NRSA-adjacent audiences).

### Core use cases

1. **Situational awareness** — "What thermal activity is happening over India
   right now, and how serious is it?"
2. **Triage** — "Which alerts need attention first?"
3. **Investigation** — "Why was this specific detection flagged, and what should
   we do about it?"
4. **Historical analysis** — "How does today compare to the recent baseline?"
5. **Facility monitoring** — "What is happening around known industrial sites?"
6. **Reporting / hand-off** — "Export the current picture for GIS tools or a
   briefing."
7. **Natural-language access** — "Ask the platform instead of manually driving
   filters." (Fire Intelligence Agent, read-only.)

---

## 2. Scope

### Approved scope (current round — targeting 5 Sept)

- **Information-architecture reorganisation** of the existing Streamlit app into
  clear sections: Command Center, Alerts, Investigation, Map, Analytics,
  Facilities, Reports / GIS, Model, Limitations. Every existing feature keeps a
  deliberate home.
- **`src/intelligence/` service + tool layer** — a framework-agnostic Python layer
  that both the manual UI and the agent call. No business logic duplicated in the
  UI.
- **Offline lat/lon → Indian state / region resolver** (`src/intelligence/geo.py`)
  using a bundled simplified state-boundary GeoJSON and pure-Python
  point-in-polygon.
- **Investigation view** — assembled from existing alert fields only
  (detection / context / why-flagged / classification / risk breakdown /
  recommended action).
- **Facilities view** — new view over the existing `facilities.parquet` joined to
  detections.
- **Analytics consolidation** — existing Timeline + Classification content plus a
  baseline-vs-current FRP comparison (shown only when data supports it).
- **Reports / GIS page** — existing GeoJSON/CSV export plus a Markdown/CSV incident
  report.
- **Fire Intelligence Agent (READ-ONLY)** — natural-language queries, data
  analysis, filtering, navigation, map focusing, opening investigations, and
  report generation. Deterministic offline parser is the guaranteed baseline;
  Claude API is an optional enhancement.
- Targeted additive change to `src/alerting/risk_engine.py`: expose the risk-score
  factor breakdown (needed by the Investigation view). No behavioural change.

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

Legend: **[IMPLEMENTED]** works today · **[PLANNED]** in the approved plan, not
yet built · **[OPTIONAL/FUTURE]** may be added later · **[NOT SUPPORTED]** will
not be built and must not be claimed.

### Data & ML pipeline

- **[IMPLEMENTED]** Stage 1 — FIRMS NRT ingestion for India + 6 global training
  regions; every row tagged `split` at ingest. VNF gas-flare catalogue (83,641
  rows). WRI Global Power Plant DB (34,936). OSM industrial polygons (37,688
  India).
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
  India detections (Sep 2026; auto-refreshes via `src/ingestion/refresh.py` when
  `FIRMS_MAP_KEY` is set)). Trained `.joblib` is git-ignored; when present
  locally and `FIRMS_MAP_KEY` is set, the dashboard loads it via
  `src/ingestion/refresh.py` to re-score live FIRMS data.
- **[IMPLEMENTED]** Stage 7 — 30 incidents scored →
  `data/incidents/stage7_incident_scores.parquet` (21/30 anomaly-flagged).
- **[IMPLEMENTED]** Stage 8 — single-file Streamlit dashboard `dashboard/app.py`.

### Alerting / intelligence

- **[IMPLEMENTED]** `src/alerting/risk_engine.py` — rule-based scoring →
  `output_class`, `risk_score`, `severity`, `land_cover_context`,
  `hazard_facility_type`, `narrative`, `nearest_city`, `dist_nearest_city_km`,
  `near_population`.
- **[IMPLEMENTED]** `src/alerting/alert_store.py` — SQLite store (`data/alerts.db`),
  lifecycle states, `get_alerts()` / `update_status()` / `counts()` / `clear_all()`.
- **[IMPLEMENTED]** `src/alerting/pipeline.py` — `run(fresh=…)` seeds the store
  from `stage6_india_scores.parquet`.
- **[IMPLEMENTED]** `dashboard/timeline.py` — daily severity aggregation and
  range queries over `alerts.db`.

### Dashboard (current, single page)

- **[IMPLEMENTED]** System/situation header (active count, severity breakdown,
  class counts).
- **[IMPLEMENTED]** Control bar — severity / status / date (Today, 24h, 7d,
  custom) / map-layer / pipeline re-run.
- **[IMPLEMENTED]** Alert feed — severity-grouped, paginated (5/page),
  expandable, with Acknowledge / Escalate / Resolve.
- **[IMPLEMENTED]** India detection map (pydeck + Carto dark) — colour by class or
  severity, confirmed-incident overlay, tooltips.
- **[IMPLEMENTED]** Tabs — Timeline (activity strip + calendar + period analysis +
  playback), GIS Export (GeoJSON / CSV + preview), Classification (3 class panels +
  land-cover / hazard tables), Incidents (30-incident table + 3 case studies),
  Model (data sources, three-way evaluation, feature importance), Limitations
  (5 caveats).

### New IA + Agent

- **[IMPLEMENTED]** `src/intelligence/` (`queries.py`, `actions.py`, `geo.py`,
  `agent/`).
- **[IMPLEMENTED]** `dashboard/` restructure: `theme.py`, `state.py`, `components/`,
  `pages/`, `agent/panel.py`; `app.py` → shell + `st.navigation`.
- **[IMPLEMENTED]** Command Center, Investigation, Map explorer, Analytics, Facilities,
  Reports pages.
- **[IMPLEMENTED]** Fire Intelligence Agent — deterministic offline runtime.
- **[OPTIONAL/FUTURE]** Fire Intelligence Agent — Claude API runtime (activated
  only when `ANTHROPIC_API_KEY` is set).
- **[OPTIONAL/FUTURE]** Agent state-changing actions with confirmation gate.
- **[NOT SUPPORTED]** Agent directly modifying `alerts.db` or any state; LLM
  issuing raw SQL / arbitrary code; any "confirmed industrial fire" claim.

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

## 4. Final feature set (after this round)

| Section | Contents | Status |
|---|---|---|
| **Command Center** | Situation overview, KPI row, class + severity summaries, live India map, top-5 priority alerts, 14-day activity strip, quick actions, "View All Alerts" | PLANNED (reuses implemented pieces) |
| **Alerts** | Full feed: filters, severity grouping, pagination, detail, manual Acknowledge/Escalate/Resolve, per-row "View Investigation" | IMPLEMENTED feed + PLANNED relocation |
| **Investigation** | Incident header, Detection, Context, Why Flagged, Classification, Risk Assessment (factor breakdown), Recommended Action, manual actions | PLANNED |
| **Map / GIS** | India detection map, all current layers/controls/interactions, click-to-investigate | IMPLEMENTED map + PLANNED page |
| **Analytics** | Timeline + calendar + period analysis + playback; classification + severity analysis; baseline-vs-current FRP comparison | IMPLEMENTED + PLANNED baseline |
| **Facilities** | Known industrial facilities with nearby detections: name, type, state, detection count, repeat count, max risk, historical activity, baseline where available | PLANNED (existing data) |
| **Reports / GIS** | GeoJSON + CSV export (filter-aware) + preview; Markdown/CSV incident report | IMPLEMENTED export + PLANNED report |
| **Model** | Real pipeline diagram, data sources, three-way evaluation, feature importance | IMPLEMENTED content + PLANNED page |
| **Limitations** | FIRMS resolution, satellite revisit, land-cover, temporal/NRT-only, false positives, operational framing | IMPLEMENTED content + PLANNED page |
| **Fire Intelligence Agent** | Command-palette panel: NL queries, analysis, filtering, navigation, map focus, open investigation, generate report — READ-ONLY | PLANNED (deterministic) + OPTIONAL (Claude) |

---

## 5. Final UI information architecture

Navigation follows the operator workflow:

```
DETECT → CLASSIFY → VALIDATE → PRIORITIZE → EXPLAIN → ACT
```

```
Shell (system id · live clock · "⌘ Fire Intelligence")
│
├── Command Center      overview: what / how bad / where / what needs attention
├── Alerts              full prioritised feed + filters + manual actions
├── Investigation       why one alert matters + recommended action
├── Map / GIS           where the thermal anomalies are
├── Analytics           timeline, calendar, classification/severity, baseline
├── Facilities          activity around known industrial infrastructure
├── Reports / GIS        GeoJSON / CSV export + incident report
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
| Simplified India state boundaries GeoJSON | Offline lat/lon → state resolver | PLANNED (bundled in `data/geo/`) |
| GIHS (Global Industrial Heat Sources) | Additional Class A | NOT SUPPORTED yet (download URL unconfirmed) |
| MODIS MCD12Q1 / ESA CCI Land Cover raster | Precise land-cover | NOT SUPPORTED yet (coordinate-zone heuristic used instead) |
| Historical FIRMS archive (LAADS DAAC) | Temporal incident matching | NOT SUPPORTED yet |

---

## 7. Data / ML approach

- **Global training, India held out.** The classifier learns physical/thermal
  patterns from non-India data; India is a locked geographic holdout for
  evaluation and deployment only. India data is still used for the facility/context
  layer, the confirmed-incident set, and the deployed dashboard.
- **No random split.** Splitting is by spatial grid / facility to avoid
  repeated-detection leakage. Three accuracy figures are reported side by side
  (random baseline, spatial holdout, India holdout).
- **VNF is a labelling oracle, not a feature.** FIRMS rows within 5 km of a known
  VNF flare site → Class A; remaining global FIRMS → `B_candidate`. All training
  is in FIRMS feature space.
- **Model.** RandomForestClassifier, 7 features: `bt_kelvin`, `frp_mw`,
  `persistence_count`, `dist_nearest_facility_km`, `agri_season_flag`,
  `day_night_bin`, `acq_month`. Feature importance is dominated by
  `dist_nearest_facility_km` (0.29), `day_night_bin` (0.25), `bt_kelvin` (0.21).
- **Anomaly rule.** `max(class probability) < 0.55` → Industrial Fire / Abnormal
  Thermal Event. This is the actual product demo: real industrial incidents fall
  outside both learned patterns.
- **Risk engine is separate and rule-based** — transparent 0–100 additive score
  (anomaly flag, FRP bands, persistence, facility proximity, classifier class,
  FIRMS confidence, night flag, population proximity) → severity bands.

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

### Capabilities (this round — READ-ONLY)

- Answer questions from actual application data ("critical industrial fire alerts
  today", "persistent sources in Odisha last 7 days", "highest-risk incidents",
  "compare Odisha and Jharkhand", "why was this classified as industrial fire",
  "summarise eastern India").
- Rank / filter / aggregate detections and alerts.
- Apply filters to the shared UI state.
- Navigate to a section.
- Focus the existing map (no separate map).
- Open an Investigation.
- Generate a report via the existing report function.
- Offer result cards: **Open Investigation**, **Show on Map**, **Generate Report**.

### Limitations

- **Read-only.** The agent never acknowledges, escalates, resolves, or otherwise
  changes incident state. Such a request is explained and redirected to the manual
  controls.
- Answers only from real data. If a value is unavailable it says so — no
  fabrication.
- No free-text database access; the LLM never issues SQL or arbitrary code. It
  can only call a fixed registry of read-only tools that map 1:1 to
  `src/intelligence/` functions.

### Offline-first requirement

The deterministic keyword/intent parser (`src/intelligence/agent/deterministic.py`)
is the **guaranteed baseline** and must handle every documented example prompt.
The application — including the agent — must be fully functional with **no API
key**.

### Optional Claude API architecture

If `ANTHROPIC_API_KEY` is present, `src/intelligence/agent/claude.py` provides a
tool-use loop over the **same** read-only tool registry (model `claude-sonnet-4-6`).
It is selected at runtime by `runtime.py`; its absence is not an error. `anthropic`
is a guarded/optional import.

---

## 9. Technology stack

- **Language:** Python 3.
- **Frontend:** Streamlit (multipage via `st.navigation`), pydeck for the map,
  Carto dark-matter basemap (no Mapbox token).
- **Data:** pandas, pyarrow (Parquet), SQLite (`data/alerts.db`).
- **ML:** scikit-learn (RandomForest, BallTree), joblib.
- **Geo:** bundled simplified GeoJSON + pure-Python point-in-polygon (no new
  geospatial dependency).
- **Agent LLM (optional):** `anthropic` SDK — optional, guarded import.
- **Config:** `python-dotenv`, `.env` (see `.env.example`).
- No React, no FastAPI, no external database, no auth layer.

---

## 10. Repository structure

```
context.md  design_brief.md  architecture.md  workflow.md   ← project docs (this set)
requirements.txt  .env.example  .gitignore

data/
  raw/                         # git-ignored downloads
  processed/
    facilities.parquet         # committed
    stage6_india_scores.parquet# committed (1105 rows, live-refreshable)
  incidents/
    confirmed_incidents_india.csv
    stage7_incident_scores.parquet
    match_summary.json
  geo/                         # PLANNED — bundled india_states.geojson
  alerts.db                    # git-ignored, auto-seeded on first run

src/
  ingestion/    # Stages 1–2: firms, vnf, facilities, gihs, config, utils, visualise
               # + refresh.py — live FIRMS NRT refresh at dashboard startup
  labeling/     # Stage 3: match_incidents
  features/     # Stage 4: engineer
  model/        # Stages 5–6: split, assemble, train
  scoring/      # Stage 7: score_incidents
  alerting/     # risk_engine, alert_store, pipeline
  intelligence/ # PLANNED — queries, actions, geo, agent/{tools,deterministic,claude,runtime,response}

dashboard/
  app.py        # current single page → PLANNED shell + st.navigation
  timeline.py
  theme.py  state.py  components/  pages/  agent/panel.py   # PLANNED

tests/          # test_ingestion, test_features, test_split (+ PLANNED intelligence/agent tests)
reports/        # stage6_evaluation.txt, stage6_feature_importance.csv, stage7_incident_report.txt
```

---

## 11. Important architectural decisions

1. **Single service layer.** All data/logic lives in `src/intelligence/` (built on
   the existing `src/alerting/` engines). The Streamlit layer is presentation
   only. This makes a future React frontend a frontend-only project.
2. **Stay in Streamlit for now.** Lower risk for the hackathon timeline; the
   current aesthetic is kept.
3. **Agent = fixed read-only tool registry.** The LLM (or the deterministic
   parser) can only invoke named functions with typed arguments. No raw state
   access.
4. **Deterministic parser is primary, Claude is optional.** Offline-first.
5. **Investigation is assembled, not stored.** It is a view over existing alert
   fields; the only backend change is exposing the risk-score factor breakdown.
6. **Offline geo.** State/region resolution uses a bundled GeoJSON + pure-Python
   point-in-polygon — no new dependency, no network.
7. **Preserve, relocate, don't rewrite.** Existing renderers and logic move into
   modules; behaviour is unchanged.

---

## 12. Known limitations & risks

- **FIRMS NRT only covers ~5 days.** No historical archive → confirmed-incident
  temporal matching is 0/30; "historical" timeline depth is limited to what is in
  `alerts.db`.
- **Land-cover is a coordinate-zone heuristic**, not a raster.
- **Class A training set is thin** (~1,901 FIRMS examples via VNF oracle); Class A
  F1 ≈ 0.18 on spatial holdout.
- **Trained model `.joblib` is not in the repo** — re-scoring new FIRMS data
  requires the model to be present locally. When `FIRMS_MAP_KEY` and
  `stage6_model.joblib` are both present, `src/ingestion/refresh.py` loads the
  model at dashboard startup to score live FIRMS data. Otherwise the dashboard
  runs off committed scored parquets + the rule-based risk engine.
- **Alert volume is ~705 India detections**, not hundreds of thousands.
- **State resolver accuracy** depends on the simplified GeoJSON; border cells may
  be approximate.
- **Streamlit reruns** — agent-applied UI state must go through the same
  `session_state` path as manual filters to stay consistent.
- **Optional Claude path** adds cost/latency/network dependency; must degrade to
  deterministic cleanly.

---

## 13. Hackathon constraints & demo priorities

- **Deadline:** internal hackathon 5 September.
- **Must run offline** on a single machine with no API keys.
- **Judge-facing clarity in ~10 seconds** on the Command Center.

### Demo priorities (in order)

1. Command Center reads instantly: active alerts, criticals, where, what to do.
2. Alerts → Investigation flow: pick a critical alert, see *why* it was flagged
   with real evidence and a recommended action.
3. Map: classification-coloured detections over India, click a detection → its
   investigation.
4. Fire Intelligence Agent (offline): the §17 demo prompt — *"Find the three
   highest-risk persistent thermal sources near industrial facilities in eastern
   India over the last 7 days and explain why"* → three result cards with real
   evidence + Open Investigation / Show on Map / Generate Report.
5. Analytics baseline comparison and Facilities view as differentiators.
6. Model + Limitations panels for technical credibility.

---

## 14. Future extensions (not in scope now)

- Agent state-changing actions (Acknowledge / Escalate / Resolve) behind an
  explicit confirmation gate.
- Claude API runtime hardening and richer multi-step reasoning.
- React + FastAPI frontend on top of the unchanged service layer.
- Historical FIRMS archive ingestion → real temporal incident matching and deeper
  timeline.
- GIHS and land-cover raster integration → better Class A / Class B precision.
- Notifications, multi-user, authentication.

---

## 15. Definition of "done" (this round)

- Every existing feature is reachable in the new IA; nothing regressed.
- No module under `dashboard/` imports `src.alerting` directly — only
  `src.intelligence`.
- `src/intelligence/` has unit tests; existing tests still pass.
- Investigation shows only real evidence; no fabricated confidence or metrics.
- Manual Acknowledge / Escalate / Resolve work exactly as before.
- Fire Intelligence Agent answers every documented example prompt **with no API
  key**, and its result cards drive the shared UI state.
- With `ANTHROPIC_API_KEY` set, the Claude runtime is used and resolves the same
  prompts through the same read-only tool layer.
- The locked "not confirmed fire detection" framing appears wherever
  classification is presented.
- `context.md` Status Tracker updated; `git status` shows only intended files.

---

## Status Tracker

Update after every work session — what's done, what's blocked, what's next.

### Pipeline (unchanged this round)

- [x] Stage 1 — Data ingestion (FIRMS NRT India + 6 global regions; VNF; GPPD; OSM). GIHS download URL still unconfirmed.
- [x] Stage 2 — Facility/context layer → `data/processed/facilities.parquet` (72,624 rows).
- [~] Stage 3 — Class A done (VNF); Class B still `B_candidate` (land-cover pending); 30 confirmed incidents curated; temporal FIRMS matching 0/30 (needs historical archive).
- [x] Stage 4 — Feature engineering (`src/features/engineer.py`).
- [x] Stage 5 — Assemble & spatial split (`src/model/assemble.py`, `src/model/split.py`).
- [x] Stage 6 — RF trained global / India held out; scores committed (`stage6_india_scores.parquet`); `.joblib` git-ignored.
- [x] Stage 7 — 30 incidents scored (21/30 anomaly-flagged) → `stage7_incident_scores.parquet`.
- [x] Stage 8 — Single-file Streamlit dashboard (`dashboard/app.py`).

### IA reorg + Fire Intelligence Agent (Session 5 — IMPLEMENTED)

- [x] Part A — `src/intelligence/` service + tool layer (`queries.py`, `actions.py`, `geo.py`) + tests.
- [x] Part A — `src/intelligence/agent/` (`tools`, `deterministic`, `claude`, `runtime`, `response`) — read-only registry (13 tools, none state-changing).
- [x] Offline geo resolver — `geo.py` bbox+centroid method (no dependency); `data/geo/india_outline.json` bundled for map context.
- [x] Part B — `dashboard/` restructure: `theme.py`, `state.py`, `data.py`, `shell.py`, `components/` (ui, mapview, charts, filterbar), `views/` (9 pages), `agent/panel.py`; `app.py` → shell + `st.navigation`.
- [x] Command Center (KPIs, live map, priority alerts, donuts, activity timeline, recent detections, quick actions, docked agent).
- [x] Alerts (filter bar, severity grouping, pagination, expander, manual Acknowledge/Escalate/Resolve, View Investigation).
- [x] Investigation (assembled: header, detection, context, why-flagged, classification, risk-factor breakdown, recommended action, manual actions, focused map).
- [x] Map Explorer · Analytics (timeline + baseline + class analysis) · Facilities (BallTree join, real names) · Reports/GIS (GeoJSON/CSV/incident report) · Model · Limitations.
- [x] `src/alerting/risk_engine.py` — additive `factors` on `RiskResult` + `risk_factors` column + `explain_score()`. `alert_store.py` — `risk_factors` TEXT column (JSON).
- [x] Agent — deterministic runtime (offline, no key); handles all documented §13/§17 prompts (35 new tests).
- [x] Agent — optional Claude runtime (`src/intelligence/agent/claude.py`), guarded; silent fallback to deterministic.
- [x] Robot: supplied `bb-8.glb` (76 MB) → textures resized + quantized → `dashboard/static/bb-8.glb` (1.9 MB); rendered via self-hosted `model-viewer.min.js` (offline).
- [x] `requirements.txt` — `plotly` added; `anthropic>=0.40` added as an optional/guarded dependency.
- [x] Tests: 49 existing + 35 new (`test_intelligence_geo/queries/actions.py`, `test_agent_deterministic.py`) = **84 passing**.

**Run:** `python -m venv .venv && .venv/Scripts/pip install -r requirements.txt`
then `.venv/Scripts/python -m streamlit run dashboard/app.py`. `data/alerts.db`
auto-seeds on first launch. No API key needed.

**Deferred (explicitly out of scope now):** agent-initiated Acknowledge /
Escalate / Resolve; historical FIRMS archive; GIHS; land-cover raster; React
frontend (service layer is already frontend-agnostic for it).

**Known follow-ups:** `st.dialog` agent closes on submit (Command Center's docked
agent is unaffected); Streamlit auto-collapses the nav sidebar below ~1000 px
width.

### Session 6 — geographic-consistency fix

Root cause traced from source → intelligence → map: the FIRMS ingestion used a
**rectangular** India bounding box (`lat 6–37, lon 68–97.5`) which also captures
Sri Lanka, Pakistan, Tibet, Bangladesh, Myanmar. Of the 697 seeded detections,
**only ~300 are actually inside an Indian state** (270 were Sri Lanka, ~91
Pakistan, etc.). Separately, the display location was `nearest_city` from a
hard-coded 30-city list, which produced impossible labels like
"Chennai, Andhra Pradesh".

- [x] `src/intelligence/geo.py` **rewritten** — authoritative offline
  point-in-polygon resolver over a bundled simplified admin GeoJSON
  (`data/geo/india_admin.geojson`, 1.2 MB: 36 dissolved state polygons + 760
  district polygons; pure-Python ray-casting; per-feature bbox pre-filter; 0.03°
  boundary tolerance for polygon-simplification + FIRMS-pixel error).
  `resolve(lat,lon) -> {state, district, in_india, zone}`. Bengaluru→Karnataka,
  Paradip→Odisha, Dhanbad→Jharkhand, etc. all correct; foreign points →
  `in_india=False` + a coarse `zone` ("Sri Lanka", "Bay of Bengal", …).
- [x] `queries.py` — every alert annotated with `state / district / in_india /
  zone / place`; **the product scope is now India-only** (`_alerts()` filters
  `in_india`); `place` = `"District, State"` (never a city→state inference);
  `outside_india_alerts()` + `geo_audit()` added; daily/analytics recomputed
  from the India set.
- [x] Coordinates are **never transformed, swapped, or clipped** — `geo` only
  *classifies* points; outside-India detections keep their true lat/lon and are
  shown on the map as an explicit, dim, opt-in "Regional context (outside India)"
  layer (Map Explorer), plus counted in the **Data validation** expander
  (plotted / in-India / outside / outside-bbox / lat-lon ranges / per-region
  breakdown / samples).
- [x] Map: CARTO dark basemap restored (`map_provider="carto"`, `map_style="dark"`,
  no Mapbox token) so surrounding countries stay visible; the bundled India
  outline is now a thin border, not a fill.
- [x] Incidents keep their **curated** `state` (human-verified); 28/30 match
  point-in-polygon, 2 are a near-border coordinate and an offshore platform —
  left as curated.
- [x] Tests: +14 (`test_intelligence_geo.py` rewritten with the required
  known-location checks + no-lat/lon-swap + audit; `test_intelligence_queries.py`
  India-scope + label-consistency + audit). **98 passing.**
- [x] Build-time only: `shapely` used to dissolve/simplify the district GeoJSON
  (script in scratch, not a runtime dependency).

**Numbers changed:** active alerts 697 → ~300 (the ~397 non-India FIRMS points
are excluded from the product but retained and viewable).

### Session 7 — Fire Intelligence Agent UI revision (presentation only)

Interaction/presentation refinement of the agent panel. **No change** to the
agent architecture, the intelligence layer, the read-only tool set, the GLB
asset, or any other view.

- [x] **Idle robot is completely static.** Removed `auto-rotate` /
  `rotation-per-second` / `camera-controls` from `<model-viewer>`; the GLB is
  `pause()`d on load so any embedded clip is frozen. Hover = a subtle
  scale + brightness response only.
- [x] **Explicit visual states** (`dashboard/agent/panel.py`):
  `IDLE` (collapsed, static) → `OPEN` (expanded, static) → `THINKING/ANSWERING`
  (a restrained CSS "scan" sweep + inset glow + `ANALYSING` tag drawn *around*
  the static robot, plus an in-conversation spinner) → back to `OPEN/IDLE`.
  Driven by `st.session_state["agent_pending"]`: the busy overlay is a plain
  CSS element Python renders only while a query is in flight, and the rerun
  after the reply lands clears it — motion can never outlive the response.
  `_THINK_FLOOR_S = 0.85` keeps the state legible when the offline parser
  answers instantly.
- [x] **Click-to-expand, in place.** Docked panel (`scope="dock"`) collapses to
  a compact card — robot + `ONLINE` + one line ("Ask about alerts, risks,
  regions or facilities.") — and expands to robot-on-top + `Conversation`
  below, in the same card, via an `Open console ▸ / Collapse ▾` control. The
  sidebar dialog (`scope="dialog"`, `collapsible=False`) is always expanded.
- [x] **Styling aligned to the dashboard.** Dropped the bright-purple chat
  bubbles: user turns are a subtle `panel2` surface with a thin accent-blue
  right border, bot turns a plain bordered panel; 6px radii; `IBM Plex Mono`
  section labels; result cards get a thin accent-blue left rule. `AGENT` purple
  is no longer used in the agent surface.
- [x] Command Center wraps the panel in `st.container(border=True)` instead of
  the old (non-wrapping) `<div class="agent-wrap">` markup.
- [x] Tests unchanged — **98 passing** (agent logic untouched).

**Last updated:** 2026-09-01 (Session 7 — Fire Intelligence Agent UI revision).

### Session 8 — Audit fixes

- [x] Fixed Claude model name: `claude-sonnet-5` → `claude-sonnet-4-6` (`agent/claude.py`)
- [x] Fixed agent panel bold stripping: placeholder substitution preserves `<strong>` through `html.escape()` (`agent/panel.py`)
- [x] Fixed agent status indicator: dynamic CLAUDE (blue `#3d7dc8`) / LOCAL (amber) replacing static "ONLINE" (`agent/panel.py`)
- [x] Fixed topbar badge: green "LIVE" → amber "NRT SNAPSHOT" (honest data-freshness label) (`shell.py`)
- [x] Fixed investigation classification labels: readable `P(A): 63%` format replacing raw floats; anomaly shown as "YES — pattern anomaly ⚠" (`investigation.py`)
- [x] Improved alert cards: truncated `alert_id` shown as monospace label (`ui.py`, `response.py`)
- [x] Improved map tooltip: `alert_id` added as first line (`mapview.py`)
- [x] Improved investigation agent response: structured Observed / Model prediction / Flagged because / Recommended / Note format (`response.py`)
- [x] Tests: 97/98 passing (1 pre-existing failure in `risk_factors` SQLite round-trip, not introduced here)

**Last updated:** 2026-09-03 (Session 8 — audit fixes)

### Session 9 — Live FIRMS NRT data wiring

- [x] `src/ingestion/refresh.py` (NEW) — `maybe_refresh(max_age_hours=2.0)`: fetches live VIIRS+MODIS NRT for India bbox, lightweight feature engineering (India-only, no 335K global pipeline), `stage6_model.joblib` inference, rewrites `stage6_india_scores.parquet`, reseeds `alerts.db`. Staleness measured by `MAX(acq_date)` in alerts.db (not file mtime — git pull touches mtime). Falls back silently on any error.
- [x] `dashboard/data.py` — `maybe_refresh()` wrapper; clears Streamlit cache on successful refresh
- [x] `dashboard/app.py` — calls `maybe_refresh()` at startup; `st.toast` on refresh success or error
- [x] `dashboard/shell.py` — topbar badge: green "LIVE NRT" when FIRMS_MAP_KEY set + data < 2h old; amber "NRT SNAPSHOT" otherwise. New `sidebar_refresh_card()` with "↻ Refresh Data" button (only shown when FIRMS_MAP_KEY is set); age label shows "just now / Xh ago / X days ago"
- [x] `stage6_india_scores.parquet` updated: static Aug 22–27 snapshot (705 rows) → live Sep 3 2026 (1105 rows: 44 CRITICAL, 302 HIGH, 419 MEDIUM, 340 LOW)

**Last updated:** 2026-09-03 (Session 9 — live FIRMS NRT data wiring)
