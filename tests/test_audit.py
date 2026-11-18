"""Tests for the lead precision work (18 Nov 2026): directory pages are not a business's website, every lead says how clearly its site shows the trade, --strict, and the audit sheet and score.   python tests/test_audit.py"""
import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import audit as A, common as CM, places as P  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except (ValueError, SystemExit) as e:
        return str(e)
    return None


TMP = Path(tempfile.mkdtemp(prefix="zz-audit-"))
P.DATA = P.OV.DATA = TMP
CM.LISTS = TMP / "lists"

# ---------------------------------------------------------------- directories are not a business's own website
DIRS = ["https://www.yell.com/biz/noel-radford", "https://www.thomsonlocal.com/john-park", "https://www.ratedpeople.com/profile/m-and-h", "https://www.checkatrade.com/trades/x",
        "http://www.mybuilder.com/x", "https://www.trustatrader.com/x", "https://www.linkedin.com/company/a", "https://x.com/abc", "https://www.tripadvisor.co.uk/x", "https://www.gelbeseiten.de/x"]
OWN = ["https://barkandbite.co.uk", "https://www.taxcom.co.uk", "https://treedoctors-yorkshire.co.uk", "https://www.sexton-trees.com", "https://yellowstone-trees.co.uk", "https://xeno.co.uk"]
check("directory and social pages are not a business's website", all(P.NOT_A_SITE.search(u) for u in DIRS), str([u for u in DIRS if not P.NOT_A_SITE.search(u)]))
check("look-alike business names are kept (Bark & Bite is not bark.com, a tax firm is not x.com)", not any(P.NOT_A_SITE.search(u) for u in OWN), str([u for u in OWN if P.NOT_A_SITE.search(u)]))

# ---------------------------------------------------------------- site_live: how clearly the site says the trade
WORDS = "stump|grind"
filler = "Our family firm has served the area for many years and we pride ourselves on honest advice. " * 12


class Resp:
    def __init__(self, status, text, url="https://x.example/"):
        self.status_code, self.text, self.url, self.headers = status, text, url, {"content-type": "text/html"}


PAGES = {
    "title": Resp(200, f"<html><head><title>Stump Grinding in Leeds</title></head><body><p>{filler}</p></body></html>"),
    "heading": Resp(200, f"<html><head><title>Home</title></head><body><h1>Tree and stump removal</h1><p>{filler}</p></body></html>"),
    "meta": Resp(200, f"<html><head><title>Home</title><meta name=\"description\" content=\"Local stump grinding experts\"></head><body><p>{filler}</p></body></html>"),
    "body": Resp(200, f"<html><head><title>Home</title></head><body><p>{filler} We do stump work, stump grinding and stump removal.</p></body></html>"),
    "weak": Resp(200, f"<html><head><title>Home</title></head><body><p>{filler} We can also grind a stump.</p></body></html>"),
    "wrong": Resp(200, f"<html><head><title>Home</title></head><body><p>{filler}</p></body></html>"),
    "thin": Resp(200, "<html><head><title>Welcome</title></head><body><p>Coming soon. " + "page " * 90 + "</p></body></html>"),
    "parked": Resp(200, f"<html><head><title>TheAirportHotel.com for sale</title></head><body><p>Short page. {'x ' * 110}</p></body></html>"),
    "dead": Resp(404, ""),
    "blocked": Resp(403, ""),
    "forsale": Resp(200, "<html><body>This domain is for sale. " + "y " * 200 + "</body></html>"),
}
P.requests.get = lambda url, **k: PAGES[url.split("//")[1].split(".")[0]]
ev = {k: P.site_live(f"https://{k}.example", WORDS) for k in PAGES}
check("the trade in the page title is 'title'", ev["title"] == "title", str(ev))
check("the trade in a heading, or the description, is also 'title'", ev["heading"] == "title" and ev["meta"] == "title", str(ev))
check("the trade repeated in the page is 'body'", ev["body"] == "body", str(ev))
check("the trade mentioned once is 'weak'", ev["weak"] == "weak", str(ev))
check("a full page that never mentions the trade is rejected", ev["wrong"] == "", str(ev))
check("a page too short to tell is 'thin', not rejected", ev["thin"] == "thin", str(ev))
check("a parked domain with 'for sale' in its title is rejected", ev["parked"] == "" and ev["forsale"] == "", str(ev))
check("a dead site is rejected and a site that blocks scripts is 'blocked'", ev["dead"] == "" and ev["blocked"] == "blocked", str(ev))
check("with no words to look for the site is 'unchecked'", P.site_live("https://title.example", "") == "unchecked")
check("the page title is remembered for the audit sheet", P.SITE_TITLES.get("https://title.example") == "Stump Grinding in Leeds")
check("a yes or no caller still works (every live answer is non-empty, every dead one is empty)", all(bool(ev[k]) for k in ("title", "body", "weak", "thin", "blocked")) and not any(ev[k] for k in ("wrong", "dead", "parked")))

# ---------------------------------------------------------------- find: the evidence column, the summary and --strict (offline, on a small list)
import duckdb  # noqa: E402

COLS = "fsq_place_id,name,latitude,longitude,address,locality,region,postcode,tel,website,email,facebook_id,instagram,fsq_category_labels,date_refreshed"
vals = ",\n".join(f"('p{i}','Tree Co {i}',53.80,-1.55,'1 St','Leeds','','X1','+44','https://site{i}.example',NULL,NULL,NULL,['tree service'],DATE '2026-01-01')" for i in range(6))
duckdb.connect().sql(f"COPY (SELECT * REPLACE (latitude::DOUBLE AS latitude, longitude::DOUBLE AS longitude) FROM (VALUES {vals}) t({COLS})) TO '{(TMP / 'places-gb-stump-grinding.parquet').as_posix()}' (FORMAT parquet)")
LEVELS = {"site0": "title", "site1": "body", "site2": "weak", "site3": "thin", "site4": "blocked", "site5": "title"}
P.site_live = lambda url, words="": LEVELS[url.split("//")[1].split(".")[0]]
P.geocode = lambda place, country="US": (53.8, -1.55)
out1 = TMP / "all.csv"
P.find("stump grinding", "Leeds", miles=10, cap=20, out=str(out1), country="GB")
rows = list(csv.DictReader(open(out1, newline="", encoding="utf-8-sig")))
check("every lead says how clearly its site shows the trade, with the page title", {r["business"]: r["niche_match"] for r in rows} == {f"Tree Co {i}": v for i, v in zip(range(6), ["title", "body", "weak", "thin", "blocked", "title"])} and "site_title" in rows[0])
out2 = TMP / "strict.csv"
P.find("stump grinding", "Leeds", miles=10, cap=20, out=str(out2), country="GB", strict=True)
strict = list(csv.DictReader(open(out2, newline="", encoding="utf-8-sig")))
check("--strict keeps only the sites that say the trade clearly", sorted(r["niche_match"] for r in strict) == ["body", "title", "title"], str([r["niche_match"] for r in strict]))
P.site_live = lambda url, words="": True
out3 = TMP / "oldstyle.csv"
P.find("stump grinding", "Leeds", miles=10, cap=20, out=str(out3), country="GB")
old = list(csv.DictReader(open(out3, newline="", encoding="utf-8-sig")))
check("an old caller that answers True still works (the evidence is 'unchecked')", len(old) == 6 and all(r["niche_match"] == "unchecked" for r in old))
P.site_live = lambda url, words="": LEVELS[url.split("//")[1].split(".")[0]]
import shutil  # noqa: E402
shutil.copy(TMP / "places-gb-stump-grinding.parquet", TMP / "places-jp-stump-grinding.parquet")
P.find("stump grinding", "Leeds", miles=10, cap=20, out=str(TMP / "jp.csv"), country="JP", strict=True)
jp = list(csv.DictReader(open(TMP / "jp.csv", newline="", encoding="utf-8-sig")))
check("--strict does nothing where the English words check is off (non-English sites), so no lead is dropped for it", len(jp) == 6, str(len(jp)))

# ---------------------------------------------------------------- the audit sheet
leads = []
for i in range(40):
    lvl = ["title"] * 20 + ["body"] * 10 + ["weak"] * 6 + ["thin"] * 3 + ["blocked"]
    leads.append({"business": f"Biz {i}", "website": f"https://biz{i}.example", "site_title": f"Title {i}", "niche_match": lvl[i], "category": "Stump Grinding", "search_city": "Leeds"})
leads_csv = TMP / "leads.csv"
CM.write_csv(str(leads_csv), leads)
s1 = A.sample_rows(leads, 12, seed=1)
check("the sample has every level of evidence, not just the big strong group", {r["niche_match"] for r in s1} == {"title", "body", "weak", "thin", "blocked"}, str({r["niche_match"] for r in s1}))
check("the same seed gives the same sample, another seed another", [r["business"] for r in A.sample_rows(leads, 12, 1)] == [r["business"] for r in s1] and [r["business"] for r in A.sample_rows(leads, 12, 2)] != [r["business"] for r in s1])
check("a sample never has more than the list", len(A.sample_rows(leads[:5], 50, 1)) == 5)
sheet = A.make(str(leads_csv), sample=12, seed=1, out=str(TMP / "sheet.csv"))
srows = list(csv.DictReader(open(sheet, newline="", encoding="utf-8-sig")))
check("the sheet has an empty is_right column and the page titles to judge by", srows and all(r["is_right"] == "" for r in srows) and srows[0]["site_title"].startswith("Title") and {"business", "website", "niche_match", "note"} <= set(srows[0]))
(TMP / "none.csv").write_text("business,website" + chr(10), encoding="utf-8")
check("an empty list is explained", "empty" in (raises(A.make, str(TMP / "none.csv")) or ""))

# ---------------------------------------------------------------- scoring what you labelled
def labelled(answers):
    rows = [dict(r) for r in srows]
    for r, a in zip(rows, answers):
        r["is_right"] = a
    CM.write_csv(str(TMP / "done.csv"), rows)
    return A.score(str(TMP / "done.csv"), show=False)


by_level = {r["niche_match"]: r for r in srows}
answers = ["y" if r["niche_match"] in ("title", "body") else "n" for r in srows]     # strong are right, weak ones wrong
res = labelled(answers)
check("precision is the share marked right, overall and by how clearly the site said the trade", res["labelled"] == len(srows) and res["by_level"]["title"]["precision"] == 100 and res["by_level"]["weak"]["precision"] == 0 and 0 < res["precision"] < 100, str(res["by_level"]))
check("it says what --strict would give: better precision, fewer leads", res["strong_precision"] == 100 and 0 < res["strong_share"] < 100)
check("yes, y, no, n and wrong are all understood, blanks are skipped", labelled(["Y", "No", "wrong", "right", "", "maybe"] + [""] * (len(srows) - 6))["labelled"] == 4)
check("labels are required", "No is_right answers" in (raises(labelled, [""] * len(srows)) or ""))
bad = [dict(r) for r in srows]
for r in bad[:4]:
    r["website"] = "https://www.dirsite.example/p/" + r["business"].replace(" ", "")
    r["is_right"] = "n"
CM.write_csv(str(TMP / "repeat.csv"), bad)
check("a web address that was wrong more than once is named, to add to the directory list", A.score(str(TMP / "repeat.csv"), show=False)["repeat_wrong_hosts"] == ["dirsite.example"])
check("host names are read without www and from bare domains", A.host("https://www.Yell.com/biz/x") == "yell.com" and A.host("yell.com/biz") == "yell.com" and A.host("") == "")

sys.exit(1 if fails else 0)
