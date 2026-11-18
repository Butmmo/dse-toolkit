"""Tests for the research run (18 Nov 2026): one shared page cache, and one command that finds, checks, enriches and keeps every lead in a database.   python tests/test_research.py"""
import csv
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import common as CM, enrich as EN, pagecache as PC, places as P, research as R, tech as T  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


TMP = Path(tempfile.mkdtemp(prefix="zz-research-"))
P.DATA = P.OV.DATA = TMP
CM.LISTS = TMP / "lists"
EN.LISTS = TMP / "lists"
PC.DATA = TMP            # the default cache folder, so a test never touches the real one

HOME = "<html><head><title>Stump Grinding Leeds</title></head><body>" + "Family tree firm serving the area for many years, honest advice. " * 12 + "<script src='https://www.googletagmanager.com/gtag/js'></script></body></html>"
calls = []


class Resp:
    def __init__(self, status=200, text=HOME, url="", ctype="text/html"):
        self.status_code, self.text, self.url = status, text, url
        self.headers = PC.requests.structures.CaseInsensitiveDict({"Content-Type": ctype, "Server": "nginx"})


def fake_get(url, **k):
    calls.append(url)
    if "boom" in url:
        raise OSError("no route")
    if "flaky" in url:
        return Resp(503, "", url)
    if "robots" in url:
        return Resp(404, "", url)
    if "data.json" in url:
        return Resp(200, "{}", url, "application/octet-stream")
    return Resp(200, HOME, url)


PC.requests.get = fake_get          # the same module the other files use, so this fakes every download

# ---------------------------------------------------------------- the page cache
calls.clear()
PC.get("https://a.example/")
PC.get("https://a.example/")
check("off by default: a second download really downloads again (single commands behave as before)", len(calls) == 2, str(calls))

calls.clear()
with PC.active(TMP / "pc") as d:
    r1 = PC.get("https://a.example/")
    r2 = PC.get("https://a.example/")
    PC.get("https://b.example/")
    check("on: the same page is downloaded once, however many steps read it", calls == ["https://a.example/", "https://b.example/"], str(calls))
    check("a cached page keeps status, final address, text and case-insensitive headers", r2.status_code == 200 and r2.text == r1.text and r2.headers.get("server") == "nginx" and r2.url == "https://a.example/")
    check("hits and misses are counted", PC.stats() == {"hits": 1, "misses": 2}, str(PC.stats()))
    check("the page is kept on disk", len(list(Path(d).glob("*.json"))) == 2)
calls.clear()
with PC.active(TMP / "pc"):
    PC.get("https://a.example/")
check("the next run reads it from disk, with no download", calls == [], str(calls))
check("the cache is off again afterwards", not PC._state["on"])

calls.clear()
with PC.active(TMP / "pc2", ttl_days=0.00001):
    PC.get("https://a.example/")
    time.sleep(1.2)
    PC._mem.clear()
    PC.get("https://a.example/")
check("an old page (past its days) is downloaded again", len(calls) == 2, str(calls))

calls.clear()
with PC.active(TMP / "pc3"):
    PC.get("https://flaky.example/")
    PC.get("https://flaky.example/")
    err = None
    try:
        PC.get("https://boom.example/")
    except OSError as e:
        err = e
    try:
        PC.get("https://boom.example/")
    except OSError:
        pass
    j = PC.get("https://x.example/data.json")
check("a temporary failure (503) is not remembered", calls.count("https://flaky.example/") == 2, str(calls))
check("a network error still raises and is not remembered", err is not None and calls.count("https://boom.example/") == 2)
check("a file that is not a web page is kept without its body", j.text == "", repr(j.text))

# ---------------------------------------------------------------- every step shares the one page
calls.clear()
with PC.active(TMP / "pc4"):
    live = P.site_live("https://share.example", "stump|grind")
    prof_cols, _ = T.scan("https://share.example", render=False)
    CM.fetch("https://share.example")
    robots = [c for c in calls if "robots" in c]
page_calls = [c for c in calls if c.rstrip("/").endswith("share.example")]
check("the website check, the technology scan and the plain fetch read one download of the page", len(page_calls) == 1, str(calls))
check("and they still give their own answers", live == "title" and prof_cols["tech_status"] == "ok", f"{live} {prof_cols.get('tech_status')}")

# ---------------------------------------------------------------- the lead database
db = TMP / "leads.sqlite"
con = R.connect(db)
check("a lead is keyed on its website's domain", R.lead_key({"website": "https://www.Acme-Trees.co.uk/about", "business": "x"}) == "acme-trees.co.uk")
check("with no website it is keyed on name and city", R.lead_key({"website": "", "business": "Joe's Trees", "city": "Leeds"}) == "joe-s-trees|leeds")
check("a row with neither website nor name is skipped", R.lead_key({"website": "", "business": ""}) == "")
rows1 = [{"business": "A Trees", "website": "https://a-trees.example", "city": "Leeds", "lead_score": "70", "tech_gap_count": "3", "niche_match": "title"},
         {"business": "B Trees", "website": "", "city": "Leeds", "lead_score": "", "niche_match": ""}]
check("first save: all new", R.save_leads(con, rows1, "Stump grinding", "GB", "2026-11-18") == (2, 0))
rows2 = [dict(rows1[0], lead_score="80"), {"business": "C Trees", "website": "https://c-trees.example", "city": "Hull", "lead_score": "50"}]
check("second save: one seen before, one new", R.save_leads(con, rows2, "Stump grinding", "GB", "2026-12-01") == (1, 1))
a = dict(con.execute("SELECT * FROM leads WHERE key='a-trees.example'").fetchone())
check("a seen-before lead keeps first_seen, gets last_seen and times_seen, and its newest score", a["first_seen"] == "2026-11-18" and a["last_seen"] == "2026-12-01" and a["times_seen"] == 2 and a["lead_score"] == 80, str(a))
check("known_keys lists every lead", R.known_keys(con) == {"a-trees.example", "b-trees|leeds", "c-trees.example"}, str(R.known_keys(con)))
con.close()
check("leads: best score first, with the filter", R.leads(min_score=60, db=db).splitlines()[1].lstrip().startswith("80") and "C Trees" not in R.leads(min_score=60, db=db))
out_csv = TMP / "top.csv"
R.leads(kind="stump", csv_out=str(out_csv), db=db)
check("leads can be saved to a CSV", len(list(csv.DictReader(open(out_csv, encoding="utf-8-sig")))) == 3)
check("history says when there are no runs", "No research runs yet" in R.history(TMP / "empty.sqlite"))

# ---------------------------------------------------------------- a whole research run, offline
import duckdb  # noqa: E402

COLS = "fsq_place_id,name,latitude,longitude,address,locality,region,postcode,tel,website,email,facebook_id,instagram,fsq_category_labels,date_refreshed"
vals = ",\n".join(f"('p{i}','Tree Co {i}',53.80,-1.55,'1 St','Leeds','','X1','+44','https://site{i}.example',NULL,NULL,NULL,['tree service'],DATE '2026-01-01')" for i in range(4))
duckdb.connect().sql(f"COPY (SELECT * REPLACE (latitude::DOUBLE AS latitude, longitude::DOUBLE AS longitude) FROM (VALUES {vals}) t({COLS})) TO '{(TMP / 'places-gb-stump-grinding.parquet').as_posix()}' (FORMAT parquet)")
P.geocode = lambda place, country="US": (53.8, -1.55)
calls.clear()
db2 = TMP / "run.sqlite"
enriched_for = []


def fake_enrich(src, icp="", engine="", max_rows=100, **k):
    rows = list(csv.DictReader(open(src, encoding="utf-8-sig")))
    enriched_for.append(len(rows))
    out = TMP / "lists" / "enriched.csv"
    CM.write_csv(out, [dict(r, best_email="hi@" + r["website"].split("//")[1], lead_score=str(60 + i)) for i, r in enumerate(rows)])
    return "Saved: " + str(out.relative_to(TMP)).replace("\\", "/")


EN.enrich_file = fake_enrich
R.ROOT = TMP
final = R.run("stump grinding", "Leeds", country="GB", db=db2, today="2026-11-18")
rows = list(csv.DictReader(open(final, encoding="utf-8-sig")))
check("a run gives one combined list with the tech columns, the enrichment and the evidence", len(rows) == 4 and {"tech_status", "lead_score", "best_email", "niche_match"} <= set(rows[0]), str(rows[0].keys() if rows else ""))
check("each site's home page was downloaded once for the whole run (find, tech and enrich share it)", all(calls.count(f"https://site{i}.example") == 1 for i in range(4)), str(calls))
check("the leads are in the database with the run recorded", len(R.known_keys(R.connect(db2))) == 4 and "4 leads, 4 new, 0 seen before" in R.history(db2), R.history(db2))
n_before = len(calls)
final2 = R.run("stump grinding", "Leeds", country="GB", db=db2, today="2026-11-19")
check("a second run reads every page from the cache on disk (nothing downloaded again)", len(calls) == n_before, str(calls[n_before:]))
check("and the same leads are 'seen before', not new", "4 leads, 0 new, 4 seen before" in R.history(db2), R.history(db2))
enriched_for.clear()
R.run("stump grinding", "Leeds", country="GB", db=db2, new_only=True, today="2026-11-20")
check("--new-only drops leads already in the database, so nothing is checked or enriched again", enriched_for == [], str(enriched_for))
seen_max = []
real_tech = T.tech_file
T.tech_file = lambda src, max_rows=100, **k: (seen_max.append(max_rows), real_tech(src, max_rows=max_rows, **k))[1]
R.run("stump grinding", "Leeds", country="GB", cap=250, db=TMP / "run4.sqlite", enrich=False, today="2026-11-18")
T.tech_file = real_tech
check("every lead found is checked: the tech and enrich limit is never below how many leads were asked for", seen_max == [250], str(seen_max))
enriched_for.clear()
R.run("stump grinding", "Leeds", country="GB", db=TMP / "run3.sqlite", enrich=False, today="2026-11-18")
check("--no-enrich skips the enrich step", enriched_for == [])

sys.exit(1 if fails else 0)
