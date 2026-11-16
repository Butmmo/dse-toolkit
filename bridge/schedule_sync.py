"""Schedules sync: the schedules you made in Citadel (HQ Tools, Schedules), run by this PC when they are due.

    python bridge/schedule_sync.py          pull the schedules, queue what is due, report back
    python bridge/schedule_sync.py --dry    show what it would do, queue nothing

The runner runs this every minute (catalog.json "periodic"). A schedule is not a new way to run things: when one is due this queues an ordinary job in your account
(the same Jobs list, log, files and Cancel button as pressing Run), and the runner picks it up as usual. The rules (local time, 12-hour catch-up, never twice for
one moment, a pause after 3 failures, no Dev/Setup/Studio tools, no file pickers) are in dse/schedules.py. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from dse import briefnotify, schedules  # noqa: E402


def _runner():
    spec = importlib.util.spec_from_file_location("dse_runner", HERE / "runner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def plan(rows: list[dict], tools: dict, now: dt.datetime, checker=None) -> list[dict]:
    """For each pulled schedule: {"id", "status", "queue": moment or None, "problems"}. Pure: nothing is sent from here."""
    out = []
    for row in rows:
        s = {k: row.get(k) for k in ("tool", "params", "frequency", "weekday", "month_day", "at_time", "enabled", "reset_at")}
        problems = schedules.validate(s, tools, checker)
        try:
            d = schedules.decide(s, row.get("pc_status") or {}, now, row.get("last_job_state"))
        except ValueError:
            out.append({"id": row["id"], "status": {"note": "This schedule is not valid.", "problem": "frequency or time"}, "queue": None, "problems": ["not valid"]})
            continue
        st, queue = d["status"], d["queue"]
        if problems:
            st["problem"] = "; ".join(problems[:2])
            if queue:
                st["last_slot"], st["note"], queue = queue, f"Skipped: {problems[0]}.", None
        else:
            st["problem"] = ""             # written as empty, not removed: the database merges statuses, so a removed key would keep showing the old problem
        schedules.transitions(row.get("name", ""), row.get("pc_status") or {}, st, now)
        out.append({"id": row["id"], "status": st, "queue": queue, "problems": problems})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    r = _runner()
    api = r.Api(r.load_env())
    cat = r.load_catalog()

    def checker(field, value):
        try:
            r.check_value(field, value)
        except r.Bad as e:
            raise ValueError(str(e)) from None

    rows = api.rpc("hq_schedules_pull", {}) or []
    now = dt.datetime.now().replace(second=0, microsecond=0)
    quiet = briefnotify.is_quiet(now, briefnotify.settings())
    queued = 0
    statuses = {}
    for d in plan(rows, cat["tools"], now, checker):
        st = d["status"]
        if d["queue"]:
            if a.dry:
                print(f"would queue {d['id']} for {d['queue']}")
            else:
                try:
                    jid = api.rpc("hq_schedule_queue", {"p_schedule": d["id"], "p_slot": d["queue"]})
                    st["last_slot"] = d["queue"]
                    if jid:
                        st.update(last_job=jid, last_queued_at=now.strftime(schedules.FMT))
                        queued += 1
                except RuntimeError as e:
                    st["note"] = f"Could not queue it yet ({str(e)[:120]}); trying again."
        if not a.dry:
            for al in schedules.due_alerts(st, now, quiet):      # a quiet push for a run that failed, a schedule that paused, one that cannot run
                try:
                    delivered = bool(api.rpc("hq_brief_notify", {"p_title": al["title"], "p_body": al["body"]}, tries=1))
                except RuntimeError:
                    delivered = False
                schedules.settle(st, al["key"], delivered)
        statuses[d["id"]] = st
    if a.dry:
        print(f"{len(rows)} schedule(s) in Citadel")
        return
    if statuses:
        api.rpc("hq_schedule_status", {"p_status": statuses})
    if queued:
        print(f"{dt.datetime.now():%H:%M:%S} schedules: {queued} scheduled run(s) queued")


if __name__ == "__main__":
    main()
