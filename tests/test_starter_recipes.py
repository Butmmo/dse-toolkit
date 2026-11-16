"""Every starter recipe in Citadel's gallery is accepted by the toolkit's own validator over its REAL catalog.   python tests/test_starter_recipes.py
tests/fixtures/starter-recipes.json is written by Citadel's scripts/test-starter-recipes.mjs from the gallery's own code."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import mytools as M  # noqa: E402

spec_ = importlib.util.spec_from_file_location("dse_runner", ROOT / "bridge" / "runner.py")
R = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(R)
fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


cat = R.load_catalog(base_only=True)
tools = cat["tools"]
starters = json.loads((ROOT / "tests" / "fixtures" / "starter-recipes.json").read_text(encoding="utf-8"))
chk = M._checker(R)
check("there are starters", len(starters) >= 5)
for s in starters:
    clean, problems = M.validate(s["recipe"], tools, chk)
    check(f"{s['id']}: accepted by the toolkit with no problems", not problems, str(problems))
    e = M.tool_entry("my." + s["id"], clean, tools, " (mine)")
    check(f"{s['id']}: becomes a tool with one form field per question and a sensible time limit", len(e["fields"]) == len(s["recipe"]["inputs"]) and 1 <= e["timeout_min"] <= 120, str(e["timeout_min"]))
    check(f"{s['id']}: its form fields are legal option names and carry the rules of the value they feed", all(M.NAME.match(f["name"]) for f in e["fields"]))
by = {s["id"]: M.tool_entry("my." + s["id"], M.validate(s["recipe"], tools, chk)[0], tools, "") for s in starters}
check("the one-website starter asks for the address once and feeds it to both steps", [f["name"] for f in by["one-website-deep-look"]["fields"]] == ["pack", "site"] and by["one-website-deep-look"]["fields"][1]["type"] == "url")
check("the engine starter offers the real engine choice list of the tool it copies from", by["prepare-todays-sends"]["fields"][0]["type"] == "choice")
check("the two ask-nothing starters have an empty form, ready to schedule", by["morning-routine"]["fields"] == [] and by["monday-money-check"]["fields"] == [])
from dse import schedules as S  # noqa: E402
check("and a recipe with an empty form can be scheduled as it is", S.validate({"frequency": "weekdays", "at_time": "07:00", "tool": "my.morning-routine", "params": {}}, {"my.morning-routine": by["morning-routine"]}) == [])
ids = {x["id"] for x in starters}
check("the per-path starters are all present", {"smb-local-leads", "carebridge-home-care", "voiceai-phone-businesses", "automation-back-office", "revenue-shops", "gtm-companies", "list-file-to-todays-list", "ascent-review"} <= ids)
real_packs = {c["value"] for c in next(f for f in tools["dse.list"]["fields"] if f["name"] == "pack")["choices"]}
fixed = [st["values"]["pack"] for x in starters for st in x["recipe"]["steps"] if st["tool"] in ("dse.list", "dse.check") and not str(st["values"]["pack"]).startswith("{{")]
check("every website check the path starters fix is one this toolkit really has (a pack file in packs/)", len(fixed) >= 6 and all(p in real_packs for p in fixed), str(set(fixed) - real_packs))
check("the file starters (shops, companies) ask for the member's own list through a file field of the real tool", all(by[i]["fields"][0]["type"] == "file" and by[i]["fields"][0]["glob"] == "my-lists/*.csv" for i in ("revenue-shops", "gtm-companies")), str([by[i]["fields"][0] for i in ("revenue-shops", "gtm-companies")]))
print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
