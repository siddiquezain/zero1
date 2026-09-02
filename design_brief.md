# SIH26162 — Design Brief (Product + UI/UX Blueprint)

> How the final application should look, feel, and behave. Derived from the
> approved plan (`.claude/plans/starry-rolling-pnueli.md`) and the existing
> implementation. Companion to `context.md`, `architecture.md`, `workflow.md`.
>
> This is a blueprint, not a licence to add features. Preserve existing
> functionality; reorganise it for clarity.

---

## 1. Product identity

**India Fire Intelligence Platform** — a geospatial operational-intelligence tool
that turns the raw NASA FIRMS thermal feed over India into a prioritised, explained
picture: what thermal activity is happening, how serious it is, where, why it
matters, and what to do next. Two ways to use the same system: a conventional
operations dashboard, and an optional natural-language **Fire Intelligence Agent**.

It should read as a **serious monitoring / emergency-operations platform** —
credible to a technical evaluator or a disaster-management analyst — not a generic
AI dashboard or a student project.

---

## 2. Design philosophy

- **Clarity over decoration.** Every element earns its place. If it doesn't help
  the operator decide something, remove it.
- **Hierarchy first.** The most important information dominates each screen. A
  judge should understand the situation in ~10 seconds on the Command Center.
- **Operational, not promotional.** No hero sections, no marketing language, no
  "AI magic". Dense, precise, calm.
- **Explain, don't assert.** Where the system flags something, show the real
  signals behind it. Never fabricate confidence or evidence.
- **Preserve capability.** Reorganising the UI must not cost the operator a
  feature. Everything that exists today has a deliberate home.
- **Reuse the current visual language.** The existing dark operations aesthetic
  (IBM Plex Sans / Plex Mono, near-black surfaces, thin hairline borders, 2px
  radius, restrained semantic colour) is kept and applied consistently — not
  rebuilt.

---

## 3. Visual language

### Keep (already in `dashboard/app.py`)

- **Typeface:** IBM Plex Sans for UI text, IBM Plex Mono for numbers, codes,
  coordinates, timestamps. Numeric values are monospaced and aligned.
- **Surfaces:** layered near-black (`#070707` → `#1f1f1f`). Background is flat and
  dark; content sits on it with hairline separation, not floating cards.
- **Borders:** 1px, very low-opacity white (`rgba(255,255,255,0.04–0.15)`).
  Dividers and section rules do most of the structural work.
- **Radius:** 2px everywhere. No pills, no large rounded cards.
- **Labels:** small, uppercase, letter-spaced, muted — used as quiet section
  markers.

### Colour principles

- **Neutral foundation.** The interface is greyscale. Colour is reserved for
  meaning.
- **Semantic severity only:**
  - CRITICAL — red (`#e03131`), used sparingly. If everything is red, nothing is.
  - HIGH — amber (`#d97706`)
  - MEDIUM — muted gold (`#b5860d`)
  - LOW — green (`#2d8a2d`)
- **Classification colours** (map + legend, already defined): Industrial Fire red,
  Persistent Source orange, Natural Fire green, Confirmed Incident light grey.
- **System accent:** a single desaturated blue (`#3d7dc8`) for selected/active
  states and links. No second accent.
- The subject is fire — the UI still must **not** become orange/red overall.

### Avoid (AI-slop checklist)

Unnecessary gradients · purple/blue "AI" gradients · excessive rounded cards ·
glow / neon effects · glassmorphism · giant meaningless statistics · decorative
icons before every label · excessive badges · constant pulsing / spinning ·
animated backgrounds · huge empty hero areas · everything centered · everything
floating · generic 4-KPI-card grids.

### Motion

Subtle and purposeful only: 120–250 ms micro-transitions on hover, selection,
expand/collapse, panel open. Respect reduced-motion. The one existing "live" pulse
dot on the status indicator is acceptable; do not add more.

### Iconography

One consistent, thin-stroke icon family, used only where it aids comprehension
(nav items, layer toggles, action buttons). Never as filler.

---

## 4. Information hierarchy (global)

Every screen answers, in priority order:

1. **What is happening?** — current thermal activity / this alert.
2. **How serious?** — severity, risk score.
3. **Where?** — map / location / state.
4. **Why does it matter?** — evidence, context, classification.
5. **What next?** — recommended action, navigation to act.
6. **What changed / how does it compare?** — timeline, baseline.

Statistics are integrated into this hierarchy, not dumped as card rows. Large
numbers appear only when they deserve attention, with supporting context (e.g.
"9.5 MW current FRP · ~197% above the 1.8–3.2 MW baseline") — and only when the
data actually exists.

---

## 5. Navigation structure

A persistent left/side navigation (or top nav) with these sections, ordered along
the operator workflow `DETECT → CLASSIFY → VALIDATE → PRIORITIZE → EXPLAIN → ACT`:

```
Command Center     — overview
Alerts             — the full prioritised feed
Investigation      — deep view of one alert (usually entered from Alerts/Map/Agent)
Map / GIS          — where the anomalies are
Analytics          — time, trends, baseline
Facilities         — activity around known industrial sites
Reports / GIS       — export + incident reports
Model              — how the system works
Limitations        — honest caveats
```

- Nav shows active state, hover state, is keyboard-navigable.
- The shell header carries: system id (`SIH · 26162 · India Fire Intelligence`),
  a live IST clock + data-recency indicator, and a single **"⌘ Fire Intelligence"**
  entry point for the agent.
- Global filters (severity / status / date / classification / region) live in
  shared state and persist across sections. A filter set by the agent looks
  identical to one set by hand.
- No fake pages. Every nav item maps to real functionality.

---

## 6. Screens

For each: purpose · what the user sees · key components · primary actions ·
secondary actions · what's prioritised · how to move on.

### 6.1 Command Center

- **Purpose:** high-level operational picture in ~10 seconds.
- **Sees:** a compact situation line (active alerts requiring attention;
  CRITICAL / HIGH / MEDIUM / LOW counts; Industrial Fire / Persistent Source /
  Natural Fire counts); the live India detection map colour-coded by class; a
  short list of the top ~5 priority alerts; small classification and severity
  summaries; a 14-day fire-activity strip; a few quick actions.
- **Key components:** `situation_header`, `map_view` (shared), priority-alert
  rows, `kpi` blocks, activity strip.
- **Primary actions:** open the highest-risk investigation; "View All Alerts".
- **Secondary actions:** export critical detections (GIS); jump to a date in
  Analytics; open the agent.
- **Prioritised:** counts that signal load and urgency; the map; the few alerts
  that matter now.
- **Not here:** the full alert feed (that's the Alerts section); dense tables;
  historical deep-dives.
- **Move on:** priority-alert row → Investigation; "View All Alerts" → Alerts;
  map marker → Investigation; activity-strip day → Analytics.

### 6.2 Alerts

- **Purpose:** the complete, filterable, prioritised alert feed and triage
  surface.
- **Sees:** a compact filter toolbar (severity, status, date quick-ranges +
  custom, classification); alerts grouped by severity, paginated; each row shows
  classification · severity · location + coordinates · risk score · FRP ·
  persistence · detection date/time · nearest facility/context.
- **Key components:** `filter_bar`, severity section headers, `alert_row`
  (collapsed), expander with assessment + actions, pager.
- **Primary actions:** open an alert's **Investigation**; expand for assessment.
- **Secondary actions (manual, preserved):** Acknowledge, Escalate, Resolve;
  paginate; adjust filters.
- **Prioritised:** severity and risk; location; time; status. Typography and
  spacing carry importance — not a wall of badges.
- **Move on:** "View Investigation" on any row → Investigation (that alert
  focused); filters propagate to Map and Analytics.

### 6.3 Investigation

- **Purpose:** the place an operator understands **why** an alert matters and what
  to do. Feels like an intelligence briefing, assembled from real fields only.
- **Sees (sectioned):**
  - **Incident header** — output class, city + state, `RISK n / 100`, model class
    probability (labelled as such, not invented "confidence"), status.
  - **Detection** — FRP, persistence count, detection date/time, day/night,
    coordinates, satellite/instrument (VIIRS 375 m), FIRMS confidence.
  - **Context** — distance to nearest facility + hazard type, land-cover context,
    nearest city + population (only when population context exists).
  - **Why flagged** — a checklist of the signals that *actually* fired: repeat
    detections, near industrial facility, industrial land-use match, elevated FRP,
    night-time detection, pattern anomaly. Signals that are false or unknown are
    omitted — never shown as unchecked filler, never fabricated.
  - **Classification** — the 3-class output with the model's `predicted_label`
    and class probabilities, plus the locked framing line ("anomalous departure…
    not a confirmed fire").
  - **Risk assessment** — the real contributing factors from the risk engine
    (each `+points` component that fired), summing to the shown score.
  - **Recommended action** — one concise operational recommendation derived from
    (severity, class, anomaly), e.g. "ESCALATE FOR FIELD VERIFICATION" with a
    one-line reason.
- **Primary actions (manual, preserved):** Acknowledge, Escalate, Resolve.
- **Secondary actions:** show this detection on the map; generate a report for it;
  back to Alerts.
- **Prioritised:** the "why" and the recommended action.
- **Move on:** "Show on Map" → Map focused on this detection; status actions
  update the feed.

### 6.4 Map / GIS

- **Purpose:** answer "**where** are the thermal anomalies?" — a professional
  geospatial view, not a decorated card.
- **Sees:** the full-bleed India detection map (pydeck, Carto dark basemap);
  detections as severity/intensity-aware markers coloured by class or by severity;
  confirmed-incident overlay; optional facility layer; a clean legend; hover
  tooltips with the key metrics.
- **Key components:** shared `map_view` (same builder used on the Command Center),
  a compact side panel for layer/colour controls (not floating over the map),
  legend.
- **Primary actions:** click a detection → open its Investigation.
- **Secondary actions:** toggle colour-by (class / severity); toggle
  incident/facility layers; zoom/pan; apply the active filters.
- **Prioritised:** spatial distribution and clusters; the selected detection.
- **Not here:** every possible attribute at once; multiple competing overlays.
- **Move on:** marker → Investigation; the agent's "Show on Map" lands here with
  filters applied.

### 6.5 Analytics

- **Purpose:** temporal and categorical analysis — how today compares, where
  activity concentrates.
- **Sees:** the historical fire-activity strip; the calendar view (days coloured
  by peak severity); period analysis for a selected range (detections, high-
  confidence, critical, avg/max FRP, risk level, top land cover); playback
  controls; classification breakdown (3 class panels + land-cover and
  hazard-type distributions); a **baseline comparison** — normal FRP band
  (median ± IQR over the available history) vs current, with the percentage
  delta — rendered as an analytical stat, shown only when the data supports it,
  and labelled honestly ("insufficient history" otherwise).
- **Key components:** activity strip, calendar table, period stat grid,
  class panels, baseline stat.
- **Primary actions:** select a date / range → filters the Map and Alerts.
- **Secondary actions:** play through the range; change speed.
- **Prioritised:** critical days; the baseline delta.
- **Move on:** a selected day carries into Map and Alerts as a date filter.

### 6.6 Facilities

- **Purpose:** shift the question from "where are hotspots" to "**what is
  happening around known industrial infrastructure**" — a differentiator for
  SIH26162.
- **Sees:** a table of Indian industrial facilities (from `facilities.parquet`)
  that have nearby thermal detections: facility name, type, location, state,
  source; count of nearby detections; number of repeat detections; max risk of a
  nearby detection; a small historical-activity indication; current-vs-baseline
  where available.
- **Key components:** facility table (proper column hierarchy, numeric alignment,
  hover + selected states), row detail.
- **Primary actions:** select a facility → filter the Map / Alerts to its
  vicinity.
- **Secondary actions:** sort by activity / risk; filter by facility type or
  state.
- **Prioritised:** facilities with the most / highest-risk nearby activity.
- **Move on:** facility → Map (vicinity) / Alerts (filtered).

### 6.7 Reports / GIS

- **Purpose:** get the current picture out — for GIS tools or a briefing.
- **Sees:** filter-aware **GeoJSON** and **CSV** export of alerts (each alert a
  Point feature with the full attribute table); a GeoJSON preview (first few
  features); an **incident report** builder (Markdown / CSV summary of the
  filtered critical / industrial-fire alerts for a period).
- **Key components:** export buttons, preview code block, report builder.
- **Primary actions:** download GeoJSON / CSV; generate + download the incident
  report.
- **Secondary actions:** adjust the filters that define the export set.
- **Prioritised:** that exports respect the active filters and carry real
  attributes.
- **Move on:** exports are terminal; the agent's "Generate Report" produces the
  same artefact.

### 6.8 Model

- **Purpose:** technical credibility — show the real pipeline, not claims.
- **Sees:** the actual pipeline
  `NASA FIRMS → Preprocessing → Detection → Classification → Persistence Analysis
  → Industrial Context → Risk Engine → Alert / Investigation`; the data sources
  actually used; the three-way evaluation (random baseline, spatial holdout,
  India holdout) from `reports/stage6_evaluation.txt`; feature importance
  (`dist_nearest_facility_km`, `day_night_bin`, `bt_kelvin`, `persistence_count`,
  `frp_mw`); the VNF-oracle labelling approach and the anomaly rule.
- **Primary actions:** none — this is reference.
- **Prioritised:** honesty. No models, datasets, or methods that aren't
  implemented.

### 6.9 Limitations / Transparency

- **Purpose:** state what the system cannot do — important for judging.
- **Sees:** FIRMS spatial resolution; satellite revisit gaps; cloud/observation
  limits; false positives; classification limitations (no confirmed-fire
  ground truth; thin Class A; coordinate-zone land cover); data availability
  (NRT-only, no historical archive); the locked operational framing (anomalous
  departure — not confirmed fire detection; all alerts require human
  verification).
- **Prioritised:** clarity and candour.

### 6.10 Fire Intelligence Agent interface

- **Purpose:** natural-language access to the same intelligence layer — "ask the
  platform instead of driving filters". An enhancement, never the primary surface.
- **Placement:** opened from the shell's **"⌘ Fire Intelligence"** entry on any
  page; presented as a **compact command palette / dialog**, not a full-screen
  chat. The dashboard remains dominant behind it.
- **Sees:** a single input, a short running history, and for each answer:
  - a concise natural-language response grounded in real data;
  - **result cards** — each with a title/subtitle and up to three actions:
    **Open Investigation**, **Show on Map**, **Generate Report**;
  - when running without an API key, a quiet "Local intelligence mode" note
    (offline deterministic parser) — the agent still works fully.
- **Primary actions:** ask a question; click a result-card action (which applies
  shared filters / navigates / focuses the map / opens an investigation /
  produces a report).
- **Secondary actions:** clear history; copy an answer.
- **Prioritised:** the answer and the one or two next steps — not a long
  transcript.
- **Read-only:** if asked to acknowledge / escalate / resolve, it explains that
  this is a manual control and offers "Open Investigation" so the user can do it.
- **Never:** fabricate a value (says "not available"); dominate the layout; open
  a second map; perform a consequential action on its own.
- **Demo path:** "Find the three highest-risk persistent thermal sources near
  industrial facilities in eastern India over the last 7 days and explain why" →
  three result cards, each with real why-flagged evidence and the three actions.

---

## 7. Cross-cutting UI states

- **Loading:** preserve layout; contextual text ("Scoring detections…"), not a
  bare spinner.
- **Empty:** say what is empty, why it may be, and what to do — e.g. "No fire
  detections recorded for this period. Try another date range." Never "No data."
- **Error:** plain-language, with last-known-good context and a retry where
  possible. Don't surface raw tracebacks.
- **Selected / focus:** a clear but restrained treatment using the single system
  blue.

---

## 8. Responsiveness & accessibility

- Desktop / laptop is the primary target (operations use). Layouts should remain
  usable at tablet width — map, alerts, investigation and the agent stay
  functional; the nav collapses rather than the content breaking.
- Keyboard navigation and visible focus states on all interactive elements;
  sufficient contrast on the dark surfaces; semantic structure; reduced-motion
  support; accessible labels on icon-only controls.

---

## 9. Design acceptance test

Before calling a screen done, check: **alignment** (on one grid), **typography**
(consistent scale/weights), **spacing** (consistent rhythm), **hierarchy** (the
important thing is obvious), **density** (informative, not cluttered),
**consistency** (one system), **restraint** (no AI-slop patterns), **honesty**
(no fabricated data or claims). If shown without the project name, would a
technical evaluator take it for a serious operational intelligence platform? If
not, keep refining.
