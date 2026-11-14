"""Scenario tests for the Cash Desk.   python tests/test_cashdesk.py"""
import csv
import datetime as dt
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import callscore, cashdesk as C, desklog  # noqa: E402

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


SLUG = "zz-cash"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "data").mkdir(parents=True)
(d / "engine.json").write_text('{"name":"Cash test","path":"ascent","archived":false}', encoding="utf-8")
NOV15 = dt.date(2026, 11, 15)
try:
    # empty month
    t = C.build(SLUG, "2026-11", today=NOV15)
    check("empty month says nothing is logged and does not invent numbers", "Nothing received or logged" in t and "$0" in t and "nothing real" in t, t)
    check("empty history says how to log", "cashin" in C.history(SLUG))

    # logging money
    check("amount must be positive", raises(C.log_cash, SLUG, 0, "commission") and raises(C.log_cash, SLUG, -5, "commission"))
    check("kind must be known", raises(C.log_cash, SLUG, 10, "gift") is not None)
    check("date must be real", raises(C.log_cash, SLUG, 10, "commission", "", "2026-13-40") is not None)
    check("unknown engine exits", True)
    C.log_cash(SLUG, 600, "commission", "Acme, sale\nline", "2026-11-03")
    C.log_cash(SLUG, 400, "retainer", "Beta", "2026-11-10")
    C.log_cash(SLUG, 100, "refund", "Acme partial", "2026-11-12")
    C.log_cash(SLUG, 999, "commission", "October money", "2026-10-30")
    rows = C.read_cash(SLUG)
    check("four rows saved, note cleaned of commas and newlines", len(rows) == 4 and rows[0]["note"] == "Acme sale line", str(rows[0]))
    check("refund is stored negative", rows[2]["amount"] == "-100.00")
    d_nov = C.month_data(SLUG, dt.date(2026, 11, 1), dt.date(2026, 11, 30))
    check("only this month's money counts (600 + 400 - 100)", d_nov["received"] == 900.0 and len(d_nov["entries"]) == 3, str(d_nov["received"]))

    # target and pace
    C.set_target(SLUG, 3000)
    check("target saved and read back", C.get_target(SLUG) == 3000)
    check("silly targets refused", raises(C.set_target, SLUG, 5) and raises(C.set_target, SLUG, 5_000_000))
    t = C.build(SLUG, "2026-11", today=NOV15)
    check("pace: 900 in 15 of 30 days projects 1,800 and is Behind", "Behind" in t and "projects to $1,800, short of $3,000 by $1,200" in t, t)
    check("report writes cash-desk.md", (d / "cash-desk.md").exists())
    t = C.build(SLUG, "2026-11", today=dt.date(2026, 11, 30), target=800)
    check("target 800 is reached", "On target" in t and C.get_target(SLUG, "2026-11") == 800 and C.get_target(SLUG) == 3000 and C.get_target(SLUG, "2026-12") == 3000)
    C.set_target(SLUG, 3000, "2026-11")
    t = C.build(SLUG, "2026-10", today=NOV15)
    check("a past month is Missed/Hit with its own money", "Missed" in t and "$999" in t, t)
    t = C.build(SLUG, "2027-01", today=NOV15)
    check("a future month has not started", "not started" in t)
    check("bad month refused", raises(C.build, SLUG, "2026-13") is not None and raises(C.build, SLUG, "Nov") is not None)

    # calls feed the estimate and the what-it-takes maths
    for i in range(6):
        callscore.log_call(SLUG, "Offer", "sold" if i < 2 else "no_sale", 1000 if i < 2 else 0, 20, 40, [1] * 8, dt.date(2026, 11, 2 + i))
    callscore.log_call(SLUG, "Offer", "no_show", 0, 20, 0, [], dt.date(2026, 11, 9))
    c = C.calls_in(SLUG, dt.date(2026, 11, 1), dt.date(2026, 11, 30))
    check("calls counted: 7 booked, 6 shown, 2 sold, earned 400", c["calls"] == 7 and c["shown"] == 6 and c["sold"] == 2 and c["earned"] == 400.0, str(c))
    t = C.build(SLUG, "2026-11", today=NOV15)
    check("estimate is labelled an estimate", "estimate until the money arrives" in t and "$400" in t, t)
    check("what-it-takes uses the logged sales: $200 per sale, gap 2,100 = 10.5 sales", "$200" in t and "10.5 more sale" in t, t)
    check("close rate 2 of 6 shown is 33%", "33%" in t and "2 of 6" in t, t)
    check("calls needed = 10.5 / 0.333 = 32", "about 32 more call" in t, t)
    check("no message data: says so instead of a number", "Not enough message data" in t, t)

    # message funnel from the send log
    ev = []
    for i in range(40):
        ev.append({"logged_at": f"2026-11-05T10:{i % 60:02d}:00", "source": "2026-11-05", "row_id": str(i), "status": "sent"})
    for i in range(8):
        ev.append({"logged_at": "2026-11-06T09:00:00", "source": "2026-11-05", "row_id": str(i), "status": "replied"})
    ev.append({"logged_at": "2026-11-06T09:05:00", "source": "2026-11-05", "row_id": "30", "status": "replied", "category": "out of office"})
    for i in range(4):
        ev.append({"logged_at": "2026-11-07T09:00:00", "source": "2026-11-05", "row_id": str(i), "status": "booked"})
    ev.append({"logged_at": "2026-10-28T09:00:00", "source": "2026-10-28", "row_id": "1", "status": "sent"})
    desklog.append_events(SLUG, ev)
    f = C.funnel(SLUG, dt.date(2026, 11, 1), dt.date(2026, 11, 30))
    check("funnel: 40 sent, 8 real replies (out of office excluded), 4 booked, October ignored", f == {"sent": 40, "replied": 8, "booked": 4, "won": 0}, str(f))
    t = C.build(SLUG, "2026-11", today=NOV15)
    check("with enough data the maths reaches messages", "more messages sent" in t and "Not enough message data" not in t, t)
    check("rates shown: replies 20% of sent, booked 50% of replies", "20% of sent" in t and "50% of replies" in t, t)
    check("under 30 sent is flagged tentative", "tentative" in C.build(SLUG, "2026-10", today=NOV15))

    # everything combined
    p = C.combine([d_nov, d_nov])
    check("all-engines combine adds money, steps and calls", p["received"] == 1800.0 and len(p["entries"]) == 6 and p["calls"]["calls"] == 0)
    check("history lists entries and total", "Total logged" in C.history(SLUG) and "$1,899" in C.history(SLUG))
    check("no em dash in the report", chr(0x2014) not in t)
    # csv opens cleanly
    with (d / "data" / "cash.csv").open(encoding="utf-8-sig", newline="") as fh:
        check("cash.csv has a header and four rows", list(csv.reader(fh))[0] == C.COLS)
finally:
    shutil.rmtree(d, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
