"""Call scorecard for The Ascent: rate each sales call (real or mock) honestly, see what to practise, and watch the trend.

    python dse.py callscore <engine> --offer "Acme Coaching" --outcome sold --cash 3000 --commission 10 --talk 35 \\
        --scores 2,1,2,0,1,2,1,2
    python dse.py calls <engine>            your call history and numbers

Eight areas, each scored 0 (missed), 1 (partly) or 2 (done well). The order is the order of a good call:
  1 up-front contract    2 prepared (3 facts known)   3 problem questions (they talked most)   4 cost of the problem (in money or time)
  5 qualified (budget, decider, timing)               6 offer in their words                   7 objection handled (pause, ask, answer)
  8 asked for the decision and followed up within 10 minutes
Method: the Sandler up-front contract, SPIN-style questions (Rackham), and the pause-ask-answer objection routine; see the HQ recipe
'Prepare and run a high-ticket sales call'. Be harsh. A scorecard that flatters you teaches nothing.

It keeps engines/<engine>/data/calls.csv and reports: calls, show rate, close rate, cash per call, your average score, and the trend over
your last 5 calls against the 5 before. Commission is shown as an estimate of what YOU earned (cash x commission %).
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from .common import ROOT

ENGINES = ROOT / "engines"
AREAS = [
    ("upfront", "Up-front contract", "Open every call with time, agenda, permission to ask questions and what yes, no or a next step looks like.",
     "Write your 20-second up-front contract word for word, say it out loud 5 times, then record yourself saying it to a friend. Judge: does it sound like you?"),
    ("prepared", "Prepared (3 facts)", "Know three real facts about them before the call so the first questions are specific.",
     "Before your next call, write 3 facts about the person from their form answers and public pages. Open with a question built on one of them."),
    ("problem", "Problem questions (they talk most)", "Ask what is not working and what they have tried; let them talk about 60% of the time.",
     "Write 6 problem questions for your offer ('What is not working about that?'). In a mock call, count how long you talk: aim for under 40%."),
    ("cost", "Cost of the problem", "Get a number: what the problem costs them each month in money, time or lost deals.",
     "Practise asking 'What does that cost you each month?' and 'If nothing changes, where are you in a year?' until you can wait through the silence."),
    ("qualify", "Qualified (budget, decider, timing)", "Check budget, who else decides and when they want it fixed before you present.",
     "Write your three qualifying questions and say them naturally. Practise the budget question out loud until it stops feeling awkward."),
    ("offer", "Offer in their words", "Present in three parts using their own words: your problem, what it costs, the result you want.",
     "Take a past call and write the offer in three sentences using only phrases the prospect said. Present it aloud in under 60 seconds."),
    ("objection", "Objection handled", "Pause, ask a question, then answer. Never drop the price in panic.",
     "List your 4 most common objections. For each write the question you would ask first ('Help me understand...'). Role-play each twice."),
    ("close", "Asked for the decision, followed up", "Return to the agreed outcome and ask for yes or no; send a short follow-up within 10 minutes.",
     "Write the closing sentence ('We said we would decide today. Do you want to go ahead?') and the 3-line follow-up. Send the follow-up to yourself after every call this week."),
]
OUTCOMES = ("no_show", "no_sale", "follow_up", "sold")
COLS = ["date", "offer", "outcome", "cash", "commission_pct", "talk_pct", "score", "scores", "weakest"]


def path(slug: str) -> Path:
    return ENGINES / slug / "data" / "calls.csv"


def read_calls(slug: str) -> list[dict]:
    p = path(slug)
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def parse_scores(s: str | list[int]) -> list[int]:
    vals = [int(x) for x in (s.split(",") if isinstance(s, str) else s) if str(x).strip() != ""]
    if len(vals) != len(AREAS) or any(v not in (0, 1, 2) for v in vals):
        raise ValueError(f"Give {len(AREAS)} scores, each 0, 1 or 2, in the order of the areas.")
    return vals


def score_call(scores: list[int]) -> dict:
    total = sum(scores)
    weakest = sorted(range(len(AREAS)), key=lambda i: (scores[i], i))[:2]
    return {"total": total, "max": 2 * len(AREAS), "pct": int(100 * total / (2 * len(AREAS)) + 0.5), "weakest": [AREAS[i] for i in weakest if scores[i] < 2]}


def stats(calls: list[dict]) -> dict:
    booked = len(calls)
    shown = [c for c in calls if c["outcome"] != "no_show"]
    sold = [c for c in calls if c["outcome"] == "sold"]
    scored = [c for c in shown if c.get("score") not in ("", None)]
    cash = sum(float(c.get("cash") or 0) for c in sold)
    earned = sum(float(c.get("cash") or 0) * float(c.get("commission_pct") or 0) / 100 for c in sold)
    s = {"calls": booked, "shown": len(shown), "sold": len(sold), "cash": cash, "earned": round(earned, 2),
         "show_rate": round(100 * len(shown) / booked) if booked else None, "close_rate": round(100 * len(sold) / len(shown)) if shown else None,
         "avg_score": round(sum(float(c["score"]) for c in scored) / len(scored)) if scored else None,
         "cash_per_call": round(cash / len(shown)) if shown else None}
    last, before = scored[-5:], scored[-10:-5]
    if len(last) >= 3 and len(before) >= 3:
        s["trend"] = round(sum(float(c["score"]) for c in last) / len(last) - sum(float(c["score"]) for c in before) / len(before))
    return s


def log_call(slug: str, offer: str, outcome: str, cash: float, commission: float, talk: int, scores: list[int], today: dt.date | None = None) -> dict:
    if outcome not in OUTCOMES:
        raise ValueError("Outcome must be one of: " + ", ".join(OUTCOMES))
    today = today or dt.date.today()
    res = score_call(scores) if outcome != "no_show" else None
    p = path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    fresh = not p.exists()
    with p.open("a", encoding="utf-8-sig" if fresh else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if fresh:
            w.writeheader()
        w.writerow({"date": today.isoformat(), "offer": offer, "outcome": outcome, "cash": cash if outcome == "sold" else 0, "commission_pct": commission,
                    "talk_pct": talk, "score": res["pct"] if res else "", "scores": ",".join(map(str, scores)) if res else "",
                    "weakest": ";".join(w_[0] for w_ in res["weakest"]) if res else ""})
    return {"result": res, "stats": stats(read_calls(slug))}


def report(slug: str, offer: str, outcome: str, cash: float, commission: float, talk: int, scores: list[int]) -> str:
    out = log_call(slug, offer, outcome, cash, commission, talk, scores)
    res, st = out["result"], out["stats"]
    L = [f"Call logged: {offer}, {outcome.replace('_', ' ')}" + (f", ${cash:,.0f} cash" if outcome == "sold" else "")]
    if res:
        L.append(f"Your score: {res['total']}/{res['max']} ({res['pct']}%).")
        if talk and talk > 50:
            L.append(f"You talked {talk}% of the time. On a discovery call the prospect should talk most: aim for under 40%.")
        if res["weakest"]:
            L.append("\nWork on these first (one 10-minute drill each, before your next call):")
            for _k, name, why, drill in res["weakest"]:
                L.append(f"  - {name}: {why}\n      Drill: {drill}")
        else:
            L.append("A strong call. Write down what you did differently, and do it again.")
        if outcome == "sold" and res["pct"] < 50:
            L.append("\nYou closed, but the call scored low. Do not copy this one: the next prospect will not be as easy.")
    L += ["", f"Your numbers: {st['calls']} call(s), {st['shown']} showed" + (f" ({st['show_rate']}%)" if st["show_rate"] is not None else "")
          + f", {st['sold']} sold" + (f" ({st['close_rate']}% of shown calls)" if st["close_rate"] is not None else "")
          + f", ${st['cash']:,.0f} cash" + (f", about ${st['cash_per_call']:,} per call" if st["cash_per_call"] else "") + (f", about ${st['earned']:,.0f} to you in commission" if st["earned"] else "")
          + (f", average score {st['avg_score']}%" if st["avg_score"] is not None else "") + "."]
    if "trend" in st:
        L.append(f"Trend: your last 5 calls average {abs(st['trend'])} points {'higher' if st['trend'] >= 0 else 'lower'} than the 5 before.")
    if st["calls"] < 10:
        L.append("Fewer than 10 calls is too few to judge a close rate. Keep logging every call, including the ones that go badly.")
    return "\n".join(L)


def history(slug: str) -> str:
    calls = read_calls(slug)
    if not calls:
        return "No calls logged yet. After each call (a real one or a mock one you recorded), log it with: python dse.py callscore <engine> ..."
    st = stats(calls)
    lines = [f"{c['date']}  {c['offer'][:26]:<26} {c['outcome'].replace('_', ' '):<10} score {c['score'] or '-':>3}%  {('$' + c['cash']) if c['outcome'] == 'sold' else ''}" for c in calls[-15:]]
    return "\n".join(lines) + f"\n\n{st['calls']} calls, {st['sold']} sold, ${st['cash']:,.0f} cash" + (f", average score {st['avg_score']}%" if st["avg_score"] is not None else "")
