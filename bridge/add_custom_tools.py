"""One-off generator: "make it yours" in the catalog. Safe to re-run.

  * choice fields that can honour a value of your own get "allow_custom" (the form shows "Other: type my own")
  * the website-check pack list includes the packs you made (choices_from: packs)
  * the lead tools get your own words (site must use / skip names with)
  * two new tools: make your own website check, browse business categories
"""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]


def field(tool, name):
    return next(f for f in T[tool]["fields"] if f["name"] == name)


KIND_PAT = r"[A-Za-z][A-Za-z0-9 &'/-]{2,59}"
CUR_PAT = r"[A-Za-z]{3}"
for t in ("dse.list", "dse.find"):
    f = field(t, "kind")
    f.update(allow_custom=True, custom_pattern=KIND_PAT, custom_label="Other: type my own business type", custom_help="Any business you sell to, like wedding photographers or dog trainers. It is found among Foursquare's business categories and saved for next time; if several fit you are shown them and asked to type the exact one. The first time it builds the data (a few minutes).")
    f["label"] = "Business type (pick one, or type your own)"
f = field("dse.podcasts", "genre")
f.update(allow_custom=True, custom_pattern=r"[A-Za-z][A-Za-z &'/-]{1,39}", custom_label="Other: type my own genre", custom_help="Any topic. Your topics above then search Apple Podcasts without a genre filter.")
for t, n in (("dse.proposal", "currency"), ("dse.books", "base"), ("dse.cut_add", "currency"), ("dse.fx_add", "from_cur"), ("dse.fx_add", "to_cur")):
    field(t, n).update(allow_custom=True, custom_pattern=CUR_PAT, custom_label="Other: type a 3-letter code", custom_help="Any currency code, like NGN, CAD, AUD, ZAR, GHS or INR.")

for t in ("dse.list", "dse.check", "dse.check_one"):
    f = field(t, "pack")
    # The list is filled on the PC (built-in packs plus the ones you made). A static copy of the built-in ones stays here as a fallback,
    # so an older runner that has not been restarted still shows the paths instead of an empty list.
    builtin = [{"value": q.stem, "label": json.loads(q.read_text(encoding="utf-8")).get("label", q.stem)} for q in sorted((p.parent.parent / "packs").glob("*.json"))]
    f.update(choices_from="packs", choices=builtin, label="Your path or your own check")

WORDS = {"name": "words", "label": "Words the business's website must use (optional, your own; separate with commas)", "type": "text", "required": False, "max": 120, "pattern": r"[A-Za-z0-9][A-Za-z0-9 ,'&/-]{1,119}"}
SKIP = {"name": "skip", "label": "Leave out businesses whose name has these words (optional, your own)", "type": "text", "required": False, "max": 120, "pattern": r"[A-Za-z0-9][A-Za-z0-9 ,'&/-]{1,119}"}
for t in ("dse.list", "dse.find"):
    fs = T[t]["fields"]
    for extra in (WORDS, SKIP):
        fs[:] = [x for x in fs if x["name"] != extra["name"]]
    i = next(i for i, x in enumerate(fs) if x["name"] == "max") + 1
    fs[i:i] = [dict(WORDS), dict(SKIP)]
    args = T[t]["args"]
    args[:] = [a for a in args if a.get("field") not in ("words", "skip")]
    args += [{"opt": "--words", "field": "words"}, {"opt": "--skip", "field": "skip"}]
    T[t]["timeout_min"] = max(T[t].get("timeout_min", 10), 45)

for k in ("dse.mypack", "dse.categories"):
    T.pop(k, None)
CHK = lambda n, req=False: {"name": f"check{n}", "label": f"Check {n}: words that count as 'has it', then =>, then what you would say if missing" + ("" if req else " (optional)"), "type": "text", "required": req, "max": 300,  # noqa: E731
                           "placeholder": "online booking, book now, schedule => there is no way to book online", "pattern": r"[A-Za-z0-9][A-Za-z0-9 ,.'&/()!:;?_#%+=<>-]{9,299}"}
T["dse.mypack"] = {
    "label": "Make my own website check (for any business)", "group": "Grow",
    "help": "The built-in checks are written for one path each. Make your own for any business you sell to. Name it, say in one sentence what you offer, then write up to 4 checks, each as: words that count as the website having it, separated by commas, then =>, then what you would say if none of them appear (the gap you would open with). Example: online booking, book now, schedule => there is no way to book a session online. Your check then appears in the 'Your path or your own check' list of the lead and website tools. Nothing is sent.",
    "script": "dse.py",
    "args": [{"lit": "mypack"}, {"field": "name"}, {"opt": "--sells", "field": "sells"}] + [{"opt": "--checks", "field": f"check{n}"} for n in range(1, 5)] + [{"opt": "--opener", "field": "opener"}, {"opt": "--pages", "field": "pages"}],
    "fields": [{"name": "name", "label": "Name (the kind of business, like Wedding photographers)", "type": "text", "required": True, "max": 60, "pattern": r"[A-Za-z][A-Za-z0-9 &'/-]{2,59}"},
               {"name": "sells", "label": "What you offer, in one sentence", "type": "text", "required": True, "max": 160, "pattern": r"[A-Za-z0-9][A-Za-z0-9 ,.'&/()!:;?_#%+=-]{7,159}"},
               CHK(1, True), CHK(2), CHK(3), CHK(4),
               {"name": "opener", "label": "Your opening message (optional): use {business}, {city} and {gap_line}", "type": "text", "required": False, "max": 600, "pattern": r"[A-Za-z0-9{][A-Za-z0-9 ,.'&/()!:;?_#%+={}<>-]{29,599}"},
               {"name": "pages", "label": "Pages to look at besides the home page (optional: contact, pricing, booking)", "type": "text", "required": False, "max": 120, "pattern": r"[A-Za-z0-9][A-Za-z0-9 ,;-]{1,119}"}],
    "timeout_min": 1, "outputs": []}
T["dse.categories"] = {
    "label": "Business types: find the exact name for the lead finder", "group": "Grow",
    "help": "Search Foursquare's list of business categories (the data behind the lead finder) for the exact name of the business you sell to, like photographer or yoga studio. You can also just type your own business type in the lead tools: it is found and saved for you.",
    "script": "dse.py", "args": [{"lit": "categories"}, {"field": "search"}],
    "fields": [{"name": "search", "label": "A word (like photo, yoga, bakery)", "type": "text", "required": True, "max": 40, "pattern": r"[A-Za-z][A-Za-z ]{2,39}"}],
    "timeout_min": 3, "outputs": []}
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools in all")
