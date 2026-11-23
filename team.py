"""The team, the reviewer roster, driver alerts and the progress tracker for the scenario dashboard.

The v9 engine (transit_ai/) decides what is allowed: gates, deadlines, second review, safe default. This module only
  * names the four roles and adds the team to the ethics-training roster (the notebook's sample reviewers stay on it,
    so their blocks can still be shown),
  * lists the scenarios (the notebook's Section B sample and its 13 presets),
  * composes, sends and records the officer's alert to the bus driver, and lets the driver acknowledge it,
  * works out who acts next and draws the tracker.
"""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone

import requests

TEAM_TRAINING_DATE_DEFAULT = "2026-11-16"
ROLE_KEYS = ("dispatcher", "supervisor", "officer", "driver")
SECTION_B = "Section B sample · Route 12 cancellation + last rail connection"

# Sample reviewers from the notebook roster, with what happens if their name is used (shown as help in the forms).
SAMPLE_PEOPLE = {
    "Ana Lopez": "sample first reviewer · training current",
    "Chen Wei": "sample second reviewer · training current",
    "Farah Haddad": "sample · ethics refresher overdue → blocked",
    "Eli Turner": "sample · missing two courses → blocked",
    "Gabe Ortiz": "sample · conflict of interest with Depot B → must recuse",
    "Ben Carter": "sample planner · refresher due soon",
}


def _secret(tc, name, default=""):
    return tc.read_secret(name) or default


def team(tc):
    """The four roles, in workflow order. Names can be changed with secrets."""
    return {
        "dispatcher": {"name": _secret(tc, "DISPATCHER_NAME", "Ariyan"), "title": "Dispatcher", "icon": "🎧",
                       "does": "Opens a scenario and makes the first decision (1st reviewer)."},
        "supervisor": {"name": _secret(tc, "SUPERVISOR_NAME", "Terri-Ann"), "title": "Supervisor", "icon": "🧭",
                       "does": "Independently approves or rejects high-impact actions (2nd reviewer)."},
        "officer": {"name": _secret(tc, "OFFICER_NAME", "Grant"), "title": "Operations Officer", "icon": "🛠️",
                    "does": "Carries out the approved action, alerts the bus driver and records the result."},
        "driver": {"name": _secret(tc, "DRIVER_NAME", "Habib"), "title": "Bus Driver", "icon": "🚌",
                   "does": "Receives alerts on the driver screen (and by text, if set up) and acknowledges them."},
    }


def label(member):
    return f"{member['icon']} {member['name']} — {member['title']}"


def require_supervisor(tc):
    """Off by default: the v9 rules decide (only high-impact actions need a second reviewer)."""
    return (tc.read_secret("REQUIRE_SUPERVISOR_APPROVAL") or "0").strip().lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------------------------------------ setup
_SETUP = {"done": False}
_LOCK = threading.Lock()


def setup(tc):
    """Run once per server: add the team to the roster and apply the optional supervisor rule."""
    with _LOCK:
        if _SETUP["done"]:
            return
        date = _secret(tc, "TEAM_TRAINING_DATE", TEAM_TRAINING_DATE_DEFAULT)
        rows = [dict(r) for r in tc.ETH_SAMPLES["Transit review team (this system)"]]
        have = {r["name"].lower() for r in rows}
        t = team(tc)
        depts = {"dispatcher": "Bus Dispatch (first reviewer)", "supervisor": "Bus Operations Supervisor (second reviewer)",
                 "officer": "Bus Operations Officer", "driver": "Bus Operator"}
        for key in ROLE_KEYS:
            if t[key]["name"].lower() not in have:
                rows.append({"name": t[key]["name"], "department": depts[key], "completed": list(tc.ETH_REQUIRED),
                             "last_training": date})
        tc.load_eth_roster(rows)
        if require_supervisor(tc):
            app = tc.APP
            app.is_high_impact = lambda case, option_id: True
        _SETUP["done"] = True


# ------------------------------------------------------------------------------------------------ scenarios
def scenarios(tc):
    """Name → function that builds the raw input bundle. Same list as the notebook's Orchestrator, without the live case."""
    src = {SECTION_B: lambda: tc.workflow_inputs_to_raw(tc.SAMPLE_INPUTS, tc.VisionAgent().run(tc.RAW_SENSOR_FEED))}
    src.update({k: (lambda k=k: tc.make_raw(tc.PRESETS[k], k)) for k in tc.PRESETS})
    return src


# ------------------------------------------------------------------------------------------------ who acts next
def next_role(case):
    if case is None:
        return None
    st = case["status"]
    if st in ("AWAITING_REVIEW", "CONFLICT_REVIEW"):
        return "dispatcher"
    if st == "AWAITING_SECOND_REVIEW":
        return "supervisor"
    if st == "AWAITING_IMPLEMENTATION":
        return "officer"
    if any(not a["acknowledged_by"] for a in inbox(case)):
        return "driver"
    if st == "MONITORING":
        return "dispatcher"
    return None


def option_for(case, oid=None):
    oid = oid or case.get("approved_option_id")
    return next((o for o in case["analysis"].get("options", []) if o["option_id"] == oid), None)


def tracker(tc, case):
    """[(stage, person, state, note)] with state in done / now / todo / skip / stop."""
    t = team(tc)
    st, rv = case["status"], case.get("review") or {}
    firsts = [d for d in case["decisions"] if d["stage"] == "first review"]
    seconds = [d for d in case["decisions"] if d["stage"] == "second review"]
    out = [("Agents + rules", "AI agents · fixed rules", "done", case["analysis"]["gate"].replace("_", " ").lower())]
    if st == "CONFLICT_REVIEW":
        out.append(("Operator check", t["dispatcher"]["name"], "now", "sources disagree"))
    if firsts or st == "AWAITING_REVIEW":
        out.append((f"{t['dispatcher']['name']} decides", "Dispatcher", "now" if st == "AWAITING_REVIEW" else "done",
                    firsts[-1]["decision"] if firsts and st != "AWAITING_REVIEW" else rv.get("tier", "")))
    needs2 = rv.get("required_second")
    if st == "AWAITING_SECOND_REVIEW" or seconds:
        out.append((f"{t['supervisor']['name']} approves", "Supervisor", "now" if st == "AWAITING_SECOND_REVIEW" else "done",
                    seconds[-1]["decision"] if seconds else "high-impact action"))
    elif firsts and needs2 is False:
        out.append(("Second review", "Supervisor", "skip", "not needed (not high-impact)"))
    if st == "AWAITING_IMPLEMENTATION" or case["implementation"]:
        out.append((f"{t['officer']['name']} carries it out", "Operations Officer",
                    "now" if st == "AWAITING_IMPLEMENTATION" else "done",
                    case["implementation"][-1]["result"] if case["implementation"] and st != "AWAITING_IMPLEMENTATION" else ""))
    box = inbox(case)
    if box:
        waiting = any(not a["acknowledged_by"] for a in box)
        out.append((f"{t['driver']['name']} acknowledges", "Bus Driver", "now" if waiting else "done",
                    f"{len(box)} alert(s)"))
    if case.get("outcome") and "delay_error_min" in case["outcome"]:
        sim = str(case["outcome"].get("observed_source", "")).startswith("SIMULATED")
        out.append(("Outcome evaluated", "Outcome Evaluator", "done", "SIMULATED" if sim else "observed"))
    ends = {"SAFE_DEFAULT": ("Safe default", "rider information only"), "MONITORING": ("Continue monitoring", "recheck / re-escalate"),
            "CLOSED_FALSE_ALARM": ("Closed", "false alarm")}
    if st in ends:
        out.append((ends[st][0], "fixed rule", "stop" if st != "MONITORING" else "now", ends[st][1]))
    return out


# ------------------------------------------------------------------------------------------------ driver alerts
def inbox(case):
    """Everything the driver has been sent on this case: the engine's accessibility alert (once sent) + officer messages."""
    out = []
    da = case.get("driver_alert") or {}
    if da.get("text") and str(da.get("status", "")).startswith("sent"):
        out.append({"source": "accessibility", "ts": da.get("ts", ""), "from": "Driver alert rule (accessibility)",
                    "body": da["text"], "status": da["status"], "sms": da.get("sms", "not sent"),
                    "acknowledged_by": da.get("acknowledged_by"), "acknowledged_at": da.get("acknowledged_at")})
    for i, a in enumerate(case.get("driver_alerts") or []):
        out.append({"source": f"officer:{i}", **a})
    return out


def acknowledge(tc, case, source, driver_name):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if source == "accessibility":
        rec = case["driver_alert"]
    else:
        rec = case["driver_alerts"][int(source.split(":")[1])]
    if rec.get("acknowledged_by"):
        return
    rec["acknowledged_by"], rec["acknowledged_at"] = driver_name, now
    tc.APP.log(case, driver_name, "operations", "Driver alert", "Driver acknowledged the alert", rec.get("body", rec.get("text", ""))[:160])


INSTRUCTIONS = {
    "rider_alerts": "Rider alerts have been sent. Let riders know about the delay at each stop and continue your route.",
    "protect_connection": "Hold at the connection stop for transferring riders, then continue.",
    "reroute": "Follow the detour around the blockage. Dispatch will confirm when the normal route reopens.",
    "dispatch_second_bus": "A second bus is being sent to help. Continue service and expect it behind you.",
    "accessible_pickup": "An accessible vehicle is coming for riders you cannot board. Tell waiting riders the van is coming.",
    "do_nothing": "No change to your trip. Continue service.",
}


def compose_driver_message(tc, case):
    raw = case["raw"]
    o = option_for(case)
    kind = o["type"] if o else "rider_alerts"
    action = (o["label"] if o else "Rider information only").split(" — ")[0]
    stops = raw.get("affected_stop_ids") or []
    stop = tc.NET["stops"][stops[0]]["name"] if stops else ""
    lines = [f"OPS · Route {raw.get('route_id')} {raw.get('route_name', '')} · {case['case_id']} (scenario)",
             f"Approved: {action}.", INSTRUCTIONS.get(kind, "Follow dispatch instructions.")]
    if stop:
        lines.append(f"Affected from {stop}.")
    lines.append("Please acknowledge.")
    return " ".join(lines)[:320]


def _mask(phone):
    digits = re.sub(r"\D", "", phone or "")
    return f"•••-•••-{digits[-4:]}" if len(digits) >= 4 else "driver screen"


def twilio_ready(tc):
    sid, tok = _secret(tc, "TWILIO_ACCOUNT_SID"), _secret(tc, "TWILIO_AUTH_TOKEN")
    sender = _secret(tc, "TWILIO_FROM_NUMBER") or _secret(tc, "TWILIO_MESSAGING_SERVICE_SID")
    return bool(sid and tok and sender and _secret(tc, "DRIVER_PHONE_NUMBER"))


def _twilio_send(tc, to, body):
    sid, tok = _secret(tc, "TWILIO_ACCOUNT_SID"), _secret(tc, "TWILIO_AUTH_TOKEN")
    data = {"To": to, "Body": body}
    if _secret(tc, "TWILIO_MESSAGING_SERVICE_SID"):
        data["MessagingServiceSid"] = _secret(tc, "TWILIO_MESSAGING_SERVICE_SID")
    else:
        data["From"] = _secret(tc, "TWILIO_FROM_NUMBER")
    try:
        r = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data=data, auth=(sid, tok), timeout=20)
        js = r.json() if r.content else {}
    except (requests.RequestException, ValueError) as e:
        return False, f"could not reach Twilio ({type(e).__name__})"
    if r.status_code in (200, 201):
        return True, f"Twilio message {js.get('sid', '')} ({js.get('status', 'queued')})"
    return False, f"Twilio error {js.get('code', r.status_code)}: {js.get('message', r.text[:160])}"


def send_driver_alert(tc, case, body, sender_name):
    """Post the alert to the driver screen, and text it too if Twilio is set up."""
    body = (body or "").strip()
    if not body:
        raise ValueError("The driver message is empty.")
    phone = _secret(tc, "DRIVER_PHONE_NUMBER")
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "from": sender_name, "body": body,
           "to": _mask(phone), "status": "sent by the operations officer", "sms": "not sent", "sms_detail": "",
           "acknowledged_at": None, "acknowledged_by": None}
    if twilio_ready(tc):
        ok, detail = _twilio_send(tc, phone, body)
        rec["sms"], rec["sms_detail"] = ("sent" if ok else "failed"), detail
    else:
        rec["sms_detail"] = "text messaging not set up; driver screen only"
    case.setdefault("driver_alerts", []).append(rec)
    tc.APP.log(case, sender_name, "operations", "Driver alert", f"Alert to driver · text {rec['sms']}", f"{body} [{rec['to']}] {rec['sms_detail']}")
    return rec
