"""Tests for the open-data source (Overture) and the city tiers (18 Nov 2026): tiers from real counts, suburbs folded in, an editable cities file that is never overwritten, and find() using it.   python tests/test_cities.py"""
import csv
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import cities as CT, overture as OV, places as P  # noqa: E402

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


TMP = Path(tempfile.mkdtemp(prefix="zz-cities-"))
P.DATA = OV.DATA = CT.DATA = TMP

# ---------------------------------------------------------------- the open-data source
check("every hand-made business type has Overture categories", set(P.HAND_MADE) <= set(OV.KINDS) and all(OV.KINDS[k] for k in P.HAND_MADE), str(set(P.HAND_MADE) - set(OV.KINDS)))
check("a niche or typed type is matched to Overture only when a build asks for it (nothing touches the network before that)", OV.category_names("wedding-photographers") == [])
check("Overture files have their own names", P.extract_path("dentist", "GB", "overture").name == "overture-gb-dentist.parquet" and P.extract_path("dentist", "GB").name == "places-gb-dentist.parquet")
check("the source choices are checked", P.sources_for("both") == ["foursquare", "overture"] and P.sources_for("OVERTURE") == ["overture"] and "Unknown data source" in (raises(P.sources_for, "yelp") or ""))

# ---------------------------------------------------------------- tiers
check("a bigger pool gets more tiers, 7 to 10", [CT.tier_count(n) for n in (10, 999, 1_000, 9_999, 10_000, 99_999, 100_000, 5_000_000)] == [7, 7, 8, 8, 9, 9, 10, 10])
t = CT.assign_tiers([1000, 500, 100, 10, 3], 8)
check("tier 1 is the biggest pool and the last tier the smallest", t[0] == 1 and t[-1] == 8 and t == sorted(t), str(t))
check("tiers stay inside 1..n", all(1 <= x <= 8 for x in CT.assign_tiers([5000, 4000, 7, 3, 3, 3], 8)))
check("towns with the same pool share a tier", CT.assign_tiers([40, 40, 40], 7) == [1, 1, 1])
check("no towns gives no tiers", CT.assign_tiers([], 7) == [])

# ---------------------------------------------------------------- folding suburbs into the big town
big = {"city": "Leeds", "region": "", "pool": 300, "places": 400, "lat": 53.80, "lon": -1.55, "folded": 0}
sub = {"city": "Headingley", "region": "", "pool": 40, "places": 50, "lat": 53.82, "lon": -1.58, "folded": 0}      # about 2 miles away
far = {"city": "Hull", "region": "", "pool": 90, "places": 100, "lat": 53.74, "lon": -0.33, "folded": 0}            # about 50 miles away
kept = CT.fold([sub, far, big], 10.0)
check("a suburb is folded into the big town next to it, and its prospects are added", [k["city"] for k in kept] == ["Leeds", "Hull"] and kept[0]["pool"] == 340 and kept[0]["folded"] == 1, str(kept))
check("a town far away stays on the list", any(k["city"] == "Hull" and k["pool"] == 90 for k in kept))
check("folding does not change the towns you passed in", sub["pool"] == 40 and big["pool"] == 300)

# ---------------------------------------------------------------- rank / suggest on a small real-shaped list
import duckdb  # noqa: E402

COLS = "fsq_place_id,name,latitude,longitude,address,locality,region,postcode,tel,website,email,facebook_id,instagram,fsq_category_labels,date_refreshed"


def write(path, rows):
    vals = ",\n".join(f"('{i}','{n}',{la},{lo},'1 St','{loc}','','X1','+44','{w}',NULL,NULL,NULL,['{cat}'],DATE '2026-01-01')" for i, n, la, lo, loc, w, cat in rows)
    duckdb.connect().sql(f"COPY (SELECT * REPLACE (latitude::DOUBLE AS latitude, longitude::DOUBLE AS longitude) FROM (VALUES {vals}) t({COLS})) TO '{Path(path).as_posix()}' (FORMAT parquet)")


rows = []
for i in range(30):
    rows.append((f"l{i}", f"Leeds Dental {i}", 53.80 + i * 0.0001, -1.55, "Leeds", f"https://leeds{i}.example", "dental_clinic"))
for i in range(6):
    rows.append((f"h{i}", f"Headingley Dental {i}", 53.82, -1.58, "Headingley", f"https://head{i}.example", "dental_clinic"))
for i in range(8):
    rows.append((f"u{i}", f"Hull Dental {i}", 53.74, -0.33, "Hull", f"https://hull{i}.example", "dental_clinic"))
rows.append(("c1", "Aspen Dental Hull", 53.74, -0.33, "Hull", "https://aspen.example", "dental_clinic"))       # a chain: not a prospect
rows.append(("n1", "No Site Dental", 53.74, -0.33, "Hull", "", "dental_clinic"))                              # no website: not a prospect
for i in range(2):
    rows.append((f"t{i}", f"Tiny Dental {i}", 52.0, -2.0, "Tinytown", f"https://tiny{i}.example", "dental_clinic"))  # fewer than 3 prospects: left out
write(TMP / "overture-gb-dentist.parquet", rows)

ranked = CT.rank("dentist", "GB", "overture")
by = {r["city"]: r for r in ranked}
check("towns are rated by independent businesses with a website", by["Leeds"]["pool"] == 36 and by["Hull"]["pool"] == 8, str({k: v["pool"] for k, v in by.items()}))
check("the suburb is folded into Leeds, not listed", "Headingley" not in by and by["Leeds"]["folded"] == 1)
check("a town with too few prospects is left out", "Tinytown" not in by)
check("a chain and a business with no website do not count", by["Hull"]["places"] == 10 and by["Hull"]["pool"] == 8)
check("the biggest town is tier 1, with 7 tiers for a small pool", by["Leeds"]["tier"] == 1 and max(r["tier"] for r in ranked) <= 7 and by["Hull"]["tier"] > 1)
check("tier 1 to 3 towns are marked to use, the rest are not", by["Leeds"]["include"] == "Y" and all(r["include"] == ("Y" if r["tier"] <= 3 else "N") for r in ranked))
check("a missing list says how to build it", "build dentist" in (raises(CT.rank, "dentist", "DE", "overture") or ""))

path = CT.suggest("dentist", "GB", "overture")
check("the cities file is written with the editable columns", Path(path).name == "cities-gb-dentist.csv" and list(csv.DictReader(open(path, encoding="utf-8-sig")))[0].keys() >= {"tier", "city", "include", "lat", "lon"})
txt = Path(path).read_text(encoding="utf-8-sig").replace("Leeds,", "Leeds EDITED,", 1)
Path(path).write_text(txt, encoding="utf-8-sig")
CT.suggest("dentist", "GB", "overture")
check("your edits are never overwritten", "Leeds EDITED" in Path(path).read_text(encoding="utf-8-sig"))
CT.suggest("dentist", "GB", "overture", refresh=True)
check("--refresh rebuilds it", "Leeds EDITED" not in Path(path).read_text(encoding="utf-8-sig"))

# ---------------------------------------------------------------- loading the file back
check("towns marked Y are the ones searched", [c[0] for c in CT.load(path)] == [r["city"] for r in ranked if r["include"] == "Y"])
check("--tiers picks by tier instead of the include column", [c[0] for c in CT.load(path, str(by["Hull"]["tier"]))] == [r["city"] for r in ranked if r["tier"] == by["Hull"]["tier"]])
check("tier ranges are understood and bad ones refused", CT.parse_tiers("1-3,5") == {1, 2, 3, 5} and "not a tier" in (raises(CT.parse_tiers, "one-two") or "") and "valid" in (raises(CT.parse_tiers, "4-2") or ""))
Path(path).write_text("tier,city,region,pool,places,folded,lat,lon,include,note\n,Bradford,West Yorkshire,,,,,,Y,added by hand\n", encoding="utf-8-sig")
check("a town you add by hand (no lat/lon) is looked up by name and region", CT.load(path) == [("Bradford, West Yorkshire", None, None)])
check("a missing cities file is explained", "python dse.py cities" in (raises(CT.load, str(TMP / "nope.csv")) or ""))

# ---------------------------------------------------------------- find() with the file, and with the open-data source
CT.suggest("dentist", "GB", "overture", refresh=True)
P.geocode = lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not look up a town whose position is in the file"))
P.site_live = lambda url, words="": True
out = TMP / "gb.csv"
P.find("dentist", "", miles=10, cap=40, out=str(out), country="GB", source="overture", cities_file=path)
got = list(csv.DictReader(open(out, newline="", encoding="utf-8-sig")))
check("find() searches the towns in the file without looking their positions up", len(got) > 0 and {r["search_city"] for r in got} <= {"Leeds", "Hull"}, str({r["search_city"] for r in got}))
check("each lead says which source it came from", all(r["source"].startswith("Overture Maps Places") for r in got))
check("chains are still left out", not any("Aspen" in r["business"] for r in got))
check("find() refuses a cities file with nothing marked", "cities file" in (raises(P.find, "dentist", "", country="GB", source="overture", cities_file=path, tiers="9") or ""))

# no --out given (what the HQ Tools button does): the output file is named from the first town, for typed towns and for a cities file
from dse import common as CM  # noqa: E402
CM.LISTS = TMP / "lists"
dst1 = P.find("dentist", "", miles=10, cap=10, country="GB", source="overture", cities_file=path, tiers="1-7")
check("a search with no output name works with a cities file and names the file from the first town", Path(dst1).is_file() and "leeds-plus1" in Path(dst1).name, str(dst1))
real_geocode = P.geocode
P.geocode = lambda place, country="US": (53.8, -1.54)
dst2 = P.find("dentist", "Leeds; Hull", miles=10, cap=10, country="GB", source="overture")
dst3 = P.find("dentist", "Leeds", miles=10, cap=10, country="GB", source="overture")
check("a search with no output name works with typed towns, one or several", Path(dst2).is_file() and "leeds-plus1" in Path(dst2).name and Path(dst3).is_file() and Path(dst3).name.endswith("-leeds.csv"), f"{dst2} | {dst3}")
P.geocode = real_geocode

# both sources at once: the same business in both appears once, and each lead keeps its own source label
write(TMP / "places-gb-dentist.parquet", [("f1", "Hull Dental 0", 53.74, -0.33, "Hull", "https://hull0.example", "Dentist"), ("f2", "Foursquare Only Dental", 53.741, -0.331, "Hull", "https://fsqonly.example", "Dentist")])
P.find("dentist", "", miles=10, cap=200, out=str(TMP / "both.csv"), country="GB", source="both", cities_file=path, tiers="1-7")
both = list(csv.DictReader(open(TMP / "both.csv", newline="", encoding="utf-8-sig")))
names = [r["business"] for r in both]
check("with both sources a business in both is listed once", names.count("Hull Dental 0") == 1, str(names))
check("a business only the other source knows is added", "Foursquare Only Dental" in names)
check("the two sources are labelled separately", {r["source"].split(",")[0] for r in both} == {"Overture Maps Places", "Foursquare Open Source Places"}, str({r["source"] for r in both}))

sys.exit(1 if fails else 0)
