"""Schedules: run a tool (or one of your My tools) by itself every day, weekday, week or month, at a time you choose.

The Schedules page in Citadel stores each schedule (the tool, its values, when). This module is the PC's side, as pure logic with no network, so it can be tested:
which moment is due, whether to run it, what to say about it. bridge/schedule_sync.py (every minute, while the runner is on) does the pulling and the queueing.

The rules, all in code:
  * Times are THIS PC's local time. A schedule runs only while the PC is on and the runner is running.
  * A schedule is a normal job in your Jobs list (same log, files and Cancel button): scheduling adds no new power. Only ordinary tools, My tools and the toolkit's extras can be
    scheduled: never Dev, Setup or Studio tools. A tool that needs you to pick a file cannot be scheduled (put it inside a My tools recipe instead).
  * Each moment runs at most once. If the PC was off at the moment, the run still happens when it comes back within 12 hours; later than that it is skipped (and says so),
    never stacked up. If the previous run is still going, the new one is skipped.
  * A new schedule never runs for a moment that already passed.
  * After 3 failed runs in a row it pauses itself and tells you; pressing Resume in the app clears that.
  * You are alerted on your phone (the same quiet push and the same profile switch as the Daily Brief) when a scheduled run FAILS for the first time in a row, when a schedule PAUSES
    itself, and when a schedule CANNOT RUN on this PC (its tool is missing): once for each, never during quiet hours (it waits until they end), retried for up to 30 minutes
    if the push is held back, and dropped after 24 hours. A second and third failure in a row do not buzz again: the pause does.
  * It never sends, posts or pays: no tool does.
Standard library only.
"""
from __future__ import annotations

import datetime as dt
import re

FREQ = ("daily", "weekdays", "weekly", "monthly")
CATCHUP_H = 12
MAX_FAILS = 3
MAX_SCHEDULES = 20
DENY_GROUPS = {"Dev", "Setup", "Studio"}
DENY_PREFIX = ("dev.", "dse.studio", "dse.mytool", "dse.claude")
TIME = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
FMT = "%Y-%m-%dT%H:%M"


def schedulable(key: str, tool: dict) -> str:
    """'' when the tool may be scheduled, else the reason in plain words."""
    if key.startswith(DENY_PREFIX) or tool.get("group") in DENY_GROUPS:
        return "Dev, Setup and Studio tools cannot be scheduled"
    for f in tool.get("fields", []):
        if f.get("type") == "file" and f.get("required"):
            return f"it needs you to pick a file ('{f.get('label', f.get('name'))}'): put it in a My tools recipe, which can pass a file from one step to the next"
    return ""


def validate(s: dict, tools: dict, checker=None) -> list[str]:
    """Problems with a schedule, in plain words (empty = fine). checker(field, value) raises ValueError on a value the tool refuses."""
    p = []
    if s.get("frequency") not in FREQ:
        p.append(f"frequency must be one of {', '.join(FREQ)}")
    if not TIME.match(str(s.get("at_time", ""))):
        p.append("the time must be HH:MM (24 hours)")
    if s.get("frequency") == "weekly" and not (isinstance(s.get("weekday"), int) and 0 <= s["weekday"] <= 6):
        p.append("a weekly schedule needs a day of the week")
    if s.get("frequency") == "monthly" and not (isinstance(s.get("month_day"), int) and 1 <= s["month_day"] <= 28):
        p.append("a monthly schedule needs a day from 1 to 28")
    key = s.get("tool", "")
    tool = tools.get(key)
    if tool is None:
        p.append(f"this PC does not offer the tool '{key}'")
        return p
    why = schedulable(key, tool)
    if why:
        p.append(why)
        return p
    params = s.get("params") or {}
    fields = {f["name"]: f for f in tool.get("fields", [])}
    for k in params:
        if k not in fields:
            p.append(f"the tool has no value called '{k}'")
    if checker:
        for name, f in fields.items():
            if f.get("type") == "file":
                continue
            try:
                checker(f, params.get(name))
            except ValueError as e:
                p.append(str(e))
    return p


# ------------------------------------------------------------------ when

def _at(day: dt.date, s: dict) -> dt.datetime:
    h, m = str(s["at_time"]).split(":")
    return dt.datetime.combine(day, dt.time(int(h), int(m)))


def _day_ok(day: dt.date, s: dict) -> bool:
    f = s["frequency"]
    if f == "daily":
        return True
    if f == "weekdays":
        return day.weekday() < 5
    if f == "weekly":
        return day.weekday() == s["weekday"]
    return day.day == s["month_day"]


def slot_before(s: dict, now: dt.datetime) -> dt.datetime:
    """The latest moment this schedule was due, at or before now (local time)."""
    day = now.date()
    for _ in range(70):
        if _day_ok(day, s) and _at(day, s) <= now:
            return _at(day, s)
        day -= dt.timedelta(days=1)
    raise ValueError("schedule never due")


def next_slot(s: dict, now: dt.datetime) -> dt.datetime:
    """The next moment it is due, after now."""
    day = now.date()
    for _ in range(70):
        if _day_ok(day, s) and _at(day, s) > now:
            return _at(day, s)
        day += dt.timedelta(days=1)
    raise ValueError("schedule never due")


def describe(s: dict) -> str:
    t = str(s.get("at_time", ""))
    f = s.get("frequency")
    if f == "daily":
        return f"Every day at {t}"
    if f == "weekdays":
        return f"Every weekday (Monday to Friday) at {t}"
    if f == "weekly":
        return f"Every {DAYS[s['weekday']]} at {t}"
    return f"On day {s.get('month_day')} of every month at {t}"


# ------------------------------------------------------------------ what to do this minute

def decide(s: dict, st: dict, now: dt.datetime, job_state: str | None) -> dict:
    """The PC's decision for one schedule. Returns {"queue": the moment to run or None, "status": the new status to keep (and show in the app)}.
    st is the status kept from last time ({} for a new schedule); job_state is the state of the last job this schedule queued (done, failed, cancelled, queued, running) or None."""
    st = dict(st or {})
    st.setdefault("fails", 0)
    # Resume pressed in the app: forget the failures
    if s.get("reset_at") and st.get("reset_seen") != s["reset_at"]:
        st.update(fails=0, paused=False, reset_seen=s["reset_at"], note="Resumed.")
    # count the outcome of the last run once
    if st.get("last_job") and st.get("counted_job") != st["last_job"] and job_state in ("done", "failed", "cancelled"):
        st["counted_job"] = st["last_job"]
        st["last_state"] = job_state
        if job_state == "done":
            st["fails"] = 0
        elif job_state == "failed":
            st["fails"] = int(st.get("fails", 0)) + 1
    elif job_state:
        st["last_state"] = job_state
    if st["fails"] >= MAX_FAILS and not st.get("paused"):
        st.update(paused=True, note=f"Paused after {MAX_FAILS} failed runs in a row. Fix the cause (open the failed job in Jobs), then press Resume.")
    slot = slot_before(s, now)
    st["next_run"] = next_slot(s, now).strftime(FMT)
    queue = None
    last = st.get("last_slot")
    if not last:
        st["last_slot"] = slot.strftime(FMT)                       # a new schedule never runs for a moment that already passed
        st["note"] = st.get("note") or "Waiting for its first moment."
    elif slot.strftime(FMT) > last:
        late = now - slot
        if not s.get("enabled", True):
            st.update(last_slot=slot.strftime(FMT), note="Skipped: the schedule was off at that moment.")
        elif st.get("paused"):
            st.update(last_slot=slot.strftime(FMT), note="Skipped: the schedule is paused after failed runs.")
        elif late > dt.timedelta(hours=CATCHUP_H):
            st.update(last_slot=slot.strftime(FMT), note=f"Skipped the {slot:%a %H:%M} run: this PC was off for more than {CATCHUP_H} hours after it.")
        elif job_state in ("queued", "running"):
            st.update(last_slot=slot.strftime(FMT), note=f"Skipped the {slot:%a %H:%M} run: the previous run was still going.")
        else:
            queue = slot.strftime(FMT)
            st["note"] = f"Queued the {slot:%a %H:%M} run" + (" (late: the PC was off at the moment)." if late > dt.timedelta(minutes=5) else ".")
    return {"queue": queue, "status": st}


# ------------------------------------------------------------------ alerts: tell the member when an unattended run goes wrong

ALERT_TRIES = 30            # one try a minute: about half an hour, then give up (a push held back for that long is no longer news)
ALERT_MAX_AGE = dt.timedelta(hours=24)
SENT_KEEP = 20


def _alert(kind: str, name: str, extra: str = "") -> tuple[str, str]:
    name = (name or "A schedule")[:60]
    if kind == "fail":
        return "A scheduled run failed", f'"{name}" failed. Open Jobs in HQ Tools to see why. It will try again at its next time.'
    if kind == "pause":
        return "A schedule paused itself", f'"{name}" failed {MAX_FAILS} times in a row and is paused. Fix the cause, then press Resume on the Schedules page.'
    return "A schedule cannot run", f'"{name}" cannot run on your PC: {extra[:160]}.'


def add_alert(st: dict, key: str, kind: str, name: str, now: dt.datetime, extra: str = "") -> bool:
    """Queue one alert in the schedule's status unless this one was already queued or sent. Returns True if it was added."""
    if key in st.get("alerts_sent", []) or any(a.get("key") == key for a in st.get("alerts_pending", [])):
        return False
    title, body = _alert(kind, name, extra)
    st.setdefault("alerts_pending", []).append({"key": key, "title": title, "body": body, "at": now.strftime(FMT), "tries": 0})
    return True


def transitions(name: str, prev: dict, st: dict, now: dt.datetime) -> list[str]:
    """Look at what changed since last minute and queue the alerts it earns. Returns the keys added (for tests)."""
    prev = prev or {}
    added = []
    counted = st.get("counted_job")
    if counted and counted != prev.get("counted_job") and st.get("last_state") == "failed" and st.get("fails") == 1:
        k = f"fail:{counted}"
        if add_alert(st, k, "fail", name, now):
            added.append(k)
    if st.get("paused") and not prev.get("paused"):
        k = f"pause:{counted or st.get('reset_seen') or 'x'}"
        if add_alert(st, k, "pause", name, now):
            added.append(k)
    if not st.get("problem") and prev.get("problem"):          # fixed: the same problem coming back later is news again
        st["alerts_sent"] = [k for k in st.get("alerts_sent", []) if not k.startswith("problem:")]
    if st.get("problem") and st["problem"] != prev.get("problem"):
        k = f"problem:{st['problem'][:80]}"
        if add_alert(st, k, "problem", name, now, st["problem"]):
            added.append(k)
    return added


def due_alerts(st: dict, now: dt.datetime, quiet: bool) -> list[dict]:
    """The alerts to try to deliver this minute: none during quiet hours (they wait), and none older than 24 hours (dropped here)."""
    keep = []
    for a in st.get("alerts_pending", []):
        try:
            age = now - dt.datetime.strptime(a["at"], FMT)
        except (KeyError, ValueError):
            continue
        if age <= ALERT_MAX_AGE:
            keep.append(a)
    st["alerts_pending"] = keep
    return [] if quiet else list(keep)


def settle(st: dict, key: str, delivered: bool) -> str:
    """Record the outcome of one delivery try. Returns 'sent', 'gave up' or 'retry'."""
    pend = st.get("alerts_pending", [])
    a = next((x for x in pend if x.get("key") == key), None)
    if a is None:
        return "sent"
    a["tries"] = int(a.get("tries", 0)) + 1
    if delivered or a["tries"] >= ALERT_TRIES:
        st["alerts_pending"] = [x for x in pend if x is not a]
        st["alerts_sent"] = ([*st.get("alerts_sent", []), key])[-SENT_KEEP:]
        return "sent" if delivered else "gave up"
    return "retry"
