"""Scenario tests for the Daily Brief.   python tests/test_brief.py"""
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import brief as B, desklog as dl, engines  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def write_csv(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def row(n, name):
    return {"row": n, "business": name, "city": "Tampa", "channel": "Email", "where": f"{name.lower()}@x.example.com", "gap_used": "g", "variant": "smb-v1", "opener": "Hi",
            "website": f"https://{name.lower()}.example.com", "email": f"{name.lower()}@x.example.com", "instagram": "", "facebook": ""}


def tap(slug, source, row_id, status, day, **kw):
    dl.append_events(slug, [{"logged_at": f"{day}T10:00:00", "source": source, "row_id": str(row_id), "status": status, "list_date": source[:10], **kw}])


SLUG = "zz-brief"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "send-lists").mkdir(parents=True)
(d / "data").mkdir()
(d / "engine.json").write_text(json.dumps({"name": "Brief test", "path": "smb", "sender_name": "Bolu", "brand_name": "T Co", "archived": False}), encoding="utf-8")
today = dt.date.today()
iso = lambda n: (today - dt.timedelta(days=n)).isoformat()  # noqa: E731
brief_json, brief_md = B.BRIEF_JSON, B.BRIEF_MD
tmp = ROOT / "data" / "zz-brief-out"
B.BRIEF_JSON, B.BRIEF_MD = tmp / "brief.json", tmp / "brief.md"
B.DATA = tmp
try:
    mine = lambda b: [m for m in b["moves"] if m["engine"] == SLUG]  # noqa: E731
    b = B.build(today, top=8)
    m = mine(b)
    check("an empty engine: the move is to build a list, with the daily tool and the engine filled", m and "Nothing is going out" in m[0]["do"] and m[0]["tool"] == "dse.daily" and m[0]["values"] == {"engine": SLUG}, str(m))

    old = iso(10)
    write_csv(d / "send-lists" / f"{old}.csv", [row(i, n) for i, n in enumerate(["Alpha", "Bravo", "Charlie", "Delta"], 1)])
    tap(SLUG, old, 1, "sent", iso(9))                                            # follow-up due
    tap(SLUG, old, 2, "sent", iso(8)); tap(SLUG, old, 2, "replied", iso(7), reply="yes")     # a reply waiting
    tap(SLUG, old, 3, "sent", iso(8)); tap(SLUG, old, 3, "booked", iso(0))                  # a call booked today, no prep sheet
    b = B.build(today, top=8)
    m = mine(b)
    by = {x["tool"]: x for x in m}
    check("a reply waiting is the first move, with the reply tool and the engine", m[0]["rank"] == 1 and m[0]["tool"] == "dse.reply" and m[0]["values"] == {"engine": SLUG}, str(m[0]))
    check("a booked call without a prep sheet opens the prep tool with the engine, the list and the row already filled", "dse.call_prep" in by and by["dse.call_prep"]["values"] == {"engine": SLUG, "source": old, "row": "3"}, str(by.get("dse.call_prep")))
    check("follow-ups due open the follow-up tool", "dse.followups" in by and by["dse.followups"]["values"] == {"engine": SLUG})
    check("moves come in the review's fixed order, closest to money first", [x["rank"] for x in m] == sorted(x["rank"] for x in m))
    check("every move says how and where the number came from", all(x["how"] and x["source"] for x in m))
    top2 = B.build(today, top=2)
    full = B.build(today, top=8)
    check("the brief keeps only the first few and says how many are behind", len(top2["moves"]) == 2 and top2["more"] == len(full["moves"]) - 2 and top2["more"] > 0, str((len(top2["moves"]), top2["more"], len(full["moves"]))))
    check("the headline counts the things to do first", top2["headline"].startswith(str(len(top2["moves"]))), top2["headline"])
    check("each engine's standing is included", any(e["slug"] == SLUG and e["name"] == "Brief test" for e in b["engines"]))

    # unsent messages: the preflight tool is given the real list file, only if it exists
    write_csv(d / "send-lists" / f"{iso(0)}.csv", [row(9, "Golf")])
    b = B.build(today, top=8)
    pf = [x for x in mine(b) if x["tool"] == "dse.preflight"]
    check("unsent messages open Preflight with the list file that exists", pf and pf[0]["values"]["csv"] == f"engines/{SLUG}/send-lists/{iso(0)}.csv", str(pf))
    check("a move with no tool gives an empty tool, never a made-up one", B.action({"rank": 99}, {"slug": SLUG, "calls": [], "unsent": []}) == ("", {}, ""))

    # the files
    text = B.run(3, today)
    check("run writes the json and the readable brief", B.BRIEF_JSON.is_file() and B.BRIEF_MD.is_file() and "Your brief for" in text and json.loads(B.BRIEF_JSON.read_text(encoding="utf-8"))["date"] == today.isoformat())
    check("the readable brief says nothing is sent", "Nothing is sent or changed" in text)
    check("no em dash in the brief code or its output", chr(0x2014) not in text and chr(0x2014) not in (ROOT / "dse" / "brief.py").read_text(encoding="utf-8"))

    # the sync only sends what changed
    sys.path.insert(0, str(ROOT / "bridge"))
    import brief_sync as S  # noqa: E402
    b1 = B.build(today, top=5); b2 = dict(b1, made="later")
    check("the sync's change check ignores the time it was made", S.digest(b1) == S.digest(b2))
    tap(SLUG, old, 4, "sent", iso(0))
    check("but notices a different move", S.digest(B.build(today, top=5)) != S.digest(b1))
finally:
    shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
