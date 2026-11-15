"""Tests for "make it yours": your own business types, your own website check, your own words.   python tests/test_custom.py"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import check as chk, custom as C, places as P  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except ValueError as e:
        return str(e)
    except SystemExit as e:
        return str(e)
    return None


TMP = Path(tempfile.mkdtemp(prefix="zz-custom-"))
C.PACK_DIR = TMP / "packs"
P.CUSTOM_KINDS = TMP / "kinds.json"

# ---------------------------------------------------------------- your own website check
msg = C.make_pack("Wedding photographers", "galleries that load fast and a booking page",
                  ["online booking, book now, schedule => there is no way to book a session online", "pricing, packages => the site never shows what a session costs"])
check("a pack of your own is saved and described", "my-wedding-photographers" in msg and (C.PACK_DIR / "my-wedding-photographers.json").is_file())
check("it appears in the pack list", "my-wedding-photographers" in C.pack_ids())
pack = chk.load_pack("my-wedding-photographers")
check("the check loader finds it next to the built-in packs", pack["label"].startswith("Wedding photographers") and len(pack["checks"]) == 2)
check("the opener keeps the business, city and gap as blanks", all(x in pack["opener"] for x in ("{business}", "{city}", "{gap_line}")) and "{sells}" not in pack["opener"])
check("the built-in packs still load", chk.load_pack("smb")["label"].startswith("SMB"))
check("a name that is not a pack says how to make one", "mypack" in (raises(chk.load_pack, "nothing-here") or ""))
check("the pack id cannot be used to reach another folder", "No pack" in (raises(chk.load_pack, "my-../../etc") or ""))

# it really judges a website: words found = fine, words missing = the gap you wrote
HTML = "<html><body>" + "Welcome to our studio. " * 40 + "Book now to hold your date. Contact us today for weddings and portraits.</body></html>"
chk._get_page = lambda url, render: (200, url, HTML, False)
chk._inner_links = lambda *a, **k: []
res = chk.check_site("https://studio.example", pack, render=False)
check("a site that has what you look for is not flagged on it", res["c1"] == "yes", str(res))
check("a site missing the other thing is flagged, with your own sentence as the opener's gap", res["c2"] == "no" and res["gap_line"] == "the site never shows what a session costs", str(res))
row = {"business": "Lens & Light", "city": "Tampa", "gap_line": res["gap_line"]}
op = chk.opener(row, pack)
check("the opener fills the business, city and your gap, nothing else", op.startswith("Hi Lens & Light team") and "Tampa" in op and "never shows what a session costs" in op and "{" not in op, op)

# bad input is refused with a reason
check("a check without the => arrow is explained", "=>" in (raises(C.parse_checks, ["book now, schedule"]) or ""))
check("words and the sentence are length-checked", raises(C.parse_checks, ["a => there is no booking"]) is not None and raises(C.parse_checks, ["booking => no"]) is not None)
check("curly brackets in a sentence are refused", raises(C.parse_checks, ["booking => no {booking} here at all"]) is not None)
check("more than 8 checks refused", raises(C.parse_checks, [f"word{i} => there is no word{i} on the site" for i in range(9)]) is not None)
check("an opener must keep the gap and may only use known blanks", raises(C.make_pack, "Dog trainers", "puppy classes you can book online", ["booking => there is no booking"], "Hi {business}, I like your work and want to help.") is not None
      and raises(C.make_pack, "Dog trainers", "puppy classes you can book online", ["booking => there is no booking"], "Hi {business}, I noticed {gap_line} and {secret}.") is not None)
check("a name that is too short is refused", raises(C.make_pack, "x", "puppy classes you can book online", ["booking => there is no booking"]) is not None)
check("the long dash is never written into a pack", C.DASH not in (C.PACK_DIR / "my-wedding-photographers.json").read_text(encoding="utf-8")
      and C.DASH in (raises(C.make_pack, "Dog trainers", "puppy classes you can book online", ["booking => there is no booking " + C.DASH + " at all"]) and "" or C.DASH))

# ---------------------------------------------------------------- your own business type
CATS = [("1", "Wedding Photographer"), ("2", "Photographer"), ("3", "Photography Lab"), ("4", "Dog Trainer"), ("5", "Dentist"), ("6", "Cosmetic Dentist"), ("7", "Yoga Studio")]
P.categories = lambda: CATS
check("a built-in type is used as it is", P.resolve_kind("dentist") == "dentist" and P.kind_info("dentist")[0] == "Dentists")
check("a typed type that fits one category is found and saved", P.resolve_kind("dog trainers") == "dog-trainers" and P.kind_info("dog-trainers")[1] == ["Dog Trainer"])
saved = json.loads(P.CUSTOM_KINDS.read_text(encoding="utf-8"))
check("what is saved says what you typed and which category it became", saved["dog-trainers"]["typed"] == "dog trainers" and saved["dog-trainers"]["names"] == ["Dog Trainer"])
check("the website words come from your own words", "dog" in saved["dog-trainers"]["words"] and "trainer" in saved["dog-trainers"]["words"], saved["dog-trainers"]["words"])
check("a saved type is reused without looking anything up", (setattr(P, "categories", lambda: (_ for _ in ()).throw(RuntimeError("no lookup"))) or True) and P.resolve_kind("dog-trainers") == "dog-trainers")
P.categories = lambda: CATS
k = P.resolve_kind("photography")
check("a word that fits several categories uses all of them, so you are never asked to choose", sorted(P.kind_info(k)[1]) == ["Photographer", "Photography Lab", "Wedding Photographer"], str(P.kind_info(k)))
CATS_BROAD = [(str(i), f"Service Number {i}") for i in range(12)]
P.categories = lambda: CATS_BROAD
m = raises(P.resolve_kind, "service")
check("a word that fits too many categories asks for one more word", m and "too broad" in m and "wedding photographers" in m, str(m))
P.categories = lambda: CATS
check("a built-in type is found from what you would naturally type", P.builtin_match("Interior Designers") == "interior-design" and P.builtin_match("dentists") == "dentist" and P.builtin_match("Hair Salons") == "hair-salon" and P.builtin_match("law offices") == "law-office" and P.builtin_match("real estate") == "real-estate")
check("a word that is not a built-in is not matched to one", P.builtin_match("wedding photographers") is None and P.builtin_match("") is None)
check("a built-in typed in words needs no lookup at all", (setattr(P, "categories", lambda: (_ for _ in ()).throw(RuntimeError("no lookup"))) or True) and P.resolve_kind("Interior Designers") == "interior-design")
P.categories = lambda: CATS
check("the exact name settles it", P.resolve_kind("Wedding Photographer") == "wedding-photographer" and P.kind_info("wedding-photographer")[0] == "Wedding Photographer")
check("a plural fits the singular category", P.resolve_kind("yoga studios") == "yoga-studios" and P.kind_info("yoga-studios")[1] == ["Yoga Studio"])
check("nothing like it says so and how to browse", "categories" in (raises(P.resolve_kind, "space tourism") or ""))
check("an option-looking or empty type is refused", raises(P.resolve_kind, "--all") is not None and raises(P.resolve_kind, "  ") is not None)
check("the built-in dentist is not confused with Cosmetic Dentist", P.match_categories("dentist", CATS) == ["Dentist"])

# ---------------------------------------------------------------- your own words for the website and the names
check("your own words become a safe pattern", P.own_words("wedding, bride (2025)") == "wedding|bride\\ \\(2025\\)" and P.own_words("a, b") == "" and P.own_words("") == "")
import re  # noqa: E402
check("nothing typed can break the pattern", re.compile(P.own_words(".*(, [[x")) is not None)

# ---------------------------------------------------------------- the long dash
src = "".join((ROOT / f).read_text(encoding="utf-8") for f in ("dse/custom.py", "dse/places.py"))
check("no em dash in the new code", chr(0x2014) not in src)

shutil.rmtree(TMP, ignore_errors=True)
print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
