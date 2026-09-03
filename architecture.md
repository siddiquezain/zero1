# SIH26162 — Technical Architecture

> Companion to `context.md`, `design_brief.md`, `workflow.md`, `modeltrain.md`.
> Reflects commit `ae61893` (Session 12). Every module, field, and default below
> is from the code.
>
> Legend: **[IMPLEMENTED]** · **[OPTIONAL/FUTURE]** · **[NOT SUPPORTED]** ·
> **[DEAD CODE]** (present but unused).

---

## 1. High-level architecture

```
                         ┌───────────────────────────────────────────┐
   Operator ────────────►│  Manual UI  (Streamlit pages)              │
                         └───────────────────┬───────────────────────┘
                                             │
   Operator ──"⌘ Ask Agent"────────────────► │  Fire Intelligence Agent panel
                                             │  (docked on Command Center + st.dialog)
                                             │
                         ┌───────────────────▼───────────────────────────────────┐
                         │  dashboard/data.py   (the ONLY bridge, @st.cache_data)  │
                         └───────────────────┬───────────────────────────────────┘
                                             │  imports only src.intelligence
                         ┌───────────────────▼───────────────────────────────────┐
                         │  src/intelligence/  (framework-agnostic service layer)  │
                         │  geo · queries · actions · clustering · fingerprint     │
                         │  evidence · evolution · early_warning · facility_finger… │
                         │  agent/{tools,deterministic,claude,runtime,response}    │
                         └───────────────────┬───────────────────────────────────┘
                                             │  builds on
        ┌────────────────────────────────────┼────────────────────────────────────┐
        ▼                                    ▼                                     ▼
 src/alerting/risk_engine          src/alerting/alert_store             src/alerting/pipeline
   (rule-based scoring)            (SQLite lifecycle store)             (seed the store)
        │                                    │
        └──────────────┬─────────────────────┴────────────────┐
                       ▼                                       ▼
   data/processed/stage6_india_scores.parquet          data/alerts.db  (git-ignored,
   data/incidents/stage7_incident_scores.parquet                        auto-seeded)
   data/processed/facilities.parquet
   data/geo/india_admin.geojson  (36 states + 760 districts)

   Live path (FIRMS_MAP_KEY + stage6_model.joblib present):
   NASA FIRMS API ─► src/ingestion/refresh.maybe_refresh() ─► rewrites the parquet
                                                          ─► pipeline.run(fresh=True)
```

**Key rule:** the Streamlit layer is presentation only. All data access and logic
go through `src/intelligence/`, which is built on `src/alerting/`. **No module
under `dashboard/` imports `src.alerting` directly** — only `src.intelligence`,
and only via `dashboard/data.py`. A future React/FastAPI frontend is therefore a
frontend-only project.

**Events are derived, not stored.** Thermal-event clustering is recomputed
in-memory from `alerts.db` on cache miss, keyed by DB mtime signature. No new DB
table.

**Three scores stay distinct** — model class probability, `risk_score`,
`thermal_deviation_score` — never merged (see §8, §11).

---

## 2. Frontend architecture (Streamlit) [IMPLEMENTED]

```
dashboard/
  app.py            Shell. Order of operations:
                      T.inject()                 CSS + st.set_page_config
                      state.init()               session_state defaults
                      data.ensure_seeded()       seed alerts.db if absent
                      data.maybe_refresh()       live FIRMS if FIRMS_MAP_KEY set
                      _PAGES = {name: (render_fn, material_icon, subtitle)}   ← 8 pages
                      _requested = state.take_nav_request()
                      st.navigation([st.Page(...)], position="sidebar")
                      sidebar: shell.brand(), sidebar_refresh_card() (if key),
                               sidebar_agent_card()
                      if _requested: st.switch_page(...)   (button / agent nav)
                      nav.run()

  theme.py          The CSS design system + palette constants. inject() once per page.
  state.py          session_state model + typed helpers (filters / nav / focus / agent).
  data.py           @st.cache_data wrappers — presentation ↔ service boundary.
                    Imports ONLY: src.intelligence.{actions, queries}, agent.ask,
                                  src.ingestion.refresh.maybe_refresh
  shell.py          topbar() + sidebar cards. Imports panel._AGENT_IMG_B64,
                    refresh._age_hours, config.FIRMS_MAP_KEY.
  components/
    ui.py           section(), page_header(), kpi(), legend(), alert_card(),
                    result_card(), empty_state()
    mapview.py      build_deck(alerts, colour_by, incidents, facilities, outside,
                                focus_alert_id, view) → pydeck.Deck
    charts.py       donut(), stacked_bars(days), hbar()  — Plotly, transparent bg
    filterbar.py    render(show_status, show_class, key) — the shared analysis toolbar
  views/
    command_center.py   5 alert KPIs + 4 event KPIs + live map + priority alerts +
                        3 donut/timeline panels + recent-detections table +
                        quick actions + docked agent panel (st.container(border=True))
    alerts.py           st.tabs(["DETECTIONS","THERMAL EVENTS"])
                        DETECTIONS: filterbar, severity-grouped, paginated (_PAGE=12),
                                    per-row "View investigation →",
                                    expander with Acknowledge / Escalate / Resolve
                        THERMAL EVENTS: event cards (EVENT #<id>), "Investigate →"
    investigation.py    the assembled deep view (see §4 investigation panels)
    map_explorer.py     filterbar; layer panel (colour by class/severity;
                        Confirmed incidents; Industrial facilities;
                        Regional context (outside India); Thermal Events);
                        main pydeck map; separate event-centroid deck when toggled;
                        Data-validation expander (queries.geo_audit()); top detections
    analytics.py        activity stacked-bars + totals; baseline comparison
                        (or honest "insufficient history"); "Facility thermal
                        baselines" section; classification/severity donuts +
                        land-cover hbar; hazard table
    facilities.py       filterbar; facilities-with-activity table (Baseline /
                        Deviation columns); "Focus a facility" metrics + baseline
                        block. Fixed _RADIUS_KM = 10.0 (slider removed Session 12)
    reports.py          filterbar; GeoJSON / CSV / incident-report downloads +
                        GeoJSON preview + incident-report markdown preview
    model.py            static: pipeline chips, data sources, RF description,
                        three-way evaluation table, feature importance, risk-engine
                        explainer, "three separate scores" note
    limitations.py      static caveat panels — MODULE PRESENT, NOT IN _PAGES (Session 12)
  agent/
    panel.py            _AGENT_IMG_B64 (base64 data URI of static/agent-bot.webp),
                        _stage_html(thinking), _richtext(raw)  ← re.sub crash fix,
                        _render_message(), render(context, scope, collapsible),
                        open_dialog() = @st.dialog wrapper
  timeline.py           [DEAD CODE] get_daily_summary(), get_events_for_range() —
                        not imported anywhere. Analytics recomputes daily aggregates
                        from the alert DataFrame in queries._daily_summary().
  static/
    agent-bot.webp       used (base64-embedded)
    bb-8.glb (8.2 MB), model-viewer.min.js (910 KB)   [DEAD CODE] — earlier robot
```

- **Navigation:** `st.navigation` with explicit `st.Page` objects, one per
  `_PAGES` entry.
- **Shared state:** every page reads/writes filters through `state.py`. The
  agent's `ui_action` applies through the same helpers, then `st.rerun()` — manual
  and agent-driven filtering are indistinguishable downstream.

### `dashboard/state.py` filter model

```python
_DEFAULT_FILTERS = {
    "severity": [],              # [] = all;   list of CRITICAL/HIGH/MEDIUM/LOW
    "status": [],                # list of the six lifecycle states
    "output_class": [],          # "Industrial Fire" | "Persistent Source" | "Natural Fire"
    "state": [],                 # list of Indian state names
    "region": None,              # e.g. "eastern india" (geo.REGIONS)
    "date_from": None, "date_to": None,     # "YYYY-MM-DD"
    "near_facility_type": None,   # hazard-type keyword
    "max_dist_facility_km": None,
    "min_risk": None,
    "search": None,              # free text over place / district / state / narrative
}
```

Helpers: `init()`, `filters()` (drops empties), `raw_filters()`, `set_filters(patch,
replace)`, `clear_filters()`, `focus_alert(id)`, `request_nav(page)`,
`take_nav_request()`, `apply_ui_action(ui_action)`. Session keys also include
`focus_alert_id`, `agent_history`, `agent_open`, `agent_phase`, `agent_pending`,
`nav_request`, `alert_page`, `map_colour_by`, `show_incidents`, `show_facilities`,
`_active_page`.

### `dashboard/data.py` — cache wrappers (selected)

| Convenience fn | Wraps | TTL |
|---|---|---|
| `S(filters)` | `queries.situation_summary` | 30 s |
| `A(filters, limit, sort_by)` | `queries.list_alerts` | 30 s |
| `R(by, filters, limit)` | `queries.rank_alerts` | 30 s |
| `INV(alert_id)` | `queries.get_investigation` | 30 s |
| `ANALYTICS(df, dt)` | `queries.analytics_summary` | 30 s |
| `BASELINE(filters)` | `queries.baseline_comparison` | 30 s |
| `FACILITIES(filters, limit, radius_km)` | `queries.facilities_with_activity` | 120 s |
| `DATE_RANGE()` | `queries.data_date_range` | 30 s |
| `incidents()` | `queries.incidents` | 600 s |
| `outside_india()` / `geo_audit()` | `queries.outside_india_alerts` / `geo_audit` | 30 s |
| `EVENTS / EVENT / EVENT_FOR_ALERT / EVENT_FP / EVENT_EV / EVENT_EVO / EVENT_TRAJ / EVENTS_SIT` | the `queries.*` event fns | 30 s |
| `EVENT_DEV / FACILITY_FP / FACILITY_DEV_RANK / ABNORMAL_FACILITIES / FP_SUMMARY` | the `queries.*` facility-fingerprint fns | 60 s |
| `set_status(id, action)` | `actions.set_alert_status` + `st.cache_data.clear()` | — |
| `run_pipeline()` | `actions.run_pipeline_fresh` + `st.cache_data.clear()` | — |
| `maybe_refresh()` | `src.ingestion.refresh.maybe_refresh` + clears caches on `"refreshed"` | — |
| `export_geojson / export_csv / geojson_preview / incident_report` | `actions.*` | — |

Every cached wrapper takes a leading `_sig = queries.db_signature()` argument
(the `alerts.db` mtime) so the cache invalidates automatically on any write.

### `dashboard/theme.py` — design tokens

```
BG        #0a0e15     T0  #e8eaed  (primary text)      CRIT   #ef4444
BG_ELEV   #0f141d     T1  #8b95a5  (secondary)         HIGH   #f59e0b
PANEL     #111823     T2  #5a6472  (muted)             MED    #eab308
PANEL_2   #151d2a     ACCENT #3d7dc8 (single blue)     LOW    #22c55e
BORDER    #1e2733                                       AGENT  #7c5cff
BORDER_2  #2a3644     radius: 9px   fonts: Inter + IBM Plex Mono
```

`SEV_COLOR`, `CLASS_COLOR`, `SEV_RGBA`, `CLASS_RGBA` maps; `sev_chip()`,
`class_dot()` helpers. No gradients, no glow, no glassmorphism.

---

## 3. Backend / engine layer — `src/alerting/` [IMPLEMENTED — reuse as-is]

| Module | Responsibility | Key interface |
|---|---|---|
| `risk_engine.py` | Rule-based scoring → class + severity + context + narrative + factors | `score_row(row) -> RiskResult`; `score_dataframe(df) -> df`; `explain_score(row) -> list[(reason, +pts)]`; `deviation_factor(score) -> (reason, +pts) | None` (additive, opt-in, **not** called by `score_row`); `classify_hazard_type(str)` |
| `alert_store.py` | SQLite persistence + lifecycle | `insert_alerts(rows)`; `get_alerts(severity, status, limit)`; `update_status(alert_id, new_status)`; `counts()`; `clear_all()` |
| `pipeline.py` | Seed the store from the India scores parquet | `run(fresh: bool) -> dict` |

**Lifecycle:** `DETECTED → VALIDATING → ALERTED → ESCALATED → MONITORING →
EXTINGUISHED`. On insert, severity sets the initial status
(CRITICAL/HIGH → `ALERTED`, MEDIUM → `VALIDATING`, else `DETECTED`). Dedup: skips
a row when the same `(lat, lon, acq_date)` already has a non-EXTINGUISHED alert.

### `RiskResult` (`risk_engine.py`)

`score`, `severity`, `status` (`"DETECTED"`), `output_class`,
`land_cover_context`, `hazard_facility_type`, `narrative`, `nearest_city`,
`dist_nearest_city_km`, `near_population`, `factors: list[(reason, +int)]`.

### Risk scoring rule (additive, 0–100)

`+30` anomaly · `+25/15/8` FRP ≥ 30/15/5 MW · `+20/10` persistence ≥ 4/2 ·
`+20/12/6` nearest facility < 1/5/15 km · `+10` predicted class A · `+8` high
FIRMS confidence · `+5` night detection · `+10` within 30 km of a city (from a
30-entry hard-coded `_CITIES` list). Bands: `≥65 CRITICAL / ≥40 HIGH / ≥20
MEDIUM / <20 LOW`. The Investigation view shows exactly which components fired.

### `src/ingestion/refresh.py` [IMPLEMENTED]

`maybe_refresh(max_age_hours=2.0)` — called at startup by `dashboard/data.py` and
by the sidebar "↻ Refresh Data" button (`max_age_hours=0`). Returns a status dict,
**never raises**.

```
_age_hours()  = today − MAX(acq_date) in alerts.db, in hours (inf if no DB/date)
if age < max_age_hours          → {"status": "fresh"}
if not FIRMS_MAP_KEY            → {"status": "no_key"}       ← common local case
if not stage6_model.joblib      → {"status": "no_model"}     ← common local case
if not facilities.parquet       → {"status": "no_facilities"}
else:
  fetch VIIRS_SNPP_NRT + MODIS_NRT for INDIA_BBOX, last min(FIRMS_NRT_DAYS, 5) days
  _engineer(): grid-key persistence count, BallTree facility proximity, temporal cols
  joblib model → predict + predict_proba → max_prob → anomaly_flag (< 0.55)
  write stage6_india_scores.parquet
  pipeline.run(fresh=True)   → reseed alerts.db
  → {"status": "refreshed", "rows": n, "inserted": m}
on any exception → {"status": "error", "error": str(exc)}  (existing data unchanged)
```

`_TRAIN_FEATURES` in `refresh.py` = `[bt_kelvin, frp_mw, persistence_count,
dist_nearest_facility_km, agri_season_flag, day_night_bin, acq_month]` — the same
7 the model was trained on.

---

## 4. Intelligence / service layer — `src/intelligence/` [IMPLEMENTED]

Framework-agnostic. Pure functions, plain return types (`dict` / `list[dict]` /
`DataFrame`). **No Streamlit import anywhere in this package.** Heavy work is
`@lru_cache`-d, keyed on `queries.db_signature()`; the Streamlit layer adds
`@st.cache_data` on top.

### `geo.py`

- Loads `data/geo/india_admin.geojson` (36 dissolved state polygons + 760
  district polygons) via `@lru_cache`.
- `INDIA_BBOX = (6.0, 37.5, 67.5, 97.5)` (lat_min, lat_max, lon_min, lon_max).
- `_EDGE_TOL_DEG = 0.03` — boundary tolerance (polygon simplification + FIRMS
  pixel footprint); a **classification tolerance, not a coordinate clip**.
- `@lru_cache(maxsize=20000) _resolve_cached(lat_r, lon_r)` — exact ray-casting
  point-in-polygon for states (per-feature bbox pre-filter), then a 4-offset
  `±_EDGE_TOL_DEG` second pass (sets `on_edge`, `district=None`), then district
  PIP within the resolved state.
- `resolve(lat, lon) -> {state, district, in_india, zone}`; `state_for_point`,
  `district_for_point`, `place_label(lat, lon)`.
- `REGIONS` dict (e.g. `eastern india` = Odisha / Jharkhand / West Bengal / Bihar),
  `_REGION_ALIASES`, `_STATE_ALIASES` (incl. a `"bangalore": None` guard so a
  city token never resolves to a state), `_OUTSIDE_ZONES` (Sri Lanka, Bangladesh,
  Nepal, Bhutan, Myanmar, Pakistan, China/Tibetan Plateau, Bay of Bengal, Arabian
  Sea).
- `normalise_region`, `states_in_region`, `all_states`, `canonical_state`,
  `resolve_state_filter`, `match_locations(text)`.
- `annotate(df, lat_col, lon_col)` → adds `state / district / in_india / zone`.
- `audit_points(df, ...)` → `{plotted, in_india, outside_india, outside_india_bbox,
  lat_min/max, lon_min/max, outside_zones, sample_in_india, sample_outside}`.

**shapely is a build-time-only dependency** (used by the scratchpad
`build_districts.py` to dissolve districts → states). It is **not** imported at
runtime.

### `queries.py` (READ)

Every list/summary function accepts an optional `filters` dict (same shape as
`state.py`). Loading:

```
db_signature()  = alerts.db mtime (float)   → the universal cache key
_load_alerts_cached(_sig)  @lru_cache(8)
    alert_store.get_alerts(limit=100000) → DataFrame
    geo.annotate(df)  → state / district / in_india / zone
    df["place"]  = "District, State" | "State" | zone
    + output_class_short / output_class_code / hazard_facility_type
_all_alerts()  = the raw frame (India + outside-India)
_alerts()      = _all_alerts()[in_india]   ← the India-only product scope
```

| Function | Returns |
|---|---|
| `list_alerts(filters, limit, sort_by)` | `list[dict]` — India alerts |
| `rank_alerts(by, filters, limit)` | `list[dict]` |
| `get_alert(alert_id)` / `count_alerts(filters)` | `dict | None` / `int` |
| `get_investigation(alert_id)` | assembled `dict` (header / detection / context / why_flagged / classification / risk_assessment / recommended_action / coords) |
| `situation_summary(filters)` | totals, severity + classification counts, `by_status`, `data_window`, `top_states` |
| `compare_regions(a, b, filters)` | side-by-side `{a: {...}, b: {...}}` |
| `analytics_summary(date_from, date_to)` | `{daily[], by_class, by_severity, by_land_cover, by_hazard, totals}` |
| `baseline_comparison(filters)` | normal FRP band (Q1 / median / Q3 over prior days) vs latest day, or **`None`** when < 3 days / < 10 historical points |
| `facilities_with_activity(filters, limit, radius_km)` | `list[dict]` incl. `baseline_quality`, `deviation_level`, `deviation_score` |
| `incidents()` | 30 curated incidents (`stage7_incident_scores.parquet`) |
| `data_date_range()` / `resolve_timeframe(spec)` | data-relative timeframes |
| `outside_india_alerts(limit)` / `geo_audit()` | the opt-in "Regional context" layer + Data-validation report |
| `list_events / get_event / get_event_for_alert` | thermal-event dicts (`asdict(ThermalEvent)`) |
| `get_event_fingerprint / get_event_evidence / get_event_evolution / get_event_trajectory` | the per-event intelligence dicts |
| `find_increasing_risk_events(limit)` | events whose trajectory is `INCREASING` |
| `events_situation()` | `{total_events, high_risk_events, persistent_sources, early_warnings}` |
| `get_facility_fingerprint(facility_id, exclude_event_id=None)` | baseline dict (or `INSUFFICIENT_BASELINE`) |
| `get_event_deviation(event_id)` / `get_alert_deviation(alert_id)` | deviation dict incl. nested `baseline` + `baseline_overlap` |
| `rank_facilities_by_deviation(limit)` / `find_abnormal_facilities(limit, min_level)` | ranked / filtered facility rows |
| `facility_fingerprint_summary()` | `{facilities_with_activity, baseline_available, insufficient_baseline, events_assessed, abnormal_events, by_level}` |
| `db_signature()` / `is_seeded()` / `clear_caches()` | cache plumbing |

`clear_caches()` clears `_load_alerts_cached`, `_events_cached`, `data_date_range`,
`_india_facilities`, `_facility_index`, `_facility_fingerprints_cached`,
`_facility_deviations_cached`, `incidents`, and `geo._resolve_cached`.

**Event / facility caches:**
`_events_cached(_sig)` `@lru_cache(8)` → `clustering.cluster_alerts()` over the
India alert list. `_facility_index()` `@lru_cache(1)` → `(BallTree, facilities_df)`
— the **single** detection↔facility matcher. `_facility_fingerprints_cached(_sig)`
`@lru_cache(4)` → `{facility_id: baseline}` for every facility with ≥ 1 nearby
detection. `_facility_deviations_cached(_sig)` `@lru_cache(4)` → the
highest-deviation event assessment per facility.

### `actions.py`

| Function | Notes |
|---|---|
| `export_geojson(filters)` | `FeatureCollection` of alert Points; properties = `_CSV_COLUMNS` minus lat/lon + `risk_factors` |
| `export_csv(filters)` | fixed `_CSV_COLUMNS` (incl. `district`, `state`, `in_india`) |
| `geojson_preview(filters, n)` | first `n` features |
| `build_incident_report(filters, fmt)` | Markdown / CSV summary; defaults `severity = [CRITICAL, HIGH]` |
| `set_alert_status(alert_id, action)` | **manual UI only — NOT an agent tool.** `acknowledge → MONITORING`, `escalate → ESCALATED`, `resolve → EXTINGUISHED` |
| `run_pipeline_fresh()` | wraps `pipeline.run(fresh=True)` + `queries.clear_caches()` |
| `ensure_seeded()` | seeds the store on first run if `alerts.db` is absent |

### `clustering.py`

```python
@dataclass
class ThermalEvent:      # 29 fields
    event_id: str        # sha256("|".join(sorted(alert_ids)))[:8]
    alert_ids: list[str]
    centroid_lat: float; centroid_lon: float
    start_date: str | None; end_date: str | None; duration_days: int
    observation_count: int
    spatial_extent_km: float               # max pairwise haversine within the group
    peak_frp_mw: float | None; mean_frp_mw: float | None
    max_bt_kelvin: float | None; mean_bt_kelvin: float | None
    night_count: int; day_count: int
    persistence_count: int                  # max persistence_count in the group
    dist_nearest_facility_km: float | None; nearest_facility_type: str | None
    predicted_class: str | None             # most common predicted_label
    model_probability: float | None         # max of max(prob_A, prob_B) in the group
    anomaly_flag: int                       # 1 if any member is anomalous
    risk_score: int                         # max risk_score in the group
    severity: str                           # max severity in the group
    state: str | None; district: str | None; zone: str | None
    output_class: str | None; output_class_short: str | None; output_class_code: str | None

def cluster_alerts(alerts, spatial_km=15.0, temporal_days=3) -> list[ThermalEvent]:
    """Union-find over all alert pairs. Two alerts merge when
       haversine ≤ spatial_km AND |date gap| ≤ temporal_days.
       O(n²) pair scan — fine at ≤ 5k rows (ponytail: BallTree above that).
       Returns events sorted by risk_score descending."""
```

### `fingerprint.py` — event behaviour

```python
def compute_fingerprint(observations: list[dict]) -> dict:
    # keys:
    #   observation_count
    #   persistence, night_activity, frp_intensity,
    #   spatial_stability, industrial_proximity, seasonal_alignment
    #       each ∈ {VERY LOW, LOW, MEDIUM, HIGH, VERY HIGH}  (UNKNOWN when data absent)
    #   behaviour_category   (one of the six below)
    #   night_count, day_count, mean_frp_mw, spatial_extent_km, min_dist_facility_km
```

Six behaviour categories (`_assign_category`, priority order):
1. **Persistent Industrial Signature** — persistence + proximity + stability all HIGH/VERY HIGH
2. **Seasonal Agricultural Signature** — persistence HIGH + FRP LOW + seasonal HIGH
3. **Rapidly Expanding Fire Signature** — persistence HIGH + spatial stability LOW
4. **Recurring Thermal Source** — persistence MEDIUM/HIGH/VERY HIGH
5. **Isolated Thermal Anomaly** — default; also `< 2` observations
6. **Insufficient Evidence** — `0` observations

Agricultural months for the seasonal dimension: `{1, 2, 4, 5, 7, 8, 9, 10, 11}`.

### `evidence.py`

```python
@dataclass
class EvidenceItem:
    category: str      # THERMAL | GEOSPATIAL | BEHAVIOURAL | MODEL | RISK | SYSTEM
    label: str; value: str
    direction: str     # SUPPORTING | LIMITING | NEUTRAL
    explanation: str
    source: str        # FIRMS | facility_db | ML_model | risk_engine | system

def build_evidence(event: ThermalEvent, observations: list[dict]) -> dict:
    # {supporting[], limiting[], neutral[], total_supporting, total_limiting}
    # ALWAYS appends two SYSTEM limiting items:
    #   "Satellite Resolution — VIIRS 375m / MODIS 1km"
    #   "No Ground Confirmation — Not verified"
```

### `evolution.py`

```python
def build_evolution(observations: list[dict]) -> dict:
    # {observation_count, start_date, end_date,
    #  frames:     [{step, timestamp, cumulative_count, current_frp,
    #                risk_score, lat, lon, day_night}],   ← ordered by date
    #  milestones: [{timestamp, label, detail}]}
    # milestone labels:
    #   First Detection            — always
    #   Persistence Detected       — when n >= 2
    #   Peak FRP Observed          — the highest-FRP frame (if not the first)
    #   High-Risk Threshold Crossed — first frame with risk_score >= 60 (after frame 0)
```

### `early_warning.py`

```python
def compute_trajectory(frames: list[dict]) -> dict:
    # derives risk_scores from frames; needs >= 2 or → "INSUFFICIENT DATA"
    # delta = risk_scores[-1] - risk_scores[0]
    # trajectory: delta > 5 → INCREASING; < -5 → DECREASING; else STABLE
    # state:
    #   INCREASING + latest >= 80  → HIGH PRIORITY
    #   INCREASING + latest >= 60  → EARLY WARNING
    #   INCREASING                 → INCREASING
    #   STABLE + latest >= 60      → WATCH
    #   STABLE / DECREASING        → STABLE
    # returns {state, trajectory, delta, risk_history, signals}
```
**Describes an observed trend in existing data. Never predicts the future.**

### `facility_fingerprint.py` — facility baseline + deviation (Session 11)

Pure, deterministic, **no Streamlit / no LLM**. Distinct from `fingerprint.py`
(which fingerprints an *event*); here the subject is a *facility*.

```python
ASSOC_RADIUS_KM = 10.0     # detection ↔ facility association
MIN_OBS = 6                # minimum detections for any baseline
MIN_ACTIVE_DAYS = 2        # ... across this many distinct dates
MIN_STAT_N = 3             # minimum non-null values before a robust stat is reported
OK_OBS = 12                # ≥ this (+ ≥ 3 active days) upgrades LIMITED → OK
DEVIATION_LEVELS  = ("NORMAL", "ELEVATED", "ABNORMAL", "HIGHLY_ABNORMAL")
BEHAVIOR_CLASSES  = ("NORMAL", "ABNORMAL", "INSUFFICIENT_BASELINE")
SIGNAL_WEIGHTS    = {"intensity": 1.0, "brightness": 0.8, "persistence": 1.0,
                     "day_night": 0.7, "seasonal": 0.5}      # configurable

build_facility_baseline(facility, observations) -> dict
    # robust stats via statistics.median / statistics.quantiles(n=4) / MAD:
    #   frp / bt = {median, iqr, mad, min, max, n}   (None if < MIN_STAT_N values)
    #   median_persistence, max_persistence, night_ratio, typical_day_night,
    #   active_months, baseline_start/end, active_days, observation_count
    # gate: n < MIN_OBS or active_days < MIN_ACTIVE_DAYS
    #       → baseline_quality = "INSUFFICIENT_BASELINE", all stats None, notes[]
    #       else "LIMITED" (or "OK" at >= OK_OBS and >= 3 days)

compare_event_to_baseline(event, baseline) -> dict
    # per-signal 0-100 via a saturating curve round(100 * (1 - e^(-z/2.5))):
    #   intensity   = peak_frp_mw  vs baseline.frp  (floor 5 MW)
    #   brightness  = max_bt_kelvin vs baseline.bt   (floor 3 K)
    #   persistence = event.persistence_count vs baseline.median_persistence
    #   day_night   = event majority timing != baseline.typical_day_night → 60 else 0
    #   seasonal    = event month not in baseline.active_months → 50 else (no signal)
    # thermal_deviation_score = weighted mean over AVAILABLE signals (renormalised)
    # level: <20 NORMAL / 20-44 ELEVATED / 45-69 ABNORMAL / >=70 HIGHLY_ABNORMAL
    # behavior_class: NORMAL (NORMAL/ELEVATED) | ABNORMAL (ABNORMAL/HIGHLY_ABNORMAL)
    #                 | INSUFFICIENT_BASELINE
    # evidence[] = detail string of every signal scoring >= 20  (real numbers, no LLM)
    # interpretation: NORMAL → "monitor and keep as baseline"  (never "ignore",
    #                 never "confirmed fire")
```

**Circularity handling:** with a ~5-day window most facilities have one activity
burst, so a strict leave-one-out collapses every baseline. `queries.get_event_deviation`
therefore uses the **full facility profile** and reports
`baseline_overlap.dominated = True` when the scored event's detections are ≥ 60 %
of it. A spike still stands out against the facility's own median even when it is
part of the distribution.

---

## 5. Investigation panels (`dashboard/views/investigation.py`)

Rendered top-to-bottom for a focused `alert_id`:

1. **Event / detection header** — `EVENT #<id> · N FIRMS detections` (or
   `DETECTION <aid>`), output class + location, severity chip, status, model
   class probability, big `RISK n/100`.
2. **Detection** (`_kv`) — FRP, brightness temperature, persistence, date,
   day/night, coordinates, instrument. + event observations / duration / spatial
   extent when `obs > 1`.
3. **Context** — district, state, nearest facility km, facility type, land-cover
   context.
4. **Why this was flagged** — checklist of the signals that *actually* fired
   (anomaly, repeat detections, near facility, industrial land use, elevated FRP,
   night detection, model leans A). False/unknown signals are omitted.
5. **Location** — a small pydeck map (`mapview.build_deck`, zoom 7.2).
6. **Classification** — model classification, raw label, `P(A)` / `P(B)`, anomaly
   flag, the locked framing sentence.
7. **Risk assessment** — the `risk_factors` breakdown; the `+points` sum equals
   the score.
8. *(event only)* **Thermal Behaviour Fingerprint** — 6 dimension rows +
   behaviour category (`data.EVENT_FP`).
9. *(event only)* **Evidence Stack** — supporting / limiting expander
   (`data.EVENT_EV`).
10. *(event only)* **Event Evolution** — milestone timeline + a replay slider
    (`data.EVENT_EVO`); each frame shows observations visible / FRP / risk.
11. *(event only, when not INSUFFICIENT DATA)* **Risk Trajectory** — state,
    Δrisk, risk history, signals (`data.EVENT_TRAJ`).
12. *(event only, when available)* **Facility Thermal Baseline**
    (`_render_facility_deviation`, `data.EVENT_DEV`) — baseline window / quality /
    typical FRP·BT·persistence·timing, a big `n/100 THERMAL DEVIATION` with the
    level, evidence bullets, interpretation, and the caveat *"not part of the
    risk score above, and separate from the model class probability; an abnormal
    thermal event is not a confirmed fire."*
13. **Recommended action** — derived from `(severity, class, anomaly)` — plus the
    manual **Acknowledge / Escalate / Resolve** buttons (with toasts and
    disabled states) and **Show on map →**.

---

## 6. Fire Intelligence Agent — `src/intelligence/agent/` [IMPLEMENTED]

### Flow

```
User query
   │
   ▼
runtime.ask(message, context)      context = {page, filters, focus_alert_id}
   │
   ├─ claude_available()?  (ANTHROPIC_API_KEY set AND import anthropic OK)
   │      └─► claude.ask()  — tool-use loop, ≤ _MAX_TOOL_ROUNDS (4)
   │             any failure → fall through
   │
   └─► _deterministic(message, context)
          deterministic.parse()  → Interpretation {understood, tool, args,
                                     filters, nav, focus_alert_id, intent, note}
          tools.dispatch(tool, args)          ← try/except, never crashes
          response.build(interp, result)      ← try/except, never crashes
   │
   ▼
AgentReply { text, result_cards, ui_action, data, mode, tool, note }
   │
   ▼
dashboard/agent/panel.py  renders answer (_richtext) + result cards;
                          applies ui_action via dashboard/state.py → st.rerun()
```

`runtime.ask` **never raises** — `response.build` is wrapped in try/except too
(added Session 12 after the event intents were found to crash the panel).

### Modules

| Module | Responsibility |
|---|---|
| `tools.py` | `Tool` dataclass, `REGISTRY` (**26 read-only tools**), `dispatch(name, args)`, `anthropic_tool_schemas()`, `READ_ONLY_TOOL_NAMES`. **No state-changing tool is registered.** |
| `deterministic.py` | `Interpretation` dataclass; `parse(message, context)` (alias `interpret`). Refuses state changes (regex on acknowledge/escalate/resolve/dismiss/delete/assign/"close this…"). Covers alert intents (severity, class, state/region, timeframe, ranking, facility proximity, compare, report, export, summary, incidents), event intents (event-id regex `\bevent\s+([0-9a-f]{8})\b` → fingerprint/deviation/evidence/evolution/replay/trajectory/detail; `event_list`; `find_increasing_risk_events`), and facility-fingerprint intents (`abnormal_facilities`, `rank_facility_deviation`, `fp_summary`). |
| `claude.py` | Optional Anthropic tool-use loop. `_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")`, `_MAX_TOOL_ROUNDS = 4`. `available()`; `ask()`; `_finalise()` reuses the deterministic formatter so both paths drive the same UI state. |
| `runtime.py` | `ask()`, `claude_available()`, `_deterministic()`. |
| `response.py` | `AgentReply` dataclass; `build(interp, result, mode)` — per-intent NL formatting + `result_cards` + `ui_action`. Handles every alert / event / facility-fingerprint intent. |

### The 26 tools

**Alert / analytics (13):** `list_alerts`, `rank_alerts`, `get_alert`,
`get_investigation`, `situation_summary`, `compare_regions`,
`facilities_with_activity`, `analytics_summary`, `baseline_comparison`,
`incidents`, `build_incident_report`, `export_geojson`, `export_csv`.

**Thermal event (8):** `list_events`, `get_event`, `get_event_fingerprint`,
`get_event_evidence`, `get_event_evolution`, `get_event_trajectory`,
`find_increasing_risk_events`, `events_situation`.

**Facility thermal fingerprinting (5):** `get_facility_fingerprint`,
`get_event_deviation`, `rank_facilities_by_deviation`, `find_abnormal_facilities`,
`facility_fingerprint_summary`.

### Structures

```python
result_card = {"title", "subtitle", "alert_id", "lat", "lon", "severity",
               "actions": ["open_investigation" | "show_on_map" | "generate_report"]}
ui_action   = {"nav": <page> | None, "filters": {...} | None, "focus_alert_id": <id> | None}
AgentReply  = {"text", "result_cards", "ui_action", "data", "mode", "tool", "note"}
```

### Guarantees

- **Offline-first** — no API key → deterministic parser, fully functional.
- **The LLM never touches state** — fixed read-only registry; typed args.
- **No fabrication** — tools return real data or explicit "not available".
- **Read-only** — a state-change request returns an explanation + an
  `open_investigation` card.
- **Never crashes the panel** — `dispatch` and `response.build` both guarded.

---

## 7. Data layer

| Artefact | Format | Committed? | Used by |
|---|---|---|---|
| `data/processed/stage6_india_scores.parquet` | Parquet (~1.2k scored detections; live-refreshable) | Yes | `pipeline`, `queries` (indirectly, via the store) |
| `data/incidents/stage7_incident_scores.parquet` | Parquet (30 incidents) | Yes | `queries.incidents` |
| `data/processed/facilities.parquet` | Parquet (72,624 rows) | Yes | `queries._facility_index`, Facilities |
| `data/incidents/confirmed_incidents_india.csv` | CSV (30) | Yes | scoring, incidents |
| `data/incidents/match_summary.json` | JSON | Yes | reference (0/30 FIRMS-matched — NRT vs 2019–2023) |
| `data/geo/india_admin.geojson` | GeoJSON (1.2 MB) | Yes | `geo.py` |
| `data/geo/india_outline.json` | JSON (~3 KB) | Yes | `mapview` border |
| `data/alerts.db` | SQLite | **No** (git-ignored, auto-seeded) | `alert_store`, clustering |
| `data/processed/stage6_model.joblib` | joblib | **No** (git-ignored) | `refresh.py` only |
| `data/raw/`, `stage5_*.parquet`, `features_stage4.parquet` | — | **No** (git-ignored) | offline pipeline only |

### Alert record (SQLite `alerts` table, 28 columns)

```
alert_id (PK), lat, lon,
output_class, severity, status, risk_score,
land_cover_context, hazard_facility_type,
frp_mw, bt_kelvin, persistence_count,
dist_nearest_facility_km, nearest_facility_type,
predicted_label, prob_A, prob_B, anomaly_flag,
nearest_city, dist_nearest_city_km, near_population,
acq_date, day_night, narrative,
risk_factors (TEXT — JSON list of [reason, points]),
created_at, updated_at, acknowledged_at
```

**Thermal events, fingerprints, evidence, evolution, trajectories, and facility
baselines are not stored.** They are derived on demand from this table and cached
by DB mtime.

---

## 8. ML / classification layer

- **Training** (`src/model/`) — RandomForest; global training, India geographic
  holdout; 1° spatial-grid split with leakage assertions; VNF-oracle labelling.
  See `modeltrain.md` for every number with `path:line` citations.
- **Serving** — for the committed data, the scores are already in
  `stage6_india_scores.parquet`; the rule-based `risk_engine` derives class /
  severity / context / narrative / factors at seed time. For live FIRMS refresh
  (`FIRMS_MAP_KEY` + `stage6_model.joblib`), `src/ingestion/refresh.py` runs the
  joblib pipeline.
- **Anomaly rule** — `max(prob) < 0.55` → "Industrial Fire / Abnormal Thermal
  Event".
- **Model features (7):** `bt_kelvin`, `frp_mw`, `persistence_count`,
  `dist_nearest_facility_km`, `agri_season_flag`, `day_night_bin`, `acq_month`.
- **Feature importance (committed report):** `dist_nearest_facility_km` 0.29,
  `day_night_bin` 0.25, `bt_kelvin` 0.21, `persistence_count` 0.14, `frp_mw`
  0.10, `agri_season_flag` 0.00, `acq_month` 0.00.

---

## 9. GIS / map layer (`components/mapview.py`)

- **Renderer:** pydeck on the **CARTO dark** basemap (`map_provider="carto"`,
  `map_style="dark"` — no Mapbox token). Default view: lat 22.5, lon 81.5,
  zoom 3.85.
- **Layers (in draw order):**
  1. India outline — `PolygonLayer`, stroked, `filled=False`, thin grey border.
  2. `outside` — dim grey `ScatterplotLayer` (fill `[120,130,145,70]`), opt-in
     "Regional context (outside India)"; true coordinates, not moved.
  3. `alerts` — `ScatterplotLayer`, colour by class (`CLASS_RGBA`) or severity
     (`SEV_RGBA`), radius `6000 + risk_score·260`, `get_position=["lon","lat"]`.
  4. focus ring — white stroked circle when `focus_alert_id` matches.
  5. `facilities` — blue `ScatterplotLayer` (opt-in).
  6. `incidents` — grey `ScatterplotLayer` (opt-in, default on).
- **Thermal Events overlay** — Map Explorer draws a *separate* `pydeck.Deck`
  below the main map: amber `ScatterplotLayer` (radius 8000, `[245,158,11,180]`,
  pickable) at event centroids.
- **Interaction:** hover tooltip (mono, dark card); click a detection → the
  Investigation flow via `state.focus_alert` + `state.request_nav`.
- **Data-validation expander** (Map Explorer) — `queries.geo_audit()`: plotted /
  in-India / outside-India / outside-bbox counts, lat/lon ranges, per-zone
  breakdown, sample rows. Requirement-#10 development check.

---

## 10. State & cache management

- **Single source:** `dashboard/state.py` over `st.session_state`.
- **Filter model** shared across all pages and the agent; the agent's `ui_action`
  applies through the same `state.set_filters` / `request_nav` / `focus_alert`.
- **Cache invalidation:**
  - `@lru_cache` in `queries.py` keyed on `db_signature()` (the `alerts.db`
    mtime) — auto-invalidates on any write.
  - `@st.cache_data(ttl=30/60/120/600)` in `data.py`, each keyed on the same
    signature.
  - `set_status`, `run_pipeline`, and a successful `maybe_refresh` call
    `queries.clear_caches()` + `st.cache_data.clear()`.

---

## 11. Error handling

- **Missing data files:** loaders return `[]` / `None`; pages render honest empty
  states ("No … for this scope", never "No data").
- **`geo` no match:** `resolve()` → `in_india=False`; excluded from product scope
  by `_alerts()`.
- **`baseline_comparison` insufficient history:** returns `None`; Analytics shows
  "insufficient history" — never a fabricated number.
- **Facility baseline too thin:** `INSUFFICIENT_BASELINE`; the Investigation panel
  and Facilities table say so; the deviation score is `None`.
- **Single detection (no cluster):** the event panels are gated on `event_id is
  not None`.
- **Agent — unknown intent:** clarifying message + example prompts.
- **Agent — Claude path failure:** caught in `runtime.ask`; falls back to
  deterministic.
- **Agent — tool or formatter exception:** caught; a plain "couldn't run/format
  that" reply, never a traceback.
- **Live refresh failure:** `maybe_refresh` returns an `error` status; existing
  data is untouched; `app.py` shows a toast, not a crash.

---

## 12. Configuration / environment

From `.env` (see `.env.example`) via `python-dotenv` in
`src/ingestion/config.py` (`load_dotenv()` at import):

| Variable | Purpose | Required? |
|---|---|---|
| `FIRMS_MAP_KEY` | FIRMS ingestion + live NRT refresh at runtime | pipeline + optional runtime refresh |
| `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` | ORNL DAAC / VNF downloads | offline pipeline only |
| `INDIA_BBOX` | `68.0,6.0,97.5,37.0` (lon_min, lat_min, lon_max, lat_max) | has default |
| `FIRMS_NRT_DAYS` | NRT window (FIRMS NRT API caps at 5) | has default |
| `DATA_ROOT` | data directory | defaults to `./data` |
| `ANTHROPIC_API_KEY` | **optional** — enables the Claude agent runtime | **no** — fully functional without |
| `ANTHROPIC_MODEL` | Claude model id | optional (default `"claude-sonnet-4-6"`) |

The dashboard, the deterministic agent, and all event / facility intelligence
need **none** of these to run against the committed data.

> **Security note:** the committed `.env.example` currently holds *real*
> credentials (a FIRMS key and an Earthdata password) instead of placeholders.
> Rotate the Earthdata password and replace both with placeholders; keep real
> values only in a local `.env` (git-ignored) or in Streamlit Cloud Secrets.

---

## 13. Deployment

- **Streamlit Community Cloud** — repo `siddiquezain/zero1`, branch `main`, main
  file `dashboard/app.py`. `runtime.txt` → Python 3.12; `requirements.txt`
  installs the runtime set (no `matplotlib` / `tqdm`).
- Runs with **no secrets** (committed parquets + auto-seeded `alerts.db`).
- `.streamlit/config.toml` → `enableStaticServing = true` (serves
  `dashboard/static/agent-bot.webp`; the agent image is also base64-embedded so
  it renders even without static serving) + dark theme.
- **Netlify cannot host this** — Streamlit is a stateful Python/WebSocket server.

---

## 14. Security considerations

- **No LLM state access.** Fixed read-only tool registry; arguments typed and
  validated before dispatch.
- **No raw query interface.** No SQL / eval / shell exposed to any parser or
  model.
- **Manual-only state changes.** `set_alert_status` is not an agent tool.
- **Local-only data.** SQLite + Parquet on disk; no external DB; no PII beyond
  public facility / city data.
- **Secrets** in `.env` (git-ignored). See the security note in §12 about
  `.env.example`.
- **Outbound calls:** only the optional Claude path makes a network request —
  only the user's query text, the tool schemas, and (truncated) tool results are
  sent, never bulk data.

---

## 15. Testing

`pytest` — **191 tests, all passing.** See `context.md` §12 for the full list.
Regression guards specifically assert: `risk_engine.score_row` output is
unchanged and deterministic for a fixed row; the six lifecycle states and the
`acknowledge/escalate/resolve → status` map are unchanged; every agent tool name
is free of mutation verbs; the offline agent answers deviation queries; the
Facilities / Analytics / Investigation modules import; `panel._richtext` converts
`**bold**` without raising.

---

## 16. Modules to reuse (do NOT rewrite)

| Reuse | For |
|---|---|
| `src/alerting/alert_store.py` | all alert persistence, filtering, lifecycle, counts |
| `src/alerting/risk_engine.py` | classification + severity + context + narrative + factors |
| `src/alerting/pipeline.py` | seeding the alert store |
| `src/intelligence/queries._facility_index` | the ONE detection↔facility BallTree |
| `src/intelligence/queries._events_cached` | all event data access — extend, don't bypass |
| `src/features/engineer._query_nearest_facility` | the BallTree facility-proximity pattern |
| committed Parquet / CSV / GeoJSON under `data/` | all serving data |

New code stays in `src/intelligence/**`, `dashboard/**`, `tests/**`.
