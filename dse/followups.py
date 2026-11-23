"""Follow-ups: the next touch for everyone you messaged who has not answered.

    python dse.py followups <engine>                 plan tomorrow's follow-ups and save them as a list
    python dse.py followups <engine> --preview       show them, save nothing
    python dse.py followups <engine> --days 3        tomorrow and the two days after

Most replies come on the second or third message. This finds the businesses marked SENT with no answer, works out who is
due, drafts the next message and saves it as a normal dated list (send-lists/<date>-followups.csv), so it shows in the
Send Desk like any other list. YOU still send every message.

Rules (dse/followup_templates.json, or your own engines/<slug>/followup-templates.json):
  * only rows you marked Sent count. Rows you never marked are not guessed at: they are listed so you can mark them.
  * touch 2 and touch 3 come due a set number of days after the first message (Email 3 and 7, Instagram 3 and 7,
    Facebook 4 and 9, Website form 5 and 12). Sundays are skipped; anything overdue goes out on the next run.
  * never a second Instagram DM (Instagram delivers one message from an account that does not follow you). After an
    Instagram DM, touch 2 is a public comment on their newest post and touch 3 is a bridge note by email, website form
    or Facebook. No Instagram page on file: the bridge note goes straight away and the thread ends.
  * a thread stops for good when the business replies, books, wins, is lost, or you skip a touch. An out-of-office
    reply does not stop it. It also stops after touch 3.
  * no links in follow-ups, every message gives an easy way to say no, and nothing is sent for you.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import desklog as dl
from .common import log, write_csv
from .engines import engine_dir, load

HERE = Path(__file__).resolve().parent
CLEAN_SOURCES = re.compile(r"\d{4}-\d{2}-\d{2}-followups$")


def templates(slug: str) -> dict:
    mine = engine_dir(slug) / "followup-templates.json"
    p = mine if mine.exists() else HERE / "followup_templates.json"
    return json.loads(p.read_text(encoding="utf-8"))


def next_workday(d: dt.date) -> dt.date:
    return d + dt.timedelta(days=1) if d.weekday() == 6 else d


def pick_bridge(first: dict) -> tuple[str, str]:
    """After an Instagram DM: a way to reach them that is not Instagram."""
    if first.get("email"):
        return "Email", first["email"]
    if first.get("website"):
        return "Website form", first["website"]
    if first.get("facebook"):
        return "Facebook message", first["facebook"]
    return "", ""


def touch_plan(first: dict, n: int, prior: list[dict], tpl: dict) -> tuple[str, str, str, dict] | None:
    """(channel, where, kind, template) for touch n of this thread, or None when the thread is finished."""
    ch1 = first.get("channel", "")
    if ch1 in ("Comment (warm-up)", "LinkedIn", "Other", "Unknown", ""):
        return None
    t = tpl["touches"]
    if ch1 == "Instagram DM":
        if any(str(r.get("variant", "")).startswith("fu3-bridge") for r in prior):
            return None                                    # the bridge note already went out: finished
        handle = dl.ig_handle(first.get("instagram", "")) or dl.ig_handle(first.get("where", ""))
        if n == 2 and handle:
            return "Instagram comment", f"https://www.instagram.com/{handle}/", "comment", t["2"]["comment"]
        ch, where = pick_bridge(first)                     # touch 3, or touch 2 when there is no Instagram page to comment on
        return (ch, where, "bridge", t["3"]["bridge"]) if ch else None
    where = first.get("where", "")
    return ch1, where, "nudge" if n == 2 else "close", (t["2"]["nudge"] if n == 2 else t["3"]["close"])


def greeting(first: dict) -> str:
    host = (first.get("host") or "").split(" ")[0]
    if host:
        return f"Hi {host},"
    biz = re.sub(r"\s*\([^)]*\)\s*$", "", first.get("business") or first.get("name") or "").strip()
    return f"Hi {biz} team," if biz else "Hi,"


def render(text: str, first: dict, cfg: dict) -> str:
    biz = re.sub(r"\s*\([^)]*\)\s*$", "", first.get("business") or first.get("name") or "").strip() or "your business"
    gap = (first.get("gap_used") or first.get("gap_line") or "a gap in how your site handles enquiries").strip().rstrip(".")
    vals = {"hi": greeting(first), "business": biz, "gap_line": gap, "sender": cfg.get("sender_name", "") or "me",
            "from_brand": f" from {cfg['brand_name']}" if cfg.get("brand_name") else ""}
    try:
        return text.format(**vals).strip()
    except (KeyError, IndexError, ValueError) as e:
        return f"[follow-up wording problem: {e}] " + text


def analyse(slug: str, planned_sources: set[str] | None = None) -> dict:
    """Each thread's state: who is due for which touch and when, who is finished, and what was never marked."""
    cfg, tpl = load(slug), templates(slug)
    hist, th = dl.history(slug), dl.threads(slug)
    today = dt.date.today()
    out = {"due": [], "waiting": 0, "finished": 0, "unmarked": [], "cfg": cfg, "tpl": tpl}
    for key, t in th.items():
        first = t["first"]
        if not first:
            continue
        rows = [r for r in t["rows"] if r["_source"] not in (planned_sources or set())]
        status = {id(r): dl.status_of_row(hist, r) for r in rows}
        # a first message from a past list that was never marked: tell the member, never guess
        if dl.status_of_row(hist, first) == "to do" and first["_date"] < today.isoformat() and not first["_followup"]:
            out["unmarked"].append(first)
            continue
        stops = any(status[id(r)] in dl.ENDS_THREAD for r in rows)      # an out-of-office reply already counts as 'sent' above
        if stops:
            out["finished"] += 1
            continue
        sent_touches = [r["touch"] for r in rows if status[id(r)] == "sent"]
        if not sent_touches:
            out["waiting"] += 1
            continue
        done = max(sent_touches)
        if any(r["touch"] > done and status[id(r)] == "to do" for r in rows):
            out["waiting"] += 1                            # the next touch is already on a list: act on that
            continue
        n = done + 1
        if n > int(tpl.get("max_touches", 3)):
            out["finished"] += 1
            continue
        plan = touch_plan(first, n, rows, tpl)
        if not plan:
            out["finished"] += 1
            continue
        sched = tpl["schedule"].get(first.get("channel", ""), tpl.get("default_schedule", [4, 9]))
        first_sent = dl.sent_on(hist, first)
        if not first_sent:
            out["waiting"] += 1
            continue
        gap_days = sched[min(n - 2, len(sched) - 1)]
        due = next_workday(dt.date.fromisoformat(first_sent) + dt.timedelta(days=gap_days))
        out["due"].append({"thread": key, "first": first, "n": n, "plan": plan, "due": due, "first_sent": first_sent})
    out["due"].sort(key=lambda d: (d["due"], d["first"].get("business", "")))
    return out


def plan(slug: str, start: str | None = None, days: int = 1, write: bool = True, per_day: int | None = None) -> dict[str, list[dict]]:
    cfg = load(slug)
    per_day = per_day or int(cfg.get("followups_per_day") or max(25, int(cfg.get("per_day", 20))))
    first_day = dt.date.fromisoformat(start) if start else dt.date.today() + dt.timedelta(days=1)
    dates, d = [], first_day
    while len(dates) < days:
        if d.weekday() != 6:
            dates.append(d)
        d += dt.timedelta(days=1)
    # follow-up lists for these days that nobody has touched yet are rebuilt; touched ones are left alone
    hist = dl.history(slug)
    clicked = {s for (s, _r) in hist}
    own = {f"{x.isoformat()}-followups" for x in dates}
    rebuild = own - clicked
    A = analyse(slug, planned_sources=rebuild)
    cfg = A["cfg"]
    result: dict[str, list[dict]] = {}
    pool = list(A["due"])
    for day in dates:
        stem = f"{day.isoformat()}-followups"
        if stem in clicked:
            log(f"  {day}: its follow-up list already has taps in it, so it is left as it is")
            continue
        rows = []
        for item in [p for p in pool if p["due"] <= day][:per_day]:
            ch, where, kind, tpl = item["plan"]
            f = item["first"]
            followup_row = {"row": len(rows) + 1, "business": f.get("business") or f.get("name", ""), "city": f.get("city", ""),
                         "channel": tpl.get("channel", ch), "where": where, "gap_used": f.get("gap_used", ""),
                         "variant": tpl["variant"], "opener": render(tpl["text"], f, cfg), "website": f.get("website", ""),
                         "email": f.get("email", ""), "phone": f.get("phone", ""), "instagram": f.get("instagram", ""),
                         "facebook": f.get("facebook", ""), "touch": item["n"], "thread": item["thread"], "first_sent": item["first_sent"],
                         "notes": (tpl.get("note", "") + " " if tpl.get("note") else "") + (f"Overdue since {item['due']}." if item["due"] < day else f"Due {item['due']}.")}
            if f.get("waterfall_experiment_id"):
                for field in ("waterfall_experiment_id", "waterfall_experiment_variant", "waterfall_experiment_field",
                              "waterfall_experiment_providers", "waterfall_experiment_lead_id", "waterfall_config_sha256"):
                    followup_row[field] = f.get(field, "")
            rows.append(followup_row)
            pool.remove(item)
        result[day.isoformat()] = rows
        if write and rows:
            write_csv(engine_dir(slug) / "send-lists" / f"{stem}.csv", rows,
                      first=["row", "business", "city", "channel", "where", "gap_used", "variant", "opener"])
        elif write and not rows and stem in rebuild:
            p = engine_dir(slug) / "send-lists" / f"{stem}.csv"
            if p.exists():
                p.unlink()                              # nothing is due any more: drop the untouched list
    return result


def report(slug: str, start: str | None = None, days: int = 1, write: bool = True) -> None:
    res = plan(slug, start, days, write)
    A = analyse(slug, planned_sources={s for s in [f"{d}-followups" for d in res]} - {s for (s, _r) in dl.history(slug)})
    total = sum(len(v) for v in res.values())
    for day, rows in res.items():
        by: dict[str, int] = {}
        for r in rows:
            by[f"touch {r['touch']} {r['channel']}"] = by.get(f"touch {r['touch']} {r['channel']}", 0) + 1
        print(f"{day}: {len(rows)} follow-ups" + (f" ({', '.join(f'{v} {k}' for k, v in by.items())})" if by else "")
              + (f" -> engines/{slug}/send-lists/{day}-followups.csv" if write and rows else ""))
    if not total:
        print("Nothing is due for these days.")
    if A["unmarked"]:
        print(f"\n{len(A['unmarked'])} business(es) on past lists were never marked Sent or Skipped, so they are not followed up. "
              "Open the Send Desk and mark what you sent (Sent) or did not send (Skip):")
        for r in A["unmarked"][:8]:
            print(f"  - {r.get('business', '')} ({r['_date']}, {r.get('channel', '')})")
    print(f"\nWaiting for an answer or already planned: {A['waiting']}. Finished (replied, skipped or after touch 3): {A['finished']}.")
    if total and write:
        print("Open the Send Desk, send each message yourself, and tap Sent.")


def due_count(slug: str, upto: dt.date | None = None) -> int:
    """How many follow-ups are due by `upto` (default tomorrow), without writing anything."""
    upto = upto or dt.date.today() + dt.timedelta(days=1)
    return sum(1 for d in analyse(slug)["due"] if d["due"] <= upto)
