# SIH26162 — Project Context (Source of Truth)

> Read this file in full before doing any work. It describes what the project is,
> what is built, what is deliberately not built, and what must never be claimed.
> Update the **Status Tracker** at the bottom after every work session.
>
> Companion documents at the repository root:
> - `design_brief.md` — product identity + UI/UX blueprint, per screen
> - `architecture.md` — technical architecture, modules, interfaces, data model
> - `workflow.md` — end-to-end operational workflow and user journeys
> - `modeltrain.md` — the ML pipeline, precisely, with `path:line` citations
>
> **Currency:** this document reflects the repository at commit `ae61893`
> (Session 12). Everything below is taken from the actual code; nothing is
> aspirational unless explicitly marked `[OPTIONAL/FUTURE]` or `[NOT SUPPORTED]`.

---

## 1. Project identity

| | |
|---|---|
| **Project name** | India Thermal Event Intelligence Platform ("India Fire Intelligence") |
| **Team** | Team ZeroOne |
| **SIH problem statement** | SIH26162 |
| **Sponsor / context** | NTRO (National Technical Research Organisation), Smart India Hackathon 2026 |
| **Official PS title** | "AI-Based Detection and Classification of Industrial Fires and Persistent Thermal Sources Using NASA FIRMS, OSM & Satellite Data" |
| **Immediate milestone** | Internal hackathon demo — 5 September |
| **Repository** | https://github.com/siddiquezain/zero1 (branch `main`) |

### The problem, in our own words

Satellite thermal-anomaly feeds (NASA FIRMS MODIS/VIIRS) tell an operator *where*
a hotspot is, never *what caused it*. An analyst monitoring Indian industrial
regions cannot easily separate an accidental industrial fire from a routine gas
flare, a steel-plant thermal signature, or seasonal crop-residue burning — and
the raw feed offers no prioritisation, no context, and no explanation.

Two structural facts make a naïve "fire classifier" impossible:

1. **There is no dataset of confirmed industrial-fire incidents anywhere in the
   world** to train a supervised detector on.
2. Raw detections are **point-level**: several FIRMS pixels from one burning
   location arrive as separate rows over hours or days, giving no event-level
   picture of how a thermal source is evolving or how persistent it is.

### Core objective

Turn the raw NASA FIRMS thermal feed over India into a **prioritised, explained,
GIS-based operational picture** that:

1. Ingests and scores FIRMS NRT detections for the India bounding box.
2. Classifies each detection into three PS-aligned output classes (below) using a
   globally-trained Random Forest (India held out) plus an anomaly rule.
3. Scores each detection with a transparent rule-based **risk engine** (0–100) and
   assigns a severity (CRITICAL / HIGH / MEDIUM / LOW).
4. Raises alerts into a SQLite store with a lifecycle
   (DETECTED → VALIDATING → ALERTED → ESCALATED → MONITORING → EXTINGUISHED).
5. **Clusters** alerts into multi-pixel, multi-day **thermal events** (union-find,
   ≤15 km, ≤3 days) with deterministic SHA-256 IDs.
6. **Fingerprints** each event across six behavioural dimensions → a behaviour
   category.
7. Builds a structured **evidence stack** (supporting / limiting / neutral).
8. **Replays** how each event evolved (milestones + frame-by-frame slider).
9. Computes a **risk trajectory** (STABLE → HIGH PRIORITY) from the frame-level
   risk history.
10. Derives a **facility thermal baseline** for each industrial site and a
    **deviation score** for the current event vs that baseline.
11. Presents everything on a dark operations dashboard and exposes it through an
    optional, read-only **Fire Intelligence Agent** (natural language).

### The three output classes (PS deliverable (i))

| Output class | Meaning | How it is derived |
|---|---|---|
| **Industrial Fire / Abnormal Thermal Event** | Anomalous departure — matches neither learned pattern | model `anomaly_flag == 1` (`max(prob) < 0.55`) |
| **Persistent Industrial Thermal Source** | Continuous heat: gas flares, kilns, smelters, thermal power | model `predicted_label == "A"`, `anomaly_flag == 0` |
| **Forest / Agricultural Fire** | Natural or crop-residue burning | model `predicted_label == "B_candidate"`, `anomaly_flag == 0` |

The classes are assigned by the **rule-based risk engine**
(`src/alerting/risk_engine.py`), not by the model directly — the model predicts
two classes plus a probability; the third label is the anomaly flag. See
`modeltrain.md` §7.

### Locked framing — never deviate

> *"We detect anomalous departures from known persistent-industrial and
> natural-fire patterns — not confirmed fires, because no training data for
> confirmed industrial fires exists anywhere. Every alert requires human
> verification."*

### Target users

- Disaster-management / emergency-monitoring analysts.
- Industrial-safety and environmental-compliance monitoring teams.
- Technical evaluators (SIH judges; NTRO / ISRO / NRSC-adjacent audiences).

### Core use cases

1. **Situational awareness** — "What thermal activity is over India now, how
   serious is it?"
2. **Triage** — "Which events need attention first?"
3. **Investigation** — "Why was this flagged, what is its behaviour pattern, how
   does it compare to the facility's own baseline, and what should we do?"
4. **Early warning** — "Which events are on an increasing risk trajectory?"
5. **Facility monitoring** — "What is happening around known industrial sites, and
   is it normal for that site?"
6. **Historical analysis** — "How does today compare to the recent baseline?"
7. **Reporting / hand-off** — "Export the current picture for GIS tools or a
   briefing."
8. **Natural-language access** — "Ask the platform instead of driving filters."
   (Fire Intelligence Agent, read-only.)

---

## 2. Scope

### Implemented (as of Session 12)

**Data & ML pipeline (Stages 1–8)** — offline, produces the committed data the
dashboard serves. Not modified since the training run; see `modeltrain.md`.

- FIRMS NRT ingestion (India bbox + 6 non-India training regions); VNF gas-flare
  catalogue; WRI Global Power Plant DB; OSM `landuse=industrial` polygons.
- Feature engineering (`src/features/engineer.py`), spatial-grid split with
  leakage assertions (`src/model/split.py`, `assemble.py`).
- RandomForest classifier, global training / India geographic holdout, VNF
  labelling oracle (`src/model/train.py`).
- 30 curated confirmed incidents scored as an independent evaluation set
  (`src/scoring/score_incidents.py`).
- **Live FIRMS NRT refresh** (`src/ingestion/refresh.py`) — when `FIRMS_MAP_KEY`
  is set and `stage6_model.joblib` is present locally, fresh VIIRS+MODIS
  detections are fetched, re-scored, and `alerts.db` reseeded at startup or via a
  sidebar button. Falls back to the committed snapshot on any failure.

**Alerting**

- `src/alerting/risk_engine.py` — rule-based `output_class`, `risk_score`,
  `severity`, `land_cover_context`, `hazard_facility_type`, `narrative`,
  `nearest_city`, `dist_nearest_city_km`, `near_population`, and the additive
  `risk_factors` breakdown. `explain_score()` and (additive, opt-in)
  `deviation_factor()`.
- `src/alerting/alert_store.py` — SQLite store `data/alerts.db`, six lifecycle
  states, `risk_factors` JSON column.
- `src/alerting/pipeline.py` — `run(fresh=…)` seeds the store from
  `stage6_india_scores.parquet`.

**Intelligence service layer** — `src/intelligence/`, framework-agnostic, **no
Streamlit import anywhere in the package.**

- `geo.py` — offline lat/lon → Indian state / district resolver (pure-Python
  point-in-polygon over a bundled 1.2 MB admin GeoJSON). Product scope is
  India-only; out-of-bbox points are flagged, never moved.
- `queries.py` — every read the UI or agent needs.
- `actions.py` — read-only exports (GeoJSON / CSV / incident report) + manual-UI
  helpers (`set_alert_status`, `run_pipeline_fresh`, `ensure_seeded`).
- `clustering.py` — `ThermalEvent` (29-field dataclass), `cluster_alerts()`,
  union-find, SHA-256 event IDs.
- `fingerprint.py` — `compute_fingerprint()` — event behaviour: six dimension
  ratings + one of six behaviour categories.
- `evidence.py` — `EvidenceItem` + `build_evidence()` → supporting / limiting /
  neutral; always includes system-level "FIRMS resolution" and "no ground truth"
  limiting items.
- `evolution.py` — `build_evolution()` → ordered frames + milestones.
- `early_warning.py` — `compute_trajectory(frames)` → state + trajectory + delta
  + signals. **Describes an observed trend; never predicts.**
- `facility_fingerprint.py` (**Session 11**) — `build_facility_baseline()` +
  `compare_event_to_baseline()`: a facility-level thermal baseline and a 0–100
  deviation score, deterministic, no ML, no LLM.
- `agent/` — deterministic keyword/intent parser (guaranteed baseline) + optional
  Claude tool-use loop, over a fixed **read-only** registry of 26 tools.

**Dashboard** — `dashboard/`, Streamlit multipage via `st.navigation`.

- Eight pages: Command Center, Alerts, Investigation, Map Explorer, Analytics,
  Facilities, Reports / GIS, Model. (The Limitations page module still exists on
  disk but was removed from the sidebar in Session 12.)
- Fire Intelligence Agent as a docked panel on Command Center + a `st.dialog`
  command palette from the sidebar.

### Explicitly out of scope (this round)

| | |
|---|---|
| Agent-initiated Acknowledge / Escalate / Resolve, or any incident-state change | `[NOT SUPPORTED]` — manual controls stay fully available; the agent is read-only |
| Visual-identity rebuild | `[NOT SUPPORTED]` — the dark operations aesthetic is fixed |
| React / FastAPI frontend | `[OPTIONAL/FUTURE]` — the service layer is structured so this is a frontend-only project later |
| Historical FIRMS archive; GIHS integration; land-cover raster; model retraining | `[OPTIONAL/FUTURE]` |
| Real-time streaming ingestion; authentication / multi-user; notifications; persistent event DB table | `[OPTIONAL/FUTURE]` |
| Folding the thermal-deviation score into `risk_score` | `[NOT SUPPORTED]` — the three scores are kept distinct by design |

---

## 3. Implementation status

Legend: **[IMPLEMENTED]** works today · **[PARTIAL]** works with a stated
limitation · **[OPTIONAL/FUTURE]** may be added · **[NOT SUPPORTED]** will not be
built and must not be claimed.

### Data & ML pipeline

| Stage | Status | Notes |
|---|---|---|
| 1 — FIRMS + VNF + GPPD + OSM ingestion | [IMPLEMENTED] | every row tagged `split` at ingest |
| 2 — normalised facility table | [IMPLEMENTED] | `data/processed/facilities.parquet` — 72,624 rows (34,936 GPPD + 37,688 OSM); 39,277 in India |
| 3 — labelling | [PARTIAL] | Class A from the VNF oracle; Class B still `B_candidate` (not land-cover validated); 30 confirmed incidents curated |
| 4 — feature engineering | [IMPLEMENTED] | `src/features/engineer.py` — 7 model features + context columns |
| 5 — assemble & spatial-grid split | [IMPLEMENTED] | `src/model/assemble.py` + `split.py` with leakage assertions |
| 6 — RandomForest, global train / India holdout | [IMPLEMENTED] | scores committed to `stage6_india_scores.parquet`; trained `.joblib` is git-ignored |
| 7 — 30 incidents scored | [IMPLEMENTED] | `data/incidents/stage7_incident_scores.parquet` — 21/30 anomaly-flagged (training-run snapshot) |
| 8 — multipage Streamlit dashboard | [IMPLEMENTED] | |
| Live FIRMS NRT refresh | [IMPLEMENTED] | needs `FIRMS_MAP_KEY` **and** `stage6_model.joblib` present locally; silent fallback otherwise |

### Alerting / intelligence

| Module | Status |
|---|---|
| `risk_engine.py` (scoring, factors, `explain_score`, `deviation_factor`) | [IMPLEMENTED] |
| `alert_store.py` (SQLite, lifecycle, `risk_factors` JSON) | [IMPLEMENTED] |
| `pipeline.py` (`run(fresh=…)`) | [IMPLEMENTED] |
| `intelligence/geo.py` (offline PIP resolver, India-only scope) | [IMPLEMENTED] |
| `intelligence/queries.py` (all reads incl. events + facility fingerprints) | [IMPLEMENTED] |
| `intelligence/actions.py` (GeoJSON / CSV / incident report + manual helpers) | [IMPLEMENTED] |
| `intelligence/clustering.py` (`ThermalEvent`, `cluster_alerts`) | [IMPLEMENTED] |
| `intelligence/fingerprint.py` (event behaviour) | [IMPLEMENTED] |
| `intelligence/evidence.py` | [IMPLEMENTED] |
| `intelligence/evolution.py` | [IMPLEMENTED] |
| `intelligence/early_warning.py` | [IMPLEMENTED] |
| `intelligence/facility_fingerprint.py` (baseline + deviation) | [IMPLEMENTED] |
| `intelligence/agent/*` (deterministic + optional Claude, 26 read-only tools) | [IMPLEMENTED] deterministic; [OPTIONAL] Claude |
| `dashboard/timeline.py` | **dead code** — no longer imported; Analytics recomputes from the alert DataFrame in `queries._daily_summary()` |

### Dashboard

| Page | Status | What it shows |
|---|---|---|
| **Command Center** | [IMPLEMENTED] | 5 alert KPIs + 4 event KPIs, live India map, top priority alerts, 3 donut/timeline panels, recent-detections table, quick actions, docked agent panel |
| **Alerts** | [IMPLEMENTED] | DETECTIONS tab (severity-grouped, paginated `_PAGE=12`, manual Acknowledge/Escalate/Resolve with toasts) + THERMAL EVENTS tab (event cards, `EVENT #<id>`) |
| **Investigation** | [IMPLEMENTED] | event header, Detection, Context, Why flagged, Classification, Risk assessment (factor breakdown), Thermal Behaviour Fingerprint, Evidence Stack, Event Evolution + replay slider, Risk Trajectory, **Facility Thermal Baseline** panel, Recommended action + manual actions |
| **Map Explorer** | [IMPLEMENTED] | filterbar, layer controls (colour by class/severity, incidents, facilities, "Regional context (outside India)", "Thermal Events" centroid overlay), Data-validation expander, top detections |
| **Analytics** | [IMPLEMENTED] | activity stacked-bars + totals, baseline comparison (or honest "insufficient history"), **Facility thermal baselines** section, classification/severity donuts + land-cover hbar, hazard table |
| **Facilities** | [IMPLEMENTED] | filterbar; facilities-with-activity table incl. Baseline / Deviation columns; "Focus a facility" metrics + thermal-baseline block. Fixed 10 km association radius (slider removed Session 12) |
| **Reports / GIS** | [IMPLEMENTED] | filter-aware GeoJSON / CSV / incident-report downloads + previews |
| **Model** | [IMPLEMENTED] | pipeline chips, data sources, RF description, three-way evaluation table, feature importance, risk-engine explainer, "three separate scores" note |
| **Limitations** | [PARTIAL] | module `dashboard/views/limitations.py` exists; **removed from the sidebar in Session 12**. Re-add one line in `dashboard/app.py` `_PAGES` to restore |

### Existing capability that must never be removed

Severity / status / date / classification / state filters · alert pagination ·
alert assessment expander · manual Acknowledge / Escalate / Resolve · six
lifecycle states · India detection map with all layers, colour-by toggle,
legend, tooltips, click-to-investigate · outside-India "Regional context" layer +
Data-validation expander · activity timeline / baseline comparison · GeoJSON +
CSV + incident-report export · 3-class classification output · confirmed-incident
scoring · Model transparency content · rule-based risk engine · global-training /
India-holdout methodology and leakage checks · the read-only Fire Intelligence
Agent and its deterministic offline baseline.

---

## 4. UI information architecture

Navigation follows the operator workflow:

```
DETECT → CLASSIFY → CLUSTER → FINGERPRINT → EXPLAIN → COMPARE → ACT
```

```
Shell (SIH · 26162 · India Fire Intelligence  ·  IST clock  ·  LIVE NRT / NRT SNAPSHOT badge)
│
├── Command Center      what / how bad / where / what needs attention  (+ event KPIs)
├── Alerts              DETECTIONS tab + THERMAL EVENTS tab
├── Investigation       header · detection · context · why · classification · risk
│                       + fingerprint · evidence · evolution replay · trajectory
│                       + facility thermal baseline
├── Map Explorer        every scored detection at true coordinates + all layers
├── Analytics           activity · baseline · facility baselines · classification
├── Facilities          activity around known industrial infrastructure + baselines
├── Reports / GIS       GeoJSON / CSV / incident report
└── Model               the real pipeline, evaluation, feature importance
```

The Fire Intelligence Agent is docked on the Command Center and available as a
command-palette dialog (`⌘ Ask Agent`) from the sidebar on every page — never a
full-screen chatbot.

---

## 5. Data sources

| Source | Role | Status |
|---|---|---|
| NASA FIRMS NRT (VIIRS 375 m, MODIS 1 km), India bbox | Primary thermal detections | [IMPLEMENTED] — NRT only, ≈ last 5 days |
| VIIRS Nightfire (VNF) Global Gas Flare Survey (ORNL DAAC, 2012–2019) | Class A **labelling oracle only** (not a feature) | [IMPLEMENTED] |
| WRI Global Power Plant Database v1.3 | Facility / context layer | [IMPLEMENTED] |
| OpenStreetMap `landuse=industrial` (Overpass) | Facility / context layer | [IMPLEMENTED] |
| 30 curated confirmed Indian incidents (news / Wikipedia) | Independent evaluation / demo set | [IMPLEMENTED] |
| `data/geo/india_admin.geojson` (36 dissolved states + 760 districts, 1.2 MB) | Offline lat/lon → state/district resolver | [IMPLEMENTED] |
| `data/geo/india_outline.json` (mainland outline, ~3 KB) | Thin map emphasis border | [IMPLEMENTED] |
| GIHS (Global Industrial Heat Sources) | Additional Class A | [NOT SUPPORTED] yet |
| MODIS MCD12Q1 / ESA CCI Land Cover raster | Precise land cover | [NOT SUPPORTED] yet — heuristic used |
| Historical FIRMS archive (LAADS DAAC) | Temporal incident matching | [NOT SUPPORTED] yet |

---

## 6. Data / ML approach

- **Global training, India held out.** The classifier learns physical/thermal
  patterns from non-India FIRMS data; India is a locked geographic holdout for
  evaluation and deployment only.
- **No random split as the primary metric.** Splitting is by 1° spatial grid
  cell. Three figures are reported side by side (random baseline, spatial
  holdout, India holdout).
- **VNF is a labelling oracle, not a feature.** A global FIRMS row within 5 km of
  a known VNF flare site → Class `A`; every other global FIRMS row →
  `B_candidate` (not land-cover validated). VNF rows themselves are excluded from
  training (wrong feature space).
- **Model.** `Pipeline(SimpleImputer(median), RandomForestClassifier(300 trees,
  min_samples_leaf=10, class_weight="balanced", random_state=42))`. Seven
  features: `bt_kelvin`, `frp_mw`, `persistence_count`,
  `dist_nearest_facility_km`, `agri_season_flag`, `day_night_bin`, `acq_month`.
- **Anomaly rule.** `max(class probability) < 0.55` → "Industrial Fire / Abnormal
  Thermal Event". Not a model class — a post-hoc flag.
- **Risk engine is separate and rule-based** — a transparent 0–100 additive score
  → severity bands (≥65 CRITICAL / ≥40 HIGH / ≥20 MEDIUM / else LOW).
- **Events are derived, not stored** — recomputed in-memory from `alerts.db` on
  cache miss, keyed on DB mtime.
- **Facility thermal deviation is deterministic** — robust statistics
  (`statistics.median` / `quantiles` / MAD), no ML.

### Three distinct scores — never merged into one number

| Score | Source | Meaning |
|---|---|---|
| **model class probability** | RandomForest `prob_A` / `prob_B_candidate` | how well the detection matches a learned pattern |
| **risk_score** (0–100) | `risk_engine` additive rule | operational priority / triage |
| **thermal_deviation_score** (0–100) | `facility_fingerprint` | how far the current event departs from the facility's own baseline |

The UI and code must never imply "deviation = fire probability" or
"risk score = probability of fire".

### Hard constraints — do not violate

- There is **no dataset of confirmed industrial-fire incidents** anywhere. Do not
  build or claim a classifier trained on confirmed industrial-fire events.
- A FIRMS hotspot is **not typed by cause**. Never treat a raw hotspot as a
  labelled example.
- "Near a facility" is a **weak context feature, never a label**.
- **Never use a random train/test split** as the primary evaluation.
- **Do not tune the model against the India holdout.**
- Never claim "confirmed industrial fire detection." Keep the locked framing.

---

## 7. Fire Intelligence Agent

### Concept

A natural-language operational-intelligence layer over the *same* backend the
manual UI uses — **not** an "AI chatbot for fire detection". Two interaction
modes, one service layer:

- **Manual** — the conventional dashboard and controls.
- **Agent** — ask questions / request views in natural language.

The agent is an additional interface, never a replacement.

### Capabilities (READ-ONLY, 26 tools)

- Answer from real application data: alerts, events, fingerprints, evidence,
  evolution, trajectories, **facility baselines & deviation**, facilities,
  regions, incidents, analytics, baselines.
- Rank / filter / aggregate detections, alerts, events, and facilities.
- Find increasing-risk events; find abnormal facilities; rank facilities by
  thermal deviation.
- Apply filters to the shared UI state; navigate; focus the map; open an
  Investigation; generate a report.
- Offer result cards: **Open Investigation**, **Show on Map**, **Generate
  Report**.

### Limitations

- **Read-only.** The agent never acknowledges, escalates, resolves, or changes
  any incident state. A state-change request returns an explanation + an
  "Open Investigation" card.
- Answers only from real data — no fabrication; "not available" when a value is
  missing.
- No free-text database access; the LLM never issues SQL, shell, or arbitrary
  code. The tool registry is fixed and typed.

### Offline-first requirement

`src/intelligence/agent/deterministic.py` is the **guaranteed baseline** and
handles every documented example prompt. The application — including the agent —
is fully functional with **no API key**.

### Optional Claude runtime

If `ANTHROPIC_API_KEY` is present and `import anthropic` succeeds,
`src/intelligence/agent/claude.py` runs a tool-use loop (≤ 4 tool rounds) over
the same read-only registry. Model id from `ANTHROPIC_MODEL`
(default `"claude-sonnet-4-6"`). Any failure degrades to the deterministic parser
silently.

---

## 8. Technology stack

- **Language:** Python 3.12 (`runtime.txt` pins `python-3.12`; runs on 3.11+).
- **Frontend:** Streamlit (`st.navigation`), pydeck + CARTO dark basemap (no
  Mapbox token), Plotly for charts.
- **Data:** pandas, pyarrow (Parquet), SQLite (`data/alerts.db`).
- **ML:** scikit-learn (RandomForest, BallTree, SimpleImputer), joblib.
- **Clustering / stats:** `hashlib`, `math`, `statistics` (stdlib) — no new
  dependency.
- **Geo:** bundled simplified admin GeoJSON + pure-Python ray-casting
  point-in-polygon.
- **Agent LLM (optional):** `anthropic` SDK — guarded import; absence ≠ failure.
- **Config:** `python-dotenv`, `.env`.
- No React, no FastAPI, no external database, no auth layer, no Docker, no Redis.

`requirements.txt` installs the runtime set; `matplotlib` and `tqdm` are
commented out (used only by the offline `src/ingestion/visualise.py` script, not
by the dashboard, the intelligence layer, or the tests).

---

## 9. Repository structure

```
context.md  architecture.md  design_brief.md  workflow.md  modeltrain.md
requirements.txt  runtime.txt  .env.example  .gitignore
.streamlit/config.toml         # enableStaticServing = true, dark theme
.claude/launch.json            # streamlit run config (browser preview)

data/
  raw/                                    git-ignored downloads
  processed/
    facilities.parquet                    committed — 72,624 rows
    facilities.parquet.meta.json          committed
    stage6_india_scores.parquet           committed, live-refreshable (~1.2k rows)
    stage6_model.joblib                   GIT-IGNORED — needed only for live refresh
    stage5_*.parquet, features_stage4...  git-ignored intermediates
  incidents/
    confirmed_incidents_india.csv         committed — 30 rows
    stage7_incident_scores.parquet        committed
    match_summary.json                    committed
  geo/
    india_admin.geojson                   committed — 1.2 MB, 36 states + 760 districts
    india_outline.json                    committed — ~3 KB mainland outline
  alerts.db                               GIT-IGNORED — auto-seeded on first run

src/
  ingestion/   config, utils, firms, vnf, facilities, gihs, visualise
               refresh.py                 live FIRMS NRT refresh at startup / on demand
  labeling/    match_incidents.py         Stage 3 — FIRMS ↔ incident matching
  features/    engineer.py                Stage 4
  model/       split.py, assemble.py, train.py   Stages 5–6
  scoring/     score_incidents.py         Stage 7
  alerting/    risk_engine.py, alert_store.py, pipeline.py
  intelligence/
    geo.py               resolve(lat,lon) → {state, district, in_india, zone}
    queries.py           every read (alerts, events, facility fingerprints, analytics)
    actions.py           GeoJSON / CSV / incident report + manual-UI helpers
    clustering.py        ThermalEvent (29 fields) + union-find cluster_alerts()
    fingerprint.py       compute_fingerprint()  — event behaviour, 6 dimensions
    evidence.py          EvidenceItem + build_evidence()
    evolution.py         build_evolution()  — frames + milestones
    early_warning.py     compute_trajectory(frames)
    facility_fingerprint.py   build_facility_baseline() + compare_event_to_baseline()
    agent/
      tools.py           26 read-only tools, 1:1 to queries.* / actions exporters
      deterministic.py   regex/intent parser (guaranteed baseline); interpret = parse
      claude.py          optional Anthropic tool-use loop
      runtime.py         ask() — selects runtime, dispatches, never raises
      response.py        NL formatting of tool results + result cards + ui_action

dashboard/
  app.py        shell: theme.inject, state.init, ensure_seeded, maybe_refresh,
                st.navigation over _PAGES, agent mount, nav.run()
  theme.py      the CSS design system (palette + type scale), injected once per page
  state.py      session_state defaults + typed filter / nav / focus helpers
  data.py       @st.cache_data wrappers — the ONLY bridge to src.intelligence
  shell.py      topbar (LIVE NRT / NRT SNAPSHOT badge, IST clock) + sidebar cards
  components/   ui.py, mapview.py, charts.py, filterbar.py
  views/        command_center, alerts, investigation, map_explorer, analytics,
                facilities, reports, model, limitations (limitations unlinked)
  agent/panel.py   docked panel + st.dialog command palette + result-card rendering
  timeline.py   DEAD CODE — retained but unused
  static/       agent-bot.webp (used, base64-embedded)
                bb-8.glb, model-viewer.min.js  (committed but no longer used)

tests/          191 tests, all passing (see §12)
reports/        stage6_evaluation.txt, stage6_feature_importance.csv,
                stage7_incident_report.txt  (from the training run)
docs/superpowers/plans/  the two multi-task plan documents
```

Also at the root (working notes, not authoritative): `audit.md`, `task.md`,
`new.txt`, `redesign.md`, `review.md`, `ui.txt`.

---

## 10. Important architectural decisions

1. **Single service layer.** All data/logic lives in `src/intelligence/`, built
   on `src/alerting/`. Streamlit is presentation only. **No `dashboard/*` module
   imports `src.alerting` directly** — only `src.intelligence` (via
   `dashboard/data.py`).
2. **Events are derived, not stored.** `queries._events_cached(_sig)`,
   `@lru_cache(maxsize=8)` keyed on `db_signature()` (`alerts.db` mtime). No new
   table; auto-invalidates on any write.
3. **Deterministic IDs.** Event id = `sha256("|".join(sorted(alert_ids)))[:8]`.
   Stable across recomputation from the same alert set.
4. **Agent = fixed read-only tool registry.** The LLM or parser can only invoke
   named functions with typed arguments. No raw state, no SQL, no mutation.
5. **Deterministic parser is primary; Claude is optional.** Offline-first.
6. **Investigation is assembled, not stored** — a view over alert fields + event
   intelligence + facility baseline.
7. **Offline geo.** Pure-Python ray-casting over bundled GeoJSON. No dependency,
   no network. Coordinates are never swapped, projected, normalised, or clipped;
   out-of-India points are flagged and shown as an explicit opt-in layer.
8. **The three scores stay separate.** `risk_engine.score_row` is row-level and
   runs before events/baselines exist, so the thermal-deviation score is
   presented as its own signal, never folded into `risk_score`.
9. **Preserve, relocate, don't rewrite.** New panels layer on top of existing
   renderers.

---

## 11. Known limitations & risks

- **FIRMS NRT covers ≈ 5 days.** No historical archive. `persistence_count` is a
  5-day count; `agri_season_flag` / `acq_month` carry no signal in a single
  narrow window (both have 0.0 model importance in the committed report).
- **Facility baselines are thin.** With a ~5-day window, of ~130 facilities with a
  nearby detection only ~5 have enough history for a baseline; the rest are
  `INSUFFICIENT_BASELINE` (reported honestly, not invented). For single-burst
  facilities the baseline includes the scored event's own detections
  (`baseline_overlap.dominated`). No `ABNORMAL` facilities in typical snapshots.
- **Land cover is a coordinate-zone heuristic**, not a raster.
- **Class A training set is thin** (~1,901 FIRMS rows via the VNF oracle); Class A
  F1 ≈ 0.18 on the spatial holdout. Top model features are geographic/temporal
  (`dist_nearest_facility_km` 0.29, `day_night_bin` 0.25), not thermal.
- **The trained `.joblib` is not in the repo.** Live NRT scoring requires it
  locally + `FIRMS_MAP_KEY`. Otherwise the dashboard runs off committed parquets.
- **Events are in-memory** — O(n²) pair scan on cold cache; fine at ≤ 5k rows
  (the `ponytail` comment marks the ceiling).
- **`.env.example` contains real credentials** (a FIRMS key and an Earthdata
  password) instead of placeholders — a pre-existing security issue on the public
  repo. Rotate the Earthdata password; replace the values with placeholders.
- **`dashboard/timeline.py` and `dashboard/static/{bb-8.glb, model-viewer.min.js}`
  are dead weight** — retained but unused.
- **Optional Claude path** adds cost/latency/network; degrades to deterministic
  cleanly. Default model id `"claude-sonnet-4-6"` is not a current model — set
  `ANTHROPIC_MODEL` if using the Claude path.

---

## 12. Testing

`pytest` — **191 tests, all passing.**

```
tests/
  test_ingestion.py, test_features.py, test_split.py         original pipeline
  test_intelligence_geo.py                                   geo resolve + known coords + audit
  test_intelligence_queries.py                               filters, India scope, label consistency
  test_intelligence_actions.py                               GeoJSON / CSV / incident report
  test_agent_deterministic.py                                every documented prompt → correct tool
  test_clustering.py         (11)   cluster_alerts, ThermalEvent, event IDs
  test_fingerprint.py        (9)    event-behaviour dimensions + categories
  test_evidence.py           (7)    direction routing, system items, no fabrication
  test_evolution.py          (9)    frames, milestones, edge cases
  test_early_warning.py      (9)    state transitions, trajectory, signals
  test_events.py             (8)    query functions, LRU cache invalidation
  test_agent_events.py       (10)   event intents, deterministic parser
  test_facility_fingerprint.py (25) baseline gate, NORMAL/ELEVATED/HIGHLY_ABNORMAL,
                                    missing FRP/BT/facility, day-night & persistence
                                    deviation, determinism, no fabrication +
                                    risk-engine / lifecycle / agent regression guards
  test_agent_panel.py        (5)    _richtext bold conversion + re.sub crash regression
```

---

## 13. Hackathon constraints & demo priorities

- **Must run offline** on a single machine with no API keys. The committed
  parquets + auto-seeded `alerts.db` are enough.
- **Judge-facing clarity in ~10 seconds** on the Command Center.

### Demo path (in order)

1. Command Center reads instantly: active alerts, criticals, event KPIs, the map,
   what to do next.
2. Alerts → THERMAL EVENTS tab → "Investigate event #XXXXXXXX" → Investigation
   showing fingerprint, evidence, evolution replay, risk trajectory, **and the
   Facility Thermal Baseline panel** (deviation vs the site's own history).
3. Map Explorer: detection layer + event centroid overlay + CARTO basemap with
   neighbouring-country labels + the Data-validation expander.
4. Fire Intelligence Agent (offline): *"Which events are increasing in risk?"*,
   *"How unusual is event <id>?"*, *"Rank facilities by thermal deviation"*.
5. Analytics baseline comparison + Facilities baselines as differentiators.
6. Model page for technical credibility (three-way evaluation, feature
   importance, the "three separate scores" note).

---

## 14. Deployment

- **Target:** Streamlit Community Cloud — `share.streamlit.io` → repo
  `siddiquezain/zero1`, branch `main`, main file `dashboard/app.py`.
- Runs with **no secrets** (committed data + auto-seed). `ANTHROPIC_API_KEY` /
  `FIRMS_MAP_KEY` are optional platform secrets.
- `runtime.txt` pins Python 3.12; `.streamlit/config.toml` enables static serving.
- **Netlify is not an option** — Streamlit is a long-lived Python/WebSocket
  server, not static/serverless.

---

## 15. Future extensions (not in scope now)

- Agent state-changing actions (Acknowledge / Escalate / Resolve) behind an
  explicit confirmation gate.
- React + FastAPI frontend on top of the unchanged service layer.
- Historical FIRMS archive ingestion → real temporal incident matching → real
  multi-month facility baselines (makes the seasonal deviation signal meaningful).
- GIHS + land-cover raster integration → better Class A / Class B precision.
- Precomputed facility-baseline Parquet artefact if the alert set grows past
  ~10k rows.
- Persistent event storage (DB table) if in-memory clustering reaches scale
  limits.
- Notifications, multi-user, authentication.

---

## Status Tracker

### Pipeline (unchanged since the training run)

- [x] Stage 1 — FIRMS NRT (India + 6 global regions) · VNF · GPPD · OSM.
- [x] Stage 2 — `facilities.parquet` (72,624 rows; 39,277 IND).
- [~] Stage 3 — Class A via VNF oracle; Class B still `B_candidate`; 30 incidents curated.
- [x] Stage 4 — feature engineering.
- [x] Stage 5 — assemble & 1° spatial-grid split with leakage assertions.
- [x] Stage 6 — RandomForest, global train / India holdout; scores committed.
- [x] Stage 7 — 30 incidents scored (21/30 anomaly-flagged in the training run).
- [x] Stage 8 — multipage Streamlit dashboard.

### Session 5 — Information-architecture reorg + Fire Intelligence Agent

`dc8b983`, `61156d0`, `f4a0046` — framework-agnostic `src/intelligence/` service
layer; offline geo resolver; dashboard rebuilt as a multipage operations console;
read-only deterministic agent + optional Claude; 4 root docs + study guide.

### Session 6 — Geographic-consistency fix

`geo.py` rewritten as an authoritative point-in-polygon resolver over a bundled
1.2 MB admin GeoJSON; product scope made India-only; out-of-India FIRMS points
kept at true coordinates as an explicit opt-in "Regional context" layer + a Data-
validation expander. Coordinates never swapped / projected / normalised / clipped.

### Sessions 8–9 — Audit fixes + live FIRMS wiring

`dadbbcf`, `641dc5f`, `e044448`, `1d44ef5`, `40f2a83` — bug fixes + agent UX;
`src/ingestion/refresh.py` live FIRMS NRT fetch at startup; sidebar refresh
button; staleness check uses latest DB `acq_date`, not parquet mtime.

### Session 10 — Thermal Event Intelligence Platform (`820ceb7` … `9b277cc`)

- [x] `clustering.py` — `ThermalEvent` (29 fields), `cluster_alerts()`, union-find, SHA-256 IDs. 11 tests.
- [x] `fingerprint.py` — `compute_fingerprint()`, 6 dimensions, 6 behaviour categories. 9 tests.
- [x] `evidence.py` — `EvidenceItem`, `build_evidence()`, SUPPORTING/LIMITING/NEUTRAL. 7 tests.
- [x] `evolution.py` — `build_evolution()`, ordered frames, 4 milestone types. 9 tests.
- [x] `early_warning.py` — `compute_trajectory(frames)`, 5 risk states. 9 tests.
- [x] `queries.py` — `_events_cached` + 10 event query functions + `events_situation()`. 8 tests.
- [x] `dashboard/data.py` — 8 `@st.cache_data(ttl=30)` event wrappers.
- [x] Agent — 8 event tools + event intents (`interpret = parse` alias). 10 tests.
- [x] `investigation.py` — event header, fingerprint, evidence stack, evolution replay slider, trajectory.
- [x] `command_center.py` — 4-col event KPI row; `alerts.py` — DETECTIONS / THERMAL EVENTS tabs.
- [x] `map_explorer.py` — "Thermal Events" checkbox + amber centroid ScatterplotLayer.

### Session 11 — Facility Thermal Fingerprinting (`9df9873`, additive)

A facility-level behavioural baseline + current-event deviation score. **Additive:
no module removed, no schema migration, no model retraining, no UI redesign; RF
predictions / `risk_score` / severity thresholds unchanged.**

- **NEW** `src/intelligence/facility_fingerprint.py` — pure, deterministic, no
  Streamlit / no LLM. `build_facility_baseline(facility, observations)` → robust
  stats (`statistics.median` / `quantiles` / MAD) for FRP, brightness
  temperature, persistence, day-night ratio, active months over detections within
  `ASSOC_RADIUS_KM = 10 km`. Gate: `≥ MIN_OBS (6)` observations across
  `≥ MIN_ACTIVE_DAYS (2)` distinct dates, else
  `baseline_quality = INSUFFICIENT_BASELINE` (every stat left `None`).
  `compare_event_to_baseline(event, baseline)` → per-signal 0–100 deviations
  (intensity / brightness / persistence / day_night / seasonal), combined by the
  configurable `SIGNAL_WEIGHTS` map → `thermal_deviation_score` (0–100),
  `thermal_deviation_level` (NORMAL / ELEVATED / ABNORMAL / HIGHLY_ABNORMAL),
  `thermal_behavior_class` (NORMAL / ABNORMAL / INSUFFICIENT_BASELINE), plus
  deterministic `evidence[]` strings citing real numbers.
- `queries.py` — `_facility_index()` is now the single detection↔facility
  BallTree (`facilities_with_activity` refactored onto it, no second matcher);
  `get_facility_fingerprint`, `get_event_deviation`, `get_alert_deviation`,
  `rank_facilities_by_deviation`, `find_abnormal_facilities`,
  `facility_fingerprint_summary`; `facilities_with_activity` rows gain
  `baseline_quality` / `deviation_level` / `deviation_score`; `clear_caches()`
  extended.
- `risk_engine.py` — `deviation_factor(score)` helper only. **Not** called by
  `score_row`.
- Agent — 5 read-only tools + deterministic intents + response formatting. Also
  fixed a pre-existing crash: the Session-10 event intents had no `response.py`
  handlers, so `runtime.ask("show me thermal events")` raised
  `KeyError: 'frp_mw'` — added handlers + a `response.build` try/except.
- UI (no redesign) — Investigation `_render_facility_deviation` panel; Facilities
  table columns + baseline block; Analytics "Facility thermal baselines" section;
  Model + Limitations one note each.
- **NEW** `tests/test_facility_fingerprint.py` — 25 tests.

### Session 12 — Agent fix, deploy prep, UI trims

- `53123fe` — **fixed agent crash.** `dashboard/agent/panel._render_message` built
  a `re.sub` **replacement template** containing `\x00` sentinels; Python's
  template parser rejects that (`re.error: bad escape \x`), so **every bot reply
  crashed the page**. Extracted `panel._richtext()` and switched to a callable
  `re.sub` replacement. `tests/test_agent_panel.py` (5 tests) added.
- `67d5e5e` (collaborator) — agent illustration `agent-bot.webp` base64-embedded
  at import (`panel._AGENT_IMG_B64`) so `st.components` iframes make no HTTP
  round-trip per render; `stage6_india_scores.parquet` regenerated with fresher
  live FIRMS data.
- `ce0c1f2` — **deploy prep.** `runtime.txt` pins `python-3.12`; `requirements.txt`
  drops `matplotlib` + `tqdm` from the installed set (offline-script-only).
- `ae61893` — **UI trims.** "Limitations" removed from the sidebar nav
  (`dashboard/app.py` `_PAGES` + `dashboard/state.py` route); the Facilities
  "Search radius" slider removed → fixed `_RADIUS_KM = 10.0`.

**Test count:** 191 passing, 0 failing.

**Last updated:** 2026-09-04 (Session 12 — docs refreshed against commit `ae61893`).
