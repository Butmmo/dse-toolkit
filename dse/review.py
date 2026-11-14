"""The Weekly Review: what to do first this week, worked out from everything the other tools already saved.

    python dse.py review <engine|all> [--top 5]

It reads (all in engines/<slug>/, nothing is guessed, nothing is sent):
  data/log.csv      Send Desk taps: replies waiting, calls booked, what was sent in the last 7 days
  send-lists/       messages on your lists that are still not marked Sent
  follow-ups        threads whose next touch is due (the same rules as `dse.py followups`)
  data/calls.csv    calls on your scorecard; data/cash.csv and cash.json: money and your goal
  offers.csv        offers you are still vetting, next-goal.md: a suggested goal waiting for you

The moves are ranked by one fixed rule, closest to money first, and the report says which file each number came from:
  1 replies waiting for your answer  2 calls booked to prepare for  3 follow-ups due  4 messages on your lists not yet sent
  2.5 overdue client invoices  2.6 overdue student cuts  3.5 late client deliverables  3.6 students who have not reported  5 sold calls whose money is not logged  6 nothing sent for 7 days  7 offers still being vetted  8 a goal suggestion to accept, or a goal you are behind on
"""
from __future__ import annotations

import datetime as dt

from . import cashdesk as cd
from . import desklog as dl
from . import clients, cuts, followups, goals, vetting
from .engines import all_slugs, engine_dir, load

OPEN_OFFERS = ("researching", "applied", "interview")
DAYS = 7


def gather(slug: str, today: dt.date) -> dict:
    hist = dl.history(slug)
    rows = dl.load_lists(slug)
    replies, booked, unsent = [], [], []
    for r in rows:
        st = dl.status_of_row(hist, r)
        name = r.get("business") or r.get("name") or r["_row_id"]
        if st == "replied":
            replies.append(name)
        elif st == "booked":
            booked.append(name)
        elif st == "to do" and r["_date"] <= today.isoformat():
            unsent.append(r["_source"])
    since = (today - dt.timedelta(days=DAYS - 1)).isoformat()
    sent_week = {(e.get("source", ""), str(e.get("row_id", ""))) for e in dl.read_log(slug)
                 if e.get("status") in ("sent", "replied", "booked", "won", "lost") and str(e.get("logged_at", ""))[:10] >= since}
    try:
        due = followups.due_count(slug, today)
        unmarked = len(followups.analyse(slug)["unmarked"])
    except Exception:           # no follow-up wording file yet, or lists in an old format: the review still works without it
        due, unmarked = 0, 0
    a, b = cd.month_bounds(None, today)
    month = cd.month_data(slug, a, b)
    key = a.strftime("%Y-%m")
    target = cd.get_target(slug, key)
    offers = [o for o in vetting.read_offers(slug) if o.get("status") in OPEN_OFFERS]
    try:
        att = clients.attention(slug, today)
    except Exception:
        att = {"overdue_invoices": [], "late_items": []}
    try:
        cut = cuts.attention(slug, today)
    except Exception:
        cut = {"overdue": [], "quiet": []}
    return {"cuts": cut, "clients": att, "slug": slug, "replies": replies, "booked": booked, "unsent": unsent, "sent_week": len(sent_week), "has_lists": bool(rows), "due": due, "unmarked": unmarked,
            "month": month, "target": target, "key": key, "pace": cd.pace(month["received"], today, a, b), "offers": offers,
            "goal_note": (engine_dir(slug) / "next-goal.md").exists()}


def moves(g: dict) -> list[dict]:
    s, out = g["slug"], []
    if g["replies"]:
        n = len(g["replies"])
        out.append({"rank": 1, "do": f"Answer {n} repl{'y' if n == 1 else 'ies'} waiting for you ({', '.join(g['replies'][:3])}{'...' if n > 3 else ''}).",
                    "how": f"Open the Send Desk (Replies). For each one, python dse.py reply {s} --text \"their words\" gives the kind, a draft answer and the follow-up date. You send it yourself.", "source": "data/log.csv: rows whose latest tap is Got a reply"})
    ci = g["clients"]["overdue_invoices"]
    if ci:
        owed = sum(i["owed"] for i in ci)
        sym = ci[0]["sym"] if len({i["sym"] for i in ci}) == 1 else ""
        out.append({"rank": 2.5, "do": f"{len(ci)} overdue invoice{'s' if len(ci) != 1 else ''}, {sym}{owed:,.0f} owed ({', '.join(i['client'] for i in ci[:3])}).",
                    "how": "Send a polite reminder; when it arrives: python dse.py client paid " + f"{s}/<client> --invoice <id>", "source": "clients/*/client.json (invoice due dates and payments)"})
    co = g["cuts"]["overdue"]
    if co:
        sym = co[0]["sym"] if len({i["sym"] for i in co}) == 1 else ""
        out.append({"rank": 2.6, "do": f"{len(co)} student cut invoice{'s' if len(co) != 1 else ''} overdue, {sym}{sum(i['owed'] for i in co):,.0f} owed ({', '.join(i['student'] for i in co[:3])}).",
                    "how": "Send a friendly reminder; when it lands: python dse.py cut paid " + f"{s}/<student> --invoice <id>", "source": "cuts/*/student.json (invoice due dates and payments)"})
    if g["booked"]:
        n = len(g["booked"])
        out.append({"rank": 2, "do": f"Prepare for {n} booked call{'s' if n != 1 else ''} ({', '.join(g['booked'][:3])}{'...' if n > 3 else ''}).",
                    "how": f"After each call: python dse.py callscore {s} --offer ... then, if it went well, python dse.py proposal {s} --client ...", "source": "data/log.csv: rows whose latest tap is Call booked"})
    if g["due"]:
        out.append({"rank": 3, "do": f"Send {g['due']} follow-up{'s' if g['due'] != 1 else ''} that {'are' if g['due'] != 1 else 'is'} due.",
                    "how": f"python dse.py followups {s}, then send them from the Send Desk.", "source": "send-lists/ and data/log.csv (the follow-up rules)"})
    if g["unsent"]:
        n = len(g["unsent"])
        out.append({"rank": 4, "do": f"{n} message{'s' if n != 1 else ''} on your lists {'are' if n != 1 else 'is'} still not marked Sent.",
                    "how": f"First run python dse.py preflight {s} to catch blockers. Then open the Send Desk, send them yourself and tap Sent (or Skip).", "source": f"send-lists/ ({', '.join(sorted(set(g['unsent']))[:3])})"})
    cq = g["cuts"]["quiet"]
    if cq:
        out.append({"rank": 3.6, "do": f"{len(cq)} student{'s have' if len(cq) != 1 else ' has'} not reported earnings ({'; '.join(q['student'] + ' ' + ', '.join(q['months'][:2]) for q in cq[:3])}).",
                    "how": "Ask a friendly question. Then: python dse.py cut report " + f"{s}/<student> --month YYYY-MM --earned N (0 if nothing)", "source": "cuts/*/student.json (the agreement: report by the 7th)"})
    li = g["clients"]["late_items"]
    if li:
        out.append({"rank": 3.5, "do": f"{len(li)} deliverable{'s' if len(li) != 1 else ''} late ({'; '.join(x['client'] + ': ' + x['item'] for x in li[:3])}).",
                    "how": "Finish or tell the client the new date today; tick done with: python dse.py client done " + f"{s}/<client> --item \"...\"", "source": "clients/*/client.json (delivery dates from the proposal)"})
    c = g["month"]["calls"]
    if c["sold"] and g["month"]["received"] <= 0:
        out.append({"rank": 5, "do": f"{c['sold']} sold call(s) this month but no money logged as received.",
                    "how": f"When it arrives: python dse.py cashin {s} --amount N --kind commission", "source": "data/calls.csv (sold) and data/cash.csv (empty)"})
    if g["has_lists"] is False or g["sent_week"] == 0:
        why = "no lists yet" if not g["has_lists"] else f"nothing sent in the last {DAYS} days"
        out.append({"rank": 6, "do": f"Nothing is going out: {why}.", "how": f"python dse.py daily {s} to build today's list.", "source": "send-lists/ and data/log.csv"})
    if g["offers"]:
        n = len(g["offers"])
        out.append({"rank": 7, "do": f"{n} offer{'s' if n != 1 else ''} still being vetted ({', '.join(o['offer'] for o in g['offers'][:3])}).",
                    "how": f"python dse.py offers {s}, then decide: apply, walk away or finish the checklist.", "source": "offers.csv"})
    if g["goal_note"]:
        out.append({"rank": 8, "do": "A goal suggestion for next month is ready to accept.", "how": f"Read engines/{s}/next-goal.md, then python dse.py goal {s} --apply (or --set N).", "source": "next-goal.md"})
    elif g["pace"]["state"] == "now" and g["month"]["received"] < g["target"] and g["pace"]["projected"] < g["target"] and g["month"]["received"] > 0:
        out.append({"rank": 8, "do": f"Behind the {cd.money(g['target'])} goal: on pace for {cd.money(round(g['pace']['projected']))}.", "how": f"python dse.py cash {s} shows what closing the gap would take.", "source": "data/cash.csv, cash.json"})
    if g["unmarked"]:
        out.append({"rank": 4.5, "do": f"{g['unmarked']} older message(s) were never marked Sent or Skipped, so follow-ups cannot be planned for them.", "how": "Mark them in the Send Desk (I never guess).", "source": "send-lists/ and data/log.csv"})
    return sorted(out, key=lambda m: m["rank"])


def build(slug: str, top: int = 5, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    slugs = all_slugs() if slug == "all" else [slug]
    if slug != "all":
        load(slug)
    if not slugs:
        return "You have no engines yet. Create one in HQ Tools, then come back.\n"
    week = today - dt.timedelta(days=today.weekday())
    out = [f"# Weekly Review: {'all engines' if slug == 'all' else slug}, week of {week.isoformat()}", ""]
    allm = []
    for s in slugs:
        g = gather(s, today)
        ms = moves(g)
        allm.append((s, g, ms))
    for s, g, _ms in allm:
        m, p = g["month"], g["pace"]
        line = f"- {s}: " + (f"{cd.money(m['received'])} of {cd.money(g['target'])} received" + (f", on pace for {cd.money(round(p['projected']))}" if p["state"] == "now" and m["received"] > 0 else "")
                              + f"; {g['sent_week']} message(s) sent in the last {DAYS} days")
        out.append(line)
    flat = [(s, mv) for s, _g, ms in allm for mv in ms]
    flat.sort(key=lambda x: x[1]["rank"])
    out += ["", (f"## Your {min(top, len(flat))} moves, in order" if min(top, len(flat)) > 1 else "## Your move")] if flat else ["", "## Nothing is waiting. Keep the messages going out."]
    for i, (s, mv) in enumerate(flat[:top], 1):
        who = f"[{s}] " if slug == "all" else ""
        out += [f"{i}. {who}{mv['do']}", f"   How: {mv['how']}", f"   From: {mv['source']}"]
    if len(flat) > top:
        out.append(f"\n({len(flat) - top} more: run again with --top {len(flat)} to see them.)")
    out += ["", "Ranked by one fixed rule, closest to money first (see dse/review.py). Nothing is sent or changed by this report."]
    text = "\n".join(out) + "\n"
    if slug != "all":
        (engine_dir(slug) / "weekly-review.md").write_text(text, encoding="utf-8")
    return text
