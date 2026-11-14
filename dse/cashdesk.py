"""The Cash Desk: am I on track to this month's income target, and what would it take to get there?

    python dse.py cash <engine|all> [--month 2026-11] [--target 3000]      this month against the target
    python dse.py cashin <engine> --amount 450 --kind commission --note "Acme sale"      log money you actually RECEIVED
    python dse.py cashlog <engine>                                          the money you logged

Where every number comes from (nothing is guessed):
  money received    engines/<slug>/data/cash.csv       only what you logged with `cashin`; refunds are negative
  sales you logged  engines/<slug>/data/calls.csv      from `callscore` (sale value x your commission % = what you EARNED, an estimate until received)
  messages          engines/<slug>/data/log.csv        the Send Desk taps: sent, replied, booked, won (out-of-office replies do not count as replies)
  your target       engines/<slug>/data/cash.json      set with --target

The "what it would take" maths uses YOUR own rates from this month's data and says plainly when there is too little data to trust them.
"""
from __future__ import annotations

import calendar
import csv
import datetime as dt
import json
import re
from pathlib import Path

from . import callscore, desklog
from .engines import all_slugs, engine_dir, load

COLS = ["date", "amount", "kind", "note"]
KINDS = ("commission", "retainer", "project", "bonus", "other", "refund")
MIN_N = 30            # fewer sent messages than this: the rates are tentative
MIN_CALLS = 5
SENT = {"sent", "replied", "booked", "won", "lost"}
REPLIED = {"replied", "booked", "won"}
DEFAULT_TARGET = 3000.0


def cash_path(slug: str) -> Path:
    return engine_dir(slug) / "data" / "cash.csv"


def settings_path(slug: str) -> Path:
    return engine_dir(slug) / "data" / "cash.json"


def read_cash(slug: str) -> list[dict]:
    p = cash_path(slug)
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("date")]


def read_settings(slug: str) -> dict:
    try:
        d = json.loads(settings_path(slug).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def get_target(slug: str, month: str | None = None) -> float:
    """That month's own goal if you set one (YYYY-MM), else your standing target, else the default."""
    st = read_settings(slug)
    try:
        if month and month in (st.get("months") or {}):
            return float(st["months"][month])
        return float(st.get("target", DEFAULT_TARGET))
    except (ValueError, TypeError):
        return DEFAULT_TARGET


def set_target(slug: str, target: float, month: str | None = None) -> None:
    """Without a month: the standing target every month without its own goal uses. With one (YYYY-MM): that month only."""
    if not 50 <= target <= 1_000_000:
        raise ValueError("The target must be between 50 and 1,000,000 a month.")
    if month and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise ValueError("Month as YYYY-MM, for example 2026-11.")
    st = read_settings(slug)
    if month:
        st.setdefault("months", {})[month] = target
    else:
        st["target"] = target
    p = settings_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, indent=1) + "\n", encoding="utf-8")


def log_cash(slug: str, amount: float, kind: str, note: str = "", date: str = "") -> dict:
    load(slug)
    if kind not in KINDS:
        raise ValueError("Kind must be one of: " + ", ".join(KINDS))
    if not 0 < amount <= 10_000_000:
        raise ValueError("The amount must be more than 0 (a refund is logged with kind refund, not a minus sign).")
    day = date or dt.date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("Date as YYYY-MM-DD.")
    dt.date.fromisoformat(day)
    note = re.sub(r"\s+", " ", re.sub(r"[\r\n,]+", " ", note or "")).strip()[:120]
    row = {"date": day, "amount": f"{-amount if kind == 'refund' else amount:.2f}", "kind": kind, "note": note}
    p = cash_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    fresh = not p.exists()
    with p.open("a", encoding="utf-8-sig" if fresh else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if fresh:
            w.writeheader()
        w.writerow(row)
    return row


def month_bounds(month: str | None, today: dt.date) -> tuple[dt.date, dt.date]:
    if month:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            raise ValueError("Month as YYYY-MM, for example 2026-11.")
        y, m = int(month[:4]), int(month[5:])
    else:
        y, m = today.year, today.month
    return dt.date(y, m, 1), dt.date(y, m, calendar.monthrange(y, m)[1])


def in_month(day: str, a: dt.date, b: dt.date) -> bool:
    try:
        d = dt.date.fromisoformat(str(day)[:10])
    except ValueError:
        return False
    return a <= d <= b


def funnel(slug: str, a: dt.date, b: dt.date) -> dict:
    """Unique messages (list row) with a tap of each kind logged inside the month."""
    sent, replied, booked, won = set(), set(), set(), set()
    for e in desklog.read_log(slug):
        if not in_month(e.get("logged_at", ""), a, b):
            continue
        key = (e.get("source", ""), str(e.get("row_id", "")))
        st = e.get("status", "")
        ooo = desklog.is_out_of_office(e)
        if st in SENT or ooo:
            sent.add(key)
        if st in REPLIED and not ooo:
            replied.add(key)
        if st in ("booked", "won"):
            booked.add(key)
        if st == "won":
            won.add(key)
    return {"sent": len(sent), "replied": len(replied), "booked": len(booked), "won": len(won)}


def calls_in(slug: str, a: dt.date, b: dt.date) -> dict:
    cs = [c for c in callscore.read_calls(slug) if in_month(c.get("date", ""), a, b)]
    return {"calls": len(cs), **{k: v for k, v in callscore.stats(cs).items() if k in ("shown", "sold", "cash", "earned")}} if cs else {"calls": 0, "shown": 0, "sold": 0, "cash": 0.0, "earned": 0.0}


def month_data(slug: str, a: dt.date, b: dt.date) -> dict:
    entries = [r for r in read_cash(slug) if in_month(r["date"], a, b)]
    received = round(sum(float(r["amount"]) for r in entries), 2)
    return {"slug": slug, "entries": entries, "received": received, "funnel": funnel(slug, a, b), "calls": calls_in(slug, a, b)}


def combine(parts: list[dict]) -> dict:
    out = {"slug": "all engines", "entries": [], "received": 0.0, "funnel": {"sent": 0, "replied": 0, "booked": 0, "won": 0}, "calls": {"calls": 0, "shown": 0, "sold": 0, "cash": 0.0, "earned": 0.0}}
    for p in parts:
        out["entries"] += p["entries"]
        out["received"] = round(out["received"] + p["received"], 2)
        for k in out["funnel"]:
            out["funnel"][k] += p["funnel"][k]
        for k in out["calls"]:
            out["calls"][k] += p["calls"][k]
    out["calls"]["earned"] = round(out["calls"]["earned"], 2)
    return out


def rate(a: float, b: float) -> float | None:
    return a / b if b else None


def money(x: float) -> str:
    return f"${x:,.0f}" if abs(x - round(x)) < 0.005 else f"${x:,.2f}"


def pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.0f}%"


def of(x: float | None, what: str) -> str:
    """' (20% of sent)' or nothing at all when there is no denominator yet."""
    return "" if x is None else f" ({pct(x)} {what})"


def pace(received: float, today: dt.date, a: dt.date, b: dt.date) -> dict:
    total_days = (b - a).days + 1
    if today < a:
        return {"state": "future", "total_days": total_days}
    if today > b:
        return {"state": "past", "total_days": total_days, "elapsed": total_days}
    elapsed = (today - a).days + 1
    return {"state": "now", "total_days": total_days, "elapsed": elapsed, "left": total_days - elapsed, "projected": received / elapsed * total_days}


def what_it_takes(d: dict, gap: float) -> list[str]:
    """How many more of each step the remaining gap needs, using this month's own rates. Says so when there is too little data."""
    f, c = d["funnel"], d["calls"]
    lines: list[str] = []
    if gap <= 0:
        return ["You have reached the target. Anything more is extra."]
    sold = c["sold"]
    earned_per_sale = (c["earned"] / sold) if sold else None
    if earned_per_sale is None and d["entries"]:
        pos = [float(r["amount"]) for r in d["entries"] if float(r["amount"]) > 0]
        earned_per_sale = sum(pos) / len(pos) if pos else None
        basis = f"the average of the {len(pos)} payment(s) you logged"
    else:
        basis = f"what you earned on each of your {sold} logged sale(s)"
    if not earned_per_sale:
        return ["No sale or payment is logged yet this month, so there is nothing real to work the maths from. Log your first with `cashin`, or log a sold call with `callscore`."]
    sales_needed = gap / earned_per_sale
    lines.append(f"The gap is {money(gap)}. One sale is worth about {money(earned_per_sale)} to you ({basis}), so you need about {sales_needed:.1f} more sale(s).")
    close = rate(sold, c["shown"])
    if close and c["shown"] >= MIN_CALLS:
        calls_needed = sales_needed / close
        lines.append(f"You close {pct(close)} of the calls you show up for ({sold} of {c['shown']}), so that is about {calls_needed:.0f} more call(s).")
        show = rate(c["shown"], c["calls"])
        book_rate = rate(f["booked"], f["replied"])
        reply_rate = rate(f["replied"], f["sent"])
        if show:
            lines.append(f"{pct(show)} of your booked calls happen, so book about {calls_needed / show:.0f}.")
            booked_needed = calls_needed / show
            if book_rate and f["replied"] >= MIN_CALLS and reply_rate and f["sent"] >= MIN_N:
                lines.append(f"Replies turn into booked calls {pct(book_rate)} of the time and messages into replies {pct(reply_rate)}, so about {booked_needed / book_rate / reply_rate:.0f} more messages sent.")
            else:
                lines.append(f"Not enough message data yet (you need {MIN_N} sent and {MIN_CALLS} replies this month) to turn calls into a number of messages.")
    else:
        lines.append(f"You have only {c['shown']} shown call(s) this month; with fewer than {MIN_CALLS} your close rate is a guess, so I will not turn it into a number of calls.")
    return lines


def verdict(d: dict, target: float, p: dict) -> str:
    r = d["received"]
    if p["state"] == "now":
        if r >= target:
            return f"On target: you have already received {money(r)} of {money(target)}."
        proj = p["projected"]
        if r == 0 and not d["calls"]["earned"]:
            return "Nothing received or logged this month yet. The first logged payment starts the pace line."
        if proj >= target:
            return f"On pace: {money(r)} received in {p['elapsed']} of {p['total_days']} days projects to {money(round(proj))}, above the {money(target)} target."
        return f"Behind: {money(r)} received in {p['elapsed']} of {p['total_days']} days projects to {money(round(proj))}, short of {money(target)} by {money(round(target - proj))}."
    if p["state"] == "past":
        return (f"Hit: {money(r)} received against a {money(target)} target." if r >= target else f"Missed: {money(r)} received against a {money(target)} target ({money(target - r)} short).")
    return "That month has not started."


def build(slug: str, month: str | None = None, today: dt.date | None = None, target: float | None = None) -> str:
    today = today or dt.date.today()
    a, b = month_bounds(month, today)
    if slug == "all":
        slugs = all_slugs()
        if not slugs:
            return "You have no engines yet. Create one in HQ Tools, then come back."
        d = combine([month_data(s, a, b) for s in slugs])
        tgt = sum(get_target(s, a.strftime("%Y-%m")) for s in slugs)
        label = "all engines" if len(slugs) != 1 else "your one engine"
    else:
        load(slug)
        if target:
            set_target(slug, target, a.strftime("%Y-%m"))
        d = month_data(slug, a, b)
        tgt = get_target(slug, a.strftime("%Y-%m"))
        label = slug
    f, c = d["funnel"], d["calls"]
    p = pace(d["received"], today, a, b)
    out = [f"# Cash Desk: {label}, {a.strftime('%B %Y')}", "", verdict(d, tgt, p), ""]
    out += ["## Money", f"- Received (logged with cashin): {money(d['received'])} of {money(tgt)} ({pct(d['received'] / tgt)})"]
    if c["sold"]:
        out.append(f"- Earned on sales you logged with callscore: {money(c['earned'])} from {c['sold']} sale(s) worth {money(c['cash'])}. This is an estimate until the money arrives and you log it.")
    if p["state"] == "now":
        out.append(f"- Day {p['elapsed']} of {p['total_days']}; at this pace the month ends at {money(round(p['projected']))}.")
    out += ["", "## Steps this month (from your own logs)",
            f"- Messages sent: {f['sent']}", f"- Replies: {f['replied']}{of(rate(f['replied'], f['sent']), 'of sent')}",
            f"- Calls booked from a message: {f['booked']}{of(rate(f['booked'], f['replied']), 'of replies')}",
            f"- Calls on your scorecard: {c['calls']}, shown up: {c['shown']}{of(rate(c['shown'], c['calls']), 'of booked')}, sold: {c['sold']}{of(rate(c['sold'], c['shown']), 'of shown')}"]
    if f["sent"] < MIN_N:
        out.append(f"- Only {f['sent']} sent this month: below {MIN_N}, so the rates are tentative.")
    out += ["", "## What it would take to reach the target"] + [f"- {x}" for x in what_it_takes(d, tgt - d["received"])]
    if d["entries"]:
        out += ["", "## Money logged this month"] + [f"- {r['date']}  {money(float(r['amount']))}  {r['kind']}  {r['note']}".rstrip() for r in sorted(d["entries"], key=lambda r: r["date"])]
    out += ["", "Every figure above comes from files in engines/<engine>/data/ (cash.csv, calls.csv, log.csv). Log what you receive with: python dse.py cashin <engine> --amount N --kind commission"]
    text = "\n".join(out) + "\n"
    if slug != "all":
        (engine_dir(slug) / "cash-desk.md").write_text(text, encoding="utf-8")
    return text


def history(slug: str) -> str:
    load(slug)
    rows = read_cash(slug)
    if not rows:
        return "No money logged yet. Log what you receive: python dse.py cashin <engine> --amount N --kind commission --note \"who paid\""
    total = sum(float(r["amount"]) for r in rows)
    return "\n".join([f"{r['date']}  {money(float(r['amount'])):>10}  {r['kind']:<10} {r['note']}" for r in sorted(rows, key=lambda r: r["date"])] + [f"\nTotal logged: {money(total)} in {len(rows)} entr{'y' if len(rows) == 1 else 'ies'}."])
