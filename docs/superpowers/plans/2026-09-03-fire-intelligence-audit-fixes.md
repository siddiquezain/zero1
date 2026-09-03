# Fire Intelligence — Audit Fixes & Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all confirmed bugs and implement every audit improvement from audit.md across the agent, dashboard, and UX layers — without touching the ML pipeline.

**Architecture:** Single-file edits only — each task targets one specific file and one specific problem. No new dependencies, no new files, no new abstractions.

**Tech Stack:** Python, Streamlit, HTML/CSS (inline), regex, the existing src/ intelligence stack.

---

## Pre-flight: What We Are NOT Touching

- `src/model/` — Random Forest pipeline (working correctly)
- `src/alerting/pipeline.py` — alert ingestion (working)
- `src/alerting/alert_store.py` — SQLite store (working)
- `src/features/engineer.py` — feature engineering (working)
- `data/` — any parquet/joblib/db files (real data, do not corrupt)
- `src/intelligence/geo.py` — geo resolver (working)
- `src/intelligence/queries.py` — read-only data layer (working)
- `src/intelligence/actions.py` — read-only exports (working)
- `src/intelligence/agent/tools.py` — tool registry (read-only, correct)

---

## File Map

| File | What changes |
|---|---|
| `src/intelligence/agent/claude.py` | Fix model name `claude-sonnet-5` → `claude-sonnet-4-6` |
| `dashboard/agent/panel.py` | Fix bold rendering + agent status indicator + example queries |
| `dashboard/shell.py` | Fix misleading "LIVE" indicator → "NRT SNAPSHOT" |
| `src/intelligence/agent/response.py` | Improve evidence cards + Observed/Prediction/Inference framing + italic fix |
| `dashboard/views/investigation.py` | Clarify classification labels + italic framing fix |
| `dashboard/theme.py` | Add amber dot style for NRT status |

---

## Task 1: Fix Claude Model Name Bug

**Files:**
- Modify: `src/intelligence/agent/claude.py:19`

**Problem:** `_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")` — `claude-sonnet-5` does not exist. Claude mode silently falls back to deterministic every time it tries to use this. The correct current model is `claude-sonnet-4-6`.

- [ ] **Step 1: Edit the model default**

In `src/intelligence/agent/claude.py`, change line 19 from:
```python
_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
```
to:
```python
_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
```

- [ ] **Step 2: Verify the change**

Run:
```bash
grep -n "claude-sonnet" src/intelligence/agent/claude.py
```
Expected: `19:_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")`

- [ ] **Step 3: Commit**

```bash
git add src/intelligence/agent/claude.py
git commit -m "fix: correct claude model name from claude-sonnet-5 to claude-sonnet-4-6"
```

---

## Task 2: Fix Bold Text Stripping in Agent Panel

**Files:**
- Modify: `dashboard/agent/panel.py:117-118`

**Problem:** Line 118 does `replace("**", "")` which strips ALL markdown bold markers from every agent response. Every `**important**` becomes `important` — unformatted, indistinguishable from plain text. The fix: convert `**text**` to `<strong>text</strong>` before escaping, OR escape first then convert the escaped form.

The safe approach: escape HTML first, then replace `**` with `<strong>`/`</strong>` alternating. Use `re.sub` with a pattern.

- [ ] **Step 1: Add `re` import to panel.py**

In `dashboard/agent/panel.py`, the file already imports `html as _html`. Add `import re` to the imports section at the top (after the existing `import` block, near line 27).

Current imports block ends around line 31:
```python
import streamlit as st

from dashboard import data, state
from dashboard.components import ui
```

Add `import re` above `import streamlit as st`:
```python
import re

import streamlit as st

from dashboard import data, state
from dashboard.components import ui
```

- [ ] **Step 2: Replace the bold-stripping line**

Find this block in `panel.py` (around line 117-118):
```python
    body = _html.escape(m["text"]).replace("\n", "<br>").replace("**", "")
    st.markdown(f'<div class="agent-msg-bot">{body}</div>', unsafe_allow_html=True)
```

Replace with:
```python
    # Convert **bold** → <strong>bold</strong> before HTML escaping would break it.
    # Strategy: escape first, then map the escaped ** to strong tags alternately.
    raw = m["text"]
    body = re.sub(r'\*\*([^*\n]+)\*\*', r'<strong>\1</strong>', raw)
    body = _html.escape(body).replace("&lt;strong&gt;", "<strong>").replace("&lt;/strong&gt;", "</strong>")
    body = body.replace("\n", "<br>")
    st.markdown(f'<div class="agent-msg-bot">{body}</div>', unsafe_allow_html=True)
```

Wait — that approach double-escapes. Correct approach: do the `**` → `<strong>` substitution before any HTML escaping, then escape everything *except* the already-generated tags.

Better approach — substitute first, then escape the non-HTML parts:

```python
    # Render **bold** as <strong> in the HTML output.
    # We substitute before html.escape so the tags survive.
    raw = m["text"]
    # Replace **text** with a placeholder, escape, restore tags
    raw = re.sub(r'\*\*([^*\n]+)\*\*', r'\x00BOLD\x00\1\x00ENDBOLD\x00', raw)
    body = _html.escape(raw)
    body = body.replace('\x00BOLD\x00', '<strong>').replace('\x00ENDBOLD\x00', '</strong>')
    body = body.replace("\n", "<br>")
    st.markdown(f'<div class="agent-msg-bot">{body}</div>', unsafe_allow_html=True)
```

- [ ] **Step 3: Verify no double-escaping**

Check the file reads correctly:
```bash
grep -n "BOLD\|escape\|replace" dashboard/agent/panel.py | head -20
```

Expected: the three placeholder lines are present and the old `replace("**", "")` is gone.

- [ ] **Step 4: Commit**

```bash
git add dashboard/agent/panel.py
git commit -m "fix: render **bold** as <strong> in agent panel instead of stripping"
```

---

## Task 3: Fix Misleading "LIVE" Status Indicator

**Files:**
- Modify: `dashboard/shell.py:60`
- Modify: `dashboard/theme.py` (add amber dot colour constant)

**Problem:** The topbar shows a pulsing green "LIVE" dot. The data is a fixed 5-day NRT snapshot ingested August 2026 — it is not a live feed. The jury will ask "is this live?". The correct answer is "NRT snapshot" (Near Real Time — NASA FIRMS terminology). The dot should be amber, not green (green = confirmed live operational feed).

The data window is already shown in the topbar (`window {lo} → {hi}`), so we only need to change the label and dot colour.

- [ ] **Step 1: Update the "LIVE" pill in shell.py**

In `dashboard/shell.py`, find the topbar function (around line 55-70). The current pill:
```python
        f'<span class="tb-pill"><span class="dot"></span>LIVE</span>'
```

Replace with:
```python
        f'<span class="tb-pill"><span class="dot" style="background:#f59e0b;box-shadow:0 0 0 3px rgba(245,158,11,0.2)"></span>NRT SNAPSHOT</span>'
```

The amber colour matches `T.HIGH` (`#f59e0b`) — semantically: NRT data is not stale, but it's also not a live wire feed. Amber is honest.

- [ ] **Step 2: Update the CSS dot default in theme.py**

The `.dot` class in `theme.py` currently defaults to `background:var(--low)` (green). Since the sidebar topbar now uses an inline style override, no change to the CSS is needed — but add a note for clarity. No change needed in theme.py.

- [ ] **Step 3: Verify**

```bash
grep -n "LIVE\|NRT SNAPSHOT\|tb-pill" dashboard/shell.py
```

Expected: `LIVE` no longer appears; `NRT SNAPSHOT` is present.

- [ ] **Step 4: Commit**

```bash
git add dashboard/shell.py
git commit -m "fix: replace misleading LIVE indicator with NRT SNAPSHOT (amber) — data is a fixed 5-day NRT window"
```

---

## Task 4: Fix Agent Status — Show Actual Mode (CLAUDE vs LOCAL)

**Files:**
- Modify: `dashboard/agent/panel.py:153-155`

**Problem:** The agent header always shows `<i></i>ONLINE` with a green dot. This is wrong in two ways:
1. The green dot implies Claude is online, even when `ANTHROPIC_API_KEY` is absent.
2. "ONLINE" is ambiguous — does it mean the platform is up, or Claude is connected?

Fix: show `CLAUDE` (blue dot) when Claude is actually available, `LOCAL` (amber dot) otherwise.

- [ ] **Step 1: Update the agent header HTML in panel.py**

Find the header block in `panel.py` around line 152-155:
```python
    name = ('<span class="agent-h-name">Fire Intelligence Agent</span>'
            if collapsible else "<span></span>")
    st.markdown(f'<div class="agent-head">{name}'
                '<span class="agent-status"><i></i>ONLINE</span></div>',
                unsafe_allow_html=True)
```

Replace with:
```python
    name = ('<span class="agent-h-name">Fire Intelligence Agent</span>'
            if collapsible else "<span></span>")
    if online:
        status_dot = f'<i style="background:#3d7dc8;box-shadow:0 0 0 3px rgba(61,125,200,0.22)"></i>'
        status_label = "CLAUDE"
    else:
        status_dot = f'<i style="background:#f59e0b;box-shadow:0 0 0 3px rgba(245,158,11,0.18)"></i>'
        status_label = "LOCAL"
    st.markdown(f'<div class="agent-head">{name}'
                f'<span class="agent-status">{status_dot}{status_label}</span></div>',
                unsafe_allow_html=True)
```

Note: `online` is already computed above this block (`online = _agent_is_online()`).

- [ ] **Step 2: Verify**

```bash
grep -n "ONLINE\|status_dot\|status_label\|CLAUDE\|LOCAL" dashboard/agent/panel.py
```

Expected: `ONLINE` no longer appears in the header block; `CLAUDE`/`LOCAL` logic present.

- [ ] **Step 3: Commit**

```bash
git add dashboard/agent/panel.py
git commit -m "fix: agent status shows CLAUDE (blue) or LOCAL (amber) based on actual availability"
```

---

## Task 5: Add Alert ID and Confidence % to Agent Evidence Cards

**Files:**
- Modify: `src/intelligence/agent/response.py:30-43`

**Problem:** The audit requires evidence in the form:
```
Event: FI-0241
Classification: Industrial Fire
Confidence: 91%
Anomaly: High
```

The current `_alert_card` subtitle is:
```
"{severity} · Risk {risk_score}/100 · FRP {frp_mw} MW · Persist {persistence_count}x · {acq_date}"
```

It's missing: `alert_id` (so user can't trace back), confidence %, and explicit anomaly label.

- [ ] **Step 1: Update `_alert_card` in response.py**

Find the `_alert_card` function in `src/intelligence/agent/response.py` (lines 30-43):
```python
def _alert_card(a: dict, actions: list[str] | None = None) -> dict:
    loc = a.get("place") or a.get("state") or a.get("zone") \
          or f"{a['lat']:.3f}, {a['lon']:.3f}"
    sub = (f"{a['severity']} · Risk {a['risk_score']}/100 · "
           f"FRP {a['frp_mw'] if a['frp_mw'] is not None else '—'} MW · "
           f"Persist {a['persistence_count']}x · {a['acq_date']}")
    return {
        "title": f"{a['output_class_short']} — {loc}",
        "subtitle": sub,
        "alert_id": a["alert_id"],
        "lat": a["lat"], "lon": a["lon"],
        "severity": a["severity"],
        "actions": actions or _ACTIONS_FULL,
    }
```

Replace with:
```python
def _alert_card(a: dict, actions: list[str] | None = None) -> dict:
    loc = a.get("place") or a.get("state") or a.get("zone") \
          or f"{a['lat']:.3f}, {a['lon']:.3f}"
    conf_pct = round((a.get("model_class_probability") or 0) * 100)
    anomaly_label = "YES ⚠" if a.get("anomaly_flag") else "no"
    frp_str = f"{a['frp_mw']} MW" if a['frp_mw'] is not None else "—"
    sub = (
        f"{a['alert_id']} · {a['severity']} · Confidence {conf_pct}% · "
        f"Risk {a['risk_score']}/100 · Anomaly {anomaly_label} · "
        f"FRP {frp_str} · {a['acq_date']}"
    )
    return {
        "title": f"{a['output_class_short']} — {loc}",
        "subtitle": sub,
        "alert_id": a["alert_id"],
        "lat": a["lat"], "lon": a["lon"],
        "severity": a["severity"],
        "actions": actions or _ACTIONS_FULL,
    }
```

- [ ] **Step 2: Verify**

```bash
grep -n "conf_pct\|anomaly_label\|Confidence\|Anomaly" src/intelligence/agent/response.py
```

Expected: the three new variable lines and updated subtitle string are present.

- [ ] **Step 3: Commit**

```bash
git add src/intelligence/agent/response.py
git commit -m "feat: add alert_id, confidence %, and anomaly flag to agent evidence cards"
```

---

## Task 6: Fix Italic/Framing Text Rendering in Agent Response and Investigation

**Files:**
- Modify: `src/intelligence/agent/response.py:147` (investigation framing)
- Modify: `dashboard/views/investigation.py:131` (classification framing)

**Problem:** Both files output text like `f"_{inv['classification']['framing']}_"`. In plain text this renders as `_text_` — underscores are visible. The investigation view renders this into a `<div class="mini">` with `unsafe_allow_html=True`, so `<em>` tags would work. The agent panel escapes the text and renders underscores literally.

Fix 1 (response.py): In the agent response for investigation, don't wrap in underscores — just emit the framing text as its own plain paragraph (the `build()` method already makes it part of `reply.text` which goes through the bold-rendering pipeline fixed in Task 2).

Fix 2 (investigation.py): Replace `_text_` with proper `<em>` tag inside the already-HTML `mini` div.

- [ ] **Step 1: Fix investigation.py framing**

In `dashboard/views/investigation.py`, find around line 130-132:
```python
        st.markdown(f'<div class="mini" style="line-height:1.6;margin-top:6px">'
                    f'<em>{cl["framing"]}</em></div>', unsafe_allow_html=True)
```

This is actually already correct — it uses `<em>` tags! No change needed here.

- [ ] **Step 2: Fix response.py investigation framing**

In `src/intelligence/agent/response.py`, find the investigation `it` block around line 140-157. The last line of the reply text:
```python
        reply.text = (
            f"**{h['output_class_short']} near {h['location']}** — "
            f"risk {h['risk_score']}/100 ({h['severity']}), model class probability "
            f"{h['model_class_probability_pct']}%, status {h['status']}.\n\n"
            "Flagged because: " + ("; ".join(why) if why else "limited supporting signals") + ".\n\n"
            f"Recommended: **{inv['recommended_action']['action']}** — "
            f"{inv['recommended_action']['reason']}\n\n"
            f"_{inv['classification']['framing']}_"
        )
```

The trailing `f"_{inv['classification']['framing']}_"` renders as `_text_` in the HTML panel. Replace the final framing line and structure the text with proper Observed/Prediction/Inference format:

```python
        prob_pct = h['model_class_probability_pct']
        why_text = "; ".join(why) if why else "limited supporting signals"
        reply.text = (
            f"**{h['output_class_short']} near {h['location']}**\n\n"
            f"Observed: Thermal anomaly detected · {inv['detection']['acq_date']} · "
            f"{inv['detection']['day_night']} · FRP {inv['detection']['frp_mw'] or '—'} MW\n\n"
            f"Model prediction: {h['output_class_short']} — {prob_pct}% confidence · "
            f"Anomaly flag {'YES' if inv['classification']['anomaly_flag'] else 'no'} · "
            f"Risk {h['risk_score']}/100 ({h['severity']})\n\n"
            f"Flagged because: {why_text}\n\n"
            f"Recommended: **{inv['recommended_action']['action']}** — "
            f"{inv['recommended_action']['reason']}\n\n"
            f"Note: {inv['classification']['framing']}"
        )
```

- [ ] **Step 3: Verify**

```bash
grep -n "framing\|Observed\|prediction\|Note:" src/intelligence/agent/response.py | head -15
```

Expected: the old `f"_{inv['classification']['framing']}_"` is gone; `Observed:`, `Model prediction:`, and `Note:` lines are present.

- [ ] **Step 4: Commit**

```bash
git add src/intelligence/agent/response.py dashboard/views/investigation.py
git commit -m "fix: replace underscore italic framing with Observed/Prediction/Note structure in agent investigation response"
```

---

## Task 7: Clarify Classification Labels in Investigation View

**Files:**
- Modify: `dashboard/views/investigation.py:121-130`

**Problem:** Current classification labels:
- `"P(persistent / A)"` — cryptic, uses internal model label `A`
- `"P(natural / B)"` — same
- `"Anomaly flag"` — `"yes"` / `"no"` — too minimal

Operators need to understand: Class A = Industrial/Persistent, Class B = Natural Fire. Also "anomaly" should be flagged more clearly.

- [ ] **Step 1: Update classification kv block**

In `dashboard/views/investigation.py`, find around lines 121-130:
```python
        ui.section("Classification")
        cl = inv["classification"]
        _kv([
            ("Output class", h["output_class_short"]),
            ("Model label", cl["predicted_label"] or "—"),
            ("P(persistent / A)", f'{cl["prob_A"]}'),
            ("P(natural / B)", f'{cl["prob_B_candidate"]}'),
            ("Anomaly flag", "yes" if cl["anomaly_flag"] else "no"),
        ])
        st.markdown(f'<div class="mini" style="line-height:1.6;margin-top:6px">'
                    f'<em>{cl["framing"]}</em></div>', unsafe_allow_html=True)
```

Replace with:
```python
        ui.section("Classification")
        cl = inv["classification"]
        prob_a_pct = round((cl["prob_A"] or 0) * 100)
        prob_b_pct = round((cl["prob_B_candidate"] or 0) * 100)
        anomaly_val = "YES — pattern anomaly ⚠" if cl["anomaly_flag"] else "no"
        _kv([
            ("Model classification", h["output_class_short"]),
            ("Raw model label", cl["predicted_label"] or "—"),
            ("P(Industrial / Persistent — A)", f"{prob_a_pct}%"),
            ("P(Natural Fire — B)", f"{prob_b_pct}%"),
            ("Anomaly detected", anomaly_val),
        ])
        st.markdown(f'<div class="mini" style="line-height:1.6;margin-top:6px">'
                    f'<em>{cl["framing"]}</em></div>', unsafe_allow_html=True)
```

- [ ] **Step 2: Verify**

```bash
grep -n "prob_a_pct\|prob_b_pct\|anomaly_val\|P(Industrial\|P(Natural" dashboard/views/investigation.py
```

Expected: all four new variable/label lines present.

- [ ] **Step 3: Commit**

```bash
git add dashboard/views/investigation.py
git commit -m "fix: clarify classification labels in investigation panel — show prob % and readable class names"
```

---

## Task 8: Add Alert ID to Alert Cards in UI (alert_card helper)

**Files:**
- Modify: `dashboard/components/ui.py:46-70`

**Problem:** The alert card HTML doesn't show the `alert_id` (e.g. `FI-0241`). The audit requires that every factual answer is traceable. If an alert is shown on the dashboard without its ID, an operator can't reference it when calling for field verification or cross-referencing with the agent.

The `alert_id` is in the data dict — just not displayed. Add it as a small monospace label next to the severity chip.

- [ ] **Step 1: Update alert_card in ui.py**

In `dashboard/components/ui.py`, find the `alert_card` function (lines 46-70). The current first row of the card HTML:
```python
    st.markdown(
        f'<div class="acard" style="border-left-color:{c}">'
        f'<div class="r1">{T.sev_chip(sev)}'
        f'<span class="title">{_esc(title)}</span>'
        f'<span style="margin-left:auto" class="ago">{_esc(ago)}</span></div>'
```

Replace the `<div class="r1">` line to include the alert_id as a monospace badge:
```python
    aid_short = str(a.get("alert_id", ""))[:10]  # e.g. "FI-2026082"
    st.markdown(
        f'<div class="acard" style="border-left-color:{c}">'
        f'<div class="r1">{T.sev_chip(sev)}'
        f'<span class="title">{_esc(title)}</span>'
        f'<span style="font-family:var(--mono);font-size:9.5px;color:var(--t2);margin-left:6px">{_esc(aid_short)}</span>'
        f'<span style="margin-left:auto" class="ago">{_esc(ago)}</span></div>'
```

- [ ] **Step 2: Verify**

```bash
grep -n "aid_short\|alert_id\|r1\|div class" dashboard/components/ui.py | head -20
```

Expected: `aid_short` present, included in the HTML row.

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/ui.py
git commit -m "feat: show alert ID in alert cards for traceability"
```

---

## Task 9: Improve Agent Example Queries (Operational Quick-Actions)

**Files:**
- Modify: `dashboard/agent/panel.py:32-38`

**Problem:** The 5 example queries in `_EXAMPLES` are good but not varied enough — they all lean toward Odisha and industrial fires. The audit wants quick actions covering: high-risk events, last 24 hours, anomalies, industrial candidates, system summary. Expand and rebalance.

- [ ] **Step 1: Update `_EXAMPLES`**

In `dashboard/agent/panel.py`, find around line 32-38:
```python
_EXAMPLES = [
    "Show critical industrial fires in Odisha in the last 7 days",
    "Find persistent sources near thermal power plants",
    "Why is the Surat alert critical?",
    "Compare Odisha and Jharkhand",
    "Generate report for high-risk incidents this week",
]
```

Replace with:
```python
_EXAMPLES = [
    "Show all critical and high alerts",
    "Which alerts have anomaly flags?",
    "Find persistent sources near thermal power plants",
    "Show industrial fire candidates in the last 3 days",
    "Compare eastern india and central india",
    "What is the system summary?",
    "Why is the highest-risk alert flagged?",
    "Generate report for high-risk incidents",
]
```

- [ ] **Step 2: Verify**

```bash
grep -n "_EXAMPLES" dashboard/agent/panel.py
```

Expected: 8 entries present, none duplicated.

- [ ] **Step 3: Commit**

```bash
git add dashboard/agent/panel.py
git commit -m "feat: expand agent example queries to cover anomalies, summary, time, and region comparisons"
```

---

## Task 10: Fix Agent Note Text — Show Claude vs Local Mode Correctly

**Files:**
- Modify: `dashboard/agent/panel.py:164-169`

**Problem:** The agent note below the robot stage shows:
```python
f'{"Claude-enhanced reasoning" if online else "Local intelligence mode"}'
f' · read-only · same data as the dashboard'
```
This is correct conceptually but should be slightly more informative for the jury — specify which model when Claude is active.

- [ ] **Step 1: Update the note text**

Find around line 165-169 in `dashboard/agent/panel.py`:
```python
    st.markdown(
        f'<div class="agent-note">{"Claude-enhanced reasoning" if online else "Local intelligence mode"}'
        f' · read-only · same data as the dashboard</div>',
        unsafe_allow_html=True,
    )
```

Replace with:
```python
    from src.intelligence.agent.claude import _MODEL as _claude_model
    mode_note = f"Claude {_claude_model} · tool-use reasoning" if online else "Deterministic parser · offline mode"
    st.markdown(
        f'<div class="agent-note">{mode_note}'
        f' · read-only · same data as the dashboard</div>',
        unsafe_allow_html=True,
    )
```

- [ ] **Step 2: Verify**

```bash
grep -n "mode_note\|_claude_model\|tool-use\|Deterministic" dashboard/agent/panel.py
```

Expected: all three lines present.

- [ ] **Step 3: Commit**

```bash
git add dashboard/agent/panel.py
git commit -m "feat: agent note shows actual Claude model name when in Claude mode"
```

---

## Task 11: Improve Map Tooltip — Show Alert ID

**Files:**
- Modify: `dashboard/components/mapview.py:72-78`

**Problem:** Map tooltip does not show the alert ID. When an operator hovers a point, they see classification + severity + risk + FRP but not the ID they'd need to look up in the Alerts feed. Adding the alert_id makes the map surface traceable.

- [ ] **Step 1: Update the tooltip in mapview.py**

Find around line 72-77 in `dashboard/components/mapview.py`:
```python
        df["tip"] = df.apply(lambda r: (
            f"{_s(r['output_class_short'])}  -  {_s(r['severity'])}  -  Risk {r['risk_score']}/100\n"
            f"{_s(r.get('place')) or _s(r.get('state')) or _s(r.get('zone')) or '-'}\n"
            f"FRP {r['frp_mw'] if pd.notna(r['frp_mw']) else '-'} MW  -  "
            f"Persist {int(r['persistence_count'])}x  -  {_s(r['acq_date'])}"
        ), axis=1)
```

Replace with:
```python
        df["tip"] = df.apply(lambda r: (
            f"{_s(r['alert_id'])}  -  {_s(r['output_class_short'])}\n"
            f"{_s(r['severity'])}  -  Risk {r['risk_score']}/100\n"
            f"{_s(r.get('place')) or _s(r.get('state')) or _s(r.get('zone')) or '-'}\n"
            f"FRP {r['frp_mw'] if pd.notna(r['frp_mw']) else '-'} MW  -  "
            f"Persist {int(r['persistence_count'])}x  -  {_s(r['acq_date'])}"
        ), axis=1)
```

- [ ] **Step 2: Verify**

```bash
grep -n "alert_id\|tip\|output_class_short" dashboard/components/mapview.py | head -10
```

Expected: `alert_id` appears in the tip lambda.

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/mapview.py
git commit -m "feat: add alert ID to map hover tooltip for traceability"
```

---

## Task 12: Final Audit Report

After all tasks are complete, produce the required audit report.

- [ ] **Step 1: Run the app and verify it starts**

```bash
cd /Users/zain/SIH-2026
streamlit run dashboard/app.py --server.headless true &
sleep 5
curl -s http://localhost:8501 | head -5
kill %1
```

Expected: HTML response received (200 OK).

- [ ] **Step 2: Run existing tests**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 3: Verify no regressions in agent grounding**

Manually check the test files for agent deterministic tests:
```bash
python -m pytest tests/test_agent_deterministic.py tests/test_intelligence_queries.py -v 2>&1 | tail -20
```

Expected: all pass.

---

## Self-Review Against Audit Spec

| Audit Requirement | Task | Status |
|---|---|---|
| Claude model name correct | Task 1 | ✓ |
| Bold text rendered in agent | Task 2 | ✓ |
| No misleading "LIVE" claim | Task 3 | ✓ |
| Agent status reflects actual mode | Task 4 | ✓ |
| Evidence cards include alert_id + confidence | Task 5 | ✓ |
| Observed/Prediction framing in investigation response | Task 6 | ✓ |
| Classification labels readable | Task 7 | ✓ |
| Alert_id visible in alert cards | Task 8 | ✓ |
| Varied operational quick-action queries | Task 9 | ✓ |
| Agent note shows model name | Task 10 | ✓ |
| Map tooltip includes alert_id | Task 11 | ✓ |
| Read-only guarantee | NOT CHANGED — already correct | ✓ |
| Hallucination resistance | NOT CHANGED — already correct | ✓ |
| Query understanding | NOT CHANGED — already correct | ✓ |
| Model transparency | NOT CHANGED — already correct (Model page) | ✓ |
| Limitations page honest | NOT CHANGED — already excellent | ✓ |
| ML pipeline untouched | NOT CHANGED — as required | ✓ |

## DON'T BUILD

- **Real-time data feed**: Would require NASA FIRMS API key management, infrastructure. Demo fragile. Current NRT snapshot approach is honest and stable.
- **LLM-based free-text explainability**: No SHAP/LIME for the Random Forest — the existing additive risk engine already provides deterministic, traceable explanations.
- **Alert clustering on map**: Complex, not needed for a 700-point India dataset.
- **BB-8 robot removal**: The user intentionally added it; it works offline; it's already static/non-animating. Removing would require rebuilding the agent panel UX from scratch.
- **External API integrations**: Audit.md explicitly says "Do NOT introduce external APIs merely because they are available."
- **New database tables or schemas**: No schema changes needed.
