# SIH26162 — Design Brief (Product + UI/UX Blueprint)

> How the application looks, feels, and behaves — as built. Companion to
> `context.md`, `architecture.md`, `workflow.md`, `modeltrain.md`.
> Reflects commit `ae61893` (Session 12).
>
> This is a blueprint for consistency, not a licence to add features. Preserve
> existing capability; keep the visual language fixed.

---

## 1. Product identity

**India Fire Intelligence** — a geospatial operational-intelligence tool that
turns the raw NASA FIRMS thermal feed over India into a prioritised, explained
picture: *what* thermal activity is happening, *how serious*, *where*, *why it
matters*, *how it compares to what's normal for that site*, and *what to do next*.

Two ways to use the same system: a conventional operations dashboard, and an
optional natural-language **Fire Intelligence Agent** (read-only).

It must read as a **serious monitoring / emergency-operations platform** —
credible to a technical evaluator or a disaster-management analyst — not a generic
AI dashboard or a student project.

---

## 2. Design philosophy

- **Clarity over decoration.** Every element earns its place. If it doesn't help
  the operator decide something, it's removed.
- **Hierarchy first.** The most important information dominates each screen. A
  judge understands the situation in ~10 seconds on the Command Center.
- **Operational, not promotional.** No hero sections, no marketing language, no
  "AI magic". Dense, precise, calm.
- **Explain, don't assert.** Where the system flags something, it shows the real
  signals behind it. It never fabricates confidence or evidence — it shows
  "not available" instead.
- **Three scores, kept distinct.** Model class probability, risk score, and
  thermal-deviation score are never blurred into one number or one colour.
- **Preserve capability.** Reorganising the UI never costs the operator a
  feature.
- **Reuse the current visual language** (defined in `dashboard/theme.py`) — do
  not rebuild it.

---

## 3. Visual language (from `dashboard/theme.py`)

### Type

- **UI text:** `Inter` (system-ui fallback).
- **Numbers, codes, coordinates, timestamps, IDs:** `IBM Plex Mono`. Numeric
  values are monospaced and right-aligned.
- **Section labels:** ~10.5px, uppercase, letter-spaced (`.12em`), muted — quiet
  markers, not headings.
- Page header 18px/700; page subtitle 12px/`--t1`.

### Surfaces & structure

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0a0e15` | app background (flat, dark) |
| `--bg-elev` | `#0f141d` | sidebar |
| `--panel` | `#111823` | cards / panels |
| `--panel2` | `#151d2a` | inputs, nested panels, agent bubbles |
| `--bd` | `#1e2733` | hairline borders / dividers |
| `--bd2` | `#2a3644` | stronger borders, chips |
| radius | **9px** | panels, buttons, inputs (`--r`) |

Content sits on the background with hairline separation. No floating cards, no
drop shadows, no glassmorphism.

### Colour — semantic only

The interface is greyscale (`--t0 #e8eaed` / `--t1 #8b95a5` / `--t2 #5a6472`).
Colour is reserved for meaning:

| Meaning | Token | Value |
|---|---|---|
| CRITICAL | `--crit` | `#ef4444` — scarce; if everything is red, nothing is |
| HIGH | `--high` | `#f59e0b` |
| MEDIUM | `--med` | `#eab308` |
| LOW | `--low` | `#22c55e` |
| System accent (selected / active / links / the single non-severity highlight) | `--accent` | `#3d7dc8` |
| Agent purple (kept minimal — the agent's collapsed card and one indicator) | `--agent` | `#7c5cff` |

**Classification colours** (map + legend): Industrial Fire = `#ef4444`,
Persistent Source = `#f59e0b`, Natural Fire = `#22c55e`, Confirmed Incident =
`#9aa4b2`.

**Facility-deviation colours** (Investigation panel only): HIGHLY_ABNORMAL =
`--crit`, ABNORMAL = `#f97316`, ELEVATED = `--med`, NORMAL = `--low`,
INSUFFICIENT_BASELINE / NO_FACILITY = `--t2`.

The subject is fire — the UI still must **not** read as orange/red overall.

### Motion

Subtle, purposeful: 120–250 ms micro-transitions on hover, selection,
expand/collapse. The topbar data-recency badge has two states — green **LIVE
NRT** (`FIRMS_MAP_KEY` set and data < 2h old) and amber **NRT SNAPSHOT**
(otherwise). The agent robot has an idle state (static, subtle hover scale) and a
`thinking` state (bob + pulsing ring) while a query runs; it returns to static
when the reply lands. No other animated indicators, no animated backgrounds.

### AI-slop checklist — avoid

Unnecessary gradients · purple/blue "AI" gradients · excessive rounded cards ·
glow / neon · glassmorphism · giant meaningless statistics · a decorative icon
before every label · badge soup · constant pulsing/spinning · animated
backgrounds · huge empty hero areas · everything centred · everything floating ·
a generic 4-KPI-card grid with no context.

---

## 4. Global information hierarchy

Every screen answers, in priority order:

1. **What is happening?** — current thermal activity / this alert / this event.
2. **How serious?** — severity, risk score.
3. **Where?** — map, location, state.
4. **Why does it matter?** — evidence, context, classification, fingerprint.
5. **How does it compare?** — event trajectory, facility baseline, FRP baseline.
6. **What next?** — recommended action, navigation to act.

Statistics are integrated into this hierarchy, not dumped as card rows. A large
number appears only when it deserves attention, with supporting context
(e.g. *"Peak FRP 11.1 MW vs facility baseline median 3.21 MW (3.5× the
baseline)"*) — and only when the data actually exists.

---

## 5. Navigation

A persistent left sidebar (`st.navigation`), ordered along the operator workflow
`DETECT → CLASSIFY → CLUSTER → FINGERPRINT → EXPLAIN → COMPARE → ACT`:

```
Command Center     dashboard        overview
Alerts             notifications    the full prioritised feed + thermal events
Investigation      frame_inspect    deep view of one alert / event
Map Explorer       map              where the anomalies are, all layers
Analytics          insights         activity, baseline, facility baselines
Facilities         factory          activity around known industrial sites
Reports / GIS      description      export + incident report
Model              account_tree     how the system actually works
```

(The **Limitations** page module still exists on disk but was removed from the
sidebar in Session 12. To restore: re-add one line to `_PAGES` in
`dashboard/app.py`.)

- Active / hover states; the active item gets a red inset bar (`--crit`).
- The shell carries: brand block (`SIH · 26162 · India Fire Intelligence`), the
  IST clock + LIVE NRT / NRT SNAPSHOT badge, a `FIRMS NRT Feed` card with a
  `↻ Refresh Data` button (only when `FIRMS_MAP_KEY` is set), a
  `⌘ Ask Agent` primary button, and the honest-framing footnote.
- Global filters (severity / status / classification / state / window) live in
  `dashboard/state.py` and persist across sections. A filter set by the agent
  looks identical to one set by hand.
- No fake pages. Every nav item maps to real functionality.

---

## 6. Screens

For each: purpose · what the user sees · primary/secondary actions · what's
prioritised · how to move on.

### 6.1 Command Center

- **Purpose:** the operational picture in ~10 seconds.
- **Sees:** a 5-card KPI row (Active Alerts, Critical, High, Medium, Natural
  Fire — each with a "▲/▼ N% vs 4-day avg" trend); a 4-card event KPI row
  (Thermal Events, High-Risk Events, Persistent Sources, Early Warnings); the
  live India detection map coloured by class with a legend; the top ~4 priority
  alerts as compact cards; three small panels (By Classification donut, By
  Severity donut, Fire Activity Timeline stacked-bars); a Recent Detections
  table; a Quick Actions block (Generate report, Open full map, Export GIS,
  Re-run pipeline) with an FRP-vs-baseline mini panel; and the docked Fire
  Intelligence Agent panel on the right (`st.columns([2.8, 1])`).
- **Primary:** open a priority-alert investigation; "View all alerts →".
- **Not here:** the full alert feed; dense tables; historical deep-dives.
- **Move on:** priority-alert card → Investigation; quick actions → the relevant
  page; agent result card → Investigation / Map / Reports.

### 6.2 Alerts

- **Purpose:** the complete, filterable, prioritised feed + triage.
- **Sees:** `st.tabs(["DETECTIONS", "THERMAL EVENTS"])`.
  - **DETECTIONS:** the shared filter toolbar; alerts grouped by severity with a
    count header per group; paginated (12/page); each row shows classification ·
    severity chip · location + coordinates · risk · FRP · persistence · date; a
    `View investigation →` button; an expander with the narrative and the manual
    **Acknowledge / Escalate / Resolve** buttons (toasts + disabled states).
  - **THERMAL EVENTS:** event cards — `EVENT #<id> · N detections`, output class +
    location, a large mono risk number, left-border severity colour, an
    `Investigate →` button that focuses the event's first alert.
- **Move on:** any row / card → Investigation; filters propagate to Map and
  Analytics.

### 6.3 Investigation

- **Purpose:** where an operator understands *why* an alert matters, *how it is
  behaving*, *how it compares to what's normal for that site*, and *what to do*.
  Feels like an intelligence briefing assembled from real fields only.
- **Sees (top to bottom):**
  1. **Event / detection header** — `EVENT #<id> · N FIRMS detections`, output
     class + location, severity chip, status, model class probability, big
     `RISK n/100`.
  2. **Detection** — FRP, brightness temperature, persistence, date, day/night,
     coordinates, instrument (VIIRS 375 m / MODIS 1 km); event observations /
     duration / spatial extent when multi-detection.
  3. **Context** — district, state, nearest facility km, facility type,
     land-cover context.
  4. **Why this was flagged** — a checklist of the signals that *actually* fired.
     False/unknown signals are omitted — never shown as unchecked filler.
  5. **Location** — a small map centred on the detection.
  6. **Classification** — model classification, raw label, `P(A)` / `P(B)`,
     anomaly flag, and the locked framing sentence.
  7. **Risk assessment** — the `risk_factors` breakdown; the `+points` sum equals
     the shown score.
  8. **Thermal Behaviour Fingerprint** *(event)* — 6 dimension rows + a behaviour
     category, with "Behavioural assessment only — not ground truth."
  9. **Evidence Stack** *(event)* — a supporting / limiting expander; always
     includes the two system limiting items (satellite resolution; no ground
     confirmation).
  10. **Event Evolution** *(event)* — milestone timeline + a replay slider
      (observations visible / FRP at frame / risk at frame).
  11. **Risk Trajectory** *(event)* — STATE (STABLE … HIGH PRIORITY), Δrisk, risk
      history, signals, with "reflects observed data only — does not predict."
  12. **Facility Thermal Baseline** *(event, when available)* — the facility's own
      profile (baseline window / quality / typical FRP · BT · persistence ·
      timing), a big `n/100 THERMAL DEVIATION` in the deviation colour with the
      level, deterministic evidence bullets, an interpretation line, and the
      caveat: *"Behavioural deviation from the facility's own baseline — not part
      of the risk score above, and separate from the model class probability. An
      abnormal thermal event is not a confirmed fire."* If the facility has too
      little history: an honest INSUFFICIENT_BASELINE note.
  13. **Recommended action** — one operational recommendation from
      `(severity, class, anomaly)` — plus the manual **Acknowledge / Escalate /
      Resolve** buttons and **Show on map →**.
- **Prioritised:** the "why", the comparisons (trajectory + baseline), the
  recommended action.

### 6.4 Map Explorer

- **Purpose:** answer "*where* are the thermal anomalies?" — a professional
  geospatial view.
- **Sees:** the filter toolbar; a Layers side panel (colour by class / severity;
  Confirmed incidents; Industrial facilities; **Regional context (outside
  India)**; **Thermal Events**); a full-width pydeck map on the CARTO dark
  basemap (so Pakistan / Nepal / Bhutan / Bangladesh / Myanmar labels stay
  visible) with a thin India outline; a legend; a **Data validation** expander
  (points plotted / inside India / outside India / outside bbox, lat-lon ranges,
  per-zone breakdown, sample rows); a "Top detections in view" list.
- **Interaction:** hover tooltip (mono, dark card); click a detection →
  Investigation.
- **Outside-India detections** are plotted at their *true* coordinates, dimmed,
  explicitly labelled — never moved into India, never dropped.

### 6.5 Analytics

- **Purpose:** temporal and categorical analysis — how today compares, where
  activity concentrates.
- **Sees:** Fire activity by date (stacked bars by severity + totals); a totals
  grid (detections, critical, avg / max FRP); **Baseline comparison** — the
  normal FRP band (Q1–Q3 over prior days) vs the latest day with the % delta,
  shown only when the data supports it (otherwise an honest "insufficient
  history" panel that explains the ~5-day NRT window); **Facility thermal
  baselines** — a 4-metric summary (facilities with activity / baseline available
  / insufficient baseline / abnormal events) + a ranked table of the
  highest-deviation facilities; Classification analysis (class donut, severity
  donut, land-cover hbar); a "Detections by nearby facility type" table.
- **Move on:** the window selector carries into Map and Alerts as a date filter.

### 6.6 Facilities

- **Purpose:** shift the question from "where are hotspots" to "*what is happening
  around known industrial infrastructure, and is it normal for that site*" — a
  differentiator for SIH26162.
- **Sees:** the filter toolbar; a table of Indian facilities with nearby
  detections (fixed 10 km radius) — Facility · Type · State · Nearby · Repeat ·
  Max risk · **Baseline** (quality) · **Deviation** (score / level) · Nearest
  (km) — with a one-line explainer that baseline and deviation are separate from
  the risk score; a "Focus a facility" selector → 4 metrics + a **Thermal
  baseline** block (typical peak FRP / brightness / persistence / timing, the
  baseline window and quality) or an honest INSUFFICIENT_BASELINE empty state;
  a "Show this area on the map →" button.

### 6.7 Reports / GIS

- **Purpose:** get the current picture out.
- **Sees:** the filter toolbar; filter-aware **GeoJSON** and **CSV** downloads
  (each alert a Point feature with the full attribute table incl. `district`,
  `state`, `in_india`, `risk_factors`); an **Incident report (Markdown)**
  download; a GeoJSON preview (first 3 features) and an incident-report markdown
  preview.
- All exports respect the active filters. The agent's "Generate Report" produces
  the same artefact.

### 6.8 Model

- **Purpose:** technical credibility — show the real pipeline, not claims.
- **Sees:** the pipeline as labelled chips (`NASA FIRMS → Preprocessing →
  Detection → Classification → Persistence analysis → Industrial context → Risk
  engine → Alert / Investigation`); the data sources actually used; the
  RandomForest description (300 trees, `class_weight="balanced"`, median
  imputation; trained on 270,238 non-India rows; predicts A vs B_candidate;
  anomaly = `max(prob) < 0.55`); the three-way evaluation table (random baseline
  0.9725, spatial holdout 0.9806, India holdout — no labels); feature importance;
  the risk-engine explainer (the exact `+points` rule and bands); and the
  **"Three separate scores — not one number"** note (model probability vs
  risk_score vs thermal deviation).
- **Prioritised:** honesty. No models, datasets, or methods that aren't
  implemented.

### 6.9 Limitations (module retained, unlinked)

Honest caveat panels: no confirmed-fire claim; FIRMS spatial resolution;
satellite revisit & cloud; NRT-only (~5 days); proxy training labels; thin
industrial class; land cover is a heuristic; the agent is read-only; **facility
baselines need history** (most facilities are INSUFFICIENT_BASELINE with a 5-day
window; the deviation score is a separate behavioural signal; an abnormal thermal
event is never a confirmed fire).

### 6.10 Fire Intelligence Agent interface

- **Purpose:** natural-language access to the same intelligence layer — an
  enhancement, never the primary surface.
- **Placement:** docked on the Command Center (`st.container(border=True)`);
  opened as a `st.dialog` command palette from the sidebar `⌘ Ask Agent` on any
  page. The dashboard stays dominant.
- **Collapsed dock:** a compact card — the robot illustration, a `LOCAL` /
  `ONLINE`-style status, a one-line tagline ("Ask about alerts, risks, regions or
  facilities."), and an `Open console ▸` button. No large chat in the collapsed
  state.
- **Expanded:** the robot stays at the top; a "Conversation" divider; the running
  history; result cards; the `st.chat_input`; and the read-only reminder
  footnote.
- **Each answer:** a concise NL response grounded in real data (with `**bold**`
  rendered), plus **result cards** with up to three actions — **Open
  Investigation**, **Show on Map**, **Generate Report** — plus a mode line:
  **Claude-enhanced reasoning** when `ANTHROPIC_API_KEY` is set, **Local
  intelligence mode** otherwise.
- **Robot states:** IDLE (static, subtle hover) → THINKING (bob + pulsing ring
  while a query runs) → back to static when the reply lands. Never loops
  indefinitely. The illustration is `dashboard/static/agent-bot.webp`,
  base64-embedded at import so no HTTP round-trip is needed per render.
- **Read-only:** a request to acknowledge / escalate / resolve returns an
  explanation + an "Open Investigation" card so the user can use the manual
  control.
- **Never:** fabricate a value; dominate the layout; open a second map; perform a
  consequential action on its own; crash the panel (dispatch and formatting are
  both guarded).

---

## 7. Cross-cutting UI states

- **Loading:** preserve layout; contextual text ("Re-scoring detections…",
  "Locating nearby facilities…"), not a bare spinner.
- **Empty:** say *what* is empty, *why*, and *what to do* — e.g. "No known
  facilities have nearby detections for this scope. Widen the filters." Never
  "No data."
- **Insufficient data:** stated explicitly (baseline comparison, facility
  baseline), never a fabricated number.
- **Error:** plain language with last-known-good context; no raw tracebacks.
- **Selected / focus:** a restrained treatment using the single system blue (a
  white ring on the map).

---

## 8. Responsiveness & accessibility

- Desktop / laptop is the primary target (operations use). Layouts remain usable
  at tablet width — the map, alerts, investigation, and the agent stay
  functional; the sidebar collapses rather than the content breaking.
- Keyboard navigation and visible focus states on interactive elements;
  sufficient contrast on the dark surfaces; semantic structure; accessible labels
  on icon-only controls. Wide tables / diagrams scroll inside their own
  container — the page body never scrolls horizontally.

---

## 9. Design acceptance test

Before calling a screen done, check: **alignment** (one grid), **typography**
(consistent scale/weights, mono for numbers), **spacing** (consistent rhythm),
**hierarchy** (the important thing is obvious), **density** (informative, not
cluttered), **consistency** (one system), **restraint** (no AI-slop patterns),
**honesty** (no fabricated data or claims; the three scores kept distinct and
labelled). If shown without the project name, would a technical evaluator take it
for a serious operational-intelligence platform? If not, keep refining.
