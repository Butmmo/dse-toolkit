"""Weekly digest sync (the runner starts it every 30 minutes): once a week, builds your digest and sends it to your Dashboard and, once, to your phone.

    python bridge/digest_sync.py            do what is due this moment (usually nothing)
    python bridge/digest_sync.py --now      build and send the digest for the last full week now, even if it was sent before
    python bridge/digest_sync.py --dry      show what would be sent, send nothing

The digest is your own week in numbers from the taps, calls and payments you logged (dse/digest.py). It goes only to your own Citadel account. One digest per week; a PC that
was off on Monday catches up when it is next on; a digest more than 3 days late, or one that comes during quiet hours, is kept but not announced. Prints nothing when nothing is due.
Needs the one-time database update 20261123090000_weekly_digest.sql (the helper says so if it is missing).
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from dse import briefnotify, digest  # noqa: E402


def _runner():
    spec = importlib.util.spec_from_file_location("dse_runner", HERE / "runner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_state() -> dict:
    try:
        return json.loads(digest.STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--now", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    now = dt.datetime.now()
    cfg = digest.settings()
    if a.now:
        due = digest.due_moment(now, {"day": 0, "hour": 0})
        plan = {"week": digest.week_for(due), "notify": True, "why": "you asked for it now"}
    else:
        quiet = briefnotify.is_quiet(now, briefnotify.settings())
        plan = digest.decide(now, cfg, load_state(), quiet)
    if not plan["week"]:
        if a.dry:
            print(f"nothing due ({plan['why']})")
        return
    start, end = plan["week"]
    d = digest.build(start, end, now=now)
    text = digest.render(d)
    if a.dry:
        print(text)
        print(f"({plan['why']}; would{'' if plan['notify'] else ' not'} notify)")
        return
    digest.FOLDER.mkdir(parents=True, exist_ok=True)
    (digest.FOLDER / f"{start.isoformat()}.md").write_text(text, encoding="utf-8")
    r = _runner()
    api = r.Api(r.load_env())
    try:
        notified = api.rpc("hq_digest_push", {"p_week": start.isoformat(), "p_digest": d, "p_title": "Your week" if plan["notify"] else "", "p_body": digest.body(d) if plan["notify"] else ""}, tries=1)
    except RuntimeError as e:
        msg = str(e)
        sys.exit("the database update 20261123090000_weekly_digest.sql has not been run yet" if ("hq_digest_push" in msg and ("HTTP 404" in msg or "PGRST202" in msg or "Could not find" in msg)) else msg[:160])
    digest.STATE.parent.mkdir(exist_ok=True)
    digest.STATE.write_text(json.dumps({"last_week": start.isoformat(), "sent_at": now.isoformat(timespec="minutes"), "notified": bool(notified)}), encoding="utf-8")
    print(f"{now:%H:%M:%S} weekly digest for {digest.span(d)} sent to your Dashboard" + (" and your phone" if notified else ""))


if __name__ == "__main__":
    main()
