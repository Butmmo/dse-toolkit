"""Scenario tests for follow-ups, outcomes and the Send Desk mapping, using made-up engines (removed afterwards).

    python tests/test_member_desk.py

Dates are fixed so the checks never depend on today: week of Mon 2 Nov 2026 (first messages) and Mon 9 Nov (follow-ups).
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bridge"))
from dse import desklog as dl, followups as fu, outcomes as oc  # noqa: E402
from dse.common import write_csv  # noqa: E402

SLUG, SLUG2 = "zz-test-fu", "zz-test-out"
fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def make_engine(slug):
    d = ROOT / "engines" / slug
    shutil.rmtree(d, ignore_errors=True)
    (d / "send-lists").mkdir(parents=True)
    (d / "data").mkdir()
    (d / "engine.json").write_text(json.dumps({"name": slug, "path": "smb", "sender_name": "Bolu", "brand_name": "Test Co", "archived": False}), encoding="utf-8")
    return d


def row(n, name, channel, **kw):
    base = {"row": n, "business": name, "city": "Tampa", "channel": channel, "where": kw.pop("where", ""), "gap_used": "there's no online booking",
            "variant": "smb-v1", "opener": "Hi", "website": f"https://{name.lower().replace(' ', '')}.example.com", "email": "", "instagram": "", "facebook": ""}
    base.update(kw)
    return base


def tap(slug, source, row_id, status, when, **kw):
    dl.append_events(slug, [{"logged_at": when, "source": source, "row_id": str(row_id), "status": status, "list_date": source[:10], **kw}])


try:
    make_engine(SLUG)
    L = "2026-11-02"
    rows = [
        row(1, "Alpha Dental", "Email", where="a@alpha.example.com", email="a@alpha.example.com"),
        row(2, "Bravo Dental", "Email", where="b@bravo.example.com", email="b@bravo.example.com"),
        row(3, "Charlie Dental", "Email", where="c@charlie.example.com", email="c@charlie.example.com"),
        row(4, "Delta Dental", "Email", where="d@delta.example.com", email="d@delta.example.com"),
        row(5, "Echo Dental", "Instagram DM", where="@echodental", instagram="@echodental", email="e@echo.example.com"),
        row(6, "Foxtrot Dental", "Instagram DM", where="", email="f@fox.example.com"),
        row(7, "Golf Dental", "Email", where="g@golf.example.com", email="g@golf.example.com"),
        row(8, "Hotel Dental", "Email", where="h@hotel.example.com", email="h@hotel.example.com"),
        row(9, "India Dental", "Facebook message", where="facebook.com/india", facebook="facebook.com/india"),
        row(10, "Juliet Dental", "Website form", where="https://juliet.example.com"),
    ]
    write_csv(ROOT / "engines" / SLUG / "send-lists" / f"{L}.csv", rows)
    # taps
    for i in (1, 3, 5, 6, 8, 9, 10):
        tap(SLUG, L, i, "sent", "2026-11-02T10:00:00")
    tap(SLUG, L, 2, "sent", "2026-11-07T10:00:00")                       # sent only 2 days before the plan day: not due
    tap(SLUG, L, 3, "replied", "2026-11-04T09:00:00", reply="yes please")  # replied: finished
    tap(SLUG, L, 4, "skipped", "2026-11-02T10:05:00")                      # skipped: finished
    tap(SLUG, L, 8, "replied", "2026-11-03T09:00:00", category="out of office", reply="I am out of office")  # does not stop
    # row 7 never marked: reported, never followed up

    res = fu.plan(SLUG, start="2026-11-09", days=1, write=True)
    day = res["2026-11-09"]
    by = {r["business"]: r for r in day}
    check("due: email sent 7 days ago gets touch 2", "Alpha Dental" in by and by["Alpha Dental"]["touch"] == 2)
    check("not due yet: sent 2 days ago", "Bravo Dental" not in by)
    check("replied thread stops", "Charlie Dental" not in by)
    check("skipped first message stops", "Delta Dental" not in by)
    check("out-of-office reply does not stop the thread", "Hotel Dental" in by)
    check("Instagram DM with a handle: touch 2 is a public COMMENT, never a second DM",
          by.get("Echo Dental", {}).get("channel") == "Instagram comment" and "newest post" in by["Echo Dental"]["opener"])
    check("Instagram DM with no usable handle: bridge note by email, not a DM",
          by.get("Foxtrot Dental", {}).get("channel") == "Email" and by["Foxtrot Dental"]["variant"] == "fu3-bridge-v1")
    check("Facebook message due after 4 days", "India Dental" in by)
    check("website form due after 5 days", "Juliet Dental" in by)
    check("never-marked row is not followed up", "Golf Dental" not in by)
    check("follow-up wording has an opt-out and no link", all(("no thanks" in r["opener"].lower() or "say so" in r["opener"].lower() or "not follow" in r["opener"].lower()
                                                               or "p.s." in r["opener"].lower()) and "http" not in r["opener"] for r in day))
    check("follow-up list file written", (ROOT / "engines" / SLUG / "send-lists" / "2026-11-09-followups.csv").exists())

    A = fu.analyse(SLUG)
    check("unmarked first messages are reported", any(r["business"] == "Golf Dental" for r in A["unmarked"]))

    # Sunday is skipped
    sun = fu.plan(SLUG, start="2026-11-08", days=1, write=False)
    check("Sunday is skipped (plans Monday)", list(sun) == ["2026-11-09"])

    # re-running rebuilds the same untouched list (no duplicates)
    again = fu.plan(SLUG, start="2026-11-09", days=1, write=True)["2026-11-09"]
    check("re-planning an untouched day gives the same list", sorted(r["business"] for r in again) == sorted(by))

    # touch 3
    fs = "2026-11-09-followups"
    ids = {r["business"]: r["row"] for r in day}
    tap(SLUG, fs, ids["Alpha Dental"], "sent", "2026-11-09T10:00:00")
    tap(SLUG, fs, ids["Echo Dental"], "sent", "2026-11-09T10:00:00")
    tap(SLUG, fs, ids["Foxtrot Dental"], "sent", "2026-11-09T10:00:00")
    d10 = fu.plan(SLUG, start="2026-11-10", days=1, write=True)["2026-11-10"]
    b10 = {r["business"]: r for r in d10}
    check("touch 3 follows touch 2 (email: last note)", b10.get("Alpha Dental", {}).get("touch") == 3 and b10["Alpha Dental"]["variant"] == "fu3-close-v1")
    check("after the Instagram comment, touch 3 is the bridge note", b10.get("Echo Dental", {}).get("variant") == "fu3-bridge-v1")
    check("the bridge note that already went out ends the thread", "Foxtrot Dental" not in b10)
    left = fu.plan(SLUG, start="2026-11-09", days=1, write=True)
    check("a follow-up list you have tapped is left alone (not rewritten)", "2026-11-09" not in left)
    check("its rows are still there", len([r for r in dl.load_lists(SLUG) if r["_source"] == fs]) == len(day))

    # reply on a follow-up row stops the thread; after touch 3 sent nothing more
    tap(SLUG, fs, ids["India Dental"], "replied", "2026-11-09T12:00:00", reply="tell me more")
    ts = "2026-11-10-followups"
    tap(SLUG, ts, {r["business"]: r["row"] for r in d10}["Alpha Dental"], "sent", "2026-11-10T10:00:00")
    d11 = fu.plan(SLUG, start="2026-11-11", days=1, write=False)["2026-11-11"]
    names11 = {r["business"] for r in d11}
    check("a reply on a follow-up stops the thread", "India Dental" not in names11)
    check("nothing after touch 3", "Alpha Dental" not in names11)

    # outcomes: 30-send rule
    make_engine(SLUG2)
    L2 = "2026-11-02"
    rs, n = [], 0
    for ch, count, replies in (("Email", 35, 12), ("Facebook message", 35, 2), ("Website form", 10, 5)):
        for i in range(count):
            n += 1
            rs.append(row(n, f"{ch[:2]}Biz{i}", ch, where="x"))
    write_csv(ROOT / "engines" / SLUG2 / "send-lists" / f"{L2}.csv", rs)
    n = 0
    for ch, count, replies in (("Email", 35, 12), ("Facebook message", 35, 2), ("Website form", 10, 5)):
        for i in range(count):
            n += 1
            tap(SLUG2, L2, n, "sent", "2026-11-02T10:00:00")
            if i < replies:
                tap(SLUG2, L2, n, "replied", "2026-11-03T10:00:00")
    tap(SLUG2, L2, 1, "booked", "2026-11-04T10:00:00")
    tap(SLUG2, L2, 1, "won", "2026-11-05T10:00:00", value="500")
    s = oc.summary(SLUG2)
    check("funnel counts", s["sent"] == 80 and s["replied"] == 19 and s["won"] == 1 and s["value"] == 500, str(s))
    text = oc.report(SLUG2, write=False)
    check("calls a difference only between groups with 30+ sends", "Email gets replies" in text and "Facebook message" in text)
    check("does not judge the group with only 10 sends", "(too few to judge)" in text)
    check("money won is shown", "$500" in text)

    # desk mapping (no network)
    import desk_sync as ds
    import datetime as dt
    items = ds.build_items(dt.date(2026, 11, 3))
    keys = {i["key"] for i in items}
    check("desk rows are keyed engine|source|row", f"{SLUG}|{L}|1" in keys)
    check("an open reply stays on the desk outside the date window", any(i["status"] == "replied" for i in ds.build_items(dt.date(2026, 12, 20))))
finally:
    for s in (SLUG, SLUG2):
        shutil.rmtree(ROOT / "engines" / s, ignore_errors=True)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
