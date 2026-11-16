"""Tests for the weekly digest: which week, when it is due, the honest numbers, the words.   python tests/test_digest.py"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import digest as D  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def at(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M")


cfg = {"enabled": True, "day": 0, "hour": 7}
check("the calendar I rely on: 16 Nov 2026 is a Monday", at("2026-11-16 00:00").weekday() == 0)

# ---------------------------------------------------------------- settings
tmp = Path(tempfile.mkdtemp(prefix="zz-digest-"))
check("defaults: on, Monday, 07:00", D.settings(tmp / "none.json") == {"enabled": True, "day": 0, "hour": 7})
(tmp / "s.json").write_text(json.dumps({"enabled": False, "day": 9, "hour": "x"}), encoding="utf-8")
s = D.settings(tmp / "s.json")
check("switched off is respected, a day wraps, a bad hour falls back", s["enabled"] is False and s["day"] == 2 and s["hour"] == 7, str(s))
(tmp / "bad.json").write_text("not json", encoding="utf-8")
check("a broken settings file gives the defaults", D.settings(tmp / "bad.json")["enabled"] is True)

# ---------------------------------------------------------------- which week and when
check("at Monday 07:00 the due moment is that Monday", D.due_moment(at("2026-11-16 07:00"), cfg) == at("2026-11-16 07:00"))
check("at Monday 06:59 it is still last Monday's", D.due_moment(at("2026-11-16 06:59"), cfg) == at("2026-11-09 07:00"))
check("later in the week it is still that Monday's", D.due_moment(at("2026-11-19 15:00"), cfg) == at("2026-11-16 07:00"))
check("a Monday due moment covers the Monday to Sunday week that just ended", D.week_for(at("2026-11-16 07:00")) == (dt.date(2026, 11, 9), dt.date(2026, 11, 15)))
wed = {"enabled": True, "day": 2, "hour": 18}
check("a Wednesday due moment still covers the last full week", D.week_for(D.due_moment(at("2026-11-25 19:00"), wed)) == (dt.date(2026, 11, 16), dt.date(2026, 11, 22)))
check("across a month end", D.week_for(at("2026-12-07 07:00")) == (dt.date(2026, 11, 30), dt.date(2026, 12, 6)))
check("week_containing any day", D.week_containing(dt.date(2026, 11, 18)) == (dt.date(2026, 11, 16), dt.date(2026, 11, 22)) and D.week_containing(dt.date(2026, 11, 22))[0] == dt.date(2026, 11, 16))

# ---------------------------------------------------------------- the decision
p = D.decide(at("2026-11-16 07:05"), cfg, {})
check("due on Monday morning, announced", p["week"] == (dt.date(2026, 11, 9), dt.date(2026, 11, 15)) and p["notify"] is True)
check("not twice for the same week", D.decide(at("2026-11-16 09:00"), cfg, {"last_week": "2026-11-09"})["week"] is None)
check("a new week gets its own", D.decide(at("2026-11-23 07:00"), cfg, {"last_week": "2026-11-09"})["week"] == (dt.date(2026, 11, 16), dt.date(2026, 11, 22)))
check("a PC that was off on Monday catches up on Tuesday, announced", D.decide(at("2026-11-17 10:00"), cfg, {"last_week": "2026-11-02"})["notify"] is True)
late = D.decide(at("2026-11-20 10:00"), cfg, {"last_week": "2026-11-02"})
check("more than 3 days late: kept, not announced", late["week"] is not None and late["notify"] is False and "late" in late["why"])
q = D.decide(at("2026-11-16 22:00"), cfg, {}, quiet=True)
check("during quiet hours: kept, not announced", q["week"] is not None and q["notify"] is False and "quiet" in q["why"])
check("switched off: nothing", D.decide(at("2026-11-16 07:05"), {**cfg, "enabled": False}, {})["week"] is None)
check("before the first due moment of a fresh install it still covers the last full week", D.decide(at("2026-11-12 10:00"), cfg, {})["week"] == (dt.date(2026, 11, 2), dt.date(2026, 11, 8)))

# ---------------------------------------------------------------- the numbers (fake data sources)
WEEK = {"a": {"funnel": {"sent": 30, "replied": 4, "booked": 2, "won": 1}, "calls": {"calls": 2}, "received": 300.0, "unconverted": []},
        "b": {"funnel": {"sent": 17, "replied": 2, "booked": 0, "won": 0}, "calls": {"calls": 0}, "received": 150.5, "unconverted": [{"x": 1}]}}
PREV = {"a": {"funnel": {"sent": 20, "replied": 1, "booked": 1, "won": 0}, "calls": {"calls": 1}, "received": 0.0, "unconverted": []},
        "b": {"funnel": {"sent": 10, "replied": 1, "booked": 0, "won": 0}, "calls": {"calls": 0}, "received": 0.0, "unconverted": []}}
MONTH = {"a": {"funnel": {"sent": 0, "replied": 0, "booked": 0, "won": 0}, "calls": {"calls": 0}, "received": 800.0, "unconverted": []},
         "b": {"funnel": {"sent": 0, "replied": 0, "booked": 0, "won": 0}, "calls": {"calls": 0}, "received": 150.5, "unconverted": []}}
asked = []


def month_data(slug, a, b):
    asked.append((slug, a.isoformat(), b.isoformat()))
    if a == dt.date(2026, 11, 9) and b == dt.date(2026, 11, 15):
        return WEEK[slug]
    if a == dt.date(2026, 11, 2) and b == dt.date(2026, 11, 8):
        return PREV[slug]
    return MONTH[slug]


deps = SimpleNamespace(all_slugs=lambda: ["a", "b"], month_data=month_data, get_target=lambda slug, month: {"a": 2000, "b": 1000}[slug], name_of=lambda s: {"a": "Dentists", "b": "Movers"}[s],
                       moves=lambda today: [{"do": "2 replies waiting", "how": "Answer them first", "engine_name": "Dentists"}, {"do": "Plan the follow-ups", "how": "12 are due", "engine_name": "Movers"}])
d = D.build(dt.date(2026, 11, 9), dt.date(2026, 11, 15), deps, at("2026-11-16 07:05"))
check("totals add the engines together", d["totals"] == {"sent": 47, "replied": 6, "booked": 2, "won": 1, "calls": 2, "received": 450.5}, str(d["totals"]))
check("the week before is read for the same engines", d["prev"]["sent"] == 30 and d["prev"]["received"] == 0.0 and ("a", "2026-11-02", "2026-11-08") in asked)
check("the month so far is read from the 1st to the end of the week, and targets add up", d["month"]["received"] == 950.5 and d["month"]["target"] == 3000 and ("a", "2026-11-01", "2026-11-15") in asked and d["month"]["label"] == "November 2026")
check("one line per engine", [e["name"] for e in d["engines"]] == ["Dentists", "Movers"] and d["engines"][0]["sent"] == 30)
check("a payment in a currency with no rate is flagged, not hidden", any("exchange rate" in n for n in d["notes"]))
check("the first three moves come from the brief", [m["do"] for m in d["moves"]] == ["2 replies waiting", "Plan the follow-ups"])
check("the headline is in plain numbers", d["headline"] == "Your week (9 Nov to 15 Nov): 47 sent, 6 replies, 2 calls booked, 1 won, $450.50 received.", d["headline"])
b = D.body(d)
check("the phone text is the headline and the first thing to do, short", b.startswith(d["headline"]) and "First this week: 2 replies waiting" in b and len(b) <= 300)
r = D.render(d)
check("the markdown shows both weeks, the month against the target, each engine and the honest line", "| Sent | 47 | 30 |" in r and "November 2026 so far: $950.50 of a $3,000 target." in r and "- Movers: 17 sent" in r and "## First this week" in r and "Nothing here is estimated" in r, r)

# quiet weeks and edge cases
empty = SimpleNamespace(all_slugs=lambda: ["a"], month_data=lambda s, a, b: {"funnel": {"sent": 0, "replied": 0, "booked": 0, "won": 0}, "calls": {"calls": 0}, "received": 0.0, "unconverted": []},
                        get_target=lambda s, m: 0, name_of=lambda s: s, moves=lambda t: [])
e = D.build(dt.date(2026, 11, 9), dt.date(2026, 11, 15), empty, at("2026-11-16 07:05"))
check("a week with nothing logged says so, and why a sent message may not count", any("Nothing was logged" in n and "tap" in n for n in e["notes"]) and e["headline"].endswith("0 won."), e["headline"])
check("no money in the headline when none was received", "received" not in e["headline"])
check("no first-move line when the brief has none, and no target line without a target", "First this week" not in D.body(e) and "target" not in D.render(e))
none = SimpleNamespace(all_slugs=lambda: [], month_data=None, get_target=None, name_of=None, moves=lambda t: [])
n = D.build(dt.date(2026, 11, 9), dt.date(2026, 11, 15), none, at("2026-11-16 07:05"))
check("no engines: it says so and points to where to make one", "no engines yet" in n["headline"] and "My engines" in n["headline"])
bad = SimpleNamespace(**{**deps.__dict__, "moves": lambda t: 1 / 0})
check("a problem reading the brief never stops the digest", D.build(dt.date(2026, 11, 9), dt.date(2026, 11, 15), bad, at("2026-11-16 07:05"))["moves"] == [])
one = SimpleNamespace(**{**deps.__dict__, "all_slugs": lambda: ["a"]})
o = D.build(dt.date(2026, 11, 9), dt.date(2026, 11, 15), one, at("2026-11-16 07:05"))
check("singular wording", "30 sent, 4 replies, 2 calls booked, 1 won" in o["headline"] and "By engine" not in D.render(o))
check("the span crosses years correctly", D.span({"week_start": "2026-12-28", "week_end": "2027-01-03"}) == "28 Dec 2026 to 3 Jan")

# ---------------------------------------------------------------- the helper and the modules
sync = (ROOT / "bridge" / "digest_sync.py").read_text(encoding="utf-8")
check("the helper sends through one call, and records the week only after it succeeded", sync.count("api.rpc(") == 1 and sync.index("hq_digest_push") < sync.index("STATE.write_text"))
check("a missing database update is named", "20261123090000_weekly_digest.sql" in sync)
src = (ROOT / "dse" / "digest.py").read_text(encoding="utf-8") + sync
check("no em dash", chr(0x2014) not in src)
check("the digest module sends nothing itself", "urllib" not in src and "requests" not in src and "smtp" not in src.lower())
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
check("it runs every 30 minutes and as a tool on demand", any(x["script"] == "bridge/digest_sync.py" and x["every_s"] == 1800 for x in cat["periodic"]) and cat["tools"]["dse.digest"]["args"] == [{"lit": "--now"}])
print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
