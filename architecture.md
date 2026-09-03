# SIH26162 — Technical Architecture

> Companion to `context.md`, `design_brief.md`, `workflow.md`.
>
> Legend: **[IMPLEMENTED]** · **[OPTIONAL/FUTURE]** · **[NOT SUPPORTED]**.

---

## 1. High-level architecture

```
                        ┌──────────────────────────────────────┐
   Operator ───────────►│  Manual UI  (Streamlit pages)         │
                        └───────────────┬──────────────────────┘
                                        │  calls only
                        ┌───────────────▼──────────────────────┐
   Operator ──"⌘"──────►│  Fire Intelligence Agent panel        │
                        └───────────────┬──────────────────────┘
                                        │
                        ┌───────────────▼──────────────────────────────────────┐
                        │  src/intelligence/  (framework-agnostic service layer) │
                        │  clustering · fingerprint · evidence · evolution       │
                        │  early_warning · queries · actions · geo · agent/      │
                        └───────────────┬──────────────────────────────────────┘
                                        │  builds on
        ┌───────────────────────────────┼───────────────────────────────┐
        ▼                               ▼                               ▼
 src/alerting/risk_engine     src/alerting/alert_store          dashboard/timeline
   (rule-based scoring)        (SQLite lifecycle store)          (daily aggregation)
        │                               │                               │
        └───────────────┬───────────────┴───────────────┬───────────────┘
                        ▼                               ▼
        data/processed/stage6_india_scores.parquet   data/alerts.db
        data/incidents/stage7_incident_scores.parquet
        data/processed/facilities.parquet
        data/geo/india_admin.geojson  (36 states + 760 districts)
```

**Key rule:** the Streamlit layer is presentation only. All data access and logic
go through `src/intelligence/`, which is built on the existing `src/alerting/`
engines. This keeps a future React/FastAPI frontend a frontend-only project.

**Events are derived, not stored.** Thermal event clustering is computed in-memory
from `alerts.db` on cache miss, cached by DB mtime signature. No new DB table.

---

## 2. Frontend architecture (Streamlit) **[IMPLEMENTED]**

```
dashboard/
  app.py              shell: theme inject, st.navigation, auto-seed guard,
                      data.maybe_refresh() at startup, st.toast on refresh/error
  theme.py            CSS design system — injected once per page
  state.py            session_state defaults + typed get/set helpers:
                        filters: {severity[], status[], output_class[],
                                  state|region, date_from, date_to,
                                  near_facility_type, max_dist_facility_km,
                                  min_risk}
                        focus_alert_id, active_page, agent_history
  data.py             @st.cache_data wrappers (presentation ↔ service boundary):
                        S()           — situation_summary
                        A()           — analytics_summary
                        DATE_RANGE()  — date window
                        ALERTS()      — list_alerts
                        EVENTS(filters, sort_by, limit)
                        EVENT(event_id)
                        EVENT_FOR_ALERT(alert_id)
                        EVENT_FP(event_id)
                        EVENT_EV(event_id)
                        EVENT_EVO(event_id)
                        EVENT_TRAJ(event_id)
                        EVENTS_SIT()
                        maybe_refresh() — wraps src/ingestion/refresh.py,
                                         clears Streamlit cache on success
  shell.py            topbar (LIVE NRT / NRT SNAPSHOT badge, IST clock,
                      VIIRS/MODIS tag, date window, CRITICAL count, team label)
                      sidebar_refresh_card() — FIRMS NRT Feed + ↻ Refresh Data
                      sidebar_agent_card()   — Fire Intelligence Agent launch
  components/
    ui.py             kpi blocks, panel wrappers, section headers, alert rows
    mapview.py        build_deck() — pydeck ScatterplotLayers on Carto dark
    charts.py         plotly activity strip, severity donut, baseline chart
    filterbar.py      severity/status/class/date filter controls
  views/
    command_center.py  5-col alert KPI row + 4-col event KPI row
                       (Active Events, High-Risk Events, Persistent Sources,
                       Early Warnings) + live map + priority alerts + agent panel
    alerts.py          DETECTIONS tab (severity-grouped, paginated,
                       Acknowledge/Escalate/Resolve, View Investigation) +
                       THERMAL EVENTS tab (event cards, EVENT #XXXXXXXX label)
    investigation.py   assembled deep view:
                         event header (EVENT #<id> or DETECTION <aid>)
                         detection panel, context panel, why-flagged
                         fingerprint panel (6-dim ratings, behaviour_category)
                         evidence stack (supporting[], limiting[], neutral[])
                         evolution timeline + replay slider (frame → FRP, risk)
                         risk trajectory (state, trend, delta, signals)
                         recommended action + manual Acknowledge/Escalate/Resolve
    map_explorer.py    full map + layer/colour controls + click-to-investigate +
                       "Thermal Events" checkbox → amber ScatterplotLayer overlay
                       (event centroids, radius 8000, [245,158,11,180])
    analytics.py       timeline + calendar + period analysis + classification
    facilities.py      BallTree join → facility activity table
    reports.py         GeoJSON/CSV export + incident report
    model.py           static pipeline + evaluation + feature importance
    limitations.py     static caveats
  agent/
    panel.py           command-palette dialog (st.dialog) + chat input +
                       IDLE/OPEN/THINKING visual states + result-card rendering +
                       ui_action application via state.py → st.rerun()
  timeline.py          unchanged — get_daily_summary(), get_events_for_range()
```

- **Navigation:** `st.navigation` with explicit `st.Page` objects.
- **Shared state:** all pages read/write filters through `state.py`. Agent
  `ui_action` applies through the same helpers → `st.rerun()` — manual and
  agent-driven filtering are indistinguishable downstream.
- **No `dashboard/*` module imports `src.alerting` directly** — only
  `src.intelligence`.

---

## 3. Backend / engine architecture

### `src/alerting/` **[IMPLEMENTED — reuse as-is]**

| Module | Responsibility | Key interface |
|---|---|---|
| `risk_engine.py` | Rule-based scoring → class + severity + context + narrative + factors | `score_row(row) -> RiskResult`; `score_dataframe(df) -> df`; `explain_score(factors) -> str` |
| `alert_store.py` | SQLite persistence + lifecycle | `insert_alerts(rows)`; `get_alerts(severity, status, limit)`; `update_status(alert_id, new_status)`; `counts()`; `clear_all()` |
| `pipeline.py` | Seed the store from India scores | `run(fresh: bool) -> dict` |

**Lifecycle:** `DETECTED → VALIDATING → ALERTED → ESCALATED → MONITORING →
EXTINGUISHED`. `risk_factors` column stores additive factor breakdown as JSON.

### `src/ingestion/refresh.py` **[IMPLEMENTED]**

`maybe_refresh(max_age_hours=2.0)` — called by `dashboard/data.py` at startup
and by the sidebar "↻ Refresh Data" button (when `FIRMS_MAP_KEY` is set).
Staleness measured by `MAX(acq_date)` in `alerts.db`. Fetches VIIRS_SNPP_NRT
and MODIS_NRT for the India bbox, lightweight feature engineering (BallTree
facility proximity, temporal columns), runs `stage6_model.joblib` inference,
rewrites `stage6_india_scores.parquet`, reseeds `alerts.db`. Falls back
silently on any failure — dashboard always has data.

---

## 4. Intelligence / service layer — `src/intelligence/` **[IMPLEMENTED]**

Framework-agnostic. Pure functions, plain return types (`dict` / `list[dict]`).
**No Streamlit import anywhere in this package.**

### `clustering.py`

```python
@dataclass
class ThermalEvent:
    event_id: str          # SHA-256(sorted alert_ids)[:8]
    alert_ids: list[str]
    centroid_lat: float
    centroid_lon: float
    observation_count: int
    start_date: str        # ISO date
    end_date: str
    duration_days: int
    peak_frp_mw: float
    mean_frp_mw: float
    max_bt_kelvin: float
    mean_bt_kelvin: float
    max_risk_score: float
    mean_risk_score: float
    severity: str          # max severity in event
    output_class: str      # most frequent class
    anomaly_count: int
    night_count: int
    total_count: int
    min_dist_facility_km: float
    nearest_facility_type: str
    state: str
    district: str
    persistence_count: int
    agri_season_count: int
    day_night_breakdown: dict
    confidence_breakdown: dict

def cluster_alerts(alerts: list[dict],
                   spatial_km: float = 15.0,
                   temporal_days: int = 3) -> list[ThermalEvent]:
    """Union-find O(n²) pair scan. Fine at ≤5k rows.
    ponytail: O(n²) scan, BallTree if scale > 5k matters."""
```

Event IDs: `hashlib.sha256("|".join(sorted(alert_ids)).encode()).hexdigest()[:8]`

### `fingerprint.py`

```python
def compute_fingerprint(observations: list[dict]) -> dict:
    """Returns 13 keys:
    persistence, night_activity, frp_intensity,
    spatial_stability, industrial_proximity, seasonal_alignment
    (each: VERY HIGH | HIGH | MEDIUM | LOW | VERY LOW),
    observation_count, duration_days, behaviour_category,
    peak_frp, mean_frp, night_fraction"""
```

Six behaviour categories (priority order):
1. **Persistent Industrial Signature** — high persistence + high proximity
2. **Recurring Thermal Source** — medium persistence + medium proximity
3. **Rapidly Expanding Fire Signature** — high FRP + low stability
4. **Seasonal Agricultural Signature** — high seasonal_alignment + low proximity
5. **Isolated Thermal Anomaly** — default single-event
6. **Insufficient Evidence** — < 2 observations

Agricultural months: `{1, 2, 4, 5, 7, 8, 9, 10, 11}`

### `evidence.py`

```python
@dataclass
class EvidenceItem:
    category: str      # ANOMALY | INTENSITY | PERSISTENCE | FACILITY | ...
    label: str
    value: str
    direction: str     # SUPPORTING | LIMITING | NEUTRAL
    explanation: str
    source: str        # FIRMS | MODEL | RISK ENGINE | SYSTEM

def build_evidence(event: ThermalEvent, observations: list[dict]) -> dict:
    """Returns: supporting[], limiting[], neutral[],
    total_supporting, total_limiting.
    NEUTRAL items → neutral[], never supporting[].
    Always includes FIRMS-resolution and no-ground-truth limiting items."""
```

### `evolution.py`

```python
def build_evolution(observations: list[dict]) -> dict:
    """Returns:
    observation_count, start_date, end_date,
    frames: [{step, timestamp, cumulative_count, current_frp,
              risk_score, lat, lon, day_night}],
    milestones: [{label, timestamp, step, description}]

    Milestone types:
      First Detection    — always present
      Persistence Detected — when cumulative_count >= 2
      Peak FRP Observed  — frame where FRP is highest (if != first)
      High-Risk Threshold Crossed — when risk_score >= 60 (after frame 0)
    """
```

### `early_warning.py`

```python
def compute_trajectory(frames: list[dict]) -> dict:
    """Single argument; derives risk_scores internally from frames.
    Returns:
      state: STABLE | WATCH | INCREASING | EARLY WARNING | HIGH PRIORITY
      trajectory: INCREASING | STABLE | DECREASING
      delta: float (last_risk - first_risk)
      risk_history: list[float]
      signals: list[str]

    Trajectory logic: delta > 5 → INCREASING, < -5 → DECREASING, else STABLE.
    State escalation: HIGH PRIORITY if INCREASING + max_risk >= 70;
    EARLY WARNING if INCREASING; WATCH if STABLE + max >= 50; else STABLE.
    """
```

### `queries.py` (READ)

Every function takes an optional `filters` dict (same shape as `state.py`).
Returns plain data. All event functions are backed by `_events_cached(_sig)`
with `@lru_cache(maxsize=8)` keyed on `db_signature()` (DB mtime → auto-
invalidates when data changes).

| Function | Returns |
|---|---|
| `list_alerts(filters, limit)` | `list[dict]` |
| `get_alert(alert_id)` | `dict` |
| `get_investigation(alert_id)` | assembled `dict` |
| `rank_alerts(by, filters, limit)` | `list[dict]` |
| `situation_summary(filters)` | `dict` — severity/class counts, drivers |
| `compare_regions(a, b, filters)` | side-by-side `dict` |
| `facilities_with_activity(filters)` | `list[dict]` |
| `analytics_summary(date_from, date_to)` | `dict` |
| `baseline_comparison(filters)` | `dict` or `None` |
| `incidents()` | `list[dict]` |
| `list_events(filters, sort_by, limit)` | `list[dict]` — ThermalEvent dicts |
| `get_event(event_id)` | `dict` |
| `get_event_for_alert(alert_id)` | `dict` or `None` |
| `get_event_fingerprint(event_id)` | fingerprint `dict` |
| `get_event_evidence(event_id)` | evidence `dict` |
| `get_event_evolution(event_id)` | evolution `dict` |
| `get_event_trajectory(event_id)` | trajectory `dict` |
| `find_increasing_risk_events(min_delta, limit)` | `list[dict]` |
| `events_situation()` | `{total_events, high_risk_events, persistent_sources, early_warnings}` |

`clear_caches()` clears both `_alerts_cached` and `_events_cached`.

### `actions.py`

| Function | Notes |
|---|---|
| `export_geojson(filters)` | GeoJSON FeatureCollection of alert Points |
| `export_csv(filters)` | CSV with fixed column list |
| `build_incident_report(filters)` | Markdown/CSV summary |
| `run_pipeline_fresh()` | wraps `src.alerting.pipeline.run(fresh=True)` |
| `set_alert_status(alert_id, action)` | manual UI only — NOT an agent tool |

### `geo.py`

- `resolve(lat, lon) -> {state, district, in_india, zone}` — pure-Python
  ray-casting over `data/geo/india_admin.geojson` (1.2 MB; 36 dissolved state
  polygons + 760 district polygons; per-feature bbox pre-filter; 0.03° tolerance).
- `REGIONS: dict[str, set[str]]` — region → state name set.
- `states_in_region(name) -> set[str]`.
- Foreign points → `in_india=False` + coarse `zone` label.
- `_alerts()` in queries.py filters to `in_india=True` (India-only product scope).

---

## 5. Fire Intelligence Agent architecture — `src/intelligence/agent/` **[IMPLEMENTED]**

### Flow

```
User query (natural language)
        │
        ▼
runtime.ask(message, context)     context = {current_page, active_filters, focus_alert_id}
        │
        ├── ANTHROPIC_API_KEY set? ──► claude.py  (Anthropic tool-use loop, optional)
        │
        └── else ──────────────────► deterministic.py  (guaranteed baseline)
                                            │
                        both emit ► one or more tool calls from tools.py registry
                                            │
                                            ▼
                        tool dispatch → queries.py / actions.py (read-only)
                                            │
                                            ▼
                        results → response.py (NL formatting) + result_cards + ui_action
                                            │
                                            ▼
                                AgentReply { text, tool_calls, result_cards, ui_action }
                                            │
                                            ▼
                        dashboard/agent/panel.py renders answer + cards;
                        applies ui_action via dashboard/state.py → st.rerun()
```

### Modules

| Module | Responsibility |
|---|---|
| `tools.py` | Read-only tool registry: alert tools (13) + event tools (8) = 21 total. JSON-schema definitions, 1:1 to `queries.*`. No state-changing tool registered. |
| `deterministic.py` | Regex/intent parser. Alert intents + event intents (event_list, event_detail, event_fingerprint, event_evidence, event_evolution, event_replay, event_trajectory, find_increasing_risk_events). Event ID regex: `\bevent\s+([0-9a-f]{8})\b`. `interpret = parse` alias. |
| `claude.py` | Anthropic SDK tool-use loop, model `claude-sonnet-4-6`. Guarded import — absent or failed key → unavailable, not an error. |
| `runtime.py` | `ask()` — selects runtime, dispatches tool calls, assembles `AgentReply`. |
| `response.py` | Deterministic NL formatting of tool results. Used in offline mode and as fallback formatter for Claude path. |

### Tool registry — event tools (new in Session 10)

| Tool | Maps to |
|---|---|
| `list_events` | `queries.list_events` |
| `get_event` | `queries.get_event` |
| `get_event_fingerprint` | `queries.get_event_fingerprint` |
| `get_event_evidence` | `queries.get_event_evidence` |
| `get_event_evolution` | `queries.get_event_evolution` |
| `get_event_trajectory` | `queries.get_event_trajectory` |
| `find_increasing_risk_events` | `queries.find_increasing_risk_events` |
| `events_situation` | `queries.events_situation` |

### Structures

- `result_card = { title, subtitle, actions: ["open_investigation" | "show_on_map" | "generate_report"], payload }`
- `ui_action = { nav: <page> | None, filters: {…} | None, focus_alert_id: <id> | None }`

### Guarantees

- **Offline-first:** with no API key the agent is fully functional via deterministic parser.
- **The LLM never touches state.** Fixed read-only tool registry only.
- **No fabrication:** tools return real data or explicit "not available".
- **Read-only:** state-change requests return explanation + `open_investigation` card.

---

## 6. Data layer

| Artefact | Format | Committed? | Used by |
|---|---|---|---|
| `data/processed/stage6_india_scores.parquet` | Parquet (1105 scored detections) | Yes | `pipeline`, `queries` |
| `data/incidents/stage7_incident_scores.parquet` | Parquet (30 incidents) | Yes | Analytics / `queries` |
| `data/processed/facilities.parquet` | Parquet (72,624 rows) | Yes | Facilities / `queries` |
| `data/incidents/confirmed_incidents_india.csv` | CSV (30) | Yes | scoring, case studies |
| `data/geo/india_admin.geojson` | GeoJSON (1.2 MB) | Yes | `geo.py` |
| `data/alerts.db` | SQLite | No (git-ignored, auto-seeded) | `alert_store`, `timeline`, clustering |
| `data/raw/`, `*.joblib` | — | No (git-ignored) | pipeline only |

### Alert record (SQLite `alerts` table)

`alert_id, lat, lon, output_class, severity, status, risk_score,
land_cover_context, hazard_facility_type, frp_mw, bt_kelvin, persistence_count,
dist_nearest_facility_km, nearest_facility_type, predicted_label, prob_A, prob_B,
anomaly_flag, nearest_city, dist_nearest_city_km, near_population, acq_date,
day_night, narrative, risk_factors (JSON), created_at, updated_at, acknowledged_at`

**Thermal events are not stored.** They are derived on demand from the alerts
table via `cluster_alerts()`, cached by DB mtime.

---

## 7. Thermal Event data model

```python
ThermalEvent                    # derived in-memory from alerts
  event_id: str                 # SHA-256(sorted alert_ids)[:8 hex]
  alert_ids: list[str]
  centroid_lat/lon: float
  observation_count: int
  start_date/end_date: str      # ISO
  duration_days: int
  peak_frp_mw/mean_frp_mw: float
  max_bt_kelvin/mean_bt_kelvin: float
  max_risk_score/mean_risk_score: float
  severity: str                 # max in event
  output_class: str             # most frequent
  anomaly_count/night_count/total_count: int
  min_dist_facility_km: float
  nearest_facility_type: str
  state/district: str
  persistence_count: int
  agri_season_count: int
  day_night_breakdown/confidence_breakdown: dict

Fingerprint (dict, 13 keys)     # per event, from compute_fingerprint()
  persistence/night_activity/frp_intensity/
  spatial_stability/industrial_proximity/
  seasonal_alignment: str       # VERY HIGH | HIGH | MEDIUM | LOW | VERY LOW
  behaviour_category: str       # one of 6 categories
  observation_count/duration_days: int
  peak_frp/mean_frp: float
  night_fraction: float

EvidenceItem                    # per item in evidence stack
  category: str
  label/value/explanation/source: str
  direction: str                # SUPPORTING | LIMITING | NEUTRAL

Evolution (dict)                # from build_evolution()
  observation_count: int
  start_date/end_date: str
  frames: list[dict]            # ordered: step, timestamp, cumulative_count,
                                #          current_frp, risk_score, lat, lon, day_night
  milestones: list[dict]        # label, timestamp, step, description

Trajectory (dict)               # from compute_trajectory(frames)
  state: str                    # STABLE|WATCH|INCREASING|EARLY WARNING|HIGH PRIORITY
  trajectory: str               # INCREASING|STABLE|DECREASING
  delta: float                  # last_risk - first_risk
  risk_history: list[float]
  signals: list[str]
```

---

## 8. ML / classification layer

- **Training** (`src/model/`) — RandomForest, global data, India held out, spatial
  grid split, VNF-oracle labelling.
- **Serving** — for static committed data, scores are already in
  `stage6_india_scores.parquet`; the rule-based `risk_engine` derives
  class/severity/context/narrative at load time. For live FIRMS refresh
  (`FIRMS_MAP_KEY` set), `src/ingestion/refresh.py` loads `stage6_model.joblib`.
- **Anomaly rule** — `max(prob) < 0.55` → Industrial Fire / Abnormal Thermal Event.
- **Features:** `bt_kelvin`, `frp_mw`, `persistence_count`,
  `dist_nearest_facility_km`, `agri_season_flag`, `day_night_bin`, `acq_month`.

---

## 9. GIS / map layer

- **Renderer:** pydeck `ScatterplotLayer`s on Carto dark-matter basemap
  (no Mapbox token). Builder = `mapview.build_deck()`.
- **Layers:**
  - Detection layer — colour by class or severity, radius by risk.
  - Confirmed-incident overlay.
  - Optional facility layer.
  - "Thermal Events" overlay — amber `ScatterplotLayer`, radius 8000,
    fill `[245, 158, 11, 180]`, pickable, tooltip `{label}\nRisk: {risk_score}`.
    Rendered as separate `pydeck.Deck` below the main map when checked.
- **Interaction:** hover tooltip; click detection → `focus_alert_id` + Investigation.
- **Outside-India detections** — kept with true lat/lon; shown as dim opt-in
  "Regional context" layer + counted in Data Validation expander.

---

## 10. State management

- **Single source:** `dashboard/state.py` over `st.session_state`.
- **Filter model** shared across all pages and the agent.
- **Navigation / focus:** `active_page`, `focus_alert_id` in session state.
- **Agent history:** `agent_history` list in session state.
- **Cache invalidation:**
  - `@st.cache_data(ttl=30)` on event wrappers (short TTL — events recompute fast).
  - `@st.cache_data(ttl=60)` on alert loaders.
  - `pipeline` re-run and status changes call `.clear()` on relevant loaders.
  - `queries.clear_caches()` clears both `_alerts_cached` and `_events_cached`.
- **Event cache key:** `db_signature()` — `alerts.db` mtime as float. Cache
  auto-invalidates on any write (refresh, status change, pipeline re-run).

---

## 11. Error handling

- **Missing data files:** loaders return empty `[]`; pages render empty states.
- **`geo` no match:** `resolve()` returns `in_india=False`; excluded from product
  scope by `_alerts()` filter.
- **`baseline_comparison` insufficient history:** returns `None`; Analytics shows
  honest "insufficient history" — never a fabricated number.
- **Single detection (no cluster):** Investigation event panels are gated on
  `event_id is not None`; isolated detections show existing panels only.
- **Agent — unknown intent:** returns clarifying message + example prompts.
- **Agent — Claude path failure:** caught in `runtime.ask`; falls back to
  deterministic; offline note shown.
- **Agent — absent data:** tool returns "not available"; `response.py` states
  it plainly.
- **No raw tracebacks** shown to the user.

---

## 12. Configuration / environment

From `.env` (see `.env.example`) via `python-dotenv`:

| Variable | Purpose | Required? |
|---|---|---|
| `FIRMS_MAP_KEY` | NASA FIRMS ingestion + live NRT refresh at runtime | pipeline + optional runtime refresh |
| `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` | ORNL DAAC / VNF downloads | pipeline only |
| `INDIA_BBOX` | India bounding box | has default |
| `FIRMS_NRT_DAYS` | NRT window (max 5, FIRMS API cap) | has default |
| `DATA_ROOT` | data directory | defaults to `./data` |
| `ANTHROPIC_API_KEY` | **Optional** — enables Claude agent runtime | **no** — fully functional without |

The dashboard, deterministic agent, and all event intelligence need **none** of
these to run against the committed data.

---

## 13. Optional Claude API integration

- Selected by `runtime.py` only if `ANTHROPIC_API_KEY` is set and
  `import anthropic` succeeds.
- Same read-only tool registry as the deterministic parser (21 tools, no mutations).
- `anthropic>=0.40` in `requirements.txt` — optional/guarded import.
- Model id: `claude-sonnet-4-6`.
- Any failure → silent fallback to deterministic + offline note.

---

## 14. Deterministic offline baseline

- `deterministic.py` is the **guaranteed baseline** — always selected when no
  Claude key is present.
- Covers: alert intents (severity, class, state/region, timeframe, ranking,
  facility proximity) + event intents (list, detail, fingerprint, evidence,
  evolution, replay, trajectory, increasing-risk search).
- Event ID detected by regex: `\bevent\s+([0-9a-f]{8})\b`.
- `interpret = parse` alias — tests and external callers use either name.
- Covered by `tests/test_agent_deterministic.py` and `tests/test_agent_events.py`.

---

## 15. Security considerations

- **No LLM state access.** Fixed read-only tool registry; arguments typed and
  validated before dispatch.
- **No raw query interface.** No SQL/eval/shell exposed to any parser or model.
- **Manual-only state changes.** `set_alert_status` is not an agent tool.
- **Local-only data.** SQLite + Parquet on disk; no external DB; no PII beyond
  public facility/city data.
- **Secrets** in `.env` (git-ignored); never logged or surfaced in the UI.
- **Outbound calls:** only the optional Claude path makes a network request — only
  the user query text + tool schemas/results are sent, never bulk data.

---

## 16. Testing

```
tests/
  # Original pipeline tests
  test_ingestion.py
  test_features.py
  test_split.py

  # Intelligence layer
  test_intelligence_geo.py       (geo resolve + known coords + audit)
  test_intelligence_queries.py   (filters, India scope, label consistency)
  test_intelligence_actions.py   (export GeoJSON/CSV/report)
  test_agent_deterministic.py    (every documented example prompt → correct tool call)

  # Thermal Event Intelligence (Session 10)
  test_clustering.py      (11 tests — cluster_alerts, ThermalEvent, event IDs)
  test_fingerprint.py     (9 tests  — event-behaviour dimensions, categories)
  test_evidence.py        (7 tests  — direction routing, system items, no fabrication)
  test_evolution.py       (9 tests  — frames, milestones, edge cases)
  test_early_warning.py   (9 tests  — state transitions, trajectory, signals)
  test_events.py          (8 tests  — query functions, LRU cache invalidation)
  test_agent_events.py    (10 tests — event intents, deterministic parser)

  # Facility Thermal Fingerprinting (Session 11)
  test_facility_fingerprint.py (25 tests — baseline gate, NORMAL/ELEVATED/
                                HIGHLY_ABNORMAL, missing FRP/BT/facility, day-night
                                & persistence deviation, determinism, no fabrication,
                                risk-engine + lifecycle + agent regression guards)

Total: 186 tests, all passing.
```

### Facility Thermal Fingerprinting (Session 11, additive)

```
src/intelligence/facility_fingerprint.py     (NEW — pure, deterministic, no Streamlit/LLM)
  build_facility_baseline(facility, observations) -> baseline dict
      robust stats (statistics.median / quantiles / MAD) for FRP, brightness
      temperature, persistence, day-night ratio, active months.
      gate: >=6 obs across >=2 days  ->  baseline_quality LIMITED / OK
      else                            ->  INSUFFICIENT_BASELINE (fields stay None)
  compare_event_to_baseline(event, baseline) -> deviation dict
      per-signal 0-100 (intensity, brightness, persistence, day_night, seasonal),
      weighted by SIGNAL_WEIGHTS  ->  thermal_deviation_score / _level / behavior_class
      + deterministic evidence[] strings (real numbers, no LLM)

queries.py  (extended, not rewritten)
  _facility_index()                  the ONE detection<->facility BallTree
  get_facility_fingerprint / get_event_deviation / get_alert_deviation
  rank_facilities_by_deviation / find_abnormal_facilities
  facility_fingerprint_summary
  facilities_with_activity rows  +=  baseline_quality / deviation_level / deviation_score

risk_engine.deviation_factor(score)  additive helper — NOT called by score_row.
                                     risk_score / severity / thresholds unchanged.

Three distinct scores, never merged:
  model class probability   RandomForest (prob_A / prob_B_candidate)
  risk_score                risk_engine additive rule (operational priority)
  thermal_deviation_score   facility_fingerprint (baseline-relative behaviour)

Data flow:
  FIRMS -> alert_store -> queries._alerts()
        -> clustering.cluster_alerts()  -> ThermalEvent
        -> _facility_index() nearest facility (centroid)
        -> build_facility_baseline(facility, detections within 10 km)
        -> compare_event_to_baseline(event, baseline)  -> deviation
        -> Investigation panel / Facilities table / Analytics section / agent tools

UI (additive only): investigation._render_facility_deviation, facilities table
+ focus block, analytics "Facility thermal baselines", model + limitations notes.
```

**Manual smoke:** `streamlit run dashboard/app.py` — every section loads; event
KPIs on Command Center; DETECTIONS/THERMAL EVENTS tabs on Alerts; Investigation
shows fingerprint + evidence + evolution slider + trajectory; Map Explorer event
checkbox works; Agent answers event queries offline.

---

## 17. Modules to reuse (do NOT rewrite)

| Reuse | For |
|---|---|
| `src/alerting/alert_store.py` | all alert persistence, filtering, lifecycle, counts |
| `src/alerting/risk_engine.py` | classification + severity + context + narrative + factors |
| `src/alerting/pipeline.py` | seeding the alert store |
| `dashboard/timeline.py` | daily aggregation / range queries |
| `src/intelligence/clustering.py` | event computation — extend, don't rewrite |
| `src/intelligence/queries._events_cached` | all event data access — extend, don't bypass |
| committed Parquet/CSV under `data/` | all serving data |

New code stays in: `src/intelligence/**`, `dashboard/**`, `tests/**`.
