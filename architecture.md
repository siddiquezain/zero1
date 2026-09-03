# SIH26162 — Technical Architecture

> Final technical architecture per the approved plan
> (`.claude/plans/starry-rolling-pnueli.md`) and the existing codebase.
> Companion to `context.md`, `design_brief.md`, `workflow.md`.
>
> Legend: **[IMPLEMENTED]** · **[PLANNED]** · **[OPTIONAL/FUTURE]** ·
> **[NOT SUPPORTED]**.

---

## 1. High-level architecture

```
                        ┌───────────────────────────────┐
   Operator ───────────►│  Manual UI  (Streamlit pages)  │
                        └───────────────┬───────────────┘
                                        │  calls only
                        ┌───────────────▼───────────────┐
   Operator ──"⌘"──────►│  Fire Intelligence Agent panel │
                        └───────────────┬───────────────┘
                                        │
                        ┌───────────────▼───────────────────────────┐
                        │  src/intelligence/  (framework-agnostic)   │
                        │  queries.py · actions.py · geo.py · agent/ │
                        └───────────────┬───────────────────────────┘
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
        data/geo/india_states.geojson  [PLANNED]
```

**Key rule:** the Streamlit layer is presentation only. All data access and logic
go through `src/intelligence/`, which is built on the existing `src/alerting/`
engines. This keeps a future React/FastAPI frontend a frontend-only project.

---

## 2. Frontend architecture (Streamlit)

### Current **[IMPLEMENTED]**

- `dashboard/app.py` — one ~1,760-line page: injected CSS design system,
  session-state init, data loaders (`@st.cache_data`), HTML renderers
  (`_alert_row_html`, `_alert_detail_html`, `_sev_section_head`), GeoJSON export
  (`_alerts_to_geojson`), map builder (`_build_map`), the situation header, the
  control bar, the 2-column alert-feed + map, and 6 `st.tabs`.
- `dashboard/timeline.py` — `get_daily_summary()`, `get_events_for_range()` over
  `data/alerts.db`.
- Auto-seed guard: on first run, if `data/alerts.db` is absent,
  `src.alerting.pipeline.run(fresh=True)` is called.

### Target **[IMPLEMENTED]**

```
dashboard/
  app.py              shell: st.set_page_config → theme, st.navigation, shell
                      header (system id, live clock, "⌘ Fire Intelligence"),
                      agent panel mount, auto-seed guard. Calls
                      data.maybe_refresh() at startup; shows st.toast on
                      refresh or error.
  theme.py            the CSS design-system block (moved verbatim) + page config.
                      Single source; injected once per page.
  state.py            session_state defaults + typed get/set helpers for the
                      shared filter model and navigation/focus:
                        filters: {severity[], status[], output_class[],
                                  state|region, date_from, date_to,
                                  near_facility_type, max_dist_facility_km,
                                  min_risk}
                        focus_alert_id, active_page, agent_history
  data.py             maybe_refresh() wrapper: calls src/ingestion/refresh.py,
                      clears Streamlit cache on successful refresh.
  components/          pure renderers, NO business logic, NO src.alerting import:
    situation_header.py   from the "intel-bar" block
    alert_row.py          from _alert_row_html / _alert_detail_html / _sev_section_head
    map_view.py           from _build_map + legend  (shared: Command Center + Map)
    kpi.py                small stat blocks
    filter_bar.py         the control bar as a reusable component
  pages/              one module per nav section (see §9):
    command_center.py alerts.py investigation.py map_explorer.py
    analytics.py facilities.py reports.py model.py limitations.py
  agent/
    panel.py           command-palette dialog (st.dialog) + chat input +
                       result-card rendering + ui_action application
  shell.py            topbar badge: green "LIVE NRT" when FIRMS_MAP_KEY set +
                      data < 2h old; amber "NRT SNAPSHOT" otherwise.
                      sidebar_refresh_card() renders "FIRMS NRT Feed" card +
                      "↻ Refresh Data" button (shown only when FIRMS_MAP_KEY set);
                      age label: "just now / Xh ago / X days ago".
  timeline.py          unchanged
```

On startup, `app.py` calls `data.maybe_refresh()` which calls
`src/ingestion/refresh.py`. If `FIRMS_MAP_KEY` is set and `MAX(acq_date)` in
`alerts.db` is > 2h ago, fetches fresh VIIRS+MODIS NRT, feature-engineers India
rows (lightweight), runs `stage6_model.joblib`, rewrites
`stage6_india_scores.parquet`, reseeds `alerts.db`. Sidebar shows "FIRMS NRT
Feed" card with "↻ Refresh Data" button when key is set.

- **Navigation:** `st.navigation` with explicit `st.Page` objects (this disables
  Streamlit's implicit `pages/` auto-discovery, so the folder name is safe).
- **Shared state:** all pages read/write filters through `state.py`. An agent
  `ui_action` is applied through the *same* helpers, then `st.rerun()` — so
  agent-driven and manual filtering are indistinguishable downstream.
- **Data loaders** stay `@st.cache_data`-wrapped in the page/service boundary; the
  service layer functions themselves are plain (cache at call site).
- **No `dashboard/*` module imports `src.alerting` directly** — only
  `src.intelligence`. `_alerts_to_geojson` moves into `actions.py`.

---

## 3. Backend / engine architecture

### `src/alerting/` **[IMPLEMENTED — reuse as-is]**

| Module | Responsibility | Key interface |
|---|---|---|
| `risk_engine.py` | Rule-based scoring of a FIRMS row → class + severity + context + narrative | `score_row(row) -> RiskResult`; `score_dataframe(df) -> df`; constants `OUTPUT_CLASS_*`, `classify_hazard_type()` |
| `alert_store.py` | SQLite persistence + lifecycle | `insert_alerts(rows) -> int`; `get_alerts(severity, status, limit) -> list[dict]`; `update_status(alert_id, new_status)`; `counts() -> dict`; `clear_all()`; `LIFECYCLE_STATES` |
| `pipeline.py` | Seed the store from India scores | `run(fresh: bool) -> dict` |

**Lifecycle:** `DETECTED → VALIDATING → ALERTED → ESCALATED → MONITORING →
EXTINGUISHED`. Severity → initial status mapping is in `insert_alerts`
(CRITICAL/HIGH → `ALERTED`, MEDIUM → `VALIDATING`, else `DETECTED`).

### Targeted additive change **[PLANNED]**

`risk_engine.py`: add `factors: list[tuple[str, int]]` to `RiskResult`, populated
where each `s += …` occurs in `score_row`; `score_dataframe` carries a
`risk_factors` column. Purpose: the Investigation "Risk Assessment" section shows
the real components that produced the score. **No behavioural change**; existing
callers and tests keep working; tests updated to cover the new field.

### `src/ingestion|labeling|features|model|scoring/` **[IMPLEMENTED — not touched this round]**

The Stage 1–7 pipeline. Relevant reuse: `src/features/engineer.py`
`_query_nearest_facility()` / BallTree pattern is the reference implementation for
the Facilities proximity join.

---

## 4. Intelligence / service layer — `src/intelligence/` **[PLANNED]**

Framework-agnostic. Pure functions, plain return types (`dict` / `list[dict]` /
`DataFrame`). **No Streamlit import anywhere in this package.**

### `geo.py`

- Bundled `data/geo/india_states.geojson` (public-domain simplified state
  polygons; `.gitignore` updated with `!data/geo/*.geojson`).
- `state_for_point(lat, lon) -> str | None` — pure-Python ray-casting
  point-in-polygon. ~30 polygons, ~705 points → trivially fast. **No new
  dependency, no network.**
- `REGIONS: dict[str, set[str]]` — e.g. `"eastern india" -> {Odisha, Jharkhand,
  West Bengal, Bihar, …}`; `states_in_region(name) -> set[str]`.
- `annotate_states(df) -> df` — adds a `state` column (callers cache the result).

### `queries.py` (READ)

Every function takes an optional `filters` dict (same shape as `state.py`).
Returns plain data.

| Function | Builds on | Returns |
|---|---|---|
| `list_alerts(filters, limit)` | `alert_store.get_alerts` + Python post-filter (date/class/state) | `list[dict]` |
| `get_alert(alert_id)` | `alert_store` | `dict` |
| `get_investigation(alert_id)` | `alert_store` + `risk_engine` factors + `geo` | assembled `dict`: `header / detection / context / why_flagged / classification / risk_assessment / recommended_action` |
| `rank_alerts(by, filters, limit)` | `list_alerts` + sort | `list[dict]` |
| `situation_summary(filters)` | `alert_store.counts` + `list_alerts` | `dict` of severity/class counts, drivers |
| `compare_regions(a, b, filters)` | `list_alerts` + `geo` | side-by-side `dict` |
| `facilities_with_activity(filters)` | `facilities.parquet` + scored parquet, BallTree | `list[dict]` |
| `analytics_summary(date_from, date_to)` | `timeline.get_daily_summary` / `get_events_for_range` | `dict` |
| `baseline_comparison(filters)` | scored data / daily summary | `dict` or `None` (insufficient data — never invented) |
| `incidents()` | `stage7_incident_scores.parquet` + `geo` | `list[dict]` |

**"Why flagged" rule:** each entry is emitted only if the underlying value is
truthy/known (`anomaly_flag`, `persistence_count >= 2`,
`dist_nearest_facility_km < threshold`, land-cover match, `frp_mw` above the
training median, `day_night == "N"`). Missing/false → omitted. Nothing fabricated.

### `actions.py` (read-only outputs + manual-UI helpers)

| Function | Notes |
|---|---|
| `export_geojson(filters)` | reuses `_alerts_to_geojson` (moved here) |
| `export_csv(filters)` | reuses the existing CSV column list |
| `build_incident_report(filters)` | Markdown / CSV summary of filtered critical / industrial-fire alerts |
| `run_pipeline_fresh()` | wraps `src.alerting.pipeline.run(fresh=True)` — used by the manual "Re-run" control |
| `set_alert_status(alert_id, action)` | thin wrapper over `alert_store.update_status`; **used only by the manual UI (Alerts / Investigation). NOT registered as an agent tool this round.** |

---

## 5. Fire Intelligence Agent architecture — `src/intelligence/agent/` **[PLANNED]**

### Flow

```
User query (natural language)
        │
        ▼
runtime.ask(message, context)          context = {current_page, active_filters}
        │
        ├── ANTHROPIC_API_KEY set? ──► claude.py   (Anthropic tool-use loop)   [OPTIONAL/FUTURE]
        │                                   │
        └── else ──────────────────► deterministic.py  (keyword/intent parser) [PLANNED — baseline]
                                            │
                        both emit ► one or more tool calls from tools.py registry
                                            │
                                            ▼
                        tool dispatch → queries.py / actions.py (read-only surface only)
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
| `tools.py` | The **read-only tool registry**: JSON-schema definitions mapping 1:1 to `queries.*` + `actions.export_geojson/export_csv/build_incident_report`. **No state-changing tool is registered.** One registry, consumed by both runtimes. |
| `deterministic.py` | Regex/keyword intent + entity extraction: severity words, class words, state/region names (from `geo.REGIONS`), timeframe ("today", "last N days"), ranking verbs ("highest", "top N"), "near facility". Produces a tool call. Must cover every documented example prompt. **Guaranteed baseline.** |
| `claude.py` | Anthropic SDK tool-use loop, model `claude-sonnet-4-6`, same registry. **Guarded/optional import** — `import anthropic` failure or missing key ⇒ this runtime is simply unavailable, not an error. |
| `runtime.py` | `ask()` — selects runtime, dispatches tool calls, assembles `AgentReply`. `AgentReply = { text, tool_calls, result_cards, ui_action }`. **No `pending_confirmation` / mutation path this round.** |
| `response.py` | Deterministic NL formatting of tool results — used directly in offline mode and as the fallback formatter for the Claude path. |

### Structures

- `result_card = { title, subtitle, actions: [ "open_investigation" |
  "show_on_map" | "generate_report" ], payload }`
- `ui_action = { nav: <page> | None, filters: {…} | None, focus_alert_id: <id> |
  None }`

### Guarantees

- **Offline-first:** with no API key the agent is fully functional via
  `deterministic.py`.
- **The LLM never touches state.** It can only call named read-only tools with
  typed arguments — no SQL, no shell, no arbitrary code, no write path.
- **No fabrication:** tools return real data or an explicit "not available";
  `response.py` surfaces that verbatim.
- **Read-only:** a state-change request returns an explanation + an
  `open_investigation` card; incident state is untouched.

---

## 6. Data layer

| Artefact | Format | Committed? | Used by |
|---|---|---|---|
| `data/processed/stage6_india_scores.parquet` | Parquet (1105 scored India detections; live-refreshable via `src/ingestion/refresh.py`) | Yes | `pipeline`, `queries` |
| `data/incidents/stage7_incident_scores.parquet` | Parquet (30 incidents) | Yes | Incidents / Analytics / `queries` |
| `data/processed/facilities.parquet` | Parquet (72,624; cols `facility_id,lat,lon,facility_type,source,name,country`) | Yes | Facilities / `queries` |
| `data/incidents/confirmed_incidents_india.csv` | CSV (30) | Yes | scoring, case studies |
| `data/geo/india_states.geojson` | GeoJSON (simplified) | Yes **[PLANNED]** | `geo.py` |
| `data/alerts.db` | SQLite | No (git-ignored, auto-seeded) | `alert_store`, `timeline` |
| `data/raw/`, `*.joblib` | — | No (git-ignored) | pipeline only (local) |

### Alert record (SQLite `alerts` table — `alert_store._SCHEMA`)

`alert_id, lat, lon, output_class, severity, status, risk_score,
land_cover_context, hazard_facility_type, frp_mw, bt_kelvin, persistence_count,
dist_nearest_facility_km, nearest_facility_type, predicted_label, prob_A, prob_B,
anomaly_flag, nearest_city, dist_nearest_city_km, near_population, acq_date,
day_night, narrative, created_at, updated_at, acknowledged_at`.

The Investigation view is **assembled from these fields + the risk-factor
breakdown + the resolved state** — it is not a stored entity.

---

## 7. ML / classification layer

- **Training** (`src/model/`) — RandomForest, global data, India held out, spatial
  grid split, VNF-oracle labelling. Not re-run this round. Details in `context.md`
  §7 and `reports/stage6_evaluation.txt`.
- **Serving** — for static committed data, the dashboard does not load the model
  (class + probability + `anomaly_flag` are already in
  `stage6_india_scores.parquet`; the rule-based `risk_engine` derives
  class/severity/context/narrative at load time via `score_dataframe`). For live
  FIRMS refresh (`FIRMS_MAP_KEY` set), `src/ingestion/refresh.py` loads
  `stage6_model.joblib` to score fresh detections.
- **Anomaly rule** — `max(prob) < 0.55` → Industrial Fire / Abnormal Thermal
  Event.

---

## 8. GIS / map layer

- **Renderer:** pydeck `ScatterplotLayer`s on a Carto dark-matter basemap (no
  Mapbox token). Builder = `_build_map` → moved to `components/map_view.py`,
  shared by Command Center and Map.
- **Layers:** scored detections (colour by class or severity, radius by risk),
  confirmed-incident overlay, optional facility layer.
- **Interaction:** hover tooltip (monospace metric block); click a detection →
  set `focus_alert_id` + navigate to Investigation.
- **Export:** GeoJSON `FeatureCollection` of Point features with the full alert
  attribute table (`actions.export_geojson`); CSV with the fixed column list.

---

## 9. Module responsibilities (pages) **[PLANNED]**

| Page module | Responsibility | Service calls |
|---|---|---|
| `command_center.py` | Overview: situation line, live map, top-5 priority alerts, activity strip, quick actions | `situation_summary`, `rank_alerts`, `analytics_summary` |
| `alerts.py` | Full feed + filters + pagination + manual actions + "View Investigation" | `list_alerts`, `set_alert_status` |
| `investigation.py` | Assembled deep view + manual actions | `get_investigation`, `set_alert_status`, `export_*` |
| `map_explorer.py` | Full map + layer/colour controls + click-to-investigate | `list_alerts`, `incidents`, `facilities_with_activity` |
| `analytics.py` | Timeline + calendar + period analysis + playback + classification + baseline | `analytics_summary`, `baseline_comparison` |
| `facilities.py` | Facilities with nearby activity | `facilities_with_activity` |
| `reports.py` | GeoJSON/CSV export + incident report | `export_geojson`, `export_csv`, `build_incident_report` |
| `model.py` | Static pipeline + evaluation content | reads `reports/*` |
| `limitations.py` | Static caveats | — |

---

## 10. State management

- **Single source:** `dashboard/state.py` over `st.session_state`.
- **Filter model** is shared across all pages and the agent.
- **Navigation / focus:** `active_page`, `focus_alert_id` in session state; the
  agent and manual clicks set the same keys.
- **Agent history:** `agent_history` list in session state.
- **Cache invalidation:** `@st.cache_data(ttl=60)` on loaders; `pipeline`
  re-run and status changes call `.clear()` on the relevant loaders (existing
  pattern in `app.py`).
- **Streamlit rerun model:** every `ui_action` is applied through `state.py`
  helpers then `st.rerun()`, guaranteeing manual and agent paths converge.

---

## 11. Error handling

- **Missing data files:** loaders return empty `DataFrame` / `[]`; pages render
  designed empty states (`design_brief.md` §7).
- **`geo` no match:** `state_for_point` returns `None`; queries treat "unknown
  state" as unfiltered for that dimension and note it.
- **`baseline_comparison` insufficient history:** returns `None`; the Analytics
  page shows an honest "insufficient history" note, never a fabricated number.
- **Agent — unknown intent (deterministic):** returns a clarifying message +
  suggested example prompts; no tool call.
- **Agent — Claude path failure (timeout / network / SDK / quota):** caught in
  `runtime.ask`; transparently falls back to `deterministic.py`; the offline note
  is shown.
- **Agent — asked for absent data:** the tool returns "not available";
  `response.py` states it plainly.
- **No raw tracebacks** are shown to the user.

---

## 12. Configuration / environment

From `.env` (see `.env.example`) via `python-dotenv`:

| Variable | Purpose | Required? |
|---|---|---|
| `FIRMS_MAP_KEY` | NASA FIRMS ingestion + dashboard runtime live refresh | pipeline + dashboard runtime (live refresh) |
| `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` | ORNL DAAC / VNF downloads (pipeline only) | pipeline only |
| `INDIA_BBOX` | India bounding box | has default |
| `FIRMS_NRT_DAYS` | NRT window | has default |
| `DATA_ROOT` | data directory | defaults to `./data` |
| `ANTHROPIC_API_KEY` | **Optional** — enables the Claude agent runtime | **no** — app + agent fully work without it |

The dashboard and the deterministic agent need **none** of these to run against
the committed data.

---

## 13. Optional Claude API integration

- Selected at runtime by `runtime.py` **only if** `ANTHROPIC_API_KEY` is set *and*
  `import anthropic` succeeds.
- Same read-only tool registry as the deterministic parser — the LLM cannot do
  anything the deterministic parser cannot.
- `anthropic>=0.40` added to `requirements.txt` as an optional/guarded import
  (its absence must not break `pip install` expectations for the offline path —
  it installs, but is only imported lazily inside `claude.py`).
- Model id: `claude-sonnet-4-6`.
- Any failure ⇒ silent fallback to deterministic + the offline note.

## 14. Deterministic offline fallback

- `deterministic.py` is the **guaranteed baseline** and the default.
- It must map every example prompt in `context.md` §8 / the plan §13 & §17 to the
  correct tool call and arguments (covered by `tests/test_agent_deterministic.py`).
- The entire product — dashboard and agent — must be demoable on a laptop with no
  network and no keys.

---

## 15. Security considerations

- **No LLM state access.** The agent's only capability surface is the fixed
  read-only tool registry; arguments are typed and validated before dispatch.
- **No raw query interface.** No SQL/eval/shell exposed to any parser or model.
- **Manual-only state changes.** `set_alert_status` is not an agent tool this
  round.
- **Local-only data.** SQLite + Parquet on disk; no external DB; no PII beyond
  public facility/city data.
- **Secrets** stay in `.env` (git-ignored); `ANTHROPIC_API_KEY` is never logged or
  surfaced in the UI.
- **Outbound calls:** only the optional Claude path makes a network request, and
  only the user's query text + tool schemas/results are sent — no credentials,
  no bulk data dump.

---

## 16. Testing strategy

- **Existing** (`tests/`): `test_ingestion.py`, `test_features.py`,
  `test_split.py` — must keep passing.
- **New** **[PLANNED]:**
  - `test_intelligence_geo.py` — `state_for_point` for known incident coords
    (e.g. Paradip → Odisha, Dhanbad → Jharkhand); region membership.
  - `test_intelligence_queries.py` — every `filters` key honoured;
    `get_investigation` "why flagged" contains only true signals; no key
    fabricated when the source value is missing.
  - `test_intelligence_actions.py` — `export_geojson` / `export_csv` /
    `build_incident_report` produce valid output for a filtered set.
  - `test_agent_deterministic.py` — each documented example prompt → expected
    (read-only) tool call + args; the tool registry exposes no state-changing
    tool.
- **Manual smoke:** `streamlit run dashboard/app.py` — every section loads; no
  `src.alerting` import remains in `dashboard/`; manual Acknowledge/Escalate/
  Resolve unchanged; agent answers the demo prompt offline and its cards drive
  shared state.

---

## 17. Modules to reuse (do NOT rewrite)

| Reuse | For |
|---|---|
| `src/alerting/alert_store.py` | all alert persistence, filtering, lifecycle, counts |
| `src/alerting/risk_engine.py` | classification + severity + context + narrative (+ new additive `factors`) |
| `src/alerting/pipeline.py` | seeding the alert store |
| `dashboard/timeline.py` | daily aggregation / range queries |
| `src/features/engineer.py` `_query_nearest_facility` | BallTree proximity pattern for Facilities |
| `_build_map`, `_alert_row_html`, `_alert_detail_html`, `_sev_section_head`, `_alerts_to_geojson` (from `app.py`) | move into `components/` / `actions.py`; keep behaviour |
| committed Parquet/CSV under `data/` | all serving data |

New code is limited to: `src/intelligence/**`, `dashboard/{theme,state}.py`,
`dashboard/components/**`, `dashboard/pages/**`, `dashboard/agent/panel.py`,
`data/geo/india_states.geojson`, new tests, and the additive `factors` field in
`risk_engine.py`.
