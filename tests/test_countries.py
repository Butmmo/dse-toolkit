"""Tests for the lead finder in more countries (18 Nov 2026): groups, one-country search, file names, geocoding by country, and a full find() on a small fake business list.   python tests/test_countries.py"""
import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import countries as C, places as P  # noqa: E402

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


# ---------------------------------------------------------------- the lists
tiers = {k: v[0] for k, v in C.GROUPS.items()}
check("the rich markets are tier 1 and the fast-developing ones tier 2",
      all(tiers[k] == 1 for k in ("uk", "eu", "gulf", "israel", "japan", "korea", "australasia")) and
      all(tiers[k] == 2 for k in ("north-africa", "south-east-asia", "southern-africa", "eastern-africa", "china", "turkey-and-neighbours")))
check("every code in a group has a name", all(c in C.NAMES for _, _, cs in C.GROUPS.values() for c in cs))
check("the EU group has all 27 members", len(C.resolve("eu")) == 27)
check("Israel and Turkey are searchable", C.one("IL") == "IL" and C.one("tr") == "TR" and "TR" in C.resolve("turkey-and-neighbours"))
check("a code, a group name and a list all resolve, without repeats", C.resolve("gb") == ["GB"] and C.resolve("uk,GB,gulf")[:2] == ["GB", "AE"] and len(C.resolve("uk,GB")) == 1)
check("an unknown country is refused, never guessed", "Unknown country" in (raises(C.resolve, "Narnia") or ""))
check("searching needs exactly one country", "pick one country" in (raises(C.one, "eu") or "") and "Give a country" in (raises(C.one, "") or ""))
check("the listing shows tier 1 before tier 2", (lambda l: l.index("Tier 1 (rich markets, do these first)") < l.index("Tier 2 (fast-developing markets)"))(C.listing()))

# ---------------------------------------------------------------- files and the site-word rule
check("the US file keeps its old name", P.extract_path("dentist").name == "places-us-dentist.parquet" and P.extract_path("dentist", "US").name == "places-us-dentist.parquet")
check("another country gets its own file", P.extract_path("dentist", "GB").name == "places-gb-dentist.parquet")
check("English words are checked only where sites are in English", P.site_words_for("GB", "", "dent") == "dent" and P.site_words_for("JP", "", "dent") == "" and P.site_words_for("DE", "", "dent") == "")
check("your own words always apply", P.site_words_for("JP", "shika", "dent") == "shika")

# ---------------------------------------------------------------- geocoding is country aware
TMP = Path(tempfile.mkdtemp(prefix="zz-countries-"))
P.DATA = TMP
P.GEOCACHE = TMP / "geocode.csv"
P.time.sleep = lambda s: None
seen = []


class Resp:
    def __init__(self, lat): self.lat = lat
    def json(self): return [{"lat": str(self.lat), "lon": "-1.5"}] if self.lat is not None else []


def fake_get(url, params=None, **k):
    seen.append(params)
    q = params["q"]; return Resp(53.8 if q.startswith("Leeds") else 27.9 if q.startswith("Tampa") else None)


P.requests.get = fake_get
check("a UK city is looked up inside the UK, not the US", P.geocode("Leeds", "GB") == (53.8, -1.5) and seen[-1]["countrycodes"] == "gb" and "USA" not in seen[-1]["q"], str(seen[-1]))
n = len(seen)
P.geocode("Leeds", "GB")
check("the answer is cached per country", len(seen) == n)
P.geocode("Tampa FL")
check("the US still adds USA and its old cache key", seen[-1]["q"] == "Tampa FL, USA" and seen[-1]["countrycodes"] == "us" and "tampa fl" in P.GEOCACHE.read_text(encoding="utf-8"))
check("an unknown city names the country", "United Kingdom" in (raises(P.geocode, "Nowhereville", "GB") or ""))

# ---------------------------------------------------------------- find() end to end on a small fake list (no network)
import duckdb  # noqa: E402

con = duckdb.connect()
fake = (TMP / "places-gb-dentist.parquet").as_posix()
con.sql(f"""COPY (SELECT * REPLACE (latitude::DOUBLE AS latitude, longitude::DOUBLE AS longitude) FROM (VALUES
  ('a1','Leeds Smile Studio',53.80,-1.54,'1 High St','Leeds','England','LS1','+44 1','https://smile.example',NULL,NULL,NULL,['Health > Dentist'],DATE '2026-01-01'),
  ('a2','Aspen Dental Leeds',53.81,-1.55,'2 High St','Leeds','England','LS2','+44 2','https://aspen.example',NULL,NULL,NULL,['Health > Dentist'],DATE '2026-01-01'),
  ('a3','Far Away Dental',51.50,-0.12,'3 Low St','London','England','EC1','+44 3','https://far.example',NULL,NULL,NULL,['Health > Dentist'],DATE '2026-01-01')
) t(fsq_place_id,name,latitude,longitude,address,locality,region,postcode,tel,website,email,facebook_id,instagram,fsq_category_labels,date_refreshed)) TO '{fake}' (FORMAT parquet)""")
words_used = []
P.site_live = lambda url, words="": (words_used.append(words), True)[1]
out = TMP / "leeds.csv"
P.find("dentist", "Leeds", miles=10, cap=10, out=str(out), country="GB")
rows = list(csv.DictReader(open(out, newline="", encoding="utf-8-sig")))
check("find() works for a UK city and returns only independent businesses in range", [r["business"] for r in rows] == ["Leeds Smile Studio"], str([r["business"] for r in rows]))
check("a non-US lead says its country", rows and rows[0]["country"] == "GB")
check("the English words check ran for the UK", words_used and words_used[0] != "")
import shutil  # noqa: E402
shutil.copy(fake, P.extract_path("dentist", "JP"))        # same list, pretend it is Japan: sites there are not in English
P.geocode = lambda place, country="US": (53.8, -1.54)
words_used.clear()
P.find("dentist", "Tokyo", miles=10, cap=10, out=str(TMP / "tokyo.csv"), country="JP")
check("find() does not apply the English words check in Japan", words_used and all(w == "" for w in words_used), str(words_used))
check("find() refuses a group of countries", "pick one country" in (raises(P.find, "dentist", "Paris", country="eu") or ""))

sys.exit(1 if fails else 0)
