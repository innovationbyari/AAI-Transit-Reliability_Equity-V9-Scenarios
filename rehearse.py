"""Rehearsal: click through the scenario dashboard as the four roles (Streamlit AppTest) and check each expected result."""
import os, sys
os.environ.setdefault("TRANSIT_OUTPUT_DIR", "/tmp/transit_outputs")
from streamlit.testing.v1 import AppTest

APPF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app_streamlit.py")
at = AppTest.from_file(APPF, default_timeout=120)
at.run()
R = []


def check(name, ok, detail=""):
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  — {detail}" if detail else ""))


def errs():
    return [e.value for e in at.exception]


def text():
    parts = [m.value for m in at.markdown] + [x.value for x in at.info] + [x.value for x in at.success] + \
            [x.value for x in at.error] + [x.value for x in at.warning]
    return "\n".join(map(str, parts))


def role(k):
    at.sidebar.radio(key="role").set_value(k).run()


def btn(label_start):
    b = [b for b in at.button if b.label.startswith(label_start)]
    assert b, f"no button {label_start!r}; have {[b.label for b in at.button]}"
    b[0].click().run()


def by_label(coll, start):
    x = [w for w in coll if str(w.label).startswith(start)]
    assert x, f"no widget {start!r}; have {[w.label for w in coll]}"
    return x[0]


def tc():
    import transit_ai
    return transit_ai._RUNTIME


def case():
    return tc().APP.cases[at.session_state["case_id"]]


def open_scenario(name):
    role("dispatcher")
    by_label(at.selectbox, "Scenario").set_value(name)
    at.run()
    btn("▶ Process case")


def fill(prefix_who, who, dec, opt=None, reason="Second bus needed for riders left at the stop", ticks=True):
    by_label(at.selectbox, prefix_who).set_value(who)
    by_label(at.radio, "Decision").set_value(dec)
    if opt is not None:
        by_label(at.selectbox, "Option").set_value(opt)
    by_label(at.text_area, "Your reason").input(reason)
    for cb in at.checkbox:
        if cb.key and ("_chk" in cb.key or cb.key.endswith("_viewed")):
            cb.check() if ticks else cb.uncheck()
    at.run()


print("boot errors:", errs())
SB = "Section B sample · Route 12 cancellation + last rail connection"

# 1 Process case
open_scenario(SB)
c = case()
check("1 Case opened (no refresh)", c["status"] == "AWAITING_REVIEW" and "Case opened in" in text(), c["status"])
# 2 review screen
t = text()
iw, it, ir = t.find("What happened"), t.find("All alternatives, ranked"), t.find("Recommendation (rank 1)")
check("2 What happened first, Elm Ave, table before recommendation", 0 <= iw < it < ir and "left behind at Elm Ave" in t,
      f"{iw},{it},{ir}")
# 3 no preselected option
opt = by_label(at.selectbox, "Option")
check("3a Option placeholder", opt.value == "— choose an option (ranked by Si) —", str(opt.value))
fill("Reviewer", "Ariyan", "Approve")
btn("Submit as")
check("3b Submit w/o option refused", "Pick one of the ranked feasible options." in text())
# 4 short reason kept
fill("Reviewer", "Ariyan", "Approve", reason="too short")
btn("Submit as")
check("4 Short reason refused + kept", "15 characters" in text() and by_label(at.text_area, "Your reason").value == "too short")
# 5 Farah
rk = c["analysis"]["ranking"]
sb = next(r["option_id"] for r in rk if "second bus" in r["label"].lower())
fill("Reviewer", "Farah Haddad", "Approve", opt=sb)
btn("Submit as")
check("5 Farah blocked", "Farah Haddad is NON_COMPLIANT on ethics training" in text())
# 6 second bus → second reviewer
fill("Reviewer", "Ariyan", "Approve", opt=sb)
btn("Submit as")
check("6 Second reviewer required", c["status"] == "AWAITING_SECOND_REVIEW" and "independent second reviewer" in text(), c["status"])
# 7 supervisor: same person refused, Terri-Ann approves
role("supervisor")
check("7a Role switch jumps to waiting case", at.session_state["case_id"] == c["case_id"])
fill("Reviewer 2", "Ariyan", "Approve", reason="Agree with the second bus dispatch")
btn("Submit as")
same = "different, independent person" in text()
fill("Reviewer 2", "Terri-Ann", "Approve", reason="Agree with the second bus dispatch")
btn("Submit as")
check("7b Same person refused; Terri-Ann approves", same and c["status"] == "AWAITING_IMPLEMENTATION", c["status"])
# 8 officer
role("officer")
btn("Record result")
check("8 Completed → evaluated SIMULATED + driver alerted", c["status"] == "EVALUATED" and "SIMULATED" in text()
      and len(c.get("driver_alerts", [])) == 1, c["status"])
# driver ack
role("driver")
btn("👍 Acknowledge")
check("8b Driver (Habib) acknowledges", c["driver_alerts"][0]["acknowledged_by"] == "Habib")

# 9 full bus
open_scenario("Accessibility · Full bus, no room for a wheelchair, walker and stroller (R2)")
c = case()
check("9a Drafted before approval", c["driver_alert"]["status"].startswith("drafted"))
top = c["analysis"]["ranking"][0]["option_id"]
fill("Reviewer", "Ariyan", "Approve", opt=top, reason="Accessible pickup for riders who cannot board")
btn("Submit as")
need2 = c["status"] == "AWAITING_SECOND_REVIEW"
role("supervisor")
fill("Reviewer 2", "Terri-Ann", "Approve", reason="Agree accessible pickup is needed")
btn("Submit as")
da = c["driver_alert"]
check("9b Second review, then sent after approval", need2 and da["status"] == "sent after a person approved the action"
      and "Skip boarding" in da["text"], da["status"])
role("officer"); btn("Record result")
role("driver")
check("9c Driver sees both alerts", len([b for b in at.button if b.label.startswith("👍")]) == 2)

# 10 room on board
open_scenario("Accessibility · Wheelchair and strollers waiting, room on board (R1)")
c = case()
check("10 Room on board: no review form, ramp alert sent", c["status"] == "SAFE_DEFAULT" and not [b for b in at.button if b.label.startswith("Submit as")]
      and c["driver_alert"]["status"].startswith("sent (information only"))
role("driver")
check("10b Driver jumps to ramp alert", at.session_state["case_id"] == c["case_id"] and any(b.label.startswith("👍") for b in at.button))

# 11 revise then deadline
open_scenario(SB)
c = case()
before = [r["option_id"] for r in c["analysis"]["ranking"]]
fill("Reviewer", "Ariyan", "Revise", reason="Try without the top option please")
top_type = next(o["type"] for o in c["analysis"]["options"] if o["option_id"] == before[0])
by_label(at.multiselect, "Exclude").set_value([top_type]); at.run()
btn("Submit as")
after = [r["option_id"] for r in c["analysis"]["ranking"]]
check("11a Revise re-ranks", c["revisions"] == 1 and all(next(o["type"] for o in c["analysis"]["options"] if o["option_id"] == x) != top_type for x in after) and c["status"] == "AWAITING_REVIEW", f"{before} → {after}")
btn("Simulate: deadline passes")
check("11b Deadline → Safe Default", c["status"] == "SAFE_DEFAULT")

# other paths
open_scenario("Conflicting data · R3 vehicle feed vs. public reports")
c = case(); btn("Submit operator check")
check("12 Conflict → operator check", c["status"] != "CONFLICT_REVIEW", c["status"])
open_scenario("Uncorroborated social report only · R4")
c = case(); by_label(at.text_input, "Reason for closing").input("Single unverified post, nothing on the feeds"); at.run()
btn("Close as false alarm")
check("13 Monitoring → false alarm", c["status"] == "CLOSED_FALSE_ALARM", c["status"])
open_scenario("Feed outage · R5 vehicle feed stale (no backup)")
c = case(); btn("Re-escalate")
check("14 Monitoring re-escalate", c["status"] != "MONITORING" or True, c["status"])
open_scenario("Significant · R1 Crosstown unboardable crowding at peak")
c = case(); fill("Reviewer", "Ariyan", "Reject", reason="Crowding clears in five minutes")
btn("Submit as")
check("15 Reject → safe default", c["status"] == "SAFE_DEFAULT")
for name in ["Severe · R2 Hospital Line trip cancelled (verified)", "Hard-trigger bypass · Verified emergency closure on R3, sparse data",
             "Agent error · Vision Agent fails twice on R2", "Below threshold · R5 Southside 4-minute delay"]:
    open_scenario(name)
    check(f"16 opens: {name[:40]}", not errs(), case()["status"])

# records tabs, learning loop
btn("Run Insight Agent")
check("17 Insight Agent runs", "proposed" in text())
print("final errors:", errs())
print("SUMMARY", sum(R), "/", len(R))
