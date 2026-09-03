# Fire Intelligence — Read-Only Agent + Dashboard Full Audit & Enhancement

You are acting as a **senior AI/ML engineer, geospatial intelligence engineer, backend architect, UX/product designer, and hackathon jury reviewer**.

We have built a prototype called **Fire Intelligence** for SIH 2026, focused on detecting, classifying, monitoring, and communicating potential industrial fires.

We recently added a **read-only intelligence agent** as an enhancement layer.

The agent:

* Accepts natural-language questions/requests from users.
* Searches/uses the data already available inside our system.
* Returns relevant fire/event information when available.
* Is intentionally **read-only**.
* Does NOT modify system data.
* Currently does NOT depend on external APIs for its core operation.
* Should help an operator investigate fire events faster rather than simply acting as a generic chatbot.

Your job is NOT to immediately rewrite things.

First perform a **deep technical, functional, UX, and product audit** of the current implementation. Understand what actually exists, identify weaknesses, then make sensible improvements.

---

# PHASE 1 — UNDERSTAND THE EXISTING SYSTEM

Before changing anything:

1. Inspect the entire repository structure.
2. Identify:

   * frontend/dashboard
   * backend
   * ML pipeline
   * fire detection/classification logic
   * data sources
   * database/local datasets
   * agent implementation
   * agent prompt/system instructions
   * search/retrieval logic
   * API/routes if any
   * map implementation
   * alert/event system
   * anomaly detection
   * industrial/natural/other classification
3. Trace the actual data flow:

Detection → preprocessing → features → ML prediction → classification → anomaly flag → event storage → dashboard → agent → user response

4. Do NOT assume that functionality exists merely because documentation/comments claim it exists.
5. Distinguish clearly between:

   * implemented
   * partially implemented
   * mocked/demo
   * hardcoded
   * unused
   * broken

Create a concise architecture assessment before modifying anything.

---

# PHASE 2 — AUDIT THE READ-ONLY AGENT

Perform a serious audit of the agent.

## A. Agent purpose

Determine whether the agent genuinely behaves like a **Fire Intelligence investigation assistant**, or whether it is effectively just a generic chatbot sitting on top of the dashboard.

It should ideally help answer questions such as:

* "Show me recent industrial fire events."
* "Are there any high-confidence industrial fires?"
* "What happened near this location?"
* "Which incidents are currently high priority?"
* "Why was this event classified as industrial fire?"
* "What is the confidence of this detection?"
* "Are there repeated thermal events in this area?"
* "Show events from the last 24 hours."
* "Which fires have the highest anomaly scores?"
* "What events require attention?"
* "Compare these two incidents."
* "Give me a summary of this incident."
* "Are there any suspicious/recurrent thermal sources?"
* "What evidence do we have for calling this an industrial fire?"

Evaluate whether the current implementation can answer these accurately.

---

# PHASE 3 — AGENT DATA/GROUNDING AUDIT

This is extremely important.

Determine:

### 1. What data can the agent actually access?

Document every accessible field, for example:

* event ID
* timestamp
* latitude/longitude
* location
* temperature/brightness temperature
* confidence
* predicted label
* class probabilities
* anomaly flag
* anomaly score
* source/sensor
* fire radiative power if available
* temporal persistence
* spatial characteristics
* industrial proximity
* historical events
* severity
* alert status

Only list fields that actually exist.

### 2. Grounding

The agent must NEVER invent:

* fire events
* coordinates
* temperatures
* confidence values
* industrial facilities
* timestamps
* classifications
* sensor observations

If information is unavailable, it should explicitly say so.

Audit the current implementation for hallucination risks.

### 3. Source attribution

Every factual answer should ideally be traceable to the underlying Fire Intelligence data.

For example:

> "3 high-confidence industrial-fire candidates were detected in the last 24 hours."

The user should be able to understand **where that information came from**.

Design a lightweight evidence/source mechanism if one doesn't exist.

Example:

**Evidence**

* Event: FI-0241
* Detected: 03 Sep 2026, 08:42 IST
* Classification: Industrial Fire
* Confidence: 91%
* Anomaly: High
* Location: XX

Do NOT expose fake evidence.

---

# PHASE 4 — READ-ONLY GUARANTEE

Audit whether the agent can accidentally:

* modify data
* delete records
* create events
* change classifications
* change alert severity
* execute arbitrary commands
* access secrets
* manipulate files
* call unintended tools

The agent should have a strict principle:

> OBSERVE → RETRIEVE → ANALYZE → EXPLAIN

Never:

> MODIFY → DELETE → EXECUTE → DEPLOY

Implement appropriate safeguards if necessary.

---

# PHASE 5 — QUERY UNDERSTANDING

Audit natural-language handling.

The agent should understand:

### Time queries

* today
* yesterday
* last 6 hours
* last 24 hours
* this week
* recent
* between two dates

### Geographic queries

* near this location
* within X km
* Hyderabad
* coordinates
* industrial area
* around this incident

### Severity queries

* high priority
* critical
* anomalous
* high confidence

### Classification queries

* industrial fire
* natural fire
* other thermal source
* unknown

### Investigation queries

* why?
* evidence?
* confidence?
* compare?
* summarize?
* what changed?
* repeated events?

If the current agent cannot reliably interpret these, improve the query-understanding layer.

Do NOT build an unnecessarily complex LLM framework.

Prefer a simple deterministic approach where appropriate:

Natural language
→ intent extraction
→ structured filters
→ database/data retrieval
→ deterministic calculations
→ LLM explanation

This should minimize hallucinations.

---

# PHASE 6 — AGENT RESPONSE QUALITY

Audit the response format.

Avoid generic responses such as:

> "Sure! I can help you with fire incidents."

The agent should behave like an operational intelligence assistant.

Responses should be:

* concise
* evidence-based
* structured
* decision-oriented
* transparent about uncertainty

For example:

**3 High-Priority Events Found**

| Event   | Classification  | Confidence | Anomaly | Time  |
| ------- | --------------- | ---------: | ------: | ----- |
| FI-0241 | Industrial Fire |        91% |    High | 08:42 |
| FI-0238 | Industrial Fire |        87% |    High | 06:17 |
| FI-0231 | Natural Fire    |        94% |     Low | 04:52 |

Then:

**Why FI-0241 is high priority**

* Industrial-fire probability: 91%
* Anomaly detected: Yes
* Persistent thermal signature: Yes
* Proximity to industrial zone: X km

Only display fields that actually exist.

---

# PHASE 7 — UNCERTAINTY & SAFETY

The agent should NOT make dangerous definitive claims.

Avoid:

> "There is definitely an industrial fire."

Prefer:

> "The system classified this event as an industrial-fire candidate with 91% confidence."

Clearly distinguish:

* observation
* model prediction
* inference
* recommendation

Example:

**Observed:** Thermal anomaly detected.

**Model prediction:** Industrial Fire — 91%.

**Inference:** Pattern is consistent with an industrial thermal event.

This distinction is important for a serious SIH prototype.

---

# PHASE 8 — AGENT UX

Audit the chat interface.

Look for:

* unclear input box
* poor empty state
* weak suggested questions
* excessive text
* poor hierarchy
* no loading state
* no error state
* no evidence display
* no event linking
* no way to jump from an answer to the event on the map
* poor mobile/desktop behavior
* generic chatbot styling
* unnecessary animations
* AI-slop visual design

Improve it toward:

**Mission Control / Geospatial Intelligence interface**

rather than:

**Generic AI chatbot.**

Suggested quick actions could include:

* 🔥 High-risk events
* 🕐 Last 24 hours
* 🗺 Nearby incidents
* ⚠ Anomalies
* 🏭 Industrial candidates
* 📊 System summary

But only implement features that make sense for the actual data.

---

# PHASE 9 — DASHBOARD AUDIT

After auditing the agent, perform a COMPLETE audit of the dashboard.

Review:

## Information architecture

Determine whether an operator can immediately understand:

1. What is happening?
2. Where?
3. How serious?
4. What changed recently?
5. Which events need attention?
6. Why should they trust the system?

The dashboard should communicate this within seconds.

---

# MAP AUDIT

Inspect:

* map readability
* marker hierarchy
* clustering
* industrial fire vs natural fire differentiation
* anomaly visualization
* selected-event behavior
* event detail interaction
* timeline
* filtering
* zoom behavior
* geographic context
* performance

Avoid excessive colored markers and visual noise.

The map should feel like an actual monitoring interface.

---

# EVENT / ALERT PANEL

Audit the event table/card.

It should expose meaningful intelligence such as:

* priority
* classification
* confidence
* anomaly
* timestamp
* location
* event ID

Avoid showing meaningless decorative metrics.

Add:

* sorting
* filtering
* search
* severity filtering
* classification filtering
* time filtering

ONLY if the underlying data supports them.

---

# EVENT DETAIL VIEW

When an event is selected, the user should be able to understand:

### What happened?

### Where?

### When?

### How confident is the model?

### Why was it classified this way?

### Is it anomalous?

### What evidence supports it?

Design this as an **incident intelligence panel**, not merely a database record.

---

# MODEL TRANSPARENCY

Because this is an ML-based SIH solution, the dashboard should make the ML understandable without overwhelming the user.

Where appropriate, show:

**Prediction**
Industrial Fire

**Probability**
91%

**Alternative classes**
Natural Fire — 6%
Other Thermal — 3%

**Anomaly**
Detected

**Key contributing signals**
Only if these are actually available from the model.

Do NOT fabricate explainability.

---

# SYSTEM HEALTH / DATA FRESHNESS

Check whether the dashboard communicates:

* last data update
* number of events
* active alerts
* model status
* data freshness
* processing status

If the system is a prototype and data is simulated/replayed, label it honestly.

Never pretend simulated data is live.

---

# VISUAL DESIGN DIRECTION

Improve the dashboard toward:

**Professional geospatial intelligence / emergency operations center**

Not:

* generic SaaS dashboard
* AI chatbot aesthetic
* excessive gradients
* purple/blue AI-slop styling
* oversized rounded cards
* unnecessary glassmorphism
* excessive icons
* childish colors

Prioritize:

* strong typography
* restrained palette
* clear hierarchy
* dark/light contrast where appropriate
* subtle borders
* dense but readable information
* purposeful whitespace
* consistent spacing
* meaningful color semantics

Red/orange should communicate actual risk, not decoration.

---

# PHASE 10 — SIH JURY PERSPECTIVE

After the technical audit, review the entire system as if you were an SIH jury member seeing it for the first time.

Answer:

1. What is genuinely impressive?
2. What looks like a basic dashboard?
3. What looks fake or hardcoded?
4. What would a jury challenge?
5. What questions would they ask?
6. Where could they catch us exaggerating?
7. What feature would provide the strongest "wow" factor?
8. What feature is unnecessary and should be removed?
9. What demonstrates actual ML rather than UI?
10. What demonstrates operational usefulness?
11. Does the agent meaningfully enhance the core solution?
12. Does the complete system tell a convincing end-to-end story?

---

# PHASE 11 — PRIORITIZED IMPROVEMENTS

Do NOT simply dump a huge list of suggestions.

Categorize improvements into:

### P0 — Critical

Must fix before judging/demo.

### P1 — High Value

Strongly improves technical credibility or UX.

### P2 — Nice to Have

Useful but not essential.

### DON'T BUILD

Features that sound impressive but add unnecessary complexity, risk, or demo fragility.

For every recommendation explain:

* Problem
* Proposed solution
* Why it matters
* Implementation complexity
* Expected jury impact

---

# PHASE 12 — IMPLEMENTATION

After completing the audit:

1. Fix genuine bugs.
2. Fix broken agent behavior.
3. Improve grounding.
4. Improve query handling.
5. Improve response structure.
6. Add evidence/source references.
7. Enforce read-only behavior.
8. Improve dashboard UX where clearly justified.
9. Improve visual hierarchy.
10. Preserve existing working ML/data pipeline.
11. Do NOT rewrite functioning components merely for the sake of rewriting.
12. Do NOT introduce unnecessary dependencies.
13. Do NOT create fake data to make the system look better.
14. Do NOT claim real-time capabilities if the system isn't actually real-time.
15. Do NOT introduce external APIs merely because they are available.

Maintain the current architecture unless there is a compelling technical reason to change it.

---

# IMPORTANT ENGINEERING RULES

## No hallucinated functionality

Never write:

> "Implemented X"

unless X actually works.

## No fake metrics

Never invent:

* accuracy
* precision
* recall
* number of detections
* response time
* sensor coverage
* live status
* confidence
* fire events

## No unnecessary overengineering

We have a limited SIH development timeline.

Prefer:

simple + reliable + explainable

over:

complex + impressive-looking + fragile.

## Preserve the core ML system

Do not damage or replace the existing:

* feature engineering
* Random Forest classification
* prediction probabilities
* anomaly logic
* event pipeline

unless you identify a genuine bug.

---

# REQUIRED FINAL REPORT

Before finishing, provide a report in this structure:

## 1. Current Architecture

Briefly explain what the system actually does.

## 2. Agent Audit

| Area                     | Status | Problem | Severity |
| ------------------------ | ------ | ------- | -------- |
| Grounding                |        |         |          |
| Retrieval                |        |         |          |
| Query understanding      |        |         |          |
| Hallucination resistance |        |         |          |
| Read-only safety         |        |         |          |
| Response quality         |        |         |          |
| Evidence                 |        |         |          |
| UX                       |        |         |          |

## 3. Dashboard Audit

Same format.

## 4. Top 10 Problems

Rank them by importance.

## 5. Changes Implemented

Clearly separate actual implemented changes from suggestions.

## 6. Recommended Next Improvements

P0 / P1 / P2 / DON'T BUILD

## 7. Jury Perspective

Explain exactly how the improved system would appear to an SIH jury.

## 8. Demo Flow

Give us the strongest 2–3 minute demonstration flow showing:

Detection
→ Classification
→ Risk
→ Map
→ Incident details
→ Agent investigation
→ Evidence
→ Operator decision

## 9. Remaining Risks

Be brutally honest.

---

# FINAL PRINCIPLE

The objective is NOT to make the Fire Intelligence dashboard look more complicated.

The objective is to make it feel like a **credible operational intelligence system** where:

**Satellite/thermal observation → ML classification → anomaly detection → geospatial event → risk prioritization → human investigation through the read-only intelligence agent**

forms one coherent story.

Think like an engineer, operator, ML reviewer, UX designer, and skeptical SIH jury member simultaneously.

Start by auditing the existing codebase. Do not make major changes until you understand what is already implemented.
