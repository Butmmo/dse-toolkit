"""Weekly digest: your week in a few honest numbers, and what to do first this week.

    python dse.py digest [--week YYYY-MM-DD]     print the digest for the last full week (or the Mon-Sun week that contains that date); sends nothing
    python bridge/digest_sync.py [--now]         what the runner does once a week: build it, keep it on this PC, send it to your Dashboard and (once) to your phone

What it counts: the taps you logged in the Send Desk (sent, replied, call booked, won), the calls you scored, and the money you logged in the Cash Desk, for the Monday-to-Sunday
week that just ended, all engines together and one line per engine, next to the week before. Nothing is estimated: a message you sent but never tapped is not counted, and the digest
says so. Then the first things to do this week, from the Daily Brief. When it arrives: Monday at 07:00 on this PC by default (data/digest.json: {"enabled": true, "day": 0, "hour": 7}),
or when the PC is next on during that week; one push to your phone (not during quiet hours, not for a digest more than 3 days late, and never if you switched brief notifications off in your profile).
It never sends a message to anyone but you. Standard library only.
"""
from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

from .common import DATA

SETTINGS = DATA / "digest.json"
STATE = DATA / "digest-state.json"
FOLDER = DATA / "digests"
DEFAULTS = {"enabled": True, "day": 0, "hour": 7}
LATE_DAYS = 3
FIELDS = ("sent", "replied", "booked", "won")


def settings(path=None) -> dict:
    try:
        s = json.loads((path or SETTINGS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    out = {**DEFAULTS, **{k: s[k] for k in DEFAULTS if k in s}}
    for k, n in (("day", 7), ("hour", 24)):
        try:
            out[k] = int(out[k]) % n
        except (TypeError, ValueError):
            out[k] = DEFAULTS[k]
    out["enabled"] = bool(out["enabled"])
    return out


# ------------------------------------------------------------------ which week, and when

def due_moment(now: dt.datetime, cfg: dict) -> dt.datetime:
    """The most recent moment at or before now that is the configured weekday and hour (local time)."""
    day = now.date()
    for _ in range(8):
        m = dt.datetime.combine(day, dt.time(cfg["hour"]))
        if day.weekday() == cfg["day"] and m <= now:
            return m
        day -= dt.timedelta(days=1)
    raise ValueError("no due moment")


def week_for(due: dt.datetime) -> tuple[dt.date, dt.date]:
    """The Monday-to-Sunday week the digest due at that moment covers: the last full week that ended before that day."""
    d = due.date()
    end = d - dt.timedelta(days=d.weekday() + 1)          # the Sunday before (a Monday's due moment covers the week that just ended)
    return end - dt.timedelta(days=6), end


def week_containing(day: dt.date) -> tuple[dt.date, dt.date]:
    start = day - dt.timedelta(days=day.weekday())
    return start, start + dt.timedelta(days=6)


def decide(now: dt.datetime, cfg: dict, state: dict, quiet: bool = False) -> dict:
    """What to do this moment: {"week": (start, end) or None, "notify": bool, "why": words}. One digest per week, never twice, and a PC that was off catches up once."""
    if not cfg.get("enabled", True):
        return {"week": None, "notify": False, "why": "switched off"}
    due = due_moment(now, cfg)
    start, end = week_for(due)
    if state.get("last_week") == start.isoformat():
        return {"week": None, "notify": False, "why": "already made for this week"}
    late = now - due > dt.timedelta(days=LATE_DAYS)
    return {"week": (start, end), "notify": not quiet and not late, "why": "late: kept, not announced" if late else ("quiet hours: kept, not announced" if quiet else "due")}


# ------------------------------------------------------------------ the numbers

def _deps() -> SimpleNamespace:
    from . import brief, cashdesk
    from .engines import all_slugs, engine_dir

    def name_of(slug: str) -> str:
        try:
            return json.loads((engine_dir(slug) / "engine.json").read_text(encoding="utf-8")).get("name") or slug
        except (OSError, ValueError):
            return slug

    return SimpleNamespace(all_slugs=all_slugs, month_data=cashdesk.month_data, get_target=cashdesk.get_target, name_of=name_of, moves=lambda today: brief.build(today=today, top=3)["moves"])


def _row(d: dict) -> dict:
    f = d["funnel"]
    return {"sent": f["sent"], "replied": f["replied"], "booked": f["booked"], "won": f["won"], "calls": d["calls"]["calls"], "received": round(float(d["received"]), 2)}


def _sum(rows: list[dict]) -> dict:
    out = {k: 0 for k in (*FIELDS, "calls")}
    out["received"] = 0.0
    for r in rows:
        for k in out:
            out[k] = round(out[k] + r[k], 2) if k == "received" else out[k] + r[k]
    return out


def build(start: dt.date, end: dt.date, deps=None, now: dt.datetime | None = None) -> dict:
    """The digest for the Monday-to-Sunday week start..end. deps: the data sources (tests pass their own)."""
    deps = deps or _deps()
    now = now or dt.datetime.now()
    pstart, pend = start - dt.timedelta(days=7), end - dt.timedelta(days=7)
    mstart = end.replace(day=1)
    engines, prev_rows, notes = [], [], []
    month_received, month_target, unconverted = 0.0, 0.0, 0
    for slug in deps.all_slugs():
        w = deps.month_data(slug, start, end)
        p = deps.month_data(slug, pstart, pend)
        m = deps.month_data(slug, mstart, end)
        engines.append({"slug": slug, "name": deps.name_of(slug), **_row(w)})
        prev_rows.append(_row(p))
        month_received += float(m["received"])
        unconverted += len(w.get("unconverted", []))
        try:
            month_target += float(deps.get_target(slug, end.strftime("%Y-%m")) or 0)
        except Exception:
            pass
    totals, prev = _sum([{k: e[k] for k in (*FIELDS, "calls", "received")} for e in engines]), _sum(prev_rows)
    if unconverted:
        notes.append(f"{unconverted} payment(s) in another currency have no exchange rate logged, so they are not counted in the money.")
    if engines and not any(totals[k] for k in (*FIELDS, "calls")) and not totals["received"]:
        notes.append("Nothing was logged this week. Messages, replies and calls count only when you tap them in the Send Desk, so a message you sent but did not tap is not counted.")
    try:
        moves = [{"do": m["do"], "how": m["how"], "engine": m.get("engine_name", "")} for m in deps.moves(now.date())][:3]
    except Exception:
        moves = []
    d = {"week_start": start.isoformat(), "week_end": end.isoformat(), "made": now.isoformat(timespec="minutes"), "engines": engines[:8], "totals": totals, "prev": prev,
         "month": {"received": round(month_received, 2), "target": round(month_target, 2) or None, "label": end.strftime("%B %Y")}, "moves": moves, "notes": notes}
    d["headline"] = headline(d)
    return d


# ------------------------------------------------------------------ words

def money(x: float) -> str:
    return f"${x:,.0f}" if abs(x - round(x)) < 0.005 else f"${x:,.2f}"


def span(d: dict) -> str:
    a, b = dt.date.fromisoformat(d["week_start"]), dt.date.fromisoformat(d["week_end"])
    return f"{a.day} {a:%b}" + (f" {a.year}" if a.year != b.year else "") + f" to {b.day} {b:%b}"


def headline(d: dict) -> str:
    t = d["totals"]
    if not d["engines"]:
        return "You have no engines yet, so there is nothing to count. Create one in HQ Tools, My engines."
    bits = [f"{t['sent']} sent", f"{t['replied']} repl{'y' if t['replied'] == 1 else 'ies'}", f"{t['booked']} call{'' if t['booked'] == 1 else 's'} booked", f"{t['won']} won"]
    if t["received"]:
        bits.append(f"{money(t['received'])} received")
    return f"Your week ({span(d)}): " + ", ".join(bits) + "."


def body(d: dict) -> str:
    """The phone notification: the headline and the first thing to do."""
    first = d["moves"][0]["do"] if d["moves"] else ""
    return (d["headline"] + (f" First this week: {first}" if first else ""))[:300]


def render(d: dict) -> str:
    t, p = d["totals"], d["prev"]
    out = [f"# {d['headline']}", ""]
    if d["engines"]:
        out += ["| | This week | Week before |", "|---|---|---|"]
        for label, k in (("Sent", "sent"), ("Replies", "replied"), ("Calls booked", "booked"), ("Won", "won"), ("Calls scored", "calls")):
            out.append(f"| {label} | {t[k]} | {p[k]} |")
        out.append(f"| Money received | {money(t['received'])} | {money(p['received'])} |")
        if d["month"]["target"]:
            out += ["", f"{d['month']['label']} so far: {money(d['month']['received'])} of a {money(d['month']['target'])} target."]
        elif d["month"]["received"]:
            out += ["", f"{d['month']['label']} so far: {money(d['month']['received'])} received."]
        if len(d["engines"]) > 1:
            out += ["", "## By engine"] + [f"- {e['name']}: {e['sent']} sent, {e['replied']} replies, {e['booked']} booked, {e['won']} won, {money(e['received'])}" for e in d["engines"]]
    if d["moves"]:
        out += ["", "## First this week"] + [f"{i}. [{m['engine']}] {m['do']}: {m['how']}" for i, m in enumerate(d["moves"], 1)]
    if d["notes"]:
        out += [""] + [f"Note: {n}" for n in d["notes"]]
    out += ["", "Counts come only from the taps, calls and payments you logged. Nothing here is estimated and nothing was sent to anyone."]
    return "\n".join(out) + "\n"


def run_cli(args: list[str]) -> int:
    day = None
    if "--week" in args:
        i = args.index("--week")
        try:
            day = dt.date.fromisoformat(args[i + 1])
        except (IndexError, ValueError):
            print("Use --week YYYY-MM-DD (any day inside the week you want).")
            return 2
    if day:
        start, end = week_containing(day)
    else:
        start, end = week_for(due_moment(dt.datetime.now(), {"day": 0, "hour": 0}))
    print(render(build(start, end)))
    return 0
