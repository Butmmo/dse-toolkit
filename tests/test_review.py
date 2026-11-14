"""Scenario tests for the Weekly Review and the monthly goals.   python tests/test_review.py"""
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import callscore, cashdesk as C, desklog as dl, goals as G, review as R, vetting  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except ValueError as e:
        return str(e)
    return None


def write_csv(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def row(n, name, **kw):
    return {"row": n, "business": name, "city": "Tampa", "channel": "Email", "where": f"{name.lower()}@x.example.com", "gap_used": "g", "variant": "smb-v1", "opener": "Hi",
            "website": f"https://{name.lower()}.example.com", "email": f"{name.lower()}@x.example.com", "instagram": "", "facebook": "", **kw}


def tap(slug, source, row_id, status, day, **kw):
    dl.append_events(slug, [{"logged_at": f"{day}T10:00:00", "source": source, "row_id": str(row_id), "status": status, "list_date": source[:10], **kw}])


SLUG = "zz-review"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "send-lists").mkdir(parents=True)
(d / "data").mkdir()
(d / "engine.json").write_text(json.dumps({"name": "Review test", "path": "smb", "sender_name": "Bolu", "brand_name": "T Co", "archived": False}), encoding="utf-8")
today = dt.date.today()
iso = lambda n: (today - dt.timedelta(days=n)).isoformat()  # noqa: E731
try:
    # an empty engine
    t = R.build(SLUG, today=today)
    check("empty engine: the one move is to build a list", "Nothing is going out" in t and "daily" in t and "Your move" in t, t)

    old, new = iso(10), iso(0)
    write_csv(d / "send-lists" / f"{old}.csv", [row(i, n) for i, n in enumerate(["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"], 1)])
    write_csv(d / "send-lists" / f"{new}.csv", [row(7, "Golf"), row(8, "Hotel")])
    src = old
    tap(SLUG, src, 1, "sent", iso(9))                           # sent 9 days ago, no answer: follow-up due
    tap(SLUG, src, 2, "sent", iso(8)); tap(SLUG, src, 2, "replied", iso(7), reply="yes")     # reply waiting
    tap(SLUG, src, 3, "sent", iso(8)); tap(SLUG, src, 3, "booked", iso(6))                  # call booked
    tap(SLUG, src, 4, "sent", iso(1))                           # sent yesterday: not due
    tap(SLUG, src, 6, "skipped", iso(9))
    # row 5 never marked (older list): unmarked and unsent
    vetting.save_offer(SLUG, {"date": iso(2), "offer": "Acme Co", "url": "", "status": "researching", "verdict": "AMBER", "score": 50})
    callscore.log_call(SLUG, "Acme Co", "sold", 1000, 20, 40, [1] * 8, today)

    g = R.gather(SLUG, today)
    check("replies waiting: Bravo", g["replies"] == ["Bravo"], str(g["replies"]))
    check("booked: Charlie", g["booked"] == ["Charlie"], str(g["booked"]))
    check("follow-ups due counted by the same rules as dse.py followups", g["due"] >= 1, str(g["due"]))
    check("unsent: Echo (old list), Golf and Hotel (today's list)", len(g["unsent"]) == 3, str(g["unsent"]))
    check("sent in the last 7 days: Bravo? no (sent 8 days ago, replied 7 days ago) counts via the reply tap; Delta yes", g["sent_week"] >= 1, str(g["sent_week"]))
    check("one open offer", len(g["offers"]) == 1)
    ms = R.moves(g)
    ranks = [m["rank"] for m in ms]
    check("moves come in the fixed order, closest to money first", ranks == sorted(ranks) and ranks[:3] == [1, 2, 3], str(ranks))
    check("sold call with no money logged is flagged", any(m["rank"] == 5 for m in ms))
    check("open offer is flagged", any(m["rank"] == 7 for m in ms))
    check("a never-marked old message is flagged, not guessed", any(m["rank"] == 4.5 for m in ms))
    check("nothing flagged for 'nothing is going out' while messages went out this week", not any(m["rank"] == 6 for m in ms))
    t = R.build(SLUG, top=3, today=today)
    check("top 3 only shows 3 and says how to see more", t.count("\n   How:") == 3 and "more: run again with --top" in t, t)
    check("each move says where its number came from", t.count("From:") == 3)
    check("report saved", (d / "weekly-review.md").exists())
    check("the all-engines review lists this engine", f"[{SLUG}]" in R.build("all", top=30, today=today))
    check("no em dash in the review", chr(0x2014) not in R.build(SLUG, top=30, today=today))

    # money logged clears the 'log your money' move; behind-on-goal move appears
    C.log_cash(SLUG, 200, "commission", "Acme", today.isoformat())
    ms = R.moves(R.gather(SLUG, today))
    check("logging money clears the sold-call move", not any(m["rank"] == 5 for m in ms))
    check("behind the goal is flagged once money exists and pace is short", any(m["rank"] == 8 and "Behind" in m["do"] for m in ms) or today.day == 1, str([m["do"] for m in ms]))

    # ---- goals
    T = dt.date(2026, 12, 3)        # early December
    C.log_cash(SLUG, 600, "commission", "", "2026-09-10")
    C.log_cash(SLUG, 1000, "commission", "", "2026-10-10")
    C.log_cash(SLUG, 1200, "commission", "", "2026-11-10")
    h = G.complete_months(SLUG, T)
    check("last three complete months with their money", h == [("2026-09", 600.0), ("2026-10", 1000.0), ("2026-11", 1400.0)], str(h))
    s = G.suggest(SLUG, T)
    check("base = last month when it beats the average (1,400); +20% = 1,680; rounded up to 1,700", s["base"] == 1400 and s["suggested"] == 1700.0, str(s))
    check("0% stretch = 1,400", G.suggest(SLUG, T, 0)["suggested"] == 1400.0)
    h2 = G.complete_months(SLUG, dt.date(2026, 11, 20))
    check("months before your first logged money are not counted", h2 == [("2026-09", 600.0), ("2026-10", 1000.0)], str(h2))
    avg = G.suggest(SLUG, dt.date(2026, 11, 20))
    check("base = average (800) when the last month does not beat it: 1,000 is the last and beats 800, so 1,000", avg["base"] == 1000.0 and avg["suggested"] == 1200.0, str(avg))
    check("no history: no suggestion, standing target stays", G.suggest("web-development-work", T)["suggested"] is None)
    check("default month: early in a month with no goal = this month", G.default_month(SLUG, dt.date(2026, 12, 3)) == "2026-12")
    check("default month: late in the month = next month", G.default_month(SLUG, dt.date(2026, 12, 20)) == "2027-01")
    t = G.report(SLUG, "2026-12", today=T)
    check("report shows the working and does not change anything", "Base $1,400" in t and "$1,700" in t and C.get_target(SLUG, "2026-12") == 3000 and "carried forward" in t, t)
    t = G.report(SLUG, "2026-12", apply=True, today=T)
    check("--apply saves that month's goal only", C.get_target(SLUG, "2026-12") == 1700 and C.get_target(SLUG, "2027-01") == 3000 and "Saved" in t, t)
    G.report(SLUG, "2026-12", set_to=2500, today=T)
    check("--set overrides", C.get_target(SLUG, "2026-12") == 2500)
    check("bad month, stretch and goal refused", raises(G.report, SLUG, "2026-13") and raises(G.report, SLUG, "2026-12", 500.0) and raises(G.report, SLUG, "2026-12", set_to=5))
    check("the Cash Desk uses the month's own goal", "$2,500" in C.build(SLUG, "2026-12", today=T), "")

    # what the goal needs, from rates (direct)
    dd = {"entries": [], "funnel": {"sent": 100, "replied": 20, "booked": 10, "won": 2}, "calls": {"calls": 10, "shown": 8, "sold": 2, "cash": 2000.0, "earned": 400.0}}
    n = G.needs(dd, 2000)
    check("2,000 goal at $200 a sale = 10 sales; close 25% = 40 calls; show 80% = 50 booked; 50% book rate = 100 replies; 20% reply = 500 messages",
          round(n["sales"]) == 10 and round(n["calls"]) == 40 and round(n["booked"]) == 50 and round(n["messages"]) == 500, str(n))
    thin = {"entries": [], "funnel": {"sent": 10, "replied": 1, "booked": 0, "won": 0}, "calls": {"calls": 2, "shown": 2, "sold": 1, "cash": 500.0, "earned": 100.0}}
    n = G.needs(thin, 1000)
    check("too little data: sales shown, calls and messages are not invented", n["sales"] and n["calls"] is None and n["messages"] is None and n["notes"], str(n))
    check("no sale at all: no numbers", G.needs({"entries": [], "funnel": {"sent": 0, "replied": 0, "booked": 0, "won": 0}, "calls": {"calls": 0, "shown": 0, "sold": 0, "cash": 0.0, "earned": 0.0}}, 1000)["sales"] is None)

    # background suggestion file
    p = G.write_note(SLUG, dt.date(2026, 12, 20))          # plans 2027-01, which has no goal of its own
    check("next-goal.md written when the month ahead has no goal", p and p.exists() and "2027-01" in p.read_text(encoding="utf-8"))
    check("and it changed no goal", C.get_target(SLUG, "2027-01") == 3000)
    C.set_target(SLUG, 2000, "2027-01")
    check("note removed once you set that month's goal", G.write_note(SLUG, dt.date(2026, 12, 20)) is None and not (d / "next-goal.md").exists())
    check("no em dash in goal report", chr(0x2014) not in G.report(SLUG, "2026-12", today=T))
finally:
    shutil.rmtree(d, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
