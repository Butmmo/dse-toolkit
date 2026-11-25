"""Self-review a sales conversation and see what to practise.

Scores are a self-review, not a standardized assessment or proof of skill. Historical outcome rates
describe only the calls logged; they do not predict future sales or income. Commission arithmetic
is only an estimate from the written terms and customer payment entered; cleared income belongs in
the Cash Desk.
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from .common import ROOT

ENGINES = ROOT / "engines"
RUBRIC_VERSION = "2"
AREAS = [
    ("agenda", "Agreed agenda and permission", "Agree the purpose and time, ask permission before sensitive questions, and make clear the other person can pause or decline.",
     "Role-play an opening. Ask what they would like to cover and confirm they are comfortable continuing."),
    ("prepared", "Relevant preparation", "Use relevant information shared for this conversation or appropriate public business information. Avoid unnecessary personal or sensitive details.",
     "Practise summarizing one relevant, non-sensitive detail and invite the person to correct you."),
    ("discovery", "Open questions and listening", "Ask open questions and listen without imposing a talk-time ratio or steering the person to a predetermined answer.",
     "Role-play asking one open question, reflecting the answer accurately, and checking that you understood."),
    ("impact", "Impact without pressure", "Explore impact only when useful and welcome. Do not force financial disclosure, amplify fear, or invent a cost of inaction.",
     "Practise asking whether the person wants to explore impact. Accept 'no' and move on."),
    ("fit", "Fit and constraints", "Explain relevant requirements and constraints honestly. Ask about decision roles or budget only when appropriate and with permission.",
     "Practise explaining one real requirement and asking whether it fits the person's situation."),
    ("offer", "Clear, evidence-based explanation", "Describe what is offered, what is not included, and what evidence supports any claim. Do not promise outcomes you cannot verify.",
     "Explain the offer in plain language, separate known facts from unknowns, and invite questions."),
    ("objection", "Questions and concerns respected", "Answer questions directly. Respect uncertainty, a request for time, and a decision not to proceed; do not treat them as objections to overcome.",
     "Role-play hearing 'I need time'. Acknowledge it, offer requested information, and leave the decision with them."),
    ("nextstep", "Participant-led ending", "Summarize accurately and agree a next step only if the other person wants one. Follow up only as agreed and honor requests to stop.",
     "Practise closing with a summary and ask whether they want any next step, including none."),
]
OUTCOMES = ("no_show", "no_sale", "follow_up", "sold")
COLS = ["date", "offer", "outcome", "cash", "commission_pct", "score", "scores", "weakest", "rubric_version"]


def path(slug: str) -> Path:
    return ENGINES / slug / "data" / "calls.csv"


def read_calls(slug: str) -> list[dict]:
    p = path(slug)
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row.setdefault("rubric_version", "1")
    return rows


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
    shown = [c for c in calls if c["outcome"] != "no_show"]
    sold = [c for c in calls if c["outcome"] == "sold"]
    scored = [c for c in shown if c.get("score") not in ("", None) and c.get("rubric_version") == RUBRIC_VERSION]
    cash = sum(float(c.get("cash") or 0) for c in sold)
    earned = sum(float(c.get("cash") or 0) * float(c.get("commission_pct") or 0) / 100 for c in sold)
    s = {"calls": len(calls), "shown": len(shown), "sold": len(sold), "cash": cash, "earned": round(earned, 2),
         "show_rate": round(100 * len(shown) / len(calls)) if calls else None, "close_rate": round(100 * len(sold) / len(shown)) if shown else None,
         "avg_score": round(sum(float(c["score"]) for c in scored) / len(scored)) if scored else None,
         "cash_per_call": round(cash / len(shown)) if shown else None}
    last, before = scored[-5:], scored[-10:-5]
    if len(last) >= 3 and len(before) >= 3:
        s["trend"] = round(sum(float(c["score"]) for c in last) / len(last) - sum(float(c["score"]) for c in before) / len(before))
    return s


def log_call(slug: str, offer: str, outcome: str, cash: float, commission: float, talk: int, scores: list[int], today: dt.date | None = None) -> dict:
    if outcome not in OUTCOMES:
        raise ValueError("Outcome must be one of: " + ", ".join(OUTCOMES))
    if cash < 0 or commission < 0:
        raise ValueError("Amounts and commission must be zero or greater.")
    today = today or dt.date.today()
    res = score_call(scores) if outcome != "no_show" else None
    p = path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    fresh = not p.exists()
    if not fresh:
        with p.open(encoding="utf-8-sig", newline="") as existing:
            needs_version = "rubric_version" not in (csv.DictReader(existing).fieldnames or [])
        if needs_version:
            legacy_rows = read_calls(slug)
            with p.open("w", encoding="utf-8-sig", newline="") as migrated:
                writer = csv.DictWriter(migrated, fieldnames=COLS)
                writer.writeheader()
                for row in legacy_rows:
                    row["rubric_version"] = "1"
                    writer.writerow({key: row.get(key, "") for key in COLS})
    with p.open("a", encoding="utf-8-sig" if fresh else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if fresh:
            w.writeheader()
        w.writerow({"date": today.isoformat(), "offer": offer, "outcome": outcome, "cash": cash if outcome == "sold" else 0, "commission_pct": commission,
                    "score": res["pct"] if res else "", "scores": ",".join(map(str, scores)) if res else "",
                    "weakest": ";".join(w_[0] for w_ in res["weakest"]) if res else "", "rubric_version": RUBRIC_VERSION})
    return {"result": res, "stats": stats(read_calls(slug))}


def report(slug: str, offer: str, outcome: str, cash: float, commission: float, talk: int, scores: list[int]) -> str:
    out = log_call(slug, offer, outcome, cash, commission, talk, scores)
    res, st = out["result"], out["stats"]
    L = [f"Call logged: {offer}, {outcome.replace('_', ' ')}"]
    if res:
        L.append(f"Your self-review: {res['total']}/{res['max']} ({res['pct']}%). This score reflects your assessment of this call only; it is not a standardized skill assessment or a predictor of future results.")
        if res["weakest"]:
            L.append("\nChoose one area to practise next:")
            for _k, name, why, drill in res["weakest"]:
                L.append(f"  - {name}: {why}\n      Practice: {drill}")
        else:
            L.append("All areas were self-rated as done well. Consider asking a trusted practice partner for feedback; this remains self-review, not certification.")
    L += ["", f"History for calls you logged: {st['calls']} total, {st['shown']} attended, {st['sold']} marked sold" + (f" ({st['close_rate']}% of attended)" if st["close_rate"] is not None else "") + ". These are descriptive counts from your records, not a forecast."]
    if cash and commission > 0:
        L.append(f"Customer payment entered: ${cash:,.2f}. If the written agreement applies {commission:g}% to this amount, the arithmetic is about ${cash * commission / 100:,.2f} gross commission before reversals, taxes, fees, and expenses. This is not money received; log cleared commission separately in the Cash Desk.")
    elif cash:
        L.append("A customer payment was entered, but no commission arithmetic is shown because no positive written rate was entered. Log cleared commission separately in the Cash Desk.")
    if "trend" in st:
        L.append(f"Your recorded self-review average is {abs(st['trend'])} points {'higher' if st['trend'] >= 0 else 'lower'} across the latest and preceding groups. This is not a standardized performance trend.")
    legacy = sum(1 for c in read_calls(slug) if c.get("rubric_version") != RUBRIC_VERSION and c.get("score") not in ("", None))
    if legacy:
        L.append(f"{legacy} earlier score(s) use a previous rubric and are excluded from the current self-review average and trend.")
    if st["calls"] < 10:
        L.append("Fewer than 10 logged calls is too little history to interpret a close rate; even larger samples describe only the calls you recorded and are not a prediction.")
    L.append("Use fictional scenarios for practice. Do not enter prospect names, contact details, recordings, or confidential information.")
    return "\n".join(L)


def history(slug: str) -> str:
    calls = read_calls(slug)
    if not calls:
        return "No calls logged yet. After a call, record only necessary, non-sensitive facts and the agreed outcome."
    st = stats(calls)
    lines = [f"{c['date']}  {c['offer'][:26]:<26} {c['outcome'].replace('_', ' '):<10} self-review {c['score'] or '-':>3}%" + (" [previous rubric]" if c.get("rubric_version") != RUBRIC_VERSION and c.get("score") else "") for c in calls[-15:]]
    return "\n".join(lines) + f"\n\n{st['calls']} calls, {st['sold']} marked sold" + (f", average self-review {st['avg_score']}%" if st["avg_score"] is not None else "") + ". Historical counts are not a forecast."
