"""Transit Reliability & Equity: scenario dashboard with role views, on the v9 notebook engine (Streamlit).

Run locally:  streamlit run app_streamlit.py
Streamlit Community Cloud: main file app_streamlit.py; settings go in App settings → Secrets (see README.md).

Flow
  Step 1  Who are you? Dispatcher (1st reviewer), Supervisor (2nd reviewer), Operations Officer, or Bus Driver.
  Step 2  The dispatcher opens one of the notebook's scenarios (all synthetic, labelled SIMULATED).
  Then    "My task" shows exactly what your role must do on the selected case.
The v9 engine (transit_ai/) runs the AI agents and the fixed rules; people make every decision. All cases are shared by
everyone using the same link.
"""
import hmac
import html
import os
import sys

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Transit Reliability & Equity · Scenarios", page_icon="🚌", layout="wide")
ss = st.session_state
PLACEHOLDER = "— choose an option (ranked by Si) —"


# ================================================================================================ access
def _secret_value(name):
    try:
        v = st.secrets.get(name)
    except Exception:
        v = None
    return v or os.environ.get(name)


def password_gate():
    pw = _secret_value("DASHBOARD_PASSWORD")
    if not pw or ss.get("authenticated"):
        return
    st.markdown("## 🚌 Transit Reliability & Equity")
    st.caption("Scenario dashboard · synthetic data")
    with st.form("login"):
        typed = st.text_input("Dashboard password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            if hmac.compare_digest(typed.encode(), str(pw).encode()):
                ss["authenticated"] = True
                st.rerun()
            st.error("Wrong password.")
    st.stop()


password_gate()


@st.cache_resource(show_spinner="Starting up: loading the v9 engine (agents, rules, rosters) …")
def load_core():
    try:                                            # the engine reads settings from environment variables
        for k, v in st.secrets.items():
            if isinstance(v, (str, int, float, bool)):
                os.environ.setdefault(k, str(v))
    except Exception:
        pass
    for k, v in {"DATA_MODE": "sample", "USE_CV": "false", "USE_SLM": "false", "USE_LLM_ORGANIZER": "false"}.items():
        os.environ.setdefault(k, v)                 # scenarios only: no NJ Transit login, no camera model, no FLAN-T5
    app_dir = os.path.dirname(os.path.abspath(__file__))
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    os.chdir(app_dir)                               # the engine writes transit_outputs/ next to the app
    from transit_ai import load
    import team as T
    tc = load(verbose=False)
    T.setup(tc)
    return tc, T


tc, T = load_core()
APP = tc.APP
TEAM = T.team(tc)
SCEN = T.scenarios(tc)


# ================================================================================================ helpers
def flash(text, kind="info"):
    ss["flash"] = (kind, text)


def show_flash():
    if ss.get("flash"):
        kind, text = ss.pop("flash")
        {"error": st.error, "success": st.success, "warning": st.warning}.get(kind, st.info)(text)


def act(fn, ok=None):
    """Run a person's submission. Refusals (gates, rubber-stamp checks, deadlines) are shown, not raised; the form keeps what was typed."""
    try:
        with APP.lock:
            fn()
            c = current_case()
            if c is not None and c["status"] == "IMPLEMENTED":      # the Outcome Evaluator runs at once after a completed action
                APP.evaluate_outcome(c, APP.simulate_observed(c))
                ok = (ok or "") + " The Outcome Evaluator compared predicted and observed results (SIMULATED)."
        flash(ok or APP.last_message, "success")
        return True
    except ValueError as e:
        flash("⛔ " + str(e), "error")
    except Exception as e:  # never leave the person without a screen
        flash(f"⛔ Unexpected error: {type(e).__name__}: {e}", "error")
    return False


def current_case():
    cid = ss.get("case_id")
    return APP.cases.get(cid) if cid else None


def md_table(df):
    st.dataframe(df, hide_index=True, width="stretch")


def opt_label(c, oid):
    o = T.option_for(c, oid)
    return o["label"] if o else str(oid)


def case_label(c):
    who = T.next_role(c)
    tag = f" · 👉 {TEAM[who]['name']}" if who else ""
    return f"{c['case_id']} · {c['scenario_name'][:58]} · {tc.STATUS_HELP.get(c['status'], c['status'])[:34]}{tag}"


def names_for(default):
    """Team member first, then the notebook's sample reviewers (type any other name too)."""
    others = [n for n in [TEAM["dispatcher"]["name"], TEAM["supervisor"]["name"], TEAM["officer"]["name"], *T.SAMPLE_PEOPLE] if n != default]
    return [default, *others]


SAMPLE_HELP = "Sample names from the notebook, to show the gates: " + "; ".join(f"{k} ({v})" for k, v in T.SAMPLE_PEOPLE.items())


# ================================================================================================ sidebar
with st.sidebar:
    st.markdown("### 🚌 Transit Reliability & Equity")
    st.markdown("<span style='background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:6px;font-size:12px'>"
                "SCENARIO MODE · synthetic data · outcomes SIMULATED</span>", unsafe_allow_html=True)
    st.markdown("**Step 1 · Who are you?**")
    role = st.radio("Role", T.ROLE_KEYS, format_func=lambda k: T.label(TEAM[k]), key="role", label_visibility="collapsed")
    st.caption(TEAM[role]["does"])

    if "_goto" in ss:                       # a case just opened: select it
        ss["case_id"] = ss.pop("_goto")
    # when the role changes, jump to the case waiting for that person
    if ss.get("_last_role") != role:
        ss["_last_role"] = role
        waiting = [c for c in APP.cases.values() if T.next_role(c) == role]
        if waiting:
            ss["case_id"] = waiting[-1]["case_id"]

    st.markdown("**Case**")
    ids = list(APP.cases)[::-1]
    if ids:
        if ss.get("case_id") not in APP.cases:   # nothing selected yet, or it was cleared
            ss["case_id"] = ids[0]
        st.selectbox("Case", ids, key="case_id", format_func=lambda i: case_label(APP.cases[i]), label_visibility="collapsed")
    else:
        st.caption("No cases yet. The dispatcher opens a scenario on **✅ My task**.")
    if st.button("↻ Refresh", width="stretch", help="See what others have done and check the deadline"):
        st.rerun()
    st.divider()
    st.caption(f"Rules v{APP.PM.current['version']} · explanations: {'live LLM' if tc.LLM_READY else 'built-in template'} · "
               f"deadline scale × {tc.DEMO_DEADLINE_SCALE:g}")


# ================================================================================================ header
c = current_case()
st.markdown("## 🚌 Bus disruption response · scenario dashboard")
st.caption("AI agents sense, organize and explain · fixed, published rules score · **people decide**. "
           "Every case here is a synthetic scenario from the v9 notebook; nothing is dispatched.")
show_flash()

if c is not None:
    if c["status"] in tc.REVIEW_STATUSES and APP.enforce_deadline(c):
        st.warning("⏱ The review deadline passed with no complete response, so the case went to the **Safe Default** "
                   "(verified rider information only).")
    A = c["analysis"]
    left = APP.seconds_left(c)
    clock = f" · ⏱ **{int(left // 60)} min {int(left % 60)} s left** (covers both reviewers)" if left is not None else ""
    st.markdown(f"**{c['case_id']}** · {html.escape(c['scenario_name'])} · route {c['raw']['route_id']} {c['raw']['route_name']} · "
                f"rules v{c['policy_version']} · status **{tc.STATUS_HELP.get(c['status'], c['status'])}**{clock}")
    colors = {"done": ("#dcfce7", "#166534", "✅"), "now": ("#ffedd5", "#9a3412", "👉"), "todo": ("#f1f5f9", "#475569", "⏳"),
              "skip": ("#f1f5f9", "#64748b", "➖"), "stop": ("#fee2e2", "#991b1b", "■")}
    chips = []
    for stage, who, state, note in T.tracker(tc, c):
        bg, fg, icon = colors[state]
        border = "2px solid #f97316" if state == "now" else f"1px solid {fg}"
        chips.append(f"<div style='display:inline-block;margin:3px;padding:6px 10px;border-radius:8px;background:{bg};color:{fg};"
                     f"border:{border};font:12px/1.3 sans-serif;vertical-align:top'><b>{icon} {html.escape(stage)}</b><br>"
                     f"<span style='font-size:11px'>{html.escape(who)}{' · ' + html.escape(str(note)) if note else ''}</span></div>")
    st.markdown("<div>" + " → ".join(chips) + "</div>", unsafe_allow_html=True)

tab_task, tab_case, tab_map, tab_rec, tab_help = st.tabs(["✅ My task", "📄 Case summary", "🗺️ Map", "🗂️ Records", "❓ How to use"])


# ================================================================================================ review forms
def review_inputs(prefix):
    reason = st.text_area("Your reason (required, at least 15 characters)", key=f"{prefix}_reason")
    st.markdown("**Checklist** (all required)")
    checks = [t for i, t in enumerate(tc.REVIEW_CHECKLIST) if st.checkbox(t, key=f"{prefix}_chk{i}")]
    viewed = st.checkbox("I viewed every alternative before deciding (rubber-stamp protection)", key=f"{prefix}_viewed")
    return reason, checks, viewed


def expire(case):
    with APP.lock:
        case["review"]["deadline_at"] = tc.iso(tc.utcnow() - tc.timedelta(seconds=1))
        APP.enforce_deadline(case)
    flash("Deadline passed with no complete response → Safe Default.", "warning")


def show_brief(case):
    st.markdown(case["explanation"]["brief_md"])
    if case["explanation"].get("narrative"):
        st.info(f"**Explanation Agent** ({case['explanation']['narrative_source']}, non-authoritative): {case['explanation']['narrative']}")


def dispatcher_task(case):
    me = TEAM["dispatcher"]["name"]
    with st.expander("▶ Open a new scenario", expanded=case is None or case["status"] not in ("AWAITING_REVIEW", "CONFLICT_REVIEW")):
        pick = st.selectbox("Scenario", list(SCEN), key="scenario_pick")
        use_llm = st.checkbox("Live LLM explanation", value=tc.LLM_READY, disabled=not tc.LLM_READY, key="use_llm",
                              help="Needs OPENAI_API_KEY (or another provider) in Secrets; otherwise the built-in template is used.")
        if st.button("▶ Process case", type="primary"):
            with st.status("Running agents and rules …", expanded=True) as box:
                hook = lambda msg: box.write(f"⏳ {msg} …")
                tc.PROGRESS_HOOK = hook
                try:
                    import time
                    t0 = time.time()
                    box.write(f"⏳ Processing {pick} …")
                    with APP.lock:
                        new = APP.new_case(SCEN[pick](), use_llm=use_llm)
                    for e in new["audit"]:
                        box.write(f"✓ {e['stage']} · {e['event']}")
                    box.update(label=f"Case opened in {time.time() - t0:.0f} s", state="complete", expanded=False)
                    ss["_goto"] = new["case_id"]          # applied before the case picker is drawn on the next run
                    who = T.next_role(new)
                    flash(f"Case opened in {time.time() - t0:.0f} s: {new['case_id']}. "
                          + (f"Next: {TEAM[who]['name']} ({TEAM[who]['title']})." if who else
                             f"No decision needed: {tc.STATUS_HELP.get(new['status'], new['status'])}."), "success")
                except Exception as e:
                    box.update(label="Could not open the case", state="error")
                    flash(f"⛔ Could not open the case: {type(e).__name__}: {e}", "error")
                finally:
                    tc.PROGRESS_HOOK = None
            st.rerun()
    if case is None:
        return
    stt, A = case["status"], case["analysis"]
    p = f"d_{case['case_id']}_{case['revisions']}_{len(case['implementation'])}"

    if stt == "AWAITING_REVIEW":
        st.subheader(f"🔔 Your decision, {me}")
        show_brief(case)
        if case["review"].get("no_feasible_option"):
            st.warning("No feasible option under the current constraints: revise the constraints or reject.")
        who = st.selectbox("Reviewer", names_for(me), key=f"{p}_who", accept_new_options=True, help=SAMPLE_HELP)
        dec = st.radio("Decision", ["Approve", "Revise", "Reject"], horizontal=True, key=f"{p}_dec")
        ranked = [r["option_id"] for r in A["ranking"]]
        lab = {r["option_id"]: f"Rank {r['rank']} · {r['label']} (Si {r['Si']:.3f})" for r in A["ranking"]}
        opt = st.selectbox("Option", [PLACEHOLDER] + ranked, key=f"{p}_opt", format_func=lambda x: lab.get(x, x),
                           help="Nothing is preselected: pick the option yourself.")
        reason, checks, viewed = review_inputs(p)
        rev = None
        with st.expander("Revision constraints (used only for Revise; max two revisions)"):
            pd_ = tc.get_case_policy(case)["planner_defaults"]
            budget = st.number_input("Budget cap $", value=int(pd_["budget_cap_usd"]), step=50, key=f"{p}_budget")
            hold = st.number_input("Max hold min", value=int(pd_["max_hold_min"]), step=1, key=f"{p}_hold")
            alt = st.checkbox("Allow alternate depot", key=f"{p}_alt")
            excl = st.multiselect("Exclude option types", ["dispatch_second_bus", "reroute", "protect_connection", "rider_alerts", "accessible_pickup"],
                                  key=f"{p}_excl")
        if dec == "Revise":
            rev = {"budget_cap_usd": budget, "max_hold_min": hold, "allow_alternate_depot": alt, "excluded_options": list(excl)}
        b1, b2 = st.columns([1, 1])
        if b1.button(f"Submit as {who or me}", type="primary", key=f"{p}_go"):
            oid = "" if opt == PLACEHOLDER else opt
            if act(lambda: APP.submit_first(case, who or "", dec, oid, reason, checks, viewed, rev)):
                st.rerun()
            st.rerun()
        if b2.button("Simulate: deadline passes", key=f"{p}_exp"):
            expire(case)
            st.rerun()

    elif stt == "CONFLICT_REVIEW":
        st.subheader("🔔 Operator check: the sources disagree")
        q = [e for e in A["evidence"] if e["status"] == "quarantined"]
        st.write("Quarantined: " + "; ".join(f"{e['source_id']} ({e['note']})" for e in q))
        res = st.radio("Result", ["resolved", "unresolved"], horizontal=True, key=f"{p}_res",
                       help="resolved = accept source precedence (vehicle data wins); unresolved = cannot tell which source is right")
        if st.button(f"Submit operator check as {me}", type="primary", key=f"{p}_op"):
            act(lambda: APP.operator_resolve(case, me, res))
            st.rerun()

    elif stt in ("MONITORING", "SAFE_DEFAULT"):
        kind = "Continue monitoring" if stt == "MONITORING" else "Safe default"
        st.subheader(f"{kind}")
        st.info(f"{case.get('safe_default_reason') or A.get('gate_reason', '')}. Verified rider information only; "
                "no dispatch, rerouting or live control.")
        if case.get("rider_alert"):
            st.markdown(f"**Rider alert:** {case['rider_alert']}")
        if case.get("driver_alert"):
            da = case["driver_alert"]
            st.markdown(f"**Driver alert** ({da['status']}): {da['text'] or '—'}")
        b1, b2, b3 = st.columns(3)
        if b1.button("Recheck (feed changed)", key=f"{p}_rc"):
            act(lambda: APP.monitor_action(case, "recheck")); st.rerun()
        if b2.button("Re-escalate (conditions worsen)", key=f"{p}_re"):
            act(lambda: APP.monitor_action(case, "re-escalate")); st.rerun()
        if b3.button("Evaluate outcome", key=f"{p}_ev", disabled=bool(case.get("outcome"))):
            act(lambda: APP.evaluate_outcome(case, APP.simulate_observed(case))); st.rerun()
        why = st.text_input("Reason for closing as a false alarm", key=f"{p}_fa")
        if st.button(f"Close as false alarm ({me})", key=f"{p}_fab"):
            act(lambda: APP.close_false_alarm(case, me, why)); st.rerun()
    else:
        st.success(f"Nothing for the dispatcher on {case['case_id']} now: {tc.STATUS_HELP.get(stt, stt)}.")


def supervisor_task(case):
    me = TEAM["supervisor"]["name"]
    if case is None or case["status"] != "AWAITING_SECOND_REVIEW":
        st.success("Nothing waiting for you on this case. High-impact actions come to you after the dispatcher approves them.")
        return
    f = case["review"]["first"]
    st.subheader(f"🔔 Independent second review, {me}")
    st.warning(f"**{f['reviewer']}** approved a high-impact action: **{opt_label(case, f['option_id'])}**. "
               f"Reason given: “{f['reason']}”. You must be a different person.")
    show_brief(case)
    p = f"s_{case['case_id']}_{case['revisions']}"
    who = st.selectbox("Reviewer 2", names_for(me), key=f"{p}_who", accept_new_options=True, help=SAMPLE_HELP)
    dec = st.radio("Decision", ["Approve", "Reject"], horizontal=True, key=f"{p}_dec")
    reason, checks, viewed = review_inputs(p)
    b1, b2 = st.columns(2)
    if b1.button(f"Submit as {who or me}", type="primary", key=f"{p}_go"):
        act(lambda: APP.submit_second(case, who or "", dec, reason, checks, viewed))
        st.rerun()
    if b2.button("Simulate: deadline passes", key=f"{p}_exp"):
        expire(case)
        st.rerun()


def officer_task(case):
    me = TEAM["officer"]["name"]
    if case is None or case["status"] != "AWAITING_IMPLEMENTATION":
        st.success("Nothing to carry out on this case. Approved actions come to you here.")
        if case is not None and case.get("outcome") and "delay_error_min" in case["outcome"]:
            show_outcome(case)
        return
    st.subheader(f"🔔 Carry out the approved action, {me}")
    st.markdown(f"Approved: **{opt_label(case, case['approved_option_id'])}**. Carry it out (outside the prototype), "
                "alert the driver, and record the result. Partial or failed actions go back to human review.")
    da = case.get("driver_alert") or {}
    if da.get("text"):
        st.markdown(f"**Accessibility driver alert** ({da['status']}): {da['text']}")
    p = f"o_{case['case_id']}_{len(case['implementation'])}"
    body = st.text_area("Message to the driver", value=T.compose_driver_message(tc, case), key=f"{p}_msg")
    res = st.radio("Result", ["Completed", "Partial", "Failed"], horizontal=True, key=f"{p}_res")
    notes = st.text_area("Notes (required for Partial or Failed)", key=f"{p}_notes")
    send = st.checkbox(f"Send this alert to {TEAM['driver']['name']}", value=True, key=f"{p}_send",
                       help="Posted on the driver screen; also sent by text if Twilio is set up in Secrets.")
    if st.button("Record result" + (" and alert the driver" if send else ""), type="primary", key=f"{p}_go"):
        def run():
            APP.record_implementation(case, me, res, notes)
            if send and res != "Failed":
                T.send_driver_alert(tc, case, body, me)
        act(run)
        st.rerun()


def driver_task(case):
    me = TEAM["driver"]["name"]
    box = T.inbox(case) if case else []
    if not box:
        st.success("No alerts for you on this case.")
        return
    st.subheader(f"📟 Driver screen · {me}")
    for a in box[::-1]:
        done = a.get("acknowledged_by")
        st.markdown(f"<div style='border:1px solid #cbd5e1;border-left:6px solid {'#16a34a' if done else '#f97316'};border-radius:8px;"
                    f"padding:10px 12px;margin:6px 0;background:#f8fafc'><b>{html.escape(a['from'])}</b> · {a['ts'][11:16]} UTC · "
                    f"{html.escape(a.get('status', ''))} · text: {html.escape(a.get('sms', 'not sent'))}<br>"
                    f"<span style='font-size:15px'>{html.escape(a['body'])}</span></div>", unsafe_allow_html=True)
        if done:
            st.caption(f"Acknowledged by {done} at {a['acknowledged_at'][11:16]} UTC")
        elif st.button("👍 Acknowledge", key=f"ack_{case['case_id']}_{a['source']}"):
            with APP.lock:
                T.acknowledge(tc, case, a["source"], me)
            flash("Acknowledged. Dispatch can see it in the timeline.", "success")
            st.rerun()


def show_outcome(case):
    o = case["outcome"]
    st.markdown(f"**Outcome Evaluator** (separate from the recommender) · observed data: **{o.get('observed_source', '')}** · "
                f"predicted vs observed delay error {o['delay_error_min']:+.1f} min · false alarm {o['false_alarm']} · "
                "policy weights unchanged.")
    md_table(pd.DataFrame([{k: v for k, v in o.items() if not isinstance(v, (dict, list))}]))


with tab_task:
    {"dispatcher": dispatcher_task, "supervisor": supervisor_task, "officer": officer_task, "driver": driver_task}[role](c)
    if c is not None and c["status"] == "EVALUATED" and role == "dispatcher":
        show_outcome(c)


# ================================================================================================ case summary
with tab_case:
    if c is None:
        st.info("No case selected.")
    else:
        st.markdown(f"**Gate:** {c['analysis']['gate']} — {c['analysis'].get('gate_reason', '')}")
        if c.get("explanation"):
            show_brief(c)
        else:
            st.markdown(tc.situation_md(c) if c["analysis"].get("scores") else "")
        if c.get("rider_alert"):
            st.markdown(f"**Rider alert:** {c['rider_alert']}")
        if T.inbox(c):
            st.markdown("**Driver alerts**")
            md_table(pd.DataFrame([{k: a.get(k) for k in ("ts", "from", "status", "sms", "acknowledged_by", "body")} for a in T.inbox(c)]))
        if c.get("outcome") and "delay_error_min" in c["outcome"]:
            show_outcome(c)
        st.markdown("**Timeline (who did what, and why)**")
        md_table(pd.DataFrame([{"time (ET)": e["ts"][11:19], "stage": e["stage"], "who": e["actor"], "what": e["event"],
                                "detail": str(e["detail"])[:240]} for e in c["audit"]]))


# ================================================================================================ map
with tab_map:
    if c is None:
        st.info("Open a case to see it on the map.")
    else:
        st.caption("Synthetic model network over a Newark basemap (the notebook's E1 network): the affected stops, "
                   "community areas and depots for the selected case.")
        try:
            components.html(tc.build_map(c).get_root().render(), height=560)
        except Exception as e:
            st.warning(f"Map unavailable: {type(e).__name__}: {e}")


# ================================================================================================ records
with tab_rec:
    t1, t2, t3, t4, t5 = st.tabs(["Cases", "Scores", "Decisions + audit", "Training + conflicts", "Learning loop"])
    with t1:
        md_table(tc.cases_df())
        with st.expander("Reset the demo (clears every case for everyone)"):
            sure = st.checkbox("Yes, clear all cases", key="reset_sure")
            if st.button("Clear all cases", disabled=not sure):
                with APP.lock:
                    APP.cases.clear()
                    APP.active_id = None
                ss["_goto"] = None
                flash("All cases cleared. Rule versions and the audit log are kept.", "success")
                st.rerun()
    with t2:
        if c is not None and c["analysis"].get("scores"):
            st.markdown(tc.sig_md(c))
            st.plotly_chart(tc.rvap_plot(c), width="stretch")
            md_table(tc.options_df(c))
            st.plotly_chart(tc.options_plot(c), width="stretch")
            st.markdown("**Evidence**")
            md_table(tc.evidence_df(c))
            st.markdown("**Exceptions**")
            md_table(tc.exceptions_df(c))
        else:
            st.info("The selected case has no scores (it stopped before the impact analyzer).")
    with t3:
        if c is not None:
            md_table(tc.decisions_df(c))
        md_table(tc.audit_df())
    with t4:
        st.caption("Ethics-training roster: the team plus the notebook's sample reviewers. Conflict-of-interest disclosures are the "
                   "notebook's samples.")
        md_table(pd.DataFrame(tc.eth_check_all())[["official", "department", "status", "missing_courses", "days_until_refresher_due"]])
    with t5:
        st.markdown("**Insight Agent → Policy Owner → backtest → new rule version.** Nothing changes until the policy owner approves.")
        if st.button("Run Insight Agent"):
            with APP.lock:
                props = tc.insight_agent(APP)
            flash(f"Insight Agent proposed {len(props)} change(s).", "success")
            st.rerun()
        md_table(tc.proposals_df())
        if APP.proposals:
            pid = st.selectbox("Proposal", [p["id"] for p in APP.proposals],
                               format_func=lambda i: next(f"{p['id']} · {p['title']}" for p in APP.proposals if p["id"] == i))
            if st.button("Preview backtest"):
                prop = next(x for x in APP.proposals if x["id"] == pid)
                _, summary = tc.run_backtest(APP, tc.apply_changes(APP.PM.current, prop["changes"]))
                st.info(f"Backtest: {summary}")
            owner = st.selectbox("Policy owner", ["Dana Brooks", *names_for(TEAM["supervisor"]["name"])], accept_new_options=True)
            pdec = st.radio("Decision", ["Approve", "Reject"], horizontal=True, key="pol_dec")
            why = st.text_input("Reason (at least 10 characters)", key="pol_why")
            if st.button("Submit policy decision", type="primary"):
                act(lambda: tc.decide_proposal(APP, pid, owner, pdec, why))
                st.rerun()
        md_table(tc.versions_df())


# ================================================================================================ help
with tab_help:
    st.markdown(f"""
**Roles** (sidebar, Step 1): {T.label(TEAM['dispatcher'])} · {T.label(TEAM['supervisor'])} · {T.label(TEAM['officer'])} · {T.label(TEAM['driver'])}.
When you switch role, the dashboard jumps to the case waiting for you. Press **↻ Refresh** to see what others have done.

**Run a scenario (about 3 minutes)**
1. **{TEAM['dispatcher']['name']}**: on **✅ My task**, open *▶ Open a new scenario*, pick one and press **▶ Process case**.
   Read the review screen, choose an option yourself, tick the checklist, write a reason and submit.
2. **{TEAM['supervisor']['name']}** (only for high-impact actions, such as a second bus or an accessible van): approve or reject.
3. **{TEAM['officer']['name']}**: check the driver message, pick the result and press **Record result and alert the driver**.
   The Outcome Evaluator runs at once; its result is labelled SIMULATED.
4. **{TEAM['driver']['name']}**: read the alert on the driver screen and press **👍 Acknowledge**.

**Show the safeguards:** type a sample name such as *Farah Haddad* as reviewer (blocked: ethics training), use the same name
as both reviewers (refused), submit with no option chosen, or with a short reason. **Simulate: deadline passes** sends the
case to the Safe Default.

Every scenario is synthetic and comes from the v9 notebook. Approved actions are recorded, not dispatched.
""")
