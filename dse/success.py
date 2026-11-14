"""The Student Success Desk: who needs a check-in, and what your DFY income is likely to be.

    python dse.py success <engine> [--view overview|flags|drafts|forecast] [--months 6]

It reads only what the Cut Desk already holds (the filings `cut sync` brought from Citadel, or the ones you entered). Nothing is guessed and nothing is sent.

Per student, with the facts behind every flag:
  progress   qualified months out of 12 and the amount remitted out of the 18,000 cap (the two ways a DFY ends)
  flags      quiet (has not filed when they should have), under the line (filed under 2,000 for months in a row: shown as an opportunity when close), zero months,
             a sharp drop against their own recent average, behind pace (few qualified months for the time that has passed), a remittance overdue,
             nearly complete, and "no filings yet"
  drafts     a short, kind message for each flag, in your name, for you to send yourself. They are questions and offers of help, never accusations

Forecast: your expected DFY income for the next months, from each student's own last three filed months. LIKELY uses their average, LOW their weakest month; both
stop at the cap or at 12 qualified months. A student with fewer than two filed months is left out and counted, because a guess from one month is not a forecast.
Money for a month arrives about the month after it is earned. It is a projection from past months, not a promise.
"""
from __future__ import annotations

import datetime as dt
import statistics
from pathlib import Path

from . import cuts
from .engines import engine_dir, load

LINE_NEAR = 0.25            # within 25% under the qualifying line counts as "close"
DROP_RATIO = cuts.DROP_RATIO
SEV = {"red": 0, "amber": 1, "info": 2}
OVERDUE_RED_DAYS = 14


def money(x: float, sym: str = "$") -> str:
    return cuts.money(x, sym)


def month_add(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    i = y * 12 + (m - 1) + n
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def month_name(ym: str) -> str:
    return dt.date(int(ym[:4]), int(ym[5:7]), 1).strftime("%b %Y")


def last_complete(today: dt.date) -> str:
    return month_add(today.strftime("%Y-%m"), -1)


def elapsed_months(start: str, today: dt.date) -> int:
    """Complete months from the agreement start through last month."""
    a = int(start[:4]) * 12 + int(start[5:7])
    b = int(last_complete(today)[:4]) * 12 + int(last_complete(today)[5:7])
    return max(0, b - a + 1)


def summary(s: dict, today: dt.date) -> dict:
    sts = sorted(s["statements"], key=lambda x: x["month"])
    dfy = s.get("program") == "dfy"
    total, qn = cuts.dfy_totals(s) if dfy else (round(sum(x["cut"] for x in sts), 2), 0)
    paid = round(sum(sum(p["amount"] for p in i["payments"]) for i in s["invoices"]), 2)
    owed_now = round(sum(cuts.owed(i) for i in s["invoices"]), 2)
    return {"s": s, "name": s["name"], "dfy": dfy, "sts": sts, "total": total, "qn": qn, "paid": paid, "owed": owed_now, "sym": s["sym"], "status": s["status"],
            "elapsed": elapsed_months(s["start"], today), "last": sts[-1]["month"] if sts else ""}


# ------------------------------------------------------------------ flags

def flags_for(u: dict, today: dt.date) -> list[dict]:
    s, sts, sym = u["s"], u["sts"], u["sym"]
    out: list[dict] = []

    def add(kind, sev, fact):
        out.append({"kind": kind, "sev": sev, "fact": fact, "student": u["name"]})

    if u["status"] != "active":
        return out
    miss = cuts.missing_months(s, today)
    if miss and not sts:
        add("no_data", "red" if len(miss) >= 2 else "amber", f"has never filed: {len(miss)} month(s) since the agreement started ({', '.join(month_name(m) for m in miss[:3])})")
    elif miss:
        add("quiet", "red" if len(miss) >= 2 else "amber", f"has not filed for {', '.join(month_name(m) for m in miss[:3])}")
    nets = [x["earned"] for x in sts]
    thr = s.get("threshold") or 0
    if u["dfy"] and thr:
        run = []
        for x in reversed(sts):
            if x["earned"] >= thr:
                break
            run.append(x)
        run.reverse()
        zeros = []
        for x in reversed(sts):
            if x["earned"] > 0:
                break
            zeros.append(x)
        if len(zeros) >= 2:
            add("zero_streak", "red", f"filed 0 for {len(zeros)} months in a row ({', '.join(month_name(x['month']) for x in zeros[::-1])})")
        elif len(run) >= 2 and run[-1]["earned"] > 0:
            vals = ", ".join(money(x["earned"], sym) for x in run[-3:])
            close = all(x["earned"] >= thr * (1 - LINE_NEAR) for x in run[-2:])
            add("under_line", "info" if close else "amber", f"under the {money(thr, sym)} line for {len(run)} months in a row ({vals})" + (": close, an opportunity" if close else ""))
    if len(sts) >= 3:
        prior = nets[-4:-1] if len(nets) >= 4 else nets[:-1]
        if prior and statistics.mean(prior) > 0 and nets[-1] < DROP_RATIO * statistics.mean(prior):
            add("drop", "amber", f"{month_name(sts[-1]['month'])} was {money(nets[-1], sym)}, under half of their recent average ({money(statistics.mean(prior), sym)})")
    if u["dfy"] and len(sts) >= 3 and u["qn"] / len(sts) < 0.5 and u["qn"] < s["months_target"]:
        add("behind_pace", "amber", f"only {u['qn']} of the {len(sts)} months they filed were qualified (the goal is {s['months_target']} qualified months)")
    for inv in s["invoices"]:
        left = cuts.owed(inv)
        if left > cuts.TOL and inv["due"] < today.isoformat():
            late = (today - dt.date.fromisoformat(inv["due"])).days
            add("unpaid", "red" if late >= OVERDUE_RED_DAYS else "amber", f"{month_name(inv['month'])} remittance of {money(left, sym)} is {late} day(s) overdue ({inv['id']})")
    if u["dfy"] and s["status"] == "active" and (u["qn"] >= s["months_target"] - 2 or u["total"] >= 0.85 * s["cap"]):
        add("near_complete", "info", f"{u['qn']} of {s['months_target']} qualified months and {money(u['total'], sym)} of {money(s['cap'], sym)}: nearly through DFY")
    return sorted(out, key=lambda f: SEV[f["sev"]])


DRAFTS = {
    "quiet": "Hi {first}, I noticed your DFY filing for {when} is not in yet. If it was a slow month, file it as it is, even if it is 0: that is fine. If something is in the way, tell me and I will help. {sender}",
    "no_data": "Hi {first}, welcome again to the program. I have not seen a first DFY filing from you yet. Where are you with your first client? Tell me and we will plan the next step together. {sender}",
    "zero_streak": "Hi {first}, I saw a couple of quiet months, and no judgment at all. What is getting in the way right now? Let us look at your pipeline together this week. {sender}",
    "under_line": "Hi {first}, your last months were {vals}, close to the $2,000 line. What is the one thing that would get you over it next month? I am happy to help you plan it. {sender}",
    "drop": "Hi {first}, last month looked lower than your usual. How did it go? Is there anything I can help with? {sender}",
    "behind_pace": "Hi {first}, the goal is 12 qualified months and you have had {qn} so far. Let us find one lever together: more outreach, a better offer or a higher price. Do you have 20 minutes this week? {sender}",
    "unpaid": "Hi {first}, a friendly reminder that your {when} remittance was due on {due}. If you have already sent it, send me the receipt so I can match it. If money is tight, tell me and we can talk about it. {sender}",
    "near_complete": "Hi {first}, you are nearly through DFY: {qn} of 12 qualified months. Well done. Let us talk about what comes next for you. {sender}",
}


def first_name(name: str) -> str:
    return (name or "").split(" ")[0] or "there"


def draft(u: dict, f: dict, sender: str) -> str:
    s = u["s"]
    miss = cuts.missing_months(s, dt.date.today())
    inv = next((i for i in s["invoices"] if cuts.owed(i) > cuts.TOL), None)
    vals = ", ".join(money(x["earned"], u["sym"]) for x in u["sts"][-3:])
    text = DRAFTS[f["kind"]].replace(" {sender}", "\n\n{sender}")
    return text.format(first=first_name(u["name"]), when=(month_name(miss[0]) if miss else (month_name(inv["month"]) if inv else "this month")), vals=vals, qn=u["qn"],
                       due=(inv["due"] if inv else ""), sender=sender or "[your name]")


# ------------------------------------------------------------------ forecast

def forecast(slug: str, months: int = 6, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    if not 1 <= months <= 24:
        raise ValueError("The forecast covers 1 to 24 months.")
    next_arrival = month_add(today.strftime("%Y-%m"), 1)
    horizon = [month_add(next_arrival, i) for i in range(months)]
    per_month = {m: {"likely": 0.0, "low": 0.0, "n": 0} for m in horizon}
    students, skipped = [], []
    for _f, s in cuts.all_students(slug):
        if s.get("program") != "dfy" or s["status"] != "active":
            continue
        sts = sorted(s["statements"], key=lambda x: x["month"])
        recent = [x["earned"] for x in sts][-3:]
        if len(recent) < 2:
            skipped.append(s["name"])
            continue
        res = {"name": s["name"], "sym": s["sym"], "recent": recent, "likely_done": "", "low_done": "", "likely_sum": 0.0, "low_sum": 0.0}
        for label, net in (("likely", statistics.mean(recent)), ("low", min(recent))):
            total, qn = cuts.dfy_totals(s)
            room = s["cap"] - total
            em = month_add(sts[-1]["month"], 1)
            last_earn = month_add(horizon[-1], -1)
            done = ""
            while em <= last_earn and not done:
                cut = min(round(net * s["percent"] / 100, 2), max(room, 0))
                arrival = max(month_add(em, 1), next_arrival)
                if arrival in per_month and cut > 0:
                    per_month[arrival][label] += cut
                    res[label + "_sum"] += cut
                room -= cut
                if net >= s["threshold"]:
                    qn += 1
                if qn >= s["months_target"] or room <= cuts.TOL:
                    done = month_add(em, 1)
                em = month_add(em, 1)
            res[label + "_done"] = done
        students.append(res)
    for m in horizon:
        per_month[m]["n"] = sum(1 for r in students if r["likely_sum"] > 0)
    return {"months": horizon, "per_month": per_month, "students": students, "skipped": skipped}


# ------------------------------------------------------------------ the report

def build_units(slug: str, today: dt.date) -> list[dict]:
    units = []
    for _f, s in cuts.all_students(slug):
        u = summary(s, today)
        u["flags"] = flags_for(u, today)
        units.append(u)
    return units


def overview_lines(units: list[dict]) -> list[str]:
    L = [f"{'Student':<24}{'Status':<10}{'Qualified':>10}{'Remitted':>20}  Flags"]
    for u in sorted(units, key=lambda x: (SEV[x["flags"][0]["sev"]] if x["flags"] else 3, x["name"])):
        prog = f"{u['qn']}/{u['s']['months_target']}" if u["dfy"] else "-"
        rem = f"{money(u['total'], u['sym'])}/{money(u['s']['cap'], u['sym'])}" if u["dfy"] else money(u["total"], u["sym"])
        fl = ", ".join(f["kind"].replace("_", " ") for f in u["flags"]) or "on track"
        L.append(f"{u['name'][:23]:<24}{u['status']:<10}{prog:>10}{rem:>20}  {fl}")
    return L


def report(slug: str, view: str = "overview", months: int = 6, today: dt.date | None = None) -> str:
    cfg = load(slug)
    today = today or dt.date.today()
    if view not in ("overview", "flags", "drafts", "forecast"):
        raise ValueError("View is overview, flags, drafts or forecast.")
    units = build_units(slug, today)
    if not units:
        return f"No students yet. DFY students arrive with: python dse.py cut sync {slug}  (or add one: python dse.py cut add {slug} --name \"Ada Obi\" --program dfy)\n"
    sender = (cfg.get("sender_name") or "").strip()
    L = [f"# Student Success Desk: {slug}", ""]
    active = [u for u in units if u["status"] == "active"]
    allf = sorted((f for u in units for f in u["flags"]), key=lambda f: SEV[f["sev"]])
    L.append(f"{len(units)} student(s): {len(active)} active, {sum(1 for u in units if u['status'] == 'completed')} completed. "
             + (f"{sum(1 for f in allf if f['sev'] == 'red')} need a check-in now, {sum(1 for f in allf if f['sev'] == 'amber')} to keep an eye on." if allf else "Everyone looks on track."))
    if view in ("overview", "flags"):
        if view == "overview":
            L += ["", "## Progress", *overview_lines(units)]
        if allf:
            L += ["", "## Flags, most urgent first"]
            for f in allf:
                L.append(f"- [{f['sev']}] {f['student']}: {f['kind'].replace('_', ' ')}: {f['fact']}")
    if view in ("overview", "drafts") and allf:
        L += ["", "## Draft messages (you send them yourself)" if view == "drafts" else "## Draft for the most urgent"]
        shown = allf if view == "drafts" else allf[:1]
        for f in shown:
            u = next(x for x in units if x["name"] == f["student"])
            L += ["", f"To {u['name']} ({f['kind'].replace('_', ' ')}):", draft(u, f, sender)]
        if view == "overview" and len(allf) > 1:
            L += ["", f"({len(allf) - 1} more: run with --view drafts)"]
    if view in ("overview", "forecast"):
        fc = forecast(slug, months, today)
        L += ["", f"## Expected DFY income, next {months} months (a projection from each student's own last 3 filed months, not a promise)"]
        if not fc["students"]:
            L.append("- Not enough history yet: a forecast needs at least two filed months for a student." + (f" Left out: {', '.join(fc['skipped'])}." if fc["skipped"] else ""))
        else:
            for m in fc["months"]:
                pm = fc["per_month"][m]
                L.append(f"- {month_name(m)}: likely {money(pm['likely'])}, low {money(pm['low'])}" + (f" ({pm['n']} student(s))" if pm["n"] else ""))
            L.append(f"- Total: likely {money(sum(fc['per_month'][m]['likely'] for m in fc['months']))}, low {money(sum(fc['per_month'][m]['low'] for m in fc['months']))}")
            done = [f"{r['name']} by {month_name(r['likely_done'])}" for r in fc["students"] if r["likely_done"]]
            if done:
                L.append("- Likely to finish DFY within the window: " + ", ".join(done))
            if fc["skipped"]:
                L.append(f"- Left out for too little history ({len(fc['skipped'])}): {', '.join(fc['skipped'])}")
    L += ["", "Every flag and figure comes from the filings in engines/<engine>/cuts/. Nothing was sent."]
    text = "\n".join(L) + "\n"
    (engine_dir(slug) / "success-desk.md").write_text(text, encoding="utf-8")
    return text


def attention(slug: str, today: dt.date) -> dict:
    """For the Weekly Review: students with a red or amber flag, most urgent first, and next month's expected DFY income."""
    units = build_units(slug, today)
    rows = []
    for u in units:
        hot = [f for f in u["flags"] if f["sev"] in ("red", "amber")]
        if hot:
            rows.append({"student": u["name"], "sev": hot[0]["sev"], "why": hot[0]["fact"], "n": len(hot)})
    rows.sort(key=lambda r: (SEV[r["sev"]], -r["n"], r["student"]))
    try:
        fc = forecast(slug, 1, today)
        m = fc["months"][0]
        nxt = {"month": m, "likely": fc["per_month"][m]["likely"], "low": fc["per_month"][m]["low"], "students": len(fc["students"])}
    except ValueError:
        nxt = None
    return {"needs": rows, "next": nxt}
