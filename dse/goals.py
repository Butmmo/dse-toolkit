"""Monthly goal setting, mostly automatic.

    python dse.py goal <engine> [--month 2026-12] [--stretch 20]            suggest the goal from your own history, with the working shown
    python dse.py goal <engine> --apply                                      save the suggestion as that month's goal
    python dse.py goal <engine> --set 4000 [--month 2026-12]                 set it yourself
    python bridge/goal_sync.py                                               (the runner does this in the background) writes engines/<slug>/next-goal.md

How the suggestion is made (nothing else goes into it):
  base       the average of the money you logged in your last 3 COMPLETE months (cash.csv); if your last month beat that average, the last month
  suggested  base plus your stretch (default 20%, change it with --stretch), rounded up to the next $50
  no history no suggestion: it keeps your standing target and says so
A month with no goal of its own simply uses your standing target, so there is always a goal, and nothing is ever changed without --apply or --set.
Then the same maths as the Cash Desk turns the goal into what each week would need (messages, calls, sales), using your own rates, or says there is too little data.
"""
from __future__ import annotations

import calendar
import datetime as dt
import math
import re
from pathlib import Path

from . import cashdesk as cd
from .engines import all_slugs, engine_dir, load

HIST_MONTHS = 3
STRETCH_DEFAULT = 20.0


def add_month(y: int, m: int, n: int) -> tuple[int, int]:
    i = y * 12 + (m - 1) + n
    return i // 12, i % 12 + 1


def key(y: int, m: int) -> str:
    return f"{y:04d}-{m:02d}"


def default_month(slug: str, today: dt.date) -> str:
    """This month while it is young and has no goal of its own; otherwise next month."""
    this = key(today.year, today.month)
    if today.day <= 10 and this not in (cd.read_settings(slug).get("months") or {}):
        return this
    return key(*add_month(today.year, today.month, 1))


def complete_months(slug: str, today: dt.date, n: int = HIST_MONTHS) -> list[tuple[str, float]]:
    """(YYYY-MM, money received) for up to the last n complete months, starting at the first month you logged anything."""
    rows = cd.read_cash(slug)
    if not rows:
        return []
    first = min(r["date"][:7] for r in rows)
    out = []
    y, m = add_month(today.year, today.month, -1)
    for _ in range(n):
        k = key(y, m)
        if k < first:
            break
        a, b = cd.month_bounds(k, today)
        out.append((k, round(sum(float(r["amount"]) for r in rows if cd.in_month(r["date"], a, b)), 2)))
        y, m = add_month(y, m, -1)
    return list(reversed(out))


def suggest(slug: str, today: dt.date, stretch: float = STRETCH_DEFAULT) -> dict:
    hist = complete_months(slug, today)
    standing = cd.get_target(slug)
    if not hist or sum(v for _k, v in hist) <= 0:
        return {"hist": hist, "base": None, "suggested": None, "standing": standing, "stretch": stretch,
                "why": "No complete month with money logged yet, so there is nothing real to base a suggestion on. Your standing target stays."}
    avg = sum(v for _k, v in hist) / len(hist)
    last = hist[-1][1]
    base = max(avg, last)
    raw = base * (1 + stretch / 100)
    sug = max(50, min(1_000_000, math.ceil(raw / 50) * 50))
    basis = (f"your last month, which beat the {len(hist)}-month average of {cd.money(avg)}" if last > avg else f"the average of your last {len(hist)} complete month(s)")
    return {"hist": hist, "base": round(base, 2), "suggested": float(sug), "standing": standing, "stretch": stretch,
            "why": f"Base {cd.money(base)} is {basis}; plus {stretch:g}% stretch is {cd.money(raw)}, rounded up to the next $50."}


def window_data(slug: str, hist: list[tuple[str, float]], today: dt.date) -> dict | None:
    if not hist:
        return None
    parts = []
    for k, _v in hist:
        a, b = cd.month_bounds(k, today)
        parts.append(cd.month_data(slug, a, b))
    d = cd.combine(parts)
    d["months"] = len(hist)
    return d


def needs(d: dict, goal: float) -> dict:
    """What the whole goal needs, from the rates in the window (a number, or None when the data is too thin to trust)."""
    f, c = d["funnel"], d["calls"]
    sold = c["sold"]
    per_sale, basis = None, ""
    if sold:
        per_sale, basis = c["earned"] / sold, f"your {sold} logged sale(s)"
    else:
        pos = [float(r["amount"]) for r in d["entries"] if float(r["amount"]) > 0]
        if pos:
            per_sale, basis = sum(pos) / len(pos), f"your {len(pos)} logged payment(s)"
    out = {"per_sale": per_sale, "basis": basis, "sales": None, "calls": None, "booked": None, "messages": None, "notes": []}
    if not per_sale:
        out["notes"].append("No sale or payment in the window, so there is no real value per sale to work from.")
        return out
    out["sales"] = goal / per_sale
    close = cd.rate(sold, c["shown"])
    if close and c["shown"] >= cd.MIN_CALLS:
        out["calls"] = out["sales"] / close
        show = cd.rate(c["shown"], c["calls"])
        if show:
            out["booked"] = out["calls"] / show
            br, rr = cd.rate(f["booked"], f["replied"]), cd.rate(f["replied"], f["sent"])
            if br and rr and f["replied"] >= cd.MIN_CALLS and f["sent"] >= cd.MIN_N:
                out["messages"] = out["booked"] / br / rr
            else:
                out["notes"].append(f"Not enough message data to turn calls into messages (needs {cd.MIN_N} sent and {cd.MIN_CALLS} replies in the window).")
    else:
        out["notes"].append(f"Only {c['shown']} shown call(s) in the window; with fewer than {cd.MIN_CALLS} the close rate is a guess, so no call numbers.")
    return out


def report(slug: str, month: str | None = None, stretch: float = STRETCH_DEFAULT, apply: bool = False, set_to: float | None = None,
           today: dt.date | None = None) -> str:
    load(slug)
    today = today or dt.date.today()
    if month and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise ValueError("Month as YYYY-MM, for example 2026-12.")
    if not 0 <= stretch <= 200:
        raise ValueError("Stretch is a percentage between 0 and 200.")
    month = month or default_month(slug, today)
    s = suggest(slug, today, stretch)
    own = month in (cd.read_settings(slug).get("months") or {})
    current = cd.get_target(slug, month)
    out = [f"# Monthly goal: {slug}, {month}", ""]
    saved = ""
    if set_to is not None:
        cd.set_target(slug, set_to, month)
        current, own, saved = set_to, True, f"Saved: your goal for {month} is now {cd.money(set_to)}."
    elif apply:
        if s["suggested"] is None:
            saved = "Nothing saved: there is no suggestion yet (see below)."
        else:
            cd.set_target(slug, s["suggested"], month)
            current, own, saved = s["suggested"], True, f"Saved: your goal for {month} is now {cd.money(s['suggested'])}."
    out.append(saved or (f"Goal for {month}: {cd.money(current)} ({'set for this month' if own else 'your standing target, carried forward'})."))
    out += ["", "## Suggestion from your history"]
    if s["hist"]:
        out.append("- Money logged: " + ", ".join(f"{k} {cd.money(v)}" for k, v in s["hist"]))
    out.append(f"- {s['why']}")
    if s["suggested"] is not None:
        out.append(f"- Suggested goal: {cd.money(s['suggested'])}")
    if s["suggested"] is not None and not apply and set_to is None:
        out.append(f"- To use it: python dse.py goal {slug} --month {month} --apply")
    goal = current
    out += ["", f"## What a {cd.money(goal)} month needs"]
    d = window_data(slug, s["hist"], today)
    if d is None:
        out.append("- Not enough history to work out the activity. Log what you receive with cashin and log your calls with callscore; this fills in by itself.")
    else:
        n = needs(d, goal)
        weeks = calendar.monthrange(int(month[:4]), int(month[5:]))[1] / 7
        if n["sales"] is None:
            out += [f"- {x}" for x in n["notes"]]
        else:
            out.append(f"- One sale is worth about {cd.money(n['per_sale'])} to you (from {n['basis']}), so about {n['sales']:.1f} sale(s) in the month, {n['sales'] / weeks:.1f} a week.")
            for k, label in (("calls", "calls to show up for"), ("booked", "calls to book"), ("messages", "messages to send")):
                if n[k] is not None:
                    out.append(f"- About {n[k]:.0f} {label} in the month, {n[k] / weeks:.0f} a week.")
            out += [f"- {x}" for x in n["notes"]]
        out.append(f"- Rates come from your last {d['months']} complete month(s) of your own logs.")
    out += ["", "Nothing here changes your goal unless you use --apply or --set."]
    return "\n".join(out) + "\n"


def write_note(slug: str, today: dt.date | None = None) -> Path | None:
    """Background helper: when the month to plan has no goal of its own and there is a suggestion, write engines/<slug>/next-goal.md. Changes no goal."""
    today = today or dt.date.today()
    month = default_month(slug, today)
    own = month in (cd.read_settings(slug).get("months") or {})
    s = suggest(slug, today)
    p = engine_dir(slug) / "next-goal.md"
    if own or s["suggested"] is None:
        if p.exists():
            p.unlink()
        return None
    p.write_text(report(slug, month, today=today), encoding="utf-8")
    return p


def write_all(today: dt.date | None = None) -> list[str]:
    done = []
    for slug in all_slugs():
        if write_note(slug, today):
            done.append(slug)
    return done
