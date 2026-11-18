"""Tests for the app's 512 niches as built-in business types (18 Nov 2026).   python tests/test_niches.py"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import niches as N, places as P  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


cat = N.CATALOG
snap = set((ROOT / "dse" / "fsq-categories-snapshot.txt").read_text(encoding="utf-8").split("\n")) - {""}

check("all 512 of the app's niches are in the catalog", len(cat) == 512 and len({e["id"] for e in cat}) == 512 and len({e["name"] for e in cat}) == 512)
check("every niche is in a group and has a door", all(e["category"] and e["door"] in ("review", "inquiry") for e in cat))
check("the hand-made types are untouched", P.KINDS["dentist"] == ("Dentists", ["Dentist"]) and len(P.HAND_MADE) == 26 and "dentist" in P.HAND_MADE)
check("every niche is a built-in type (its own, or the hand-made one it is the same as)", all((e.get("same_as") or e["id"]) in P.KINDS for e in cat))
check("a niche that is the same as a hand-made type points at it, never at itself", all(e["same_as"] in P.HAND_MADE for e in cat if "same_as" in e) and sum(1 for e in cat if "same_as" in e) >= 20)
check("every Foursquare category named is a real one (checked against Foursquare's list)", all(c in snap for e in N.entries() for c in e["fsq"]), str({c for e in N.entries() for c in e["fsq"] if c not in snap}))
check("every niche has 1 to 4 categories", all(1 <= len(e["fsq"]) <= 4 for e in N.entries()))
check("every website-words pattern is a valid pattern", all(re.compile(e["words"]) is not None for e in N.entries() if e.get("words")))

# ---- every niche can be found the way the app gives it to the finder
bad = [e["name"] for e in cat if P.builtin_match(e["term"]) is None or P.kind_info(P.builtin_match(e["term"])) is None]
check("every niche term the app passes resolves to a built-in type with categories (no Foursquare token needed)", not bad, str(bad[:5]))
check("every niche name resolves to its own type", all(P.builtin_match(e["name"]) == (e.get("same_as") or e["id"]) for e in cat))
check("a typed word that fits several niches is not guessed", P.builtin_match("service") is None)
check("a typed word that also fits one hand-made type goes to it", P.builtin_match("roofing") == "roofer" and P.builtin_match("dentists") == "dentist")

# ---- the mapping makes sense (these slipped through once: 'dent' in residential, 'law' in lawn, 'patio' in occupational ...)
cats = {e["name"]: e["fsq"] for e in N.entries()}
check("a trade niche gets its trade's category", cats["Stump Grinding"] == ["Tree Service"] and "Plumber" in cats["Septic Pumping & Portable Toilets"] and cats["Carpet Cleaning"] == ["Professional Cleaning Service"])
check("residential is not a dentist", all("Dentist" not in c for n, c in cats.items() if "Residential" in n))
check("lawn is not a law office", all("Law Office" not in c for n, c in cats.items() if "Lawn" in n))
check("outdoor is not a door contractor", all("Doors and Windows Contractor" not in c for n, c in cats.items() if "Outdoor" in n))
check("occupational therapy is not a patio builder", "Deck and Patio Contractor" not in cats["Occupational Therapists"])
check("a hot tub is not a bathroom", "Bathroom Contractor" not in cats["Hot Tub & Swim Spa Installers"])
check("patent attorneys are not party suppliers", "Party Supply Store" not in cats["Patent and Trademark Attorneys"])
check("delivery is not a horse stable", all("Stable" not in c for n, c in cats.items() if "Delivery" in n))
check("a coach rental is not a business coach", "Management Consultant" not in cats["Charter Bus & Coach Rental"])
check("boat builders and food truck builders get their own category", cats["Boat Builders"][0] == "Boat Dealership" and "Food Truck" in cats["Food Truck Builders"])
check("the website words come from the niche's own name", re.search(P.KIND_WORDS["stump-grinding"], "we do stump grinding in town") and not re.search(P.KIND_WORDS["stump-grinding"], "family dentist"))

# ---- the finder uses a niche like any built-in type
info = P.kind_info("garage-door-repair")
check("kind_info works for a niche", info and info[0] == "Garage Door Repair" and "Garage Door Supplier" in info[1] and "door" in info[2])
check("find() would reach the same list names for a niche as for a hand-made type", P.extract_path("stump-grinding", "GB").name == "places-gb-stump-grinding.parquet")
check("the by-group view covers all 512", sum(len(v) for v in N.by_category().values()) == 512 and len(N.by_category()) == 15)
check("a niche's finder term can be looked up from its id", N.term_for("stump-grinding") == "stump grinding" and N.term_for("nope") is None)

sys.exit(1 if fails else 0)
