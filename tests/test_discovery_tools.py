"""Tests for the lead-discovery buttons in the HQ Tools catalog (18 Nov 2026): every button builds a command the real CLI accepts, bad values are refused, and the published catalog stays under Citadel's size limit.   python tests/test_discovery_tools.py"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec_ = importlib.util.spec_from_file_location("dse_runner", ROOT / "bridge" / "runner.py")
R = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(R)
from dse import countries as C  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


cat = R.load_catalog(base_only=True)
T = cat["tools"]
NEW = ["dse.cities", "dse.find_tiers", "dse.registry_find", "dse.tech_site", "dse.tech"]
CHANGED = ["dse.find", "dse.list", "dse.build"]
ALL = NEW + CHANGED

# ---------------------------------------------------------------- the catalog itself
check("every new button is in the catalog", all(k in T for k in NEW), str([k for k in NEW if k not in T]))
check("every argument refers to a field of its own tool", all(a["field"] in {f["name"] for f in T[k]["fields"]} for k in ALL for a in T[k]["args"] if "field" in a))
check("every field is used by an argument (nothing the form asks for is ignored)", all(f["name"] in {a.get("field") for a in T[k]["args"]} for k in ALL for f in T[k]["fields"]), str([(k, f["name"]) for k in ALL for f in T[k]["fields"] if f["name"] not in {a.get("field") for a in T[k]["args"]}]))
check("every field has a type the runner knows", all(f["type"] in ("text", "int", "bool", "choice", "file", "url", "date") for k in ALL for f in T[k]["fields"]))
check("the new buttons are in groups the page shows", all(T[k]["group"] in ("Find clients", "Check websites") for k in NEW))
check("nothing in the new text uses an em dash", chr(0x2014) not in json.dumps({k: T[k] for k in ALL}, ensure_ascii=False))

# ---------------------------------------------------------------- the size limit (Citadel refuses a published catalog over 200,000 characters)
LIMIT = 200_000
size = len(json.dumps(R.public_catalog(R.load_catalog(base_only=True))))        # base_only = every tool: the largest case (Tool Studio on)
check(f"the published catalog stays under Citadel's {LIMIT} character limit with room to spare", size < LIMIT - 2_500, f"{size} characters, only {LIMIT - size} left (shorten text or raise the limit in Citadel)")

# ---------------------------------------------------------------- country field
for k in ("dse.find", "dse.list", "dse.cities"):
    f = next(x for x in T[k]["fields"] if x["name"] == "country")
    check(f"{k}: one two-letter country code, suggestions are real codes", f["pattern"] == r"^[A-Za-z]{2}$" and all(s in C.NAMES for s in f["suggestions"]))
fb = next(x for x in T["dse.build"]["fields"] if x["name"] == "country")
check("a build can also take a group like eu", "eu" in fb["suggestions"] and R.check_value(fb, "eu") == "eu" and R.check_value(fb, "GB") == "GB")
check("rich markets are suggested", {"GB", "AE", "JP"} <= set(next(x for x in T["dse.find"]["fields"] if x["name"] == "country")["suggestions"]))


def bad(tool, field, value):
    f = next(x for x in T[tool]["fields"] if x["name"] == field)
    try:
        R.check_value(f, value)
        return False
    except R.Bad:
        return True


check("a country written as a name, or with a dash, is refused for a search", bad("dse.find", "country", "United Kingdom") and bad("dse.find", "country", "-GB") and bad("dse.find", "country", "G"))
check("a bad data source is refused", bad("dse.find", "source", "yelp"))
check("tiers must look like 1-3", bad("dse.find_tiers", "tiers", "one-three") and R.check_value(next(x for x in T["dse.find_tiers"]["fields"] if x["name"] == "tiers"), "1-3,5") == "1-3,5")
check("business types of the app's niche list can be typed by name", not bad("dse.build", "kinds", "stump grinding,tree service,dentist") and bad("dse.build", "kinds", "dentist;rm -rf"))

# ---------------------------------------------------------------- each button builds a command the real CLI parser accepts
class Parsed(Exception):
    pass


def parse(argv):
    """Run dse.py's own parser on the arguments (strict, like a real run) and stop before anything is done."""
    import argparse
    spec = importlib.util.spec_from_file_location("dse_cli", ROOT / "dse.py")
    D = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(D)
    orig = argparse.ArgumentParser.parse_args

    def fake(self, *a, **k):
        raise Parsed(orig(self, *a, **k))
    argparse.ArgumentParser.parse_args = fake
    old = sys.argv
    sys.argv = ["dse.py"] + argv
    try:
        D.main()
    except Parsed as p:
        return p.args[0]
    finally:
        argparse.ArgumentParser.parse_args = orig
        sys.argv = old
    return None


made = []
for rel, body in (("data/cities-gb-dentist.csv", "tier,city,include\n1,Leeds,Y\n"), ("my-lists/zz-test-leads.csv", "business,website\nA,a.example\n")):
    fp = ROOT / rel
    fp.parent.mkdir(exist_ok=True)
    fp.write_text(body, encoding="utf-8")
    made.append(fp)
try:
    SAMPLES = {
        "dse.find": {"kind": "stump grinding", "cities": "Leeds", "country": "GB", "source": "both"},
        "dse.list": {"pack": "smb", "kind": "dentist", "cities": "Leeds", "country": "GB", "source": "overture"},
        "dse.build": {"kinds": "dentist,stump grinding", "country": "eu", "source": "overture"},
        "dse.cities": {"kind": "dentist", "country": "GB", "source": "both"},
        "dse.find_tiers": {"source": "both", "cities_file": "data/cities-gb-dentist.csv", "tiers": "1-3", "max": 40},
        "dse.registry_find": {"kind": "dentist", "towns": "Leeds; Bradford", "min_age": 2, "max": 50},
        "dse.tech_site": {"site": "https://smile.example", "fast": True},
        "dse.tech": {"csv": "my-lists/zz-test-leads.csv", "max": 50, "fast": True},
    }
    ns = {}
    for key, vals in SAMPLES.items():
        try:
            argv, _ = R.build_command(cat, key, vals)
            ns[key] = parse(argv[3:])
        except (Exception, SystemExit) as e:        # noqa: BLE001  (argparse refuses with SystemExit)
            ns[key] = e
    ok = {k: not isinstance(v, BaseException) and v is not None for k, v in ns.items()}
    check("every button builds a command that dse.py's own parser accepts", all(ok.values()), str({k: str(v)[:80] for k, v in ns.items() if not ok[k]}))
    if all(ok.values()):
        check("find: country and source reach the command", ns["dse.find"].country == "GB" and ns["dse.find"].source == "both" and ns["dse.find"].kind == "stump grinding")
        check("list: country and source reach the command", ns["dse.list"].country == "GB" and ns["dse.list"].source == "overture")
        check("build: a group, a source and niche names reach the command", ns["dse.build"].country == "eu" and ns["dse.build"].source == "overture" and ns["dse.build"].kinds == "dentist,stump grinding")
        check("cities: type, country and source reach the command", ns["dse.cities"].kind == "dentist" and ns["dse.cities"].country == "GB" and ns["dse.cities"].source == "both")
        ft = ns["dse.find_tiers"]
        check("find by tiers: only the file, tiers, source and count are sent (type and country come from the file name)", ft.kind == "" and ft.cities == "" and ft.country is None and ft.cities_file == "data/cities-gb-dentist.csv" and ft.tiers == "1-3" and ft.max == 40 and ft.source == "both")
        check("registry: find reaches the command", ns["dse.registry_find"].action == "find" and ns["dse.registry_find"].min_age == 2 and ns["dse.registry_find"].towns == "Leeds; Bradford")
        check("tech: one site or a list, fast mode", ns["dse.tech_site"].target == "https://smile.example" and ns["dse.tech_site"].fast and ns["dse.tech"].target == "my-lists/zz-test-leads.csv" and ns["dse.tech"].max == 50)
    # defaults: leaving the new boxes empty still gives a valid command and keeps the old behaviour
    argv, _ = R.build_command(cat, "dse.find", {"kind": "dentist", "cities": "Tampa FL"})
    d = parse(argv[3:])
    check("an old-style search (no country, no source typed) is still a US Foursquare search", d.country == "US" and d.source == "foursquare" and d.cities == "Tampa FL")
    # find takes its business type and country from the cities file's own name
    spec = importlib.util.spec_from_file_location("dse_cli2", ROOT / "dse.py")
    D2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(D2)
    seen = {}
    D2.places.find = lambda *a, **k: seen.update(args=a) or "x.csv"
    old_argv = sys.argv
    try:
        sys.argv = ["dse.py", "find", "--cities-file", "data/cities-gb-dentist.csv", "--tiers", "1-3"]
        D2.main()
    except SystemExit as e:
        seen["exit"] = str(e)
    finally:
        sys.argv = old_argv
    a = seen.get("args", ())
    check("find with only a cities file searches that file's type in that file's country", a and a[0] == "dentist" and a[8] == "GB" and a[10] == "data/cities-gb-dentist.csv" and a[11] == "1-3", str(a) + str(seen))
    seen.clear()
    try:
        sys.argv = ["dse.py", "find", "--cities-file", "data/cities-gb-dentist.csv", "--country", "IE", "dentist"]
        D2.main()
    except SystemExit as e:
        seen["exit"] = str(e)
    finally:
        sys.argv = old_argv
    a = seen.get("args", ())
    check("a country you type wins over the file name", a and a[8] == "IE", str(a))
    try:
        sys.argv = ["dse.py", "find", "Leeds"]
        D2.places.find = lambda *a, **k: seen.update(args=a) or "x.csv"
        D2.main()
    finally:
        sys.argv = old_argv
    check("a search with no type and no cities file is still explained, not run", seen["args"][0] == "Leeds")        # "Leeds" is taken as the business type, exactly as before
    # a file that is not on the form's list is refused
    check("a cities list that is not one of the offered files is refused", bad("dse.find_tiers", "cities_file", "data/cities-nope-x.csv") and bad("dse.find_tiers", "cities_file", "../secrets.csv"))
finally:
    for fp in made:
        fp.unlink(missing_ok=True)

sys.exit(1 if fails else 0)
