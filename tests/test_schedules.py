"""Tests for Schedules: when a moment is due, what the PC decides each minute, and the limits.   python tests/test_schedules.py"""
import datetime as dt
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import schedules as S  # noqa: E402

spec_ = importlib.util.spec_from_file_location("sync", ROOT / "bridge" / "schedule_sync.py")
SYNC = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(SYNC)

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def at(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M")


def sched(**k):
    return {"frequency": "daily", "at_time": "07:00", "enabled": True, "tool": "t.find", "params": {"kind": "dentists"}, **k}


# 2026-11-16 is a Monday
check("the calendar I rely on: 16 Nov 2026 is a Monday", at("2026-11-16 00:00").weekday() == 0)

# ---------------------------------------------------------------- when a moment is due
d = sched()
check("daily: before the time it is yesterday's moment", S.slot_before(d, at("2026-11-16 06:59")) == at("2026-11-15 07:00"))
check("daily: exactly at the time it is today's", S.slot_before(d, at("2026-11-16 07:00")) == at("2026-11-16 07:00"))
check("daily: next after the moment is tomorrow", S.next_slot(d, at("2026-11-16 07:00")) == at("2026-11-17 07:00") and S.next_slot(d, at("2026-11-16 06:00")) == at("2026-11-16 07:00"))
wd = sched(frequency="weekdays")
check("weekdays: Saturday's latest moment was Friday", S.slot_before(wd, at("2026-11-21 10:00")) == at("2026-11-20 07:00"))
check("weekdays: the next after Friday is Monday", S.next_slot(wd, at("2026-11-20 08:00")) == at("2026-11-23 07:00"))
wk = sched(frequency="weekly", weekday=0)
check("weekly (Monday): at Tuesday the latest was Monday", S.slot_before(wk, at("2026-11-17 10:00")) == at("2026-11-16 07:00"))
check("weekly: the next after this Monday's moment is next Monday", S.next_slot(wk, at("2026-11-16 07:00")) == at("2026-11-23 07:00"))
mo = sched(frequency="monthly", month_day=1)
check("monthly (day 1): across a month end", S.slot_before(mo, at("2026-11-30 23:00")) == at("2026-11-01 07:00") and S.next_slot(mo, at("2026-11-30 23:00")) == at("2026-12-01 07:00"))
check("monthly: across the year end", S.next_slot(mo, at("2026-12-15 10:00")) == at("2027-01-01 07:00"))
mo28 = sched(frequency="monthly", month_day=28)
check("monthly day 28 exists in February", S.next_slot(mo28, at("2027-02-10 10:00")) == at("2027-02-28 07:00"))
check("the words", S.describe(d) == "Every day at 07:00" and S.describe(wd) == "Every weekday (Monday to Friday) at 07:00" and S.describe(wk) == "Every Monday at 07:00" and S.describe(mo) == "On day 1 of every month at 07:00")

# ---------------------------------------------------------------- validation
TOOLS = {
    "t.find": {"label": "Find", "group": "Find clients", "fields": [{"name": "kind", "label": "Kind", "type": "text", "required": True}]},
    "my.chain": {"label": "A recipe", "group": "My tools", "fields": []},
    "t.needsfile": {"label": "Check", "group": "Check websites", "fields": [{"name": "list", "label": "A list", "type": "file", "required": True}]},
    "t.optfile": {"label": "Opt", "group": "Check websites", "fields": [{"name": "list", "type": "file"}]},
    "dev.run": {"label": "Run", "group": "Dev", "fields": []},
    "dse.doctor": {"label": "Check", "group": "Setup", "fields": []},
    "dse.studio_test": {"label": "t", "group": "Studio", "fields": []},
    "dse.mytool_check": {"label": "t", "group": "My tools", "fields": []},
    "dse.claude_status": {"label": "t", "group": "Setup", "fields": []},
}


def bad(**k):
    return S.validate(sched(**k), TOOLS)


check("a good schedule has no problems", S.validate(sched(), TOOLS) == [])
check("a My tools recipe can be scheduled", S.validate(sched(tool="my.chain", params={}), TOOLS) == [])
check("a bad frequency", any("frequency" in x for x in bad(frequency="hourly")))
check("a bad time", any("HH:MM" in x for x in bad(at_time="7am")) and any("HH:MM" in x for x in bad(at_time="24:00")) and any("HH:MM" in x for x in bad(at_time="07:60")))
check("weekly needs a day", any("day of the week" in x for x in bad(frequency="weekly")))
check("monthly needs a day 1 to 28 (no 31st)", any("1 to 28" in x for x in bad(frequency="monthly", month_day=31)) and any("1 to 28" in x for x in bad(frequency="monthly")))
check("a tool this PC does not offer", any("does not offer" in x for x in bad(tool="t.gone")))
check("Dev, Setup, Studio and the control tools are refused", all(any("cannot be scheduled" in x for x in bad(tool=k, params={})) for k in ("dev.run", "dse.doctor", "dse.studio_test", "dse.mytool_check", "dse.claude_status")))
check("a tool that needs a file is refused, with the way round it", any("My tools recipe" in x for x in bad(tool="t.needsfile", params={})))
check("an optional file is fine", S.validate(sched(tool="t.optfile", params={}), TOOLS) == [])
check("a value the tool does not have", any("no value called" in x for x in bad(params={"kind": "x", "zzz": 1})))


def checker(field, value):
    if field["name"] == "kind" and not value:
        raise ValueError("Kind is required")


check("a value the tool refuses (the runner's own check)", S.validate(sched(params={}), TOOLS, checker) == ["Kind is required"])

# ---------------------------------------------------------------- what the PC decides each minute
def step(s, st, now, job=None):
    r = S.decide(s, st, at(now), job)
    return r["queue"], r["status"]


q, st = step(d, {}, "2026-11-16 09:00")
check("a new schedule does not run for a moment that already passed", q is None and st["last_slot"] == "2026-11-16T07:00" and st["next_run"] == "2026-11-17T07:00")
q, st2 = step(d, st, "2026-11-16 12:00")
check("nothing more until the next moment", q is None)
q, st3 = step(d, st2, "2026-11-17 07:00")
check("at its moment it queues that moment", q == "2026-11-17T07:00" and "Queued" in st3["note"])
st3.update(last_slot=q, last_job="job-1")
q, st4 = step(d, st3, "2026-11-17 07:01", "running")
check("it never queues the same moment twice (the next minutes)", q is None)
q, st5 = step(d, st4, "2026-11-17 23:00", "done")
check("a finished run is counted and the failures reset", q is None and st5["fails"] == 0 and st5["last_state"] == "done" and st5["counted_job"] == "job-1")

# the PC was off
base = {"last_slot": "2026-11-16T07:00", "fails": 0}
q, st = step(d, base, "2026-11-17 10:00")
check("PC back 3 hours late: it still runs, and says it was late", q == "2026-11-17T07:00" and "late" in st["note"])
q, st = step(d, base, "2026-11-17 19:30")
check("PC back more than 12 hours late: skipped, and says so", q is None and "Skipped" in st["note"] and "12 hours" in st["note"] and st["last_slot"] == "2026-11-17T07:00")
q, st = step(d, {**base}, "2026-11-19 07:00")
check("after days off it runs only the newest moment, never a pile", q == "2026-11-19T07:00")
q, st = step(d, base, "2026-11-17 07:00", "running")
check("a previous run still going: skipped, not stacked", q is None and "still going" in st["note"])
q, st = step(sched(enabled=False), base, "2026-11-17 07:00")
check("a schedule that is off does not run, and does not run later when switched on for an old moment", q is None and st["last_slot"] == "2026-11-17T07:00" and "off" in st["note"])

# failures pause it
s_ = {"last_slot": "2026-11-16T07:00", "fails": 0, "last_job": "j1"}
q, s1 = step(d, s_, "2026-11-16 08:00", "failed")
check("one failure is counted", s1["fails"] == 1 and not s1.get("paused"))
s1.update(last_job="j2")
q, s2 = step(d, s1, "2026-11-16 09:00", "failed")
s2.update(last_job="j3")
q, s3 = step(d, s2, "2026-11-16 10:00", "failed")
check("three failures in a row pause it and say what to do", s3["fails"] == 3 and s3["paused"] and "Resume" in s3["note"], str(s3))
q, s4 = step(d, s3, "2026-11-17 07:00")
check("while paused it does not run", q is None and "paused" in s4["note"])
q, s5 = step(sched(reset_at="2026-11-17T08:00:00Z"), s4, "2026-11-17 08:01")
check("Resume clears the failures", s5["fails"] == 0 and not s5["paused"] and s5["reset_seen"] == "2026-11-17T08:00:00Z")
q, s6 = step(sched(reset_at="2026-11-17T08:00:00Z"), s5, "2026-11-18 07:00")
check("and it runs again at the next moment", q == "2026-11-18T07:00")
q, s7 = step(d, {"last_slot": "2026-11-16T07:00", "last_job": "jx", "fails": 2}, "2026-11-16 08:00", "failed")
check("a cancelled run is not a failure", step(d, {"last_slot": "2026-11-16T07:00", "last_job": "jc", "fails": 2}, "2026-11-16 08:00", "cancelled")[1]["fails"] == 2)

# ---------------------------------------------------------------- the helper's plan
rows = [{"id": "a", **sched(), "pc_status": {"last_slot": "2026-11-16T07:00"}},
        {"id": "b", **sched(tool="t.gone", params={}), "pc_status": {"last_slot": "2026-11-16T07:00"}},
        {"id": "c", **sched(tool="dev.run", params={}), "pc_status": {}}]
res = {x["id"]: x for x in SYNC.plan(rows, TOOLS, at("2026-11-17 07:00"))}
check("a valid due schedule is queued", res["a"]["queue"] == "2026-11-17T07:00" and not res["a"]["problems"])
check("a due schedule whose tool this PC lacks is not queued, and says why", res["b"]["queue"] is None and "does not offer" in res["b"]["status"]["problem"] and res["b"]["status"]["last_slot"] == "2026-11-17T07:00")
check("a forbidden tool is never queued", res["c"]["queue"] is None and "cannot be scheduled" in res["c"]["status"]["problem"])
check("a broken schedule does not crash the helper", SYNC.plan([{"id": "z", "frequency": "monthly", "at_time": "07:00", "pc_status": {}}], TOOLS, at("2026-11-17 07:00"))[0]["queue"] is None)

# ---------------------------------------------------------------- alerts: a quiet push when an unattended run goes wrong
NOW = at("2026-11-17 08:00")


def run_minutes(name, steps, d=None):
    """Feed a sequence of (job_state, time) into decide + transitions the way the helper does each minute; returns the final status."""
    d = d or sched()
    st = {"last_slot": "2026-11-16T07:00", "fails": 0}
    for n, (job, when, new_job) in enumerate(steps):
        prev = dict(st)
        if new_job:
            st["last_job"] = new_job
        st = S.decide(d, st, at(when), job)["status"]
        S.transitions(name, prev, st, at(when))
    return st


st = run_minutes("Dentists", [("failed", "2026-11-16 08:00", "j1")])
check("the first failed run earns one alert, in plain words", [a["key"] for a in st["alerts_pending"]] == ["fail:j1"] and "failed" in st["alerts_pending"][0]["title"].lower() and "Dentists" in st["alerts_pending"][0]["body"] and "Jobs" in st["alerts_pending"][0]["body"], str(st.get("alerts_pending")))
st = run_minutes("Dentists", [("failed", "2026-11-16 08:00", "j1"), ("failed", "2026-11-16 08:01", None)])
check("the same failure seen again the next minute does not alert twice", len(st["alerts_pending"]) == 1)
st = run_minutes("Dentists", [("failed", "2026-11-16 08:00", "j1"), ("failed", "2026-11-17 08:00", "j2")])
check("a second failure in a row does not buzz again", [a["key"] for a in st["alerts_pending"]] == ["fail:j1"] and st["fails"] == 2)
st = run_minutes("Dentists", [("failed", "2026-11-16 08:00", "j1"), ("failed", "2026-11-17 08:00", "j2"), ("failed", "2026-11-18 08:00", "j3")])
check("the third failure pauses the schedule and earns the pause alert, which says what to do", st["paused"] and [a["key"] for a in st["alerts_pending"]] == ["fail:j1", "pause:j3"] and "Resume" in st["alerts_pending"][1]["body"], str(st.get("alerts_pending")))
st = run_minutes("Dentists", [("done", "2026-11-16 08:00", "j1")])
check("a run that finished well earns no alert", not st.get("alerts_pending"))
st = run_minutes("Dentists", [("cancelled", "2026-11-16 08:00", "j1")])
check("a cancelled run earns no alert", not st.get("alerts_pending"))
long_ago = {"last_slot": "2026-11-16T07:00", "fails": 1, "last_job": "old", "counted_job": "old", "last_state": "failed"}
st2 = S.decide(sched(), long_ago, at("2026-11-16 09:00"), "failed")["status"]
S.transitions("Old", long_ago, st2, at("2026-11-16 09:00"))
check("an old failure already counted does not alert again after an update or a restart", not st2.get("alerts_pending"))

# problems: a tool this PC lacks
rows = [{"id": "p", "name": "Ghost", **sched(tool="t.gone", params={}), "pc_status": {"last_slot": "2026-11-16T07:00"}}]
res = SYNC.plan(rows, TOOLS, at("2026-11-16 12:00"))[0]["status"]
check("a schedule whose tool this PC lacks earns one alert naming the reason", [a["key"].split(":")[0] for a in res["alerts_pending"]] == ["problem"] and "does not offer" in res["alerts_pending"][0]["body"], str(res.get("alerts_pending")))
rows2 = [{"id": "p", "name": "Ghost", **sched(tool="t.gone", params={}), "pc_status": res}]
res2 = SYNC.plan(rows2, TOOLS, at("2026-11-16 12:01"))[0]["status"]
check("the same problem next minute does not alert again", len(res2["alerts_pending"]) == 1)
rows3 = [{"id": "p", "name": "Ghost", **sched(), "pc_status": res2}]
res3 = SYNC.plan(rows3, TOOLS, at("2026-11-16 12:02"))[0]["status"]
check("when the problem is fixed it is written as empty (the database merges, so removing the key would leave it showing)", res3["problem"] == "")
res3["alerts_sent"] = ["problem:" + res["problem"][:80]]
rows4 = [{"id": "p", "name": "Ghost", **sched(tool="t.gone", params={}), "pc_status": res3}]
res4 = SYNC.plan(rows4, TOOLS, at("2026-11-16 12:03"))[0]["status"]
check("a problem that comes back after being fixed is news again", any(a["key"].startswith("problem:") for a in res4["alerts_pending"]))

# delivery: quiet hours, retries, giving up
pend = {"alerts_pending": [{"key": "fail:j1", "title": "t", "body": "b", "at": "2026-11-16T08:00", "tries": 0}]}
check("during quiet hours nothing is attempted, and the alert waits", S.due_alerts(dict(pend, alerts_pending=list(pend["alerts_pending"])), at("2026-11-16 22:00"), True) == [] and len(pend["alerts_pending"]) == 1)
check("outside quiet hours it is attempted", len(S.due_alerts(pend, at("2026-11-16 08:01"), False)) == 1)
check("an alert more than 24 hours old is dropped, not sent late", S.due_alerts(dict(alerts_pending=[{"key": "k", "title": "t", "body": "b", "at": "2026-11-14T08:00", "tries": 0}]), at("2026-11-16 08:01"), False) == [])
check("a delivered alert is settled and remembered, never sent twice", S.settle(pend, "fail:j1", True) == "sent" and not pend["alerts_pending"] and pend["alerts_sent"] == ["fail:j1"] and not S.add_alert(pend, "fail:j1", "fail", "X", at("2026-11-16 08:05")))
held = {"alerts_pending": [{"key": "k", "title": "t", "body": "b", "at": "2026-11-16T08:00", "tries": 0}]}
check("a push that is held back is retried", S.settle(held, "k", False) == "retry" and held["alerts_pending"][0]["tries"] == 1)
held["alerts_pending"][0]["tries"] = S.ALERT_TRIES - 1
check("after about half an hour of tries it gives up quietly", S.settle(held, "k", False) == "gave up" and not held["alerts_pending"])
big = {"alerts_sent": [f"k{i}" for i in range(40)], "alerts_pending": [{"key": "z", "title": "t", "body": "b", "at": "2026-11-16T08:00", "tries": 0}]}
S.settle(big, "z", True)
check("the list of sent alerts stays small", len(big["alerts_sent"]) <= S.SENT_KEEP)
check("the alert texts have no em dash and name the schedule", all(chr(0x2014) not in t for t in S._alert("fail", "X") + S._alert("pause", "X") + S._alert("problem", "X", "why")))
sync_src = (ROOT / "bridge" / "schedule_sync.py").read_text(encoding="utf-8")
check("alerts go through the existing quiet push only, and the quiet hours are the brief's", sync_src.count('"hq_brief_notify"') == 1 and "briefnotify.is_quiet" in sync_src)
import re  # noqa: E402
check("a held-back or failed push never stops the schedules: the delivery is inside a try", bool(re.search(r"except RuntimeError:\s+delivered = False", sync_src)))

# ---------------------------------------------------------------- the modules
src = (ROOT / "dse" / "schedules.py").read_text(encoding="utf-8") + (ROOT / "bridge" / "schedule_sync.py").read_text(encoding="utf-8")
check("no em dash", chr(0x2014) not in src)
check("the limits are the documented ones", S.CATCHUP_H == 12 and S.MAX_FAILS == 3 and S.MAX_SCHEDULES == 20)
print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
