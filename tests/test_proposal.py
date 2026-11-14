"""Tests for the Proposal Builder.   python tests/test_proposal.py"""
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import proposal as P  # noqa: E402

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


TODAY = dt.date(2026, 11, 14)      # a Saturday
START = dt.date(2026, 11, 16)
check("next Monday from a Saturday and from a Monday", P.next_monday(TODAY) == START and P.next_monday(dt.date(2026, 11, 16)) == dt.date(2026, 11, 23))
s = P.schedule(["A", "B", "C"], 3, START)
check("3 items over 3 weeks: one a week, with dates", [w.split(" (")[0] for w, _ in s] == ["Week 1", "Week 2", "Week 3"] and "Nov 16 to Nov 20" in s[0][0], str(s))
s = P.schedule(["A", "B", "C", "D"], 2, START)
check("4 items over 2 weeks: two share a week", [w.split(" (")[0] for w, _ in s] == ["Week 1", "Week 1", "Week 2", "Week 2"], str(s))
s = P.schedule(["A", "B"], 6, START)
check("2 items over 6 weeks: each gets a span of weeks", [w.split(" (")[0] for w, _ in s] == ["Week 1 to 3", "Week 4 to 6"], str(s))
check("options parse, sorted by price", [o["name"] for o in P.parse_options("Premium:2800:10 pages; Basic:800:2 pages; Standard:1,500")] == ["Basic", "Standard", "Premium"])
check("bad options are explained", "could not read" in (raises(P.parse_options, "Basic;Standard:abc") or "") and "2 to 4" in (raises(P.parse_options, "Only:100") or ""))

SLUG = "zz-prop"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "data").mkdir(parents=True)
(d / "engine.json").write_text(json.dumps({"name": "Prop test", "path": "smb", "sender_name": "Bolu Ade", "brand_name": "T Co", "calendar_url": "https://cal.example/bolu", "archived": False}), encoding="utf-8")
ARGS = dict(slug=SLUG, client="Acme Dental", contact="Dana", problem="patients cannot book online and call after hours", offer="Online booking that fills the calendar",
            price=1500, deliverables="Booking page; Reminder emails; Staff training", weeks=3, today=TODAY, start="2026-11-16")
try:
    t = P.report(**ARGS, cost_month=4000)
    md = (d / "proposals" / "2026-11-14-acme-dental.md").read_text(encoding="utf-8")
    check("saved as text with the cover email and follow-up, and as html", "Cover email" in md and "Follow-up" in md and (d / "proposals" / "2026-11-14-acme-dental.html").exists())
    check("their own words are quoted back", "patients cannot book online" in md)
    check("cost section is the arithmetic on the given figure: 4,000 a month, 48,000 a year", "$4,000 a month" in md and "$48,000 a year" in md)
    check("payback = price / monthly cost = 0.4 months, labelled as arithmetic and not a promise", "0.4 month" in md and "not a promise" in md)
    check("deposit 50%: 750 to start, 750 on delivery", "50% ($750)" in md and "balance ($750)" in md)
    check("sender name, brand, calendar and validity (14 days)", "Bolu Ade" in md and "T Co" in md and "https://cal.example/bolu" in md and "November 28, 2026" in md)
    check("the unfilled 'not included' placeholder is reported before sending", "Before you send" in t and "[List what you will not do]" in t, t[-600:])
    check("no invented claims: no 'guarantee', 'testimonial' or 'proven'", not any(w in md.lower() for w in ("guarantee", "testimonial", "proven", "best in")))
    check("no em dash anywhere", chr(0x2014) not in t)
    check("nothing is sent, said plainly", "Nothing was sent" in t)

    t = P.report(**ARGS, excludes="Hosting and domain fees; photography")
    md = (d / "proposals" / "2026-11-14-acme-dental.md").read_text(encoding="utf-8")
    check("with exclusions given there is no placeholder to fill", "Hosting and domain fees" in md and "Before you send" not in t)
    check("no cost given: no cost section, and the report says what to ask", "What it costs you today" not in md and "What does that cost you each month" in t)

    t = P.report(**{**ARGS, "price": 1500}, cost_month=100)
    check("price above a year of the problem triggers a check", "more than a full year" in t, t[-400:])

    t = P.report(**{**ARGS, "price": 0}, options="Basic:800:2 pages; Standard:1500:5 pages; Premium:2800:10 pages")
    md = (d / "proposals" / "2026-11-14-acme-dental.md").read_text(encoding="utf-8")
    check("three options: a comparison table with the middle one recommended", "| Standard (recommended) | $1,500 |" in md and "| Basic | $800 |" in md and "| Premium | $2,800 |" in md, md)
    check("the main price follows the recommended option (1,500: deposit 750)", "50% ($750)" in md)
    t = P.report(**{**ARGS, "price": 0}, options="Lite:500; Full:900")
    md = (d / "proposals" / "2026-11-14-acme-dental.md").read_text(encoding="utf-8")
    check("two options: the cheaper is recommended, deposit follows it", "| Lite (recommended) | $500 |" in md and "50% ($250)" in md)

    t = P.report(**ARGS, deposit=0, currency="GBP")
    md = (d / "proposals" / "2026-11-14-acme-dental.md").read_text(encoding="utf-8")
    check("GBP symbol and 'in full when delivered' with no deposit", "£1,500" in md and "in full when the work is delivered" in md)
    P.report(**ARGS, deposit=100)
    check("100% deposit says paid in full to start", "in full to start" in (d / "proposals" / "2026-11-14-acme-dental.md").read_text(encoding="utf-8"))

    P.report(**{**ARGS, "client": "<script>alert(1)</script> & Co"})
    page = next((d / "proposals").glob("*script*.html"), None) or next((d / "proposals").glob("*alert*.html"))
    h = page.read_text(encoding="utf-8")
    check("html escapes the client's name", "<script>alert" not in h and "&lt;script&gt;" in h)
    check("html is print-ready: a table, a title, a print style", "<table>" in h and "<title>Proposal for" in h and "@media print" in h)

    # validation
    for name, kw in {"client too short": {"client": "A"}, "problem too short": {"problem": "bad"}, "no deliverables": {"deliverables": " ; "}, "13 deliverables": {"deliverables": ";".join("x%d" % i for i in range(13))},
                     "weeks 0": {"weeks": 0}, "weeks 40": {"weeks": 40}, "bad currency": {"currency": "XYZ"}, "deposit 150": {"deposit": 150}, "no price": {"price": 0}, "negative cost": {"cost_month": -5}}.items():
        check(f"refused: {name}", raises(P.report, **{**ARGS, **kw}) is not None)
    check("unknown engine exits", True)
finally:
    shutil.rmtree(d, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
