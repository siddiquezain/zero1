"""Investigation — deep-dive: event context, fingerprint, evidence,
evolution replay, risk trajectory, early warning, detection details.
All values from real data only — nothing fabricated."""
from __future__ import annotations

import pydeck as pdk
import streamlit as st

from dashboard import data, state
from dashboard import theme as T
from dashboard.components import mapview, ui
from dashboard.shell import topbar

_EW_COLORS = {
    "HIGH PRIORITY": T.CRIT,
    "EARLY WARNING": "#f97316",
    "INCREASING": T.HIGH,
    "WATCH": T.MED,
    "STABLE": T.LOW,
    "DECREASING": T.LOW,
    "INSUFFICIENT DATA": T.T2,
    "UNKNOWN": T.T2,
}

_FP_COLORS = {
    "VERY HIGH": T.CRIT,
    "HIGH": T.HIGH,
    "MEDIUM": T.MED,
    "LOW": T.LOW,
    "VERY LOW": "#5a6472",
    "UNKNOWN": T.T2,
}

_DEV_COLORS = {
    "HIGHLY_ABNORMAL": T.CRIT,
    "ABNORMAL": "#f97316",
    "ELEVATED": T.MED,
    "NORMAL": T.LOW,
    "INSUFFICIENT_BASELINE": T.T2,
    "NO_FACILITY": T.T2,
}


def _kv(rows: list[tuple[str, str]]) -> None:
    body = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:5px 0;'
        f'border-bottom:1px solid {T.BORDER}"><span style="color:{T.T1};font-size:11px">{k}</span>'
        f'<span style="font-family:var(--mono);font-size:11px;color:{T.T0}">{v}</span></div>'
        for k, v in rows
    )
    st.markdown(f'<div class="panel">{body}</div>', unsafe_allow_html=True)


def _fp_row(label: str, level: str) -> str:
    color = _FP_COLORS.get(level, T.T2)
    return (
        f'<div style="display:flex;justify-content:space-between;padding:5px 0;'
        f'border-bottom:1px solid {T.BORDER}">'
        f'<span style="color:{T.T1};font-size:11px">{label}</span>'
        f'<span style="font-family:var(--mono);font-size:11px;font-weight:700;color:{color}">'
        f'{level}</span></div>'
    )


def _render_fingerprint(fp: dict) -> None:
    ui.section("Thermal Behaviour Fingerprint")
    rows = [
        ("Persistence", fp.get("persistence", "UNKNOWN")),
        ("Night Activity", fp.get("night_activity", "UNKNOWN")),
        ("FRP Intensity", fp.get("frp_intensity", "UNKNOWN")),
        ("Spatial Stability", fp.get("spatial_stability", "UNKNOWN")),
        ("Industrial Proximity", fp.get("industrial_proximity", "UNKNOWN")),
        ("Seasonal Alignment", fp.get("seasonal_alignment", "UNKNOWN")),
    ]
    body = "".join(_fp_row(lbl, lvl) for lbl, lvl in rows)
    cat = fp.get("behaviour_category", "—")
    st.markdown(
        f'<div class="panel">{body}'
        f'<div style="margin-top:10px;padding-top:8px;border-top:1px solid {T.BORDER_2}">'
        f'<span style="font-size:10px;letter-spacing:.1em;color:{T.T2}">BEHAVIOUR ASSESSMENT</span>'
        f'<div style="font-size:13px;font-weight:700;margin-top:4px">{cat}</div>'
        f'<div style="font-size:10px;color:{T.T2};margin-top:2px;line-height:1.5">'
        f'Behavioural assessment only — not ground truth confirmation.</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def _render_evidence(ev: dict) -> None:
    ui.section("Evidence Stack")
    with st.expander(
            f"✓ {ev['total_supporting']} supporting  ·  "
            f"! {ev['total_limiting']} limiting", expanded=True):
        if ev["supporting"]:
            st.markdown(
                f'<div style="font-size:10px;letter-spacing:.09em;color:{T.LOW};'
                f'font-weight:700;margin-bottom:4px">SUPPORTING</div>',
                unsafe_allow_html=True,
            )
            for item in ev["supporting"]:
                st.markdown(
                    f'<div style="padding:4px 0 6px;border-bottom:1px solid {T.BORDER}">'
                    f'<div style="display:flex;gap:6px;align-items:baseline">'
                    f'<span style="color:{T.LOW};font-size:12px">✓</span>'
                    f'<span style="font-size:11.5px;font-weight:600">{item["label"]}</span>'
                    f'<span style="font-family:var(--mono);font-size:10px;color:{T.T1}">'
                    f'{item["value"]}</span></div>'
                    f'<div style="font-size:10px;color:{T.T2};margin-left:18px;line-height:1.5">'
                    f'{item["explanation"]}</div></div>',
                    unsafe_allow_html=True,
                )
        if ev["limiting"]:
            st.markdown(
                f'<div style="font-size:10px;letter-spacing:.09em;color:{T.MED};'
                f'font-weight:700;margin-top:10px;margin-bottom:4px">LIMITING</div>',
                unsafe_allow_html=True,
            )
            for item in ev["limiting"]:
                st.markdown(
                    f'<div style="padding:4px 0 6px;border-bottom:1px solid {T.BORDER}">'
                    f'<div style="display:flex;gap:6px;align-items:baseline">'
                    f'<span style="color:{T.MED};font-size:12px">!</span>'
                    f'<span style="font-size:11.5px;font-weight:600">{item["label"]}</span>'
                    f'<span style="font-family:var(--mono);font-size:10px;color:{T.T1}">'
                    f'{item["value"]}</span></div>'
                    f'<div style="font-size:10px;color:{T.T2};margin-left:18px;line-height:1.5">'
                    f'{item["explanation"]}</div></div>',
                    unsafe_allow_html=True,
                )


def _render_evolution(evo: dict) -> None:
    ui.section("Event Evolution")
    if evo["observation_count"] < 2:
        st.markdown(
            f'<div class="panel" style="color:{T.T2};font-size:11px">'
            f'Single observation — no evolution to display.</div>',
            unsafe_allow_html=True,
        )
        return

    milestones = evo.get("milestones", [])
    if milestones:
        timeline_html = ""
        for m in milestones:
            timeline_html += (
                f'<div style="display:flex;gap:10px;padding:5px 0;'
                f'border-bottom:1px solid {T.BORDER}">'
                f'<span style="font-family:var(--mono);font-size:10px;color:{T.T2};min-width:80px">'
                f'{m["timestamp"]}</span>'
                f'<span style="font-size:11px;font-weight:600">{m["label"]}</span>'
                f'<span style="font-size:10px;color:{T.T2}">{m.get("detail", "")}</span>'
                f'</div>'
            )
        st.markdown(f'<div class="panel">{timeline_html}</div>', unsafe_allow_html=True)

    frames = evo.get("frames", [])
    if len(frames) >= 2:
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
        step = st.slider(
            "Replay frame",
            min_value=1,
            max_value=len(frames),
            value=len(frames),
            key="evo_replay_slider",
        )
        f = frames[step - 1]
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Observations visible", f["cumulative_count"])
        col_b.metric("FRP at frame", f'{f["current_frp"]} MW' if f.get("current_frp") else "—")
        col_c.metric("Risk at frame", f'{f["risk_score"]}/100' if f.get("risk_score") else "—")


def _render_trajectory(traj: dict) -> None:
    ui.section("Risk Trajectory")
    state_label = traj.get("state", "UNKNOWN")
    color = _EW_COLORS.get(state_label, T.T2)
    delta = traj.get("delta", 0)
    signals = traj.get("signals", [])
    history = traj.get("risk_history", [])

    st.markdown(
        f'<div class="panel">'
        f'<div style="display:flex;justify-content:space-between;align-items:center">'
        f'<div><span style="font-size:10px;letter-spacing:.1em;color:{T.T2}">STATE</span>'
        f'<div style="font-size:18px;font-weight:700;color:{color};margin-top:2px">'
        f'{state_label}</div></div>'
        f'<div style="text-align:right"><span style="font-size:10px;color:{T.T2}">ΔRISK</span>'
        f'<div style="font-family:var(--mono);font-size:16px;font-weight:700;'
        f'color:{color if delta > 0 else T.LOW}">'
        f'{"+" if delta > 0 else ""}{delta}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if history:
        st.markdown(
            '<div style="font-size:10px;color:#5a6472;margin-top:6px">Risk history: '
            + " → ".join(str(r) for r in history)
            + '</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown("</div>", unsafe_allow_html=True)

    for sig in signals:
        st.markdown(
            f'<div style="font-size:11px;color:{T.T1};padding:2px 0">· {sig}</div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        f'<div style="font-size:10px;color:{T.T2};margin-top:6px;line-height:1.5">'
        f'Risk trajectory reflects observed data only. '
        f'It does not predict future fire behaviour.</div>',
        unsafe_allow_html=True,
    )


def _render_facility_deviation(dev: dict) -> None:
    ui.section("Facility Thermal Baseline",
               "how this event compares with the site's own observed activity")
    lvl = dev.get("thermal_deviation_level", "INSUFFICIENT_BASELINE")
    score = dev.get("thermal_deviation_score")
    color = _DEV_COLORS.get(lvl, T.T2)
    b = dev.get("baseline") or {}

    if score is None:
        msg = dev.get("note") or (b.get("notes") or ["Insufficient facility history."])[0]
        st.markdown(
            f'<div class="panel"><div class="mini" style="line-height:1.7">{msg}</div>'
            f'<div style="font-size:10px;color:{T.T2};margin-top:6px;line-height:1.6">'
            f'A baseline needs ≥6 detections across ≥2 days within 10 km of a known '
            f'facility. The FIRMS NRT feed is only ~5 days, so most facilities do not '
            f'yet have one. Shown honestly rather than fabricated.</div></div>',
            unsafe_allow_html=True)
        return

    frp = b.get("frp") or {}
    bt = b.get("bt") or {}
    ov = dev.get("baseline_overlap") or {}
    rows = [
        ("Facility", f'{b.get("facility_name") or "—"} '
                     f'({dev.get("dist_facility_km", "?")} km)'),
        ("Baseline window", f'{b.get("baseline_start", "?")} → {b.get("baseline_end", "?")} '
                            f'· {b.get("observation_count", 0)} obs / {b.get("active_days", 0)} d'),
        ("Baseline quality", b.get("baseline_quality", "—")),
        ("Typical peak FRP", f'{frp.get("median")} MW  (IQR {frp.get("iqr")})'
                             if frp else "not available"),
        ("Typical brightness", f'{bt.get("median")} K' if bt else "not available"),
        ("Typical persistence", str(b.get("median_persistence") or "—")),
        ("Typical timing", b.get("typical_day_night") or "—"),
    ]
    kv_html = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:5px 0;'
        f'border-bottom:1px solid {T.BORDER}"><span style="color:{T.T1};font-size:11px">{k}</span>'
        f'<span style="font-family:var(--mono);font-size:11px;color:{T.T0};text-align:right">{v}</span></div>'
        for k, v in rows
    )
    ev_html = "".join(
        f'<div style="padding:4px 0;font-size:11px"><span style="color:{color}">›</span> {e}</div>'
        for e in dev.get("evidence", [])
    ) or f'<div style="font-size:11px;color:{T.T2}">No material deviations from the baseline.</div>'

    st.markdown(
        f'<div class="panel">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
        f'<div style="flex:1">{kv_html}</div>'
        f'<div style="text-align:right;padding-left:14px;min-width:96px">'
        f'<div style="font-size:28px;font-weight:700;font-family:var(--mono);color:{color};line-height:1">'
        f'{score}<span style="font-size:12px;color:{T.T2}">/100</span></div>'
        f'<div style="font-size:9px;letter-spacing:.1em;color:{T.T2};margin-top:2px">THERMAL DEVIATION</div>'
        f'<div style="font-size:11px;font-weight:700;color:{color};margin-top:4px">{lvl}</div></div>'
        f'</div>'
        f'<div style="margin-top:8px;padding-top:8px;border-top:1px solid {T.BORDER_2}">{ev_html}</div>'
        f'<div style="font-size:11px;color:{T.T1};line-height:1.6;margin-top:6px">'
        f'{dev.get("interpretation", "")}</div>'
        f'<div style="font-size:10px;color:{T.T2};line-height:1.6;margin-top:6px">'
        f'Behavioural deviation from the facility\'s own baseline — <b>not</b> part of '
        f'the risk score above, and separate from the model class probability. '
        + ('Baseline includes this event\'s own detections (a longer archive would '
           'give an independent comparison). ' if ov.get("dominated") else '')
        + 'An abnormal thermal event is not a confirmed fire.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render() -> None:
    topbar("Investigation")
    aid = st.session_state.get("focus_alert_id")

    if not aid:
        ui.page_header("Investigation", "Select an alert to investigate")
        ui.empty_state(
            "No alert selected.",
            "Open an alert from the Alerts feed or a marker on the Map, "
            "or ask the agent \"why is the … alert critical?\".",
            "",
        )
        top = data.R("risk_score", state.filters(), limit=5)
        ui.section("Or start with the highest-risk alerts")
        for a in top:
            if ui.alert_card(a, ago=a["acq_date"], key_prefix="invpick"):
                state.focus_alert(a["alert_id"]); st.rerun()
        return

    inv = data.INV(aid)
    if not inv.get("found"):
        ui.empty_state("That alert is no longer available.", "It may have been re-seeded.")
        state.focus_alert(None)
        return

    # Fetch event intelligence (may be None for isolated detections)
    ev_dict = data.EVENT_FOR_ALERT(aid)
    event_id = ev_dict["event_id"] if ev_dict else None

    h = inv["header"]
    c = T.SEV_COLOR.get(h["severity"], T.T1)

    # ── Event / Alert header ──────────────────────────────────────────────
    event_label = f"EVENT #{event_id}" if event_id else f"DETECTION {aid}"
    obs_count = ev_dict.get("observation_count", 1) if ev_dict else 1
    st.markdown(
        f'<div style="display:flex;align-items:flex-start;justify-content:space-between;'
        f'border-bottom:1px solid {T.BORDER};padding-bottom:12px;margin-bottom:14px">'
        f'<div><div style="font-size:11px;color:{T.T1};font-family:var(--mono)">'
        f'{event_label} · {obs_count} FIRMS detection{"s" if obs_count != 1 else ""}</div>'
        f'<div class="page-h" style="margin-top:4px">{h["output_class_short"]} — {h["location"]}</div>'
        f'<div style="margin-top:6px">{T.sev_chip(h["severity"])} '
        f'<span class="mini">status <em>{h["status"]}</em> · model class probability '
        f'<em>{h["model_class_probability_pct"]}%</em> · predicted '
        f'<em>{h["predicted_label"] or "—"}</em></span></div>'
        f'</div>'
        f'<div style="text-align:right"><div style="font-size:30px;font-weight:700;'
        f'font-family:var(--mono);color:{c};line-height:1">{h["risk_score"]}<span '
        f'style="font-size:13px;color:{T.T2}">/100</span></div>'
        f'<div style="font-size:10px;color:{T.T2};letter-spacing:.1em">RISK SCORE</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1.25, 1], gap="medium")

    with c1:
        ui.section("Detection")
        d = inv["detection"]
        _kv([
            ("Fire Radiative Power",
             f'{d["frp_mw"]} MW' if d["frp_mw"] is not None else "not available"),
            ("Brightness temperature",
             f'{d["bt_kelvin"]} K' if d["bt_kelvin"] is not None else "not available"),
            ("Persistence", f'{d["persistence_count"]} detections in window'),
            ("Detection date", d["acq_date"]),
            ("Day / night", d["day_night"]),
            ("Coordinates", d["coordinates"]),
            ("Instrument", d["instrument"]),
        ])
        if ev_dict and obs_count > 1:
            _kv([
                ("Event observations", str(obs_count)),
                ("Event duration", f'{ev_dict.get("duration_days", 0)} day(s)'),
                ("Event spatial extent", f'{ev_dict.get("spatial_extent_km", 0):.1f} km'),
            ])

        ui.section("Context")
        ctx = inv["context"]
        _kv([
            ("District", ctx.get("district") or "outside India"),
            ("State", ctx.get("state") or "outside India"),
            ("Nearest facility",
             f'{ctx["dist_nearest_facility_km"]} km'
             if ctx["dist_nearest_facility_km"] is not None else "not available"),
            ("Facility type", ctx["hazard_facility_type"] or "not available"),
            ("Land-cover context", ctx["land_cover_context"] or "not available"),
        ])

        ui.section("Why this was flagged")
        why = inv["why_flagged"]
        if why:
            st.markdown('<div class="panel">' + "".join(
                f'<div style="padding:4px 0;font-size:11.5px">'
                f'<span style="color:{T.LOW}">✓</span> {w}</div>'
                for w in why) + '</div>', unsafe_allow_html=True)
        else:
            ui.empty_state("Limited supporting signals — low-confidence single detection.")

    with c2:
        ui.section("Location")
        one = data.INV(aid)
        pt = [{
            "alert_id": aid, "lat": one["coords"]["lat"], "lon": one["coords"]["lon"],
            "output_class_short": h["output_class_short"], "severity": h["severity"],
            "risk_score": h["risk_score"], "frp_mw": inv["detection"]["frp_mw"],
            "persistence_count": inv["detection"]["persistence_count"],
            "acq_date": inv["detection"]["acq_date"],
            "place": h["location"], "state": h["state"], "zone": None,
        }]
        st.pydeck_chart(mapview.build_deck(
            pt, colour_by="class", focus_alert_id=aid,
            view=pdk.ViewState(latitude=one["coords"]["lat"],
                               longitude=one["coords"]["lon"], zoom=7.2),
        ), use_container_width=True, height=200)

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
        st.markdown(
            f'<div class="mini" style="line-height:1.6;margin-top:6px">'
            f'<em>{cl["framing"]}</em></div>',
            unsafe_allow_html=True,
        )

        ui.section("Risk assessment")
        factors = inv["risk_assessment"]["factors"]
        if factors:
            st.markdown('<div class="panel">' + "".join(
                f'<div style="display:flex;justify-content:space-between;padding:4px 0;'
                f'font-size:11px"><span>{r}</span>'
                f'<span style="font-family:var(--mono);color:{T.HIGH}">+{p}</span></div>'
                for r, p in factors)
                + f'<div style="display:flex;justify-content:space-between;padding:7px 0 0;'
                f'margin-top:4px;border-top:1px solid {T.BORDER_2};font-size:11.5px;font-weight:700">'
                f'<span>Risk score</span><span style="font-family:var(--mono)">'
                f'{inv["risk_assessment"]["score"]}/100</span></div></div>',
                unsafe_allow_html=True)

    # ── Event intelligence panels ─────────────────────────────────────────
    if event_id:
        fp = data.EVENT_FP(event_id)
        if fp:
            _render_fingerprint(fp)

        ev = data.EVENT_EV(event_id)
        if ev:
            _render_evidence(ev)

        evo = data.EVENT_EVO(event_id)
        if evo and evo.get("observation_count", 0) > 0:
            _render_evolution(evo)

        traj = data.EVENT_TRAJ(event_id)
        if traj and traj.get("state") != "INSUFFICIENT DATA":
            _render_trajectory(traj)

        dev = data.EVENT_DEV(event_id)
        if dev:
            _render_facility_deviation(dev)

    # ── Recommended action + manual controls ──────────────────────────────
    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
    ra = inv["recommended_action"]
    st.markdown(
        f'<div class="panel" style="border-left:3px solid {c}">'
        f'<div style="font-size:10.5px;letter-spacing:.12em;color:{T.T1}">RECOMMENDED ACTION</div>'
        f'<div style="font-size:15px;font-weight:700;margin:4px 0 3px">{ra["action"]}</div>'
        f'<div style="font-size:11.5px;color:{T.T1};line-height:1.6">{ra["reason"]}</div></div>',
        unsafe_allow_html=True,
    )
    current_status = h["status"]
    _STATUS_DONE = {"MONITORING", "ESCALATED", "EXTINGUISHED"}
    st.markdown(
        f'<div style="font-size:11px;color:{T.T2};margin-bottom:6px">'
        f'Current status: <span style="font-weight:700;color:{T.T0}">{current_status}</span></div>',
        unsafe_allow_html=True,
    )
    b1, b2, b3, b4 = st.columns(4)
    if b1.button(
        "✓ Acknowledged" if current_status == "MONITORING" else "Acknowledge",
        use_container_width=True, key="inv_ack",
        disabled=current_status in _STATUS_DONE,
    ):
        r = data.set_status(aid, "acknowledge")
        if r.get("ok"):
            st.toast("Status updated → MONITORING (Acknowledged)", icon="✅")
        else:
            st.toast(f"Error: {r.get('error', 'unknown')}", icon="🚨")
        st.rerun()
    if b2.button(
        "↑ Escalated" if current_status == "ESCALATED" else "Escalate",
        use_container_width=True, key="inv_esc",
        disabled=current_status == "EXTINGUISHED",
        type="primary" if current_status not in _STATUS_DONE else "secondary",
    ):
        r = data.set_status(aid, "escalate")
        if r.get("ok"):
            st.toast("Status updated → ESCALATED", icon="🚨")
        else:
            st.toast(f"Error: {r.get('error', 'unknown')}", icon="🚨")
        st.rerun()
    if b3.button(
        "✓ Resolved" if current_status == "EXTINGUISHED" else "Resolve",
        use_container_width=True, key="inv_res",
        disabled=current_status == "EXTINGUISHED",
    ):
        r = data.set_status(aid, "resolve")
        if r.get("ok"):
            st.toast("Status updated → EXTINGUISHED (Resolved)", icon="🟢")
        else:
            st.toast(f"Error: {r.get('error', 'unknown')}", icon="🚨")
        st.rerun()
    if b4.button("Show on map  →", use_container_width=True, key="inv_map"):
        state.request_nav("Map Explorer"); st.rerun()
