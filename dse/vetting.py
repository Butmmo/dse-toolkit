"""Offer vetting for The Ascent: decide whether a commission-only high-ticket offer deserves your time, BEFORE you take calls for it.

    python dse.py vet <engine> --offer "Acme Coaching" --url https://acme.example --commission 10 --ticket 5000 --d_pay no --d_contract no ...
    python dse.py offers <engine>          your offer tracker, best first

Each question is answered yes, no or unknown (unknown = you have not asked yet; it counts against the offer until you do).
Verdicts:
  WALK AWAY   any dealbreaker answered the risky way (a fee to start, no written terms, earnings promises, money handling, an offer you cannot verify)
  RED         two or more serious flags: do not start; put the questions to them in writing and see whether they fix it
  AMBER       one serious flag
  UNCHECKED   three or more dealbreaker or serious questions still unknown: ask before you give more time
  OK          nothing risky, but fewer than three good signs so far
  PROMISING   nothing risky, a written agreement in hand and at least three good signs
It also says what one sale pays you and how many calls you would need for a target month, using YOUR close rate once you have 10 calls
logged (otherwise a clearly labelled 20% assumption). Based on the FTC's consumer advice on job scams and practitioner guidance
for commission contracts (see dse/vetting.json). It informs your decision; it is not legal advice and it cannot see the company's records.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from . import callscore
from .common import ROOT

HERE = Path(__file__).resolve().parent
ENGINES = ROOT / "engines"
STATUSES = ("researching", "applied", "interview", "active", "rejected", "walked")
COLS = ["date", "offer", "url", "status", "verdict", "score", "commission_pct", "ticket", "flags", "unknown", "notes"]
ASSUMED_CLOSE = 0.20


def data() -> dict:
    return json.loads((HERE / "vetting.json").read_text(encoding="utf-8"))


def questions() -> list[dict]:
    return data()["questions"]


def evaluate(answers: dict[str, str]) -> dict:
    """answers: question id -> 'yes' | 'no' | 'unknown' (missing = unknown)."""
    qs = questions()
    risky, unknown, good = [], [], []
    for q in qs:
        a = (answers.get(q["id"]) or "unknown").lower()
        if a not in ("yes", "no", "unknown"):
            a = "unknown"
        if q["group"] == "positive":
            if a == "yes":
                good.append(q)
            continue
        if a == q["risky"]:
            risky.append(q)
        elif a == "unknown":
            unknown.append(q)
    dead = [q for q in risky if q["group"] == "dealbreaker"]
    serious = [q for q in risky if q["group"] == "serious"]
    caution = [q for q in risky if q["group"] == "caution"]
    key_unknown = [q for q in unknown if q["group"] in ("dealbreaker", "serious")]
    have_contract = any(q["id"] == "p_contract" for q in good)
    if dead:
        verdict = "WALK AWAY"
    elif len(serious) >= 2:
        verdict = "RED"
    elif len(serious) == 1:
        verdict = "AMBER"
    elif len(key_unknown) >= 3:
        verdict = "UNCHECKED"
    elif have_contract and len(good) >= 3 and not key_unknown:
        verdict = "PROMISING"
    else:
        verdict = "OK"
    score = 100 - 40 * len(dead) - 15 * len(serious) - 5 * len(caution) - 3 * len(key_unknown) + 4 * len(good)
    score = max(0, min(100, score))
    if dead:
        score = min(score, 10)              # good signs never rescue an offer with a dealbreaker
    return {"verdict": verdict, "score": score, "dealbreakers": dead, "serious": serious, "cautions": caution, "unknown": unknown, "key_unknown": key_unknown, "good": good}


def sale_math(commission_pct: float, ticket: float, target_month: float, calls: list[dict]) -> str | None:
    if not commission_pct or not ticket:
        return None
    per_sale = ticket * commission_pct / 100
    st = callscore.stats(calls) if calls else {}
    shown = st.get("shown", 0)
    if shown >= 10 and st.get("close_rate") is not None and st["close_rate"] > 0:
        rate, basis = st["close_rate"] / 100, f"your own close rate of {st['close_rate']}% over {shown} calls"
    else:
        rate, basis = ASSUMED_CLOSE, "an ASSUMED close rate of 20% (log 10 calls to replace this with your own)"
    sales = -(-target_month // per_sale)
    return (f"One sale pays you about ${per_sale:,.0f} (${ticket:,.0f} at {commission_pct:g}%). To earn ${target_month:,.0f} a month you need about {sales:.0f} sale(s), "
            f"which is roughly {sales / rate:.0f} calls that show up, using {basis}. Check that the company really supplies that many booked calls.")


def written_questions(res: dict, offer: str) -> str:
    items = [q for q in (res["dealbreakers"] + res["serious"] + res["key_unknown"] + res["cautions"]) if q.get("ask")]
    if not items:
        return ""
    lines = [f"{i}. {q['ask']}" for i, q in enumerate(items, 1)]
    return (f"Hi, thanks for the time on {offer}. Before I go further, could you please confirm the following in writing?\n\n" + "\n".join(lines)
            + "\n\nI take every offer through the same checks, so please do not read anything into the list. Thank you.")


def tracker_path(slug: str) -> Path:
    return ENGINES / slug / "offers.csv"


def read_offers(slug: str) -> list[dict]:
    p = tracker_path(slug)
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def save_offer(slug: str, row: dict) -> None:
    rows = [r for r in read_offers(slug) if r["offer"].lower() != row["offer"].lower()] + [row]
    p = tracker_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def report(slug: str, offer: str, url: str, commission: float, ticket: float, status: str, notes: str, answers: dict[str, str], target_month: float = 3000,
           today: dt.date | None = None) -> str:
    res = evaluate(answers)
    today = today or dt.date.today()
    if res["verdict"] == "WALK AWAY" and status not in ("walked", "rejected"):
        status = "walked"
    save_offer(slug, {"date": today.isoformat(), "offer": offer, "url": url, "status": status or "researching", "verdict": res["verdict"], "score": res["score"],
                      "commission_pct": commission, "ticket": ticket, "flags": "; ".join(q["id"] for q in res["dealbreakers"] + res["serious"] + res["cautions"]),
                      "unknown": ";".join(q["id"] for q in res["unknown"]), "notes": notes})
    heads = {
        "WALK AWAY": "WALK AWAY. Do not give this offer more time.",
        "RED": "RED. Two or more serious problems. Do not start. Put the questions below to them in writing; start only if the answers fix them.",
        "AMBER": "AMBER. One serious problem. Get it fixed in writing before you start.",
        "UNCHECKED": "UNCHECKED. Too much is unknown. Ask the questions below before you spend more time.",
        "OK": "OK so far. Nothing risky found, but you have fewer than three good signs and may still be missing a written agreement. Keep checking.",
        "PROMISING": "PROMISING. Nothing risky, a written agreement in hand and several good signs. Still talk to a current closer before you commit.",
    }
    L = [f"{offer}: {heads[res['verdict']]}", f"Score {res['score']}/100 ({len(res['dealbreakers'])} dealbreaker, {len(res['serious'])} serious, {len(res['cautions'])} caution, "
         f"{len(res['good'])} good sign(s), {len(res['key_unknown'])} important question(s) unanswered).", ""]
    for title, items in (("Dealbreakers found", res["dealbreakers"]), ("Serious problems", res["serious"]), ("Cautions", res["cautions"])):
        if items:
            L.append(title + ":")
            for q in items:
                L.append(f"  - {q['q']}\n      Why it matters: {q['why']}")
            L.append("")
    if res["key_unknown"]:
        L.append("Not yet answered (ask these first):")
        L += [f"  - {q['q']}" for q in res["key_unknown"]] + [""]
    if res["good"]:
        L.append("Good signs: " + "; ".join(q["q"].rstrip("?") for q in res["good"]) + "\n")
    wq = written_questions(res, offer) if res["verdict"] != "WALK AWAY" else ""
    if wq:
        L += ["Copy this message and send it to them (their written answers are your record):", "", wq, ""]
    if res["verdict"] == "WALK AWAY":
        L += ["If you already paid or sent money, contact the company or app you used to send it right away and report it at ReportFraud.ftc.gov (US) or to your local fraud agency. Do not send more.", ""]
    sm = sale_math(commission, ticket, target_month, callscore.read_calls(slug))
    if sm and res["verdict"] != "WALK AWAY":
        L += ["What the money could look like:", "  " + sm, ""]
    L += ["Before you start, get in writing: the commission rate and what it is calculated on, the payout date, the clawback window and cap, who owns recordings, "
          "whether you are a contractor, the company's legal name, and that you pay nothing.",
          "", f"Saved to your offer tracker (python dse.py offers {slug}). Sources: FTC job-scams advice (consumer.ftc.gov/articles/job-scams) and practitioner guidance for commission contracts. "
          "This informs your decision; it is not legal advice and it cannot see the company's records."]
    return "\n".join(L)


def listing(slug: str) -> str:
    rows = read_offers(slug)
    if not rows:
        return "No offers vetted yet. Vet one with: python dse.py vet <engine> --offer \"Name\" ... (or HQ Tools: The Ascent, vet an offer)."
    order = {"PROMISING": 0, "OK": 1, "UNCHECKED": 2, "AMBER": 3, "RED": 4, "WALK AWAY": 5}
    rows.sort(key=lambda r: (order.get(r["verdict"], 9), -int(r["score"] or 0)))
    out = [f"{r['verdict']:<10} {r['score']:>3}  {r['offer'][:30]:<30} {r['status']:<11} {('$' + r['ticket'] + ' @ ' + r['commission_pct'] + '%') if r['ticket'] else '':<16} {r['date']}" for r in rows]
    return "\n".join(out)
