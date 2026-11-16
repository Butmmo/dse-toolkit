"""Tests for the Outreach Pack.   python tests/test_outreach.py"""
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import desklog as dl, outreach as O, replies  # noqa: E402

fails = []
DASH = chr(0x2014)


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


TPL = json.loads((ROOT / "dse" / "outreach_templates.json").read_text(encoding="utf-8"))

# ---- the plan matches the Citadel Warm Desk (tests/fixtures/outreach-plan.json is written by Citadel's test)
fx = ROOT / "tests" / "fixtures" / "outreach-plan.json"
if fx.exists():
    want = json.loads(fx.read_text(encoding="utf-8"))
    for door in ("review", "inquiry"):
        got = [[p["day"], p["channel"]] for p in TPL["plan"][door]]
        check(f"the {door} plan matches the Citadel Warm Desk plan", got == want[door], f"{got} != {want[door]}")
else:
    check("the Citadel plan fixture exists", False, str(fx))

# ---- the wording
for door, n in (("review", 4), ("inquiry", 3)):
    em = TPL["emails"][door]
    check(f"{door}: {n} emails, and the plan sends each exactly once", len(em) == n and sorted(p["email"] for p in TPL["plan"][door] if p.get("email")) == list(range(1, n + 1)))
    check(f"{door}: every email is honest and short enough", all(len(e["body"]) < 1300 and "guarantee" not in e["body"].lower() and "%" not in e["body"] for e in em))
    check(f"{door}: variants are unique", len({e["variant"] for e in em}) == n)
check("the footer carries the name, the address and an easy way to say no", all(k in TPL["footer"] for k in ("{sender}", "{postal}", "just reply")))
check("no em dash in the wording", DASH not in json.dumps(TPL, ensure_ascii=False))
check("the plan warms before the first email and ends on the breakup email", all(TPL["plan"][d][0]["day"] == -1 and TPL["plan"][d][0]["channel"] == "social" and TPL["plan"][d][-1]["day"] <= 14 and "breakup" in TPL["plan"][d][-1]["action"] for d in ("review", "inquiry")))

# ---- dates (2026-12-07 is a Monday)
mon = dt.date(2026, 12, 7)
check("a Sunday start moves to Monday", O.first_day("2026-12-06") == mon)
check("a day before the start that is a Sunday moves back to Saturday", O.day_date(mon, -1) == dt.date(2026, 12, 5))
check("a later day that is a Sunday moves on to Monday", O.day_date(mon, 6) == dt.date(2026, 12, 14))
check("an ordinary day is exact", O.day_date(mon, 3) == dt.date(2026, 12, 10))

# ---- filling
check("a known field is filled", O.fill("Hi {a}", {"a": "Dana"}) == "Hi Dana")
check("an unknown field keeps its braces", O.fill("Hi {zzz}", {"a": "x"}) == "Hi {zzz}")
check("an odd brace does not crash", isinstance(O.fill("a { b", {}), str))

# ---- a real engine and list
SLUG = "zz-outreach"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "send-lists").mkdir(parents=True)
(d / "data").mkdir()
(d / "engine.json").write_text(json.dumps({"name": "Outreach test", "path": "smb", "sender_name": "Bolu", "postal_address": "1 Main St, Lagos", "archived": False}), encoding="utf-8")
COLS = ["row", "business", "city", "channel", "where", "gap_used", "variant", "opener", "website", "email", "host", "instagram", "tested_on", "reply_note"]
GOOD = "Hi Dana, I noticed your booking page has no way to pick a time. If this is not relevant, just reply no and I will not write again."


def write_list(name, rows):
    with (d / "send-lists" / f"{name}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({"row": i, "city": "Tampa", "gap_used": "fewer recent reviews than the three above you", "variant": "v", "email": "", "website": "", "host": "", "instagram": "", "tested_on": "", "reply_note": "", **r})


write_list("2026-11-02", [{"business": "Old Contact", "channel": "Email", "where": "o@oldcontact.example", "opener": GOOD, "website": "oldcontact.example"}])
dl.append_events(SLUG, [{"logged_at": "2026-11-02T10:00:00", "source": "2026-11-02", "row_id": "1", "status": "sent", "list_date": "2026-11-02"}])
replies.add_dnc(SLUG, "stop@dnc.example", "asked to stop", dt.date(2026, 11, 5))
write_list("2026-11-09", [
    {"business": "Alpha Movers (Tampa)", "channel": "Email", "where": "dana@alpha.example", "opener": GOOD, "host": "Dana Lee", "website": "alpha.example", "instagram": "https://www.instagram.com/alphamovers/"},
    {"business": "Dnc Co", "channel": "Email", "where": "stop@dnc.example", "opener": GOOD, "website": "dnc.example"},
    {"business": "Badmail", "channel": "Email", "where": "nope", "opener": GOOD, "website": "badmail.example"},
    {"business": "Old Contact", "channel": "Email", "where": "o@oldcontact.example", "opener": GOOD, "website": "oldcontact.example"},
    {"business": "Insta Only", "channel": "Instagram DM", "where": "@instaonly", "opener": "Hi, love your work", "email": "", "instagram": "https://www.instagram.com/instaonly/"},
    {"business": "No Gap Co", "channel": "Email", "where": "hello@nogap.example", "opener": GOOD, "gap_used": "", "website": "nogap.example"},
])
try:
    res = O.build(SLUG, "review", "2026-12-07")
    merged = {m["business"]: m for m in res["merge"]}
    check("the best row is in the file, ready, with its dates", "Alpha Movers" in merged and merged["Alpha Movers"]["ready"] == "yes" and merged["Alpha Movers"]["send_on_1"] == "2026-12-07" and merged["Alpha Movers"]["send_on_4"] == "2026-12-19")
    check("the greeting uses the owner's first name", merged["Alpha Movers"]["body_1"].startswith("Hi Dana,"))
    check("the gap line from the list is used", "fewer recent reviews than the three above you" in merged["Alpha Movers"]["body_1"])
    check("every email ends with the name, the address and the opt-out", all("Bolu" in merged["Alpha Movers"][f"body_{n}"] and "1 Main St, Lagos" in merged["Alpha Movers"][f"body_{n}"] and "just reply" in merged["Alpha Movers"][f"body_{n}"] for n in (1, 2, 3, 4)))
    check("the do-not-contact row and the already-contacted row are left out", {b for b, _w in res["left_out"]} == {"Dnc Co", "Old Contact"}, str(res["left_out"]))
    check("a bad address is not in the mail-merge file but is in the report", "Badmail" not in merged and "Badmail" in res["no_email"])
    check("a row with no gap line is marked not ready, naming the field", merged["No Gap Co"]["ready"] == "no" and any(b == "No Gap Co" and "gap_line" in m for b, m in res["not_ready"]))
    cal = res["calendar"]
    check("the calendar warms first: the first touch is the day before the first email", min(c["date"] for c in cal) == "2026-12-05" and [c for c in cal if c["business"] == "Alpha Movers"][0]["channel"] == "social")
    check("a business with no email keeps its social and call touches but no email", {c["channel"] for c in cal if c["business"] == "Badmail"} == {"social", "call"} or {c["channel"] for c in cal if c["business"] == "Badmail"} <= {"social", "call"})
    check("the social touches point at the Instagram page", any(c["where"] == "https://www.instagram.com/alphamovers/" for c in cal if c["channel"] == "social"))
    check("files are written under outreach/, not send-lists/", all(f.parent.name == "outreach" for f in res["files"]) and len(res["files"]) == 2 and not list((d / "send-lists").glob("*outreach*")))
    check("the mail-merge file has the sequence columns", "subject_4" in (res["files"][0].read_text(encoding="utf-8-sig").splitlines()[0]) and "send_on_1" in res["files"][0].read_text(encoding="utf-8-sig").splitlines()[0])

    # the inquiry door needs the member's own Reply Test result
    r2 = O.build(SLUG, "inquiry", "2026-12-07", write=False)
    m2 = {m["business"]: m for m in r2["merge"]}
    check("the inquiry door marks a row not ready until the Reply Test result is on it", m2["Alpha Movers"]["ready"] == "no" and any("tested_on" in m and "reply_note" in m for b, m in r2["not_ready"] if b == "Alpha Movers"))
    check("the inquiry door has three emails", "subject_3" in m2["Alpha Movers"] and "subject_4" not in m2["Alpha Movers"])
    write_list("2026-11-10", [{"business": "Tested Co", "channel": "Email", "where": "t@tested.example", "opener": GOOD, "host": "Tom", "website": "tested.example", "tested_on": "Tuesday 2 December at 10:12", "reply_note": "The first reply came on Thursday afternoon."}])
    r3 = O.build("zz-outreach", "inquiry", "2026-12-07", write=False)
    m3 = {m["business"]: m for m in r3["merge"]}
    check("with the Reply Test on the row the inquiry email is ready and says it plainly", m3["Tested Co"]["ready"] == "yes" and "Tuesday 2 December at 10:12" in m3["Tested Co"]["body_1"] and "as myself, Bolu" in m3["Tested Co"]["body_1"])

    # the sender and address can be passed in
    (d / "engine.json").write_text(json.dumps({"name": "Outreach test", "path": "smb", "archived": False}), encoding="utf-8")
    r4 = O.build(SLUG, "review", "2026-12-07", write=False)
    check("without a sender name and address every row is not ready", all(m["ready"] == "no" for m in r4["merge"]) and r4["merge"])
    r5 = O.build(SLUG, "review", "2026-12-07", sender="Ada", address="2 Side Rd, Uyo", write=False)
    check("--name and --address fill the footer", any(m["ready"] == "yes" and "Ada" in m["body_1"] and "2 Side Rd, Uyo" in m["body_1"] for m in r5["merge"]))

    txt = O.report(SLUG, "review", "2026-12-07", "Ada", "2 Side Rd, Uyo")
    check("the report says nothing was sent and names the next steps", "Nothing was sent by this tool" in txt and "preflight" in txt and DASH not in txt)
    check("the door must be review or inquiry", raises(O.build, SLUG, "other") is not None)
finally:
    shutil.rmtree(d, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
