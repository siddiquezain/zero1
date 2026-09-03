You are working on an existing Smart India Hackathon 2026 project for:

SIH26162 — AI-Based Detection and Classification of Industrial Fires and Persistent Thermal Sources Using NASA FIRMS, OSM & Satellite Data.

IMPORTANT:
This is NOT a greenfield project.

The existing application already has a functioning FIRMS → feature engineering → ML classification → geospatial enrichment → risk engine → alert store → Streamlit dashboard → reports → deterministic Fire Intelligence Agent pipeline.

Your job is to UPGRADE the existing system into a much stronger "Thermal Event Intelligence Platform" WITHOUT breaking, removing, replacing, or unnecessarily rewriting the existing functionality.

The six major additions are:

1. Thermal Event Clustering
2. Thermal Behaviour Fingerprinting
3. Evidence Stack / Explainability
4. Event Evolution Replay
5. Early-Warning / Risk Trajectory
6. Upgrade the Fire Intelligence Agent into an Analyst

The final product should tell one coherent story:

DETECT → CLUSTER → UNDERSTAND → EXPLAIN → TRACK → WARN → INVESTIGATE → ASSIST HUMAN

============================================================
0. NON-NEGOTIABLE RULES
============================================================

RULE 1 — DO NOT REWRITE THE PROJECT

Do not replace the current architecture with a new framework.

Do not migrate Streamlit to React.

Do not rewrite the FIRMS pipeline.

Do not retrain the ML model unless absolutely required and explicitly justified.

Do not replace the existing risk engine.

Do not replace the existing alert lifecycle.

Do not remove existing dashboard pages or capabilities.

Reuse the existing code wherever possible.

Add new modules cleanly around the existing architecture.

------------------------------------------------------------

RULE 2 — PRESERVE ALL EXISTING FEATURES

The following must continue working:

- NASA FIRMS ingestion
- FIRMS NRT refresh
- existing cleaning/normalization
- existing feature engineering
- facility enrichment
- nearest facility calculation
- Random Forest classification
- model probabilities
- anomaly flag
- three-class dashboard interpretation
- persistence
- risk scoring
- severity
- alert generation
- alert lifecycle
- manual acknowledge
- manual escalate
- manual resolve
- monitoring state
- confirmed incident overlay
- GIS map
- facilities layer
- analytics
- CSV export
- GeoJSON export
- incident report
- Model page
- Limitations page
- Investigation page
- offline deterministic agent
- optional Claude agent fallback
- current UI theme
- existing navigation

If an existing feature appears redundant, DO NOT delete it.
Preserve it unless there is a proven bug.

------------------------------------------------------------

RULE 3 — AGENT MUST REMAIN READ-ONLY

The Fire Intelligence Agent may:

- query data
- filter data
- rank alerts
- aggregate events
- explain evidence
- open investigation
- focus the map
- trigger event replay
- generate reports
- navigate UI
- answer natural-language questions

The agent MUST NOT:

- acknowledge alerts
- escalate alerts
- resolve alerts
- change lifecycle state
- delete records
- edit database records
- retrain models
- execute arbitrary Python
- execute shell commands
- execute arbitrary SQL
- modify configuration
- modify files

Manual operational actions remain HUMAN ONLY.

------------------------------------------------------------

RULE 4 — NO FABRICATION

Never invent:

- FIRMS observations
- FRP
- brightness temperature
- facility names
- coordinates
- distances
- probabilities
- timestamps
- satellite evidence
- fire status
- extinguished status
- ground truth

Every displayed value must originate from existing data or a deterministic calculation.

If data is unavailable, explicitly display:

"Data unavailable"

or

"Not available in current observation window"

Do not manufacture plausible-looking values.

------------------------------------------------------------

RULE 5 — HONEST ML CLAIMS

The current model is a proxy classifier.

Do NOT claim:

"98% accurate industrial fire detection"

Do NOT convert model probability into real-world fire certainty.

Use terminology such as:

- model probability
- candidate classification
- anomaly flag
- supporting evidence
- assessment
- risk score

The system must communicate uncertainty.

------------------------------------------------------------

RULE 6 — OFFLINE FIRST

The core upgraded system must work without:

- Anthropic API key
- internet
- external LLM
- Mapbox token

The deterministic agent remains the guaranteed baseline.

Optional Claude integration may continue to exist as a fallback.

------------------------------------------------------------

RULE 7 — DEBUG BEFORE POLISH

Before implementing visual polish:

1. inspect repository
2. inspect architecture
3. inspect existing tests
4. inspect data schemas
5. run existing tests
6. identify failures
7. implement feature
8. write tests
9. run tests
10. debug failures
11. run application
12. verify actual UI/data flow

Do not assume code works because it compiles.

------------------------------------------------------------

RULE 8 — SMALL INCREMENTAL CHANGES

Implement one capability at a time.

After each major capability:

- run tests
- inspect output
- fix regressions
- continue

Do not make one giant uncontrolled rewrite.

============================================================
1. FIRST ACTION — FULL PROJECT AUDIT
============================================================

DO NOT CODE IMMEDIATELY.

First inspect the entire repository.

Identify:

- project structure
- dashboard entry point
- intelligence layer
- alerting layer
- model layer
- data files
- database
- tests
- existing agent
- map implementation
- investigation implementation
- risk engine
- feature engineering
- pipeline
- exports
- configuration
- requirements/dependencies

Read the relevant source files.

Pay special attention to:

dashboard/app.py
src/intelligence/
src/alerting/
src/features/
src/model/
data/
tests/

Also inspect:

architecture documentation
workflow documentation
design documentation
model documentation

if present.

Do not trust documentation blindly.
Compare documentation against actual code.

------------------------------------------------------------

2. CREATE AN IMPLEMENTATION AUDIT
------------------------------------------------------------

Before modifying code, produce an internal implementation plan containing:

A. What already exists
B. What can be reused
C. What is missing
D. What files need modification
E. What new files should be created
F. Potential regression risks
G. Required tests

Do not create duplicate functionality if an existing function can be reused.

Use the current architecture as the source of truth.

============================================================
3. TARGET ARCHITECTURE
============================================================

The upgraded architecture should conceptually become:

NASA FIRMS
     |
     v
THERMAL DETECTIONS
     |
     v
EVENT CLUSTERING
     |
     v
THERMAL EVENT OBJECT
     |
     +----------------------+
     |                      |
     v                      v
BEHAVIOUR FINGERPRINT    GIS CONTEXT
     |                   |
     |                   +-- Facilities
     |                   +-- OSM
     |                   +-- Land Cover
     |
     v
EVIDENCE STACK
     |
     v
CLASSIFICATION
     |
     v
RISK ENGINE
     |
     v
RISK TRAJECTORY
     |
     v
EARLY WARNING
     |
     v
INVESTIGATION
     |
     v
FIRE INTELLIGENCE ANALYST

IMPORTANT:

Do not force this into one enormous Python file.

Keep concerns separated.

Recommended conceptual modules:

src/intelligence/events.py
src/intelligence/clustering.py
src/intelligence/fingerprint.py
src/intelligence/evidence.py
src/intelligence/evolution.py
src/intelligence/early_warning.py

Add additional modules only if genuinely necessary.

============================================================
4. FEATURE 1 — THERMAL EVENT CLUSTERING
============================================================

GOAL:

Convert individual FIRMS detections into coherent thermal events.

Current problem:

FIRMS produces individual hotspot observations.

A real analyst should not have to reason about dozens of unrelated dots.

We need:

many detections
      ↓
spatial + temporal grouping
      ↓
THERMAL EVENT

------------------------------------------------------------
4.1 Clustering requirements
------------------------------------------------------------

Use existing FIRMS coordinates and acquisition timestamps.

Do NOT blindly use a fixed arbitrary clustering algorithm if the existing data structure suggests a better deterministic approach.

Start with a simple explainable approach.

Potential logic:

- spatial proximity
- temporal proximity
- optionally grid proximity

An event should combine observations that are:

- geographically close
- temporally close

Avoid merging unrelated hotspots across large distances or long time periods.

The clustering implementation must be deterministic.

Given identical input data, event IDs and memberships should be reproducible.

------------------------------------------------------------
4.2 Event object
------------------------------------------------------------

Create a stable event representation.

Conceptually:

ThermalEvent:

- event_id
- observations
- centroid_lat
- centroid_lon
- start_time
- end_time
- duration
- observation_count
- spatial_extent_km
- peak_frp_mw
- mean_frp_mw
- max_bt_kelvin
- mean_bt_kelvin
- night_observation_count
- day_observation_count
- persistence_count
- nearest_facility
- nearest_facility_distance_km
- facility_type
- predicted_class
- model_probability
- anomaly_flag
- risk_score
- severity
- state
- region

Only populate fields that actually exist.

Do not fabricate missing fields.

------------------------------------------------------------
4.3 Event ID

Event IDs must be deterministic.

Do not use random UUIDs if event identity needs to remain stable between runs.

Use a deterministic scheme based on:

- sorted observation identifiers if available
- or deterministic spatial/time seed

Document the strategy.

------------------------------------------------------------
4.4 Event clustering tests

Create tests for:

1. nearby detections → same event
2. distant detections → different events
3. temporally distant detections → different events
4. identical input → identical event IDs
5. empty dataframe
6. missing timestamp
7. missing coordinates
8. duplicate detections
9. single detection event
10. mixed unrelated detections

============================================================
5. FEATURE 2 — THERMAL BEHAVIOUR FINGERPRINT
============================================================

GOAL:

Do not only ask:

"What class is this?"

Also ask:

"How does this thermal source behave?"

The fingerprint must be derived from actual observations.

------------------------------------------------------------
5.1 Fingerprint dimensions
------------------------------------------------------------

Build deterministic behavioural indicators such as:

PERSISTENCE
- observation count
- duration
- recurrence

TEMPORAL
- day/night ratio
- recurrence pattern
- temporal continuity

THERMAL
- mean FRP
- peak FRP
- FRP trend
- brightness temperature statistics

SPATIAL
- spatial extent
- movement/spread
- centroid stability

INDUSTRIAL CONTEXT
- facility proximity
- industrial facility type
- industrial land-use if available

SEASONAL
- agriculture-season alignment if existing feature exists

------------------------------------------------------------
5.2 Behaviour categories

Create interpretable behaviour categories.

Possible categories:

- Persistent Industrial Signature
- Recurring Thermal Source
- Rapidly Expanding Fire Signature
- Seasonal Agricultural Signature
- Isolated Thermal Anomaly
- Insufficient Evidence

These categories are NOT ground truth.

They are behavioural assessments.

Avoid saying:

"This is definitely an industrial fire."

Use:

"Behaviour is consistent with persistent industrial thermal activity."

------------------------------------------------------------
5.3 Fingerprint visualization

Investigation page should show a compact fingerprint panel.

Example:

THERMAL BEHAVIOUR

Persistence        HIGH
Night Activity     HIGH
FRP Intensity      HIGH
Spatial Stability  HIGH
Industrial Proximity VERY HIGH
Seasonal Alignment LOW

Then:

BEHAVIOUR ASSESSMENT

Persistent Industrial Signature

------------------------------------------------------------
5.4 Fingerprint tests

Test:

- persistent source
- mostly daytime source
- mostly nighttime source
- high spatial spread
- low spatial spread
- seasonal pattern
- missing data
- single observation
- insufficient observations

============================================================
6. FEATURE 3 — EVIDENCE STACK / EXPLAINABILITY
============================================================

GOAL:

Turn the system from:

"Risk = 78"

into:

"Risk = 78 BECAUSE..."

------------------------------------------------------------
6.1 Evidence categories

Build evidence into categories:

THERMAL EVIDENCE
- FRP
- brightness temperature
- observation count
- persistence

GEOSPATIAL EVIDENCE
- nearest facility
- facility distance
- facility type
- industrial land use
- state/region

BEHAVIOURAL EVIDENCE
- persistence
- night activity
- spatial behaviour
- FRP trend

MODEL EVIDENCE
- predicted class
- model probability
- anomaly flag

RISK EVIDENCE
- risk score
- severity
- risk factors from risk engine

------------------------------------------------------------
6.2 Evidence direction

Where possible distinguish:

SUPPORTING EVIDENCE

and

CONTRADICTING / LIMITING EVIDENCE

Example:

SUPPORTING
✓ Persistent across 9 observations
✓ Close to industrial facility
✓ Strong night-time recurrence

LIMITING
! FIRMS spatial resolution limits exact source attribution
! No direct ground confirmation

This is extremely important.

The system should communicate both evidence and uncertainty.

------------------------------------------------------------
6.3 Evidence score

Do NOT invent another mysterious AI score.

Reuse the existing risk factors where possible.

Create a structured evidence object instead of another black-box numerical score.

Example:

EvidenceItem:

- category
- label
- value
- direction
- explanation
- source

------------------------------------------------------------
6.4 Investigation integration

The Investigation page should become:

EVENT HEADER

THERMAL DETECTION

BEHAVIOUR FINGERPRINT

EVIDENCE STACK

CLASSIFICATION

RISK ASSESSMENT

EVENT EVOLUTION

EARLY WARNING

RECOMMENDED OPERATOR ACTION

IMPORTANT:

Do not overcrowd the page.

Use progressive disclosure/expanders where appropriate.

============================================================
7. FEATURE 4 — EVENT EVOLUTION REPLAY
============================================================

GOAL:

Allow analysts/judges to WATCH the event develop.

------------------------------------------------------------
7.1 Timeline

For each event show:

start
|
observation
|
observation
|
observation
|
peak
|
current

Example:

12:10  First Detection
12:42  Persistence Detected
13:15  FRP Increasing
13:48  Industrial Context Identified
14:20  Event Expanded
14:52  High-Risk Threshold Crossed

Only show milestones that can actually be derived from the data.

Do not invent semantic milestones.

------------------------------------------------------------
7.2 Map replay

Use the existing map infrastructure.

DO NOT create a second unrelated map system.

The replay should:

- use existing map
- progressively reveal observations
- display the current time
- show event extent
- optionally show facility context

Possible controls:

[▶ PLAY]
[⏸ PAUSE]
[RESET]
timeline slider

If Streamlit limitations make true animation difficult, implement a robust frame-based replay with a slider.

Reliability is more important than flashy animation.

------------------------------------------------------------
7.3 Replay data

Create a deterministic ordered sequence:

event observations sorted by acquisition time.

Each frame should represent:

- observations visible up to timestamp
- current timestamp
- current FRP
- cumulative observation count
- risk if available

Do not calculate fake future information.

------------------------------------------------------------
7.4 Evolution tests

Test:

- chronological ordering
- duplicate timestamps
- single observation
- missing timestamp
- empty event
- deterministic frame generation

============================================================
8. FEATURE 5 — EARLY WARNING / RISK TRAJECTORY
============================================================

GOAL:

The system should identify when an event is becoming more concerning.

Do NOT build a complicated deep-learning forecasting system.

Use deterministic explainable trend logic first.

------------------------------------------------------------
8.1 Trend signals

Possible signals:

- persistence increasing
- FRP increasing
- spatial extent increasing
- observation frequency increasing
- risk score increasing
- industrial-context evidence strengthening

Only use signals supported by available data.

------------------------------------------------------------
8.2 Risk trajectory

Show:

Risk history:

T1 → 34
T2 → 41
T3 → 48
T4 → 61
T5 → 72

Then:

TRAJECTORY: INCREASING

Reason:

- persistence increased
- FRP increased
- industrial proximity remains strong

------------------------------------------------------------
8.3 Early-warning states

Possible states:

STABLE
WATCH
INCREASING
EARLY WARNING
HIGH PRIORITY

Do not automatically change operational alert lifecycle.

IMPORTANT:

Early-warning state is an analytical signal.

It is NOT:

ACKNOWLEDGED
ESCALATED
RESOLVED

Manual lifecycle controls remain untouched.

------------------------------------------------------------
8.4 Avoid future certainty

Never say:

"Fire will happen in 30 minutes."

Instead:

"Risk trajectory is increasing."

or:

"Observed behaviour indicates increasing concern."

------------------------------------------------------------
8.5 Early warning tests

Test:

- stable risk
- increasing risk
- decreasing risk
- insufficient history
- single observation
- missing FRP
- missing risk score

============================================================
9. FEATURE 6 — UPGRADE FIRE INTELLIGENCE AGENT INTO ANALYST
============================================================

The current agent is already offline deterministic with optional Claude.

Preserve this architecture.

Upgrade the deterministic analyst capabilities.

------------------------------------------------------------
9.1 Agent capabilities

The agent should understand requests such as:

"Show me critical industrial events."

"Show high-risk events in Andhra Pradesh."

"Which event has the highest risk?"

"Why is event 0241 high risk?"

"Show the behaviour fingerprint for event 0241."

"Show the evidence for event 0241."

"How has event 0241 evolved?"

"Replay event 0241."

"Which events are increasing in risk?"

"Which thermal events are closest to facilities?"

"Show persistent industrial sources."

"Compare Andhra Pradesh and Telangana."

"Generate a report for event 0241."

"Focus the map on event 0241."

"Open investigation for event 0241."

------------------------------------------------------------
9.2 Agent must reason over EVENTS

The agent should not only query raw alerts.

It should understand:

Alert
Detection
Event
Facility
Region
Behaviour
Evidence
Risk
Timeline

Create/extend the tool registry accordingly.

------------------------------------------------------------
9.3 Recommended read-only tools

Examples:

list_events
get_event
get_event_fingerprint
get_event_evidence
get_event_evolution
rank_events
compare_regions
find_increasing_risk_events
find_events_near_facilities
filter_events
focus_event
open_investigation
replay_event
export_event_report

Only implement tools that map to real deterministic backend functions.

------------------------------------------------------------
9.4 Agent UI actions

Agent may return UI actions such as:

{
    "action": "focus_event",
    "event_id": "..."
}

or:

{
    "action": "open_investigation",
    "event_id": "..."
}

or:

{
    "action": "replay_event",
    "event_id": "..."
}

The frontend executes these UI actions.

The agent itself must not mutate operational state.

------------------------------------------------------------
9.5 Analyst-style responses

Bad:

"Sure! I can help you with that."

Good:

"3 high-risk industrial events found in Andhra Pradesh."

Bad:

"Event 0241 is dangerous."

Good:

"Event 0241 is ranked highest because it combines high persistence, strong industrial proximity and increasing observed risk."

Bad:

"This is definitely a refinery fire."

Good:

"Evidence is consistent with persistent industrial thermal activity. FIRMS resolution limits exact source attribution."

------------------------------------------------------------
9.6 Agent deterministic parser

Extend the existing parser rather than replacing it.

Support:

- event IDs
- state
- region
- severity
- class
- timeframe
- ranking
- facility proximity
- persistence
- increasing risk
- behaviour
- evidence
- evolution
- replay
- investigation

Add tests for every documented intent.

============================================================
10. DATA MODEL
============================================================

Do not duplicate the same data in multiple databases unless necessary.

Prefer derived event intelligence over existing detection records.

Conceptually:

Detection
   |
   +---- Alert
   |
   +---- Event
          |
          +---- Fingerprint
          +---- Evidence
          +---- Evolution
          +---- Risk Trajectory

If persistence/database is necessary, use the existing persistence architecture.

Do not create a second competing SQLite database.

============================================================
11. UI INTEGRATION
============================================================

Maintain the existing serious operational dark theme.

Do NOT introduce:

- gradients
- excessive glow
- childish AI graphics
- giant cards
- random futuristic effects
- excessive animations

The design should feel like:

satellite intelligence
+
GIS
+
emergency operations
+
industrial monitoring

------------------------------------------------------------
11.1 Command Center

Add:

THERMAL EVENTS

instead of forcing every raw detection into the primary view.

Possible KPI:

ACTIVE EVENTS
HIGH-RISK EVENTS
PERSISTENT SOURCES
EARLY WARNINGS

Preserve existing KPIs.

------------------------------------------------------------
11.2 Alerts page

Allow switching between:

DETECTIONS
EVENTS

Do not remove detection-level view.

------------------------------------------------------------
11.3 Investigation page

This should become the flagship page.

Suggested order:

1. Event header
2. Current status
3. map
4. event evolution
5. behaviour fingerprint
6. evidence stack
7. classification
8. risk trajectory
9. early warning
10. operator recommendation
11. raw detection details

The page must remain readable.

------------------------------------------------------------
11.4 Map Explorer

Add event clustering visualization.

Possible modes:

RAW DETECTIONS
THERMAL EVENTS
FACILITIES
CONFIRMED INCIDENTS

Allow clicking an event to:

- focus event
- open investigation
- replay evolution

------------------------------------------------------------
11.5 Analytics

Add:

- event count over time
- persistent-event count
- event behaviour distribution
- risk trajectory distribution
- early-warning events

Only implement metrics that are actually computable.

============================================================
12. EVENT/DETECTION RELATIONSHIP
============================================================

This is critical.

Do not destroy the distinction between:

DETECTION
= individual FIRMS observation

EVENT
= group of related detections

ALERT
= operational risk record

INCIDENT
= confirmed/historical reference

Make the terminology explicit in the UI.

Example:

EVENT #0241
12 FIRMS detections
Current risk: HIGH

This prevents conceptual confusion.

============================================================
13. PERFORMANCE
============================================================

The application must remain responsive.

Do not run expensive clustering repeatedly on every Streamlit rerun if avoidable.

Use caching appropriately.

Potential strategy:

- cache source dataframe
- cache event clustering
- cache fingerprints
- cache evidence
- recompute only when source data changes

Do not introduce premature complexity.

Measure performance where useful.

============================================================
14. EDGE CASES
============================================================

The upgraded system must gracefully handle:

- zero FIRMS rows
- one detection
- missing FRP
- missing BT
- missing facility
- detection outside India
- malformed coordinates
- missing timestamps
- duplicate observations
- no event history
- no confirmed incident
- no model output
- model file unavailable
- FIRMS API unavailable
- empty agent query
- unsupported agent query
- corrupted cache
- database unavailable

The dashboard must not crash.

Use clear fallback messages.

============================================================
15. GEOLOCATION SAFETY CHECK
============================================================

Before finalizing, explicitly audit the existing geospatial logic.

Verify:

- latitude/longitude are not swapped
- coordinates correspond to FIRMS records
- India polygon filtering works
- state assignment is correct
- facility country is India where expected
- nearest facility distance is correct
- map tooltip displays original coordinates
- event centroid is correctly calculated
- events outside India are not silently labelled as Indian
- state/region names are not inferred from city text incorrectly

Do not trust reverse-geocoding labels over source coordinates.

Add tests for known coordinate/state cases if practical.

============================================================
16. TESTING STRATEGY
============================================================

After implementation, run:

1. existing unit tests
2. intelligence tests
3. event clustering tests
4. fingerprint tests
5. evidence tests
6. evolution tests
7. early-warning tests
8. agent tests
9. integration tests
10. dashboard import/startup test

Do not stop at "tests pass".

Inspect warnings and errors.

------------------------------------------------------------
16.1 Regression testing

Verify:

- existing alert lifecycle still works
- manual state changes still work
- agent cannot mutate state
- exports still work
- GeoJSON remains valid
- CSV remains valid
- map still renders
- existing pages still load
- FIRMS refresh still works
- model outputs remain unchanged
- existing risk scores remain unchanged unless intentionally extended

------------------------------------------------------------
17. STATIC TYPE / QUALITY CHECK
============================================================

Where project tooling exists, run:

- pytest
- ruff
- mypy if configured
- syntax/import checks

Fix:

- import errors
- circular imports
- undefined variables
- unused imports
- type mismatches
- serialization errors
- pandas warnings
- Streamlit state issues

Do not suppress errors blindly.

============================================================
18. DATABASE SAFETY
============================================================

If schema changes are necessary:

- make migration additive
- preserve existing records
- provide backwards-compatible defaults
- test old database startup
- test fresh database startup

Never delete existing alerts.

Never reset production/demo data automatically.

============================================================
19. DEBUGGING PROTOCOL
============================================================

Whenever a test or runtime error occurs:

DO NOT patch blindly.

Follow:

1. reproduce
2. identify root cause
3. inspect relevant data/schema
4. fix smallest correct layer
5. add regression test
6. rerun affected tests
7. rerun full suite

Example:

If event clustering produces incorrect events:

DO NOT fix it in the UI.

Fix the clustering layer.

If evidence displays wrong facility:

trace:

FIRMS row
→ facility enrichment
→ event aggregation
→ evidence builder
→ UI

Fix the earliest incorrect layer.

============================================================
20. DATA TRUTH / SOURCE OF TRUTH
============================================================

Use the actual current repository data as source of truth.

Do not hardcode:

- number of facilities
- number of alerts
- number of events
- risk values
- state counts
- model probabilities

unless they are constants genuinely defined by the system.

The current committed model outputs and data files may differ from older documentation.

Always inspect actual schemas.

============================================================
21. DOCUMENTATION
============================================================

After successful implementation, update/create:

docs/event_intelligence.md

Document:

- event definition
- clustering logic
- fingerprint logic
- evidence model
- evolution replay
- early-warning logic
- agent tools
- limitations
- data dependencies

Also update architecture documentation if needed.

Be explicit about what is:

AUTOMATED
MANUAL
AGENT-ASSISTED
OPTIONAL

============================================================
22. DEMO MODE
============================================================

If practical, create a deterministic demo selection mechanism.

The demo should allow us to select a known event and demonstrate:

1. detection
2. clustering
3. fingerprint
4. evidence
5. evolution
6. increasing risk
7. early warning
8. analyst agent

Do not create fake data.

Use real repository data.

If existing data does not support a perfect end-to-end demo, create a deterministic DEMO VIEW over real observations rather than inventing observations.

Clearly distinguish demo selection from production/live data.

============================================================
23. ACCEPTANCE CRITERIA
============================================================

The implementation is NOT complete until all of the following are true:

[ ] Existing application starts
[ ] Existing tests pass
[ ] Event clustering works
[ ] Event IDs are deterministic
[ ] Event-level aggregation works
[ ] Behaviour fingerprints work
[ ] Fingerprint is explainable
[ ] Evidence stack works
[ ] Evidence never fabricates data
[ ] Evolution timeline works
[ ] Evolution replay works
[ ] Early-warning trajectory works
[ ] Existing lifecycle remains manual
[ ] Existing maps still work
[ ] Event map mode works
[ ] Investigation page integrates all new intelligence
[ ] Agent can query events
[ ] Agent can explain events
[ ] Agent can retrieve evidence
[ ] Agent can retrieve fingerprint
[ ] Agent can retrieve evolution
[ ] Agent can trigger replay
[ ] Agent can open investigation
[ ] Agent cannot mutate alert state
[ ] Offline mode works
[ ] Optional Claude mode does not break deterministic fallback
[ ] Existing exports work
[ ] No raw SQL from agent
[ ] No arbitrary code execution from agent
[ ] No fabricated values
[ ] Geolocation logic audited
[ ] Regression tests added
[ ] Documentation updated
[ ] Application manually smoke-tested

============================================================
24. FINAL VALIDATION
============================================================

At the end:

Run the complete test suite.

Then start the application.

Perform an actual smoke test of:

COMMAND CENTER
→ ALERTS
→ MAP
→ EVENT
→ INVESTIGATION
→ FINGERPRINT
→ EVIDENCE
→ EVOLUTION
→ EARLY WARNING
→ AGENT
→ REPORT

Test the agent with at least:

"Show me high-risk industrial events."

"Why is the highest-risk event high risk?"

"Show its evidence."

"Show its behaviour fingerprint."

"How has it evolved?"

"Replay it."

"Open its investigation."

Then manually verify:

- acknowledge
- escalate
- resolve

still work ONLY through manual UI controls.

------------------------------------------------------------
25. FINAL REPORT
------------------------------------------------------------

When everything is complete, provide a concise engineering report:

1. Files changed
2. Files created
3. Features implemented
4. Tests added
5. Existing tests status
6. Final test count
7. Any remaining warnings
8. Any known limitations
9. Performance concerns
10. Demo flow
11. Exact commands to run the application
12. Any manual verification still required

Do NOT claim success if something is broken.

============================================================
FINAL PRODUCT PRINCIPLE
============================================================

The final application should NOT feel like:

"An AI chatbot attached to a fire map."

It should feel like:

"An operational thermal intelligence system."

The core narrative is:

SATELLITE DETECTION
        ↓
THERMAL EVENT
        ↓
BEHAVIOUR
        ↓
MULTI-SOURCE EVIDENCE
        ↓
CLASSIFICATION
        ↓
RISK TRAJECTORY
        ↓
EARLY WARNING
        ↓
INVESTIGATION
        ↓
HUMAN DECISION

The Fire Intelligence Agent is the analyst interface over this system.

The system should answer five questions:

1. WHAT happened?
2. WHERE is it?
3. HOW is it behaving?
4. WHY do we believe this assessment?
5. IS IT BECOMING MORE IMPORTANT?

Build this carefully, incrementally, and defensibly.

DO NOT optimize for number of features.

OPTIMIZE FOR:

CORRECTNESS
EXPLAINABILITY
RELIABILITY
DEMO IMPACT
SIH REQUIREMENT ALIGNMENT
AND OPERATIONAL CREDIBILITY.