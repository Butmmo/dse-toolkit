"""Tests for Presence's HQ tools: research for content (insights), and later graphics and video.   python tests/test_presence.py
Nothing real is contacted; no business name may ever appear in the result."""
import csv
import datetime as dt
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import presence as P  # noqa: E402

fails = []
DASH = chr(0x2014)


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


TODAY = dt.date(2026, 11, 18)


def row(i, **o):
    return {"business": f"Secret Dental {i}", "city": "Orlando", "state": "FL", "website": f"https://secret{i}.com", "phone": "(407) 555-01%02d" % i, "email": f"owner{i}@secret{i}.com",
            "instagram": "https://instagram.com/x" if i % 2 else "", "facebook": "https://facebook.com/y", "category": "Dentists", "search_city": "Orlando FL",
            "online_booking": "yes" if i % 3 else "no", "text_chat": "no", "review_link": "yes", "reviews_shown": "yes", "fresh_site": "no (c 2024)" if i == 1 else "yes",
            "gaps_found": "No text or chat; Old copyright" if i == 1 else "No text or chat", **o}


rows = [row(i) for i in range(1, 13)]
r = P.insights(rows, "dentist-orlando", TODAY)
probs = {p["key"]: (p["count"], p["of"]) for p in r["problems"]}
check("the count and the market are read from the list", r["n"] == 12 and r["category"] == "Dentists" and r["city"] == "Orlando FL" and r["made"] == "2026-11-18" and r["kind"] == "presence-insights")
check("the yes or no checks are counted as 'no' out of the rows that have them", probs["text_chat"] == (12, 12) and probs["online_booking"] == (4, 12) and probs["fresh_site"] == (1, 12))
check("social platforms are counted from the links the websites show", r["social"]["instagram"] == 6 and r["social"]["facebook"] == 12)
check("every idea carries its real numbers and says where they came from", bool(r["ideas"]) and all(i["facts"] and all(re.search(r"\d+ of \d+", f["text"]) and "HQ list of 12 dentists in Orlando FL" in f["source"] for f in i["facts"]) for i in r["ideas"]))
check("the strongest finding becomes the first idea, and the ideas use the market's own words", "text" in r["ideas"][0]["topic"].lower() and "dentists" in r["ideas"][0]["topic"])
check("ideas have a pillar from the four Presence pillars and a unique id", all(i["pillar"] in ("teach", "help", "ecosystem", "proof") for i in r["ideas"]) and len({i["id"] for i in r["ideas"]}) == len(r["ideas"]) and len(r["ideas"]) <= 8)
check("the result is counts only: no business name, website, phone or email anywhere in it", not any(x in json.dumps(r) for x in ("Secret Dental", "secret1.com", "owner1", "555-01", "@")))
check("a big enough sample is not called small, a small one is, in plain words", r["sample_note"] == "" and "Small sample" in P.insights(rows[:5], "x", TODAY)["sample_note"])
q = P.insights([{"business": "A", "website": "https://a.com", "category": "Plumbers", "instagram": "https://i", "facebook": ""}] * 3, "p", TODAY)
check("a list with no problem checks still gives platforms and an idea about where the market is", q["problems"] == [] and bool(q["ideas"]) and q["ideas"][0]["pillar"] == "ecosystem")
check("a market where few use Instagram gets an idea about being early there", any("no Instagram presence" in i["topic"] for i in P.insights([{"category": "Roofers", "facebook": "https://f", "instagram": ""}] * 6, "r", TODAY)["ideas"]))
check("an empty list is handled", P.insights([], "e", TODAY)["n"] == 0 and P.insights([], "e", TODAY)["ideas"] == [])
md = P.to_markdown(r)
check("the readable summary names the source and every finding", "Source: HQ list of 12 dentists" in md and "12 of 12 cannot be texted" in md and "## Content ideas" in md and "Secret" not in md)

tmp = Path(tempfile.mkdtemp())
try:
    P.LISTS = tmp
    f = tmp / "dentist-test.csv"
    with open(f, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    out = []
    code = P.run_insights(str(f), out=out.append)
    j = f.with_name("dentist-test-insights.json")
    check("running it on a file writes the json and the readable summary next to the list", code == 0 and j.exists() and j.with_suffix(".md").exists() and json.loads(j.read_text(encoding="utf-8"))["n"] == 12)
    check("it says counts only and shows the ideas", any("counts only" in x for x in out) and any("teach" in x for x in out))
    check("a missing file is said plainly", P.run_insights("nope.csv", out=out.append) == 1 and any("could not find" in x for x in out))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
t = cat["tools"]["dse.presence_insights"]
check("the tool is in the catalog, takes a list, uploads its two result files and says it is counts only", t["fields"][0]["type"] == "file" and len(t["outputs"]) == 2 and all(o["upload"] for o in t["outputs"]) and "counts only" in t["help"])
check("dse.py knows the presence command", "presence.cli(a.rest)" in (ROOT / "dse.py").read_text(encoding="utf-8"))
src = (ROOT / "dse" / "presence.py").read_text(encoding="utf-8")
check("it reads files and never contacts anything: no network, no sending", "requests" not in src and "urllib" not in src and "smtplib" not in src and "socket" not in src)
check("no em dash", DASH not in src + Path(__file__).read_text(encoding="utf-8"))
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
