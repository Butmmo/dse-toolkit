"""The recipe Citadel's builder makes is accepted by the toolkit's own validator (same rules, written twice).   python tests/test_mytools_contract.py
tests/fixtures/my-tool-spec.json is written by Citadel's scripts/test-my-tools.mjs from the builder's own code."""
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


TOOLS = {
    "dse.find": {"label": "Leads only", "group": "Find clients", "timeout_min": 5, "outputs": [{"glob": "my-lists/*.csv"}], "fields": [
        {"name": "kind", "label": "Business type", "type": "text", "required": True, "max": 60, "pattern": "[A-Za-z][A-Za-z0-9 &'/-]{2,59}"},
        {"name": "cities", "label": "Cities", "type": "text", "required": True, "max": 300},
        {"name": "max", "label": "How many leads", "type": "int", "min": 5, "max": 200, "default": 100},
        {"name": "words", "label": "Words", "type": "text", "max": 100}]},
    "dse.check": {"label": "Check websites", "group": "Check websites", "timeout_min": 10, "fields": [
        {"name": "list", "label": "A list", "type": "file", "required": True, "glob": "my-lists/*.csv"},
        {"name": "pack", "label": "Check for", "type": "choice", "required": True, "choices": [{"value": "smb", "label": "SMB"}]}]},
}
spec = json.loads((ROOT / "tests" / "fixtures" / "my-tool-spec.json").read_text(encoding="utf-8"))
chk = M._checker(R)
clean, problems = M.validate(spec, TOOLS, chk)
check("the toolkit accepts the recipe Citadel's builder made, with no problems", not problems, str(problems))
check("it keeps every step, input and fixed value", len(clean["steps"]) == 2 and len(clean["inputs"]) == 2 and clean["steps"][0]["values"]["max"] == 40 and clean["steps"][1]["values"]["list"] == "{{prev.file}}")
e = M.tool_entry("my.find-and-check", clean, TOOLS, " (mine)")
check("it becomes a tool whose form copies the rules of the values it asks for", [f["name"] for f in e["fields"]] == ["s1_kind", "s1_cities"] and e["fields"][0]["pattern"] == "[A-Za-z][A-Za-z0-9 &'/-]{2,59}", str(e["fields"]))
check("a Python-side check of every input name is a legal option name", all(M.NAME.match(f["name"]) for f in e["fields"]))
print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
