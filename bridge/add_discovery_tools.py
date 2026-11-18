"""One-off generator: the lead-discovery buttons in catalog.json (HQ Tools). Safe to re-run.  Run:  python bridge/add_discovery_tools.py

  * Leads (dse.find, dse.list): a country and a data source (Foursquare, Overture, both)
  * Download business data (dse.build): any business type by name, any country or group, either source
  * New: rate the towns of a country in tiers (dse.cities), search the best towns (dse.find_tiers)
  * New: the UK company register lists (dse.registry_find; its 470 MB download stays a command: python dse.py registry build <type>)
  * New: what a website is built with and what it is missing (dse.tech_site, dse.tech)

SIZE: Citadel refuses a published catalog over 600,000 characters (hq_runner_beat, raised from 200,000 on 18 Nov 2026 by migration 20261226090000 in the
Citadel repo). The catalog is about 205,000 now. The new fields and help text are still kept short, and tests/test_discovery_tools.py fails when the published catalog passes 90% of the limit.
The runner only runs these commands on your PC; nothing is sent anywhere.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from dse import countries as C  # noqa: E402

p = HERE / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
NEW = ("dse.cities", "dse.find_tiers", "dse.registry_find", "dse.tech_site", "dse.tech", "dse.audit_make", "dse.audit_score")
for k in [k for k in T if k in NEW + ("dse.registry_build", "dse.directories", "dse.countries")]:
    del T[k]

SUGGEST = ["GB", "DE", "FR", "AE", "IL", "JP"]      # any two-letter code in python dse.py countries works
GROUPS = ["eu", "gulf", "uk"]
KIND = {"name": "kind", "label": "Business type", "type": "text", "required": True, "max": 60, "pattern": r"[A-Za-z][A-Za-z0-9 &'/-]{2,59}"}
SOURCE = {"name": "source", "label": "Data from", "type": "choice", "required": False, "default": "foursquare",
          "choices": [{"value": "foursquare", "label": "Foursquare"}, {"value": "overture", "label": "Overture"}, {"value": "both", "label": "Both"}]}
WORDS = {"name": "words", "label": "Words the website must use (optional)", "type": "text", "required": False, "max": 120, "pattern": r"[A-Za-z0-9][A-Za-z0-9 ,'&/-]{1,119}"}
SKIP = {"name": "skip", "label": "Leave out names with these words (optional)", "type": "text", "required": False, "max": 120, "pattern": r"[A-Za-z0-9][A-Za-z0-9 ,'&/-]{1,119}"}
MILES = {"name": "miles", "label": "Miles around each town", "type": "int", "min": 5, "max": 100, "default": 25}
MAX = {"name": "max", "label": "How many leads", "type": "int", "min": 5, "max": 500, "default": 100}
STRICT = {"name": "strict", "label": "Only sites that say the trade clearly", "type": "bool", "default": False,
          "hint": "Keeps a lead only if its own site names the trade in its title or headings, or repeats it. Drops 'mentioned once' and 'too short to tell'."}
FAST = {"name": "fast", "label": "Fast (skip the hidden browser)", "type": "bool", "default": False}
LISTS = [{"glob": "my-lists/*.csv", "upload": True}]


def country(required=False, groups=False) -> dict:
    f = {"name": "country", "label": "Country" + (" or group" if groups else ""), "type": "text", "required": required, "max": 40 if groups else 2,
         "pattern": r"^[A-Za-z][A-Za-z-]{1,30}$" if groups else r"^[A-Za-z]{2}$", "suggestions": (GROUPS if groups else []) + SUGGEST}
    if not required:
        f["default"] = "US"
    return f


def add_after(tool: str, after: str, fields: list[dict], args: list[dict]):
    t = T[tool]
    drop = {f["name"] for f in fields}
    t["fields"] = [f for f in t["fields"] if f["name"] not in drop]
    t["args"] = [a for a in t["args"] if a.get("field") not in drop]
    i = next(i for i, f in enumerate(t["fields"]) if f["name"] == after) + 1
    t["fields"][i:i] = fields
    t["args"] += args


NICHE_HINT = ("Any of the app's 512 niches by name (like stump grinding or wedding photographers), or any business of your own: a new one is matched to "
              "Foursquare's business categories and remembered. The first time for a type it builds its data (a few minutes).")
for tool in ("dse.find", "dse.list"):
    add_after(tool, "cities", [country(), dict(SOURCE)], [{"opt": "--country", "field": "country"}, {"opt": "--source", "field": "source"}])
    next(f for f in T[tool]["fields"] if f["name"] == "kind")["hint"] = NICHE_HINT
    add_after(tool, "skip", [dict(STRICT)], [{"flag": "--strict", "field": "strict"}])
T["dse.build"]["fields"] = [
    {"name": "kinds", "label": "Business types (comma-separated)", "type": "text", "required": True, "max": 300,
     "pattern": r"^[A-Za-z][A-Za-z0-9 &'/-]*(,[A-Za-z][A-Za-z0-9 &'/-]*)*$", "placeholder": "dentist,plumber,stump grinding"},
    country(groups=True), dict(SOURCE)]
T["dse.build"]["args"] = [{"lit": "build"}, {"field": "kinds"}, {"opt": "--country", "field": "country"}, {"opt": "--source", "field": "source"}]

T["dse.cities"] = {
    "label": "Rate the towns of a country (tiers)", "group": "Find clients",
    "help": "Rates towns by how many independent businesses with a website they hold (tier 1 = richest). Download the data first.",
    "script": "dse.py", "args": [{"lit": "cities"}, {"field": "kind"}, {"opt": "--country", "field": "country"}, {"opt": "--source", "field": "source"}],
    "fields": [dict(KIND), country(required=True), dict(SOURCE)],
    "timeout_min": 20, "outputs": [{"glob": "data/cities-*.csv", "upload": True}]}
T["dse.find_tiers"] = {
    "label": "Leads from my best towns (tiers)", "group": "Find clients",
    "help": "Searches the towns in a cities list marked Y, or the tiers you give.",
    "script": "dse.py", "args": [{"lit": "find"}, {"opt": "--cities-file", "field": "cities_file"}, {"opt": "--source", "field": "source"}, {"opt": "--tiers", "field": "tiers"}, {"flag": "--strict", "field": "strict"}],
    "fields": [{"name": "cities_file", "label": "Cities list", "type": "file", "required": True, "glob": "data/cities-*.csv"}, dict(SOURCE),
               {"name": "tiers", "label": "Only tiers (like 1-3)", "type": "text", "required": False, "max": 20, "pattern": r"^\d{1,2}(-\d{1,2})?(,\d{1,2}(-\d{1,2})?)*$"}, dict(STRICT)],
    "timeout_min": 90, "outputs": list(LISTS)}

T["dse.registry_find"] = {
    "label": "UK company register: find by town", "group": "Find clients",
    "help": "UK companies by town, oldest first (Companies House). Download once: python dse.py registry build <type>.",
    "script": "dse.py", "args": [{"lit": "registry"}, {"lit": "find"}, {"field": "kind"}, {"field": "towns"}, {"opt": "--min-age", "field": "min_age"}],
    "fields": [dict(KIND), {"name": "towns", "label": "Towns", "type": "text", "required": True, "max": 300, "pattern": r"^[A-Za-z][A-Za-z0-9 .,;'&-]{1,299}$"},
               {"name": "min_age", "label": "At least this many years old", "type": "int", "min": 0, "max": 50, "default": 1}],
    "timeout_min": 10, "outputs": list(LISTS)}

T["dse.tech_site"] = {"label": "What a website is built with", "group": "Check websites",
                      "help": "Reads one homepage: platform, booking, chat, analytics and what is not detected.",
                      "script": "dse.py", "args": [{"lit": "tech"}, {"field": "site"}, {"flag": "--fast", "field": "fast"}],
                      "fields": [{"name": "site", "label": "Website", "type": "url", "required": True}, dict(FAST)], "timeout_min": 5, "outputs": []}
T["dse.tech"] = {"label": "What every website on a list is built with", "group": "Check websites",
                 "help": "Adds technology and what-is-missing columns to a lead list.",
                 "script": "dse.py", "args": [{"lit": "tech"}, {"field": "csv"}, {"opt": "--max", "field": "max"}, {"flag": "--fast", "field": "fast"}],
                 "fields": [{"name": "csv", "label": "List", "type": "file", "required": True, "glob": "my-lists/*.csv", "exclude": "tech"},
                            {"name": "max", "label": "Most sites in this run", "type": "int", "min": 1, "max": 2000, "default": 100}, dict(FAST)],
                 "timeout_min": 120, "outputs": [{"glob": "my-lists/*-tech-*.csv", "upload": True}]}

T["dse.audit_make"] = {"label": "Check a lead list: make a sample sheet to label", "group": "Check websites",
                       "help": "Picks about 20 leads from a lead list, strongest and weakest mixed, into a sheet with an empty is_right column. Open it on your PC and write y or n for each: is it a real business of the type, with its own website?",
                       "script": "dse.py", "args": [{"lit": "audit"}, {"field": "csv"}, {"opt": "--sample", "field": "sample"}],
                       "fields": [{"name": "csv", "label": "Lead list", "type": "file", "required": True, "glob": "my-lists/*.csv", "exclude": "audit"},
                                  {"name": "sample", "label": "How many to check", "type": "int", "min": 5, "max": 60, "default": 20}],
                       "timeout_min": 2, "outputs": [{"glob": "my-lists/*-audit-*.csv", "upload": True}]}
T["dse.audit_score"] = {"label": "Check a lead list: score the sheet you labelled", "group": "Check websites",
                        "help": "Reads the y and n you wrote and shows how many leads are right, by how clearly the site says the trade, and what to change (Only sites that say the trade clearly, or a directory to add).",
                        "script": "dse.py", "args": [{"lit": "audit"}, {"field": "csv"}, {"flag": "--score", "field": "go"}],
                        "fields": [{"name": "csv", "label": "Labelled sheet", "type": "file", "required": True, "glob": "my-lists/*audit*.csv"}, {"name": "go", "label": "Score it", "type": "bool", "default": True}],
                        "timeout_min": 2, "outputs": []}

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len([k for k in T if k in NEW]), "new tools,", len(T), "in all")
