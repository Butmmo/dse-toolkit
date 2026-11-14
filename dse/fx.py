"""Exchange rates YOU enter, so money in different currencies can be added up honestly.

    python dse.py fx add <engine> --from GBP --to USD --rate 1.27 [--date 2026-11-14] [--note "my bank's rate that day"]
    python dse.py fx list <engine>

Nothing here is looked up or guessed. A rate is a line in engines/<engine>/data/fx-rates.csv (date, from, to, rate, note) that you put there: the rate your bank or
Grey or Payoneer gave you when the money landed, or the rate your accountant tells you to use. To value a payment, the most recent rate ON OR BEFORE the payment's
date is used (a rate given the other way round, USD to GBP, is turned over). A rate more than 45 days older than the payment is used but marked old.
A payment with no usable rate is never converted: it is listed, with the exact command that would fix it.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path

from .engines import engine_dir, load

COLS = ["date", "from", "to", "rate", "note"]
OLD_DAYS = 45
CUR = re.compile(r"^[A-Z]{3}$")


def path(slug: str) -> Path:
    return engine_dir(slug) / "data" / "fx-rates.csv"


def read_rates(slug: str) -> list[dict]:
    p = path(slug)
    if not p.exists():
        return []
    out = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                out.append({"date": r["date"], "from": r["from"].upper(), "to": r["to"].upper(), "rate": float(r["rate"]), "note": r.get("note", "")})
            except (KeyError, ValueError, AttributeError):
                continue
    return out


def add_rate(slug: str, from_cur: str, to_cur: str, rate: float, date: str = "", note: str = "", today: dt.date | None = None) -> str:
    load(slug)
    today = today or dt.date.today()
    f, t = (from_cur or "").upper(), (to_cur or "").upper()
    if not CUR.match(f) or not CUR.match(t) or f == t:
        raise ValueError("Give two different 3-letter currency codes, for example --from GBP --to USD.")
    if not 0.000001 <= rate <= 10_000_000:
        raise ValueError("The rate must be more than 0 (how many units of the TO currency one unit of the FROM currency buys).")
    day = date or today.isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("Date as YYYY-MM-DD.")
    d = dt.date.fromisoformat(day)
    if d > today + dt.timedelta(days=1):
        raise ValueError("A rate cannot be dated in the future.")
    note = re.sub(r"\s+", " ", re.sub(r"[\r\n,]+", " ", note or "")).strip()[:100]
    p = path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    fresh = not p.exists()
    with p.open("a", encoding="utf-8-sig" if fresh else "utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        if fresh:
            w.writeheader()
        w.writerow({"date": day, "from": f, "to": t, "rate": f"{rate:.6f}".rstrip("0").rstrip("."), "note": note})
    return f"Saved: 1 {f} = {rate:g} {t} on {day}.\n"


def rate_for(slug: str, day: dt.date, cur: str, base: str, rates: list[dict] | None = None) -> dict | None:
    """The rate to turn `cur` into `base` for a payment on `day`: {rate, date, inverse, old}, or None when you have not given one."""
    cur, base = cur.upper(), base.upper()
    if cur == base:
        return {"rate": 1.0, "date": day.isoformat(), "inverse": False, "old": False}
    best = None
    for r in rates if rates is not None else read_rates(slug):
        if r["date"] > day.isoformat():
            continue
        if r["from"] == cur and r["to"] == base:
            cand = {"rate": r["rate"], "date": r["date"], "inverse": False}
        elif r["from"] == base and r["to"] == cur and r["rate"] > 0:
            cand = {"rate": 1 / r["rate"], "date": r["date"], "inverse": True}
        else:
            continue
        if best is None or cand["date"] >= best["date"]:
            best = cand
    if best is None:
        return None
    best["old"] = (day - dt.date.fromisoformat(best["date"])).days > OLD_DAYS
    return best


def convert(slug: str, amount: float, day: dt.date, cur: str, base: str, rates: list[dict] | None = None) -> tuple[float, dict] | None:
    r = rate_for(slug, day, cur, base, rates)
    return None if r is None else (round(amount * r["rate"], 2), r)


def listing(slug: str) -> str:
    load(slug)
    rs = sorted(read_rates(slug), key=lambda r: (r["date"], r["from"]))
    if not rs:
        return f"No exchange rates yet. Add one when money in another currency lands: python dse.py fx add {slug} --from GBP --to USD --rate 1.27 --date 2026-11-14\n"
    return "\n".join([f"{r['date']}  1 {r['from']} = {r['rate']:g} {r['to']}   {r['note']}".rstrip() for r in rs] + [f"\n{len(rs)} rate(s). These are the rates YOU entered; nothing is looked up.\n"])


def fix_hint(slug: str, cur: str, base: str, day: dt.date) -> str:
    return f"python dse.py fx add {slug} --from {cur} --to {base} --rate <rate> --date {day.isoformat()}"
