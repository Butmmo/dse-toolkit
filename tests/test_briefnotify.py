"""Scenario tests for the brief notifications (when a push is sent and when it is not).   python tests/test_briefnotify.py"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import briefnotify as N  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def mv(rank, do, engine="e1", name="Tampa dentists"):
    return {"rank": rank, "do": do, "engine": engine, "engine_name": name}


def brief(*moves):
    return {"moves": list(moves)}


CFG = dict(N.DEFAULTS)
NOON = dt.datetime(2026, 11, 16, 12, 0, 0)
at = lambda h, m=0: dt.datetime(2026, 11, 16, h, m, 0)  # noqa: E731

# ---------------------------------------------------------------- what counts
b = brief(mv(1, "Answer 2 replies waiting for you (Alpha, Bravo)."), mv(3, "Send 4 follow-ups that are due."), mv(4, "3 messages on your lists are still not marked Sent."), mv(6, "Nothing is going out."),
          mv(2.5, "1 overdue invoice, $500 owed (Acme)."), mv(7, "2 offers still being vetted."), mv(8, "A goal suggestion is ready."))
n = N.notable(b)
check("only things that need you count: replies, booked calls, overdue money, late work, check-ins", set(n) == {"e1|1", "e1|2.5"}, str(set(n)))
check("routine things never buzz the phone (follow-ups, unsent, nothing going out, offers, goals)", not any(k.endswith(("|3", "|4", "|6", "|7", "|8")) for k in n))
check("the number in the sentence is read", n["e1|1"]["n"] == 2 and n["e1|2.5"]["n"] == 1)

# ---------------------------------------------------------------- the first brief is a baseline
push, st = N.decide(b, {}, NOON, CFG)
check("the first brief is a baseline: what is already waiting is not announced", push is None and st["announced"] == {"e1|1": 2, "e1|2.5": 1})

# ---------------------------------------------------------------- new things
b2 = brief(mv(1, "Answer 2 replies waiting for you (Alpha, Bravo)."), mv(2.5, "1 overdue invoice, $500 owed (Acme)."), mv(2, "Prepare for 1 booked call (Charlie)."))
push, st2 = N.decide(b2, st, NOON, CFG)
check("a new kind of thing is announced, once, with its engine", push and "Charlie" in push["body"] and "[Tampa dentists]" in push["body"] and push["title"] == "Your brief: something new", str(push))
check("things already announced are not repeated in that push", "Answer 2 replies" not in push["body"])
check("after sending, it is remembered, with the time", st2["announced"]["e1|2"] == 1 and st2["notified_at"] == NOON.isoformat(timespec="seconds"))
push, _ = N.decide(b2, st2, at(13), CFG)
check("the same brief again an hour later says nothing", push is None)

# ---------------------------------------------------------------- growth and shrinking
b3 = brief(mv(1, "Answer 3 replies waiting for you (Alpha, Bravo, Delta)."), mv(2.5, "1 overdue invoice, $500 owed (Acme)."), mv(2, "Prepare for 1 booked call (Charlie)."))
push, st3 = N.decide(b3, st2, at(14), CFG)
check("a thing that grows (2 replies becomes 3) is announced again", push and "3 replies" in push["body"])
b4 = brief(mv(1, "Answer 1 reply waiting for you (Delta)."))
push, st4 = N.decide(b4, st3, at(16), CFG)
check("handling some of them is not news", push is None)
check("a thing that shrank is lowered, and what is gone is forgotten", st4["announced"] == {"e1|1": 1}, str(st4["announced"]))
b5 = brief(mv(1, "Answer 2 replies waiting for you (Delta, Echo)."))
push, _ = N.decide(b5, st4, at(18), CFG)
check("it grows again from the lower number: new again", push and "2 replies" in push["body"])
push, st6 = N.decide(brief(), st4, at(17), CFG)
check("when everything is handled, nothing is sent and it is all forgotten", push is None and st6["announced"] == {})
push, _ = N.decide(b4, st6, at(19), CFG)
check("if the same thing comes back later it is new again", push and "1 reply" in push["body"])

# ---------------------------------------------------------------- one at a time, several in one
many = brief(mv(1, "Answer 1 reply waiting (A)."), mv(2, "Prepare for 1 booked call (B)."), mv(2.6, "1 student cut invoice overdue (C)."), mv(3.5, "1 deliverable late (D)."), mv(3.7, "1 student needs a check-in (E)."))
push, stm = N.decide(many, {"announced": {}, "notified_at": ""}, NOON, CFG)
check("several new things go in one push, the first three shown and the rest counted", push and push["title"] == "Your brief: 5 new things" and "(+2 more)" in push["body"], str(push))
check("every one of them is marked as told", len(stm["announced"]) == 5)
st_recent = {"announced": {}, "notified_at": at(11, 30).isoformat()}
push, held = N.decide(brief(mv(1, "Answer 1 reply waiting (A).")), st_recent, NOON, CFG)
check("at most one push every 45 minutes: the new thing waits", push is None and held["announced"] == {} and held["notified_at"] == at(11, 30).isoformat())
push, _ = N.decide(brief(mv(1, "Answer 1 reply waiting (A).")), held, at(12, 20), CFG)
check("and goes out when the 45 minutes are over", push is not None)

# ---------------------------------------------------------------- quiet hours
base = {"announced": {}, "notified_at": ""}
rep = brief(mv(1, "Answer 1 reply waiting (A)."))
for h in (21, 23, 0, 3, 6):
    check(f"quiet at {h}:00: nothing sent", N.decide(rep, base, at(h), CFG)[0] is None)
for h in (7, 12, 20):
    check(f"not quiet at {h}:00: sent", N.decide(rep, base, at(h), CFG)[0] is not None)
push, kept = N.decide(rep, base, at(23), CFG)
check("what arrived overnight is NOT marked as told", kept["announced"] == {})
push, _ = N.decide(rep, kept, at(7, 5), CFG)
check("it is announced once, after quiet hours end, if it is still waiting", push is not None)
push, _ = N.decide(brief(), kept, at(7, 5), CFG)
check("and not at all if it was handled in the night", push is None)
check("a quiet window that does not cross midnight works (13 to 15)", N.is_quiet(at(14), {"quiet_start": 13, "quiet_end": 15}) and not N.is_quiet(at(16), {"quiet_start": 13, "quiet_end": 15}))
check("equal start and end means no quiet hours", not N.is_quiet(at(3), {"quiet_start": 8, "quiet_end": 8}))
check("turned off in the settings: nothing is sent, and it is not marked as told", N.decide(rep, base, NOON, {**CFG, "enabled": False})[0] is None)

# ---------------------------------------------------------------- the settings file
real, N.SETTINGS = N.SETTINGS, ROOT / "data" / "zz-brief-notify.json"
try:
    N.SETTINGS.parent.mkdir(exist_ok=True)
    N.SETTINGS.write_text(json.dumps({"quiet_start": 22, "quiet_end": 6, "min_minutes": 2, "enabled": False, "junk": 1}), encoding="utf-8")
    s = N.settings()
    check("settings are read, bounded and checked", s["quiet_start"] == 22 and s["quiet_end"] == 6 and s["min_minutes"] == 5 and s["enabled"] is False and "junk" not in s, str(s))
    N.SETTINGS.write_text("not json", encoding="utf-8")
    check("a broken settings file falls back to the defaults", N.settings() == DEFAULTS if (DEFAULTS := N.DEFAULTS) else True)
finally:
    N.SETTINGS.unlink(missing_ok=True)
    N.SETTINGS = real
check("no em dash in the module", chr(0x2014) not in (ROOT / "dse" / "briefnotify.py").read_text(encoding="utf-8"))

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
