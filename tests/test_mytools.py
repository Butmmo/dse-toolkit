"""Tests for My tools (recipes): checking, merging into the catalog, running a chain, and the limits that make sharing them safe.   python tests/test_mytools.py"""
import copy
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import mytools as M  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


spec_ = importlib.util.spec_from_file_location("dse_runner", ROOT / "bridge" / "runner.py")
R = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(R)

# ---- a tiny fake toolkit: two tools that make and count a file, one that fails, and a Dev tool (never allowed in a recipe)
STEP = ROOT / "tests" / "zz_step.py"
OUT = ROOT / "tests" / "zz-out"
STEP.write_text('''import sys, pathlib
out = pathlib.Path(__file__).parent / "zz-out"
cmd = sys.argv[1]
if cmd == "make":
    out.mkdir(exist_ok=True)
    (out / (sys.argv[2] + ".csv")).write_text("a\\n1\\n2\\n3\\n")
    print("made", sys.argv[2])
elif cmd == "count":
    print("rows", len(open(sys.argv[2]).read().strip().splitlines()) - 1)
elif cmd == "fail":
    sys.exit(3)
''', encoding="utf-8")
TOOLS = {
    "t.make": {"label": "Make a list", "group": "Find clients", "script": "tests/zz_step.py", "args": [{"lit": "make"}, {"field": "word"}], "timeout_min": 1,
               "fields": [{"name": "word", "label": "A word", "type": "text", "required": True, "max": 20, "pattern": "[a-z]{1,20}", "hint": "lowercase"}],
               "outputs": [{"glob": "tests/zz-out/*.csv", "upload": True}]},
    "t.count": {"label": "Count a list", "group": "Check websites", "script": "tests/zz_step.py", "args": [{"lit": "count"}, {"field": "file"}], "timeout_min": 1,
                "fields": [{"name": "file", "label": "A list", "type": "file", "required": True, "glob": "tests/zz-out/*.csv"}]},
    "t.fail": {"label": "Always fails", "group": "Find clients", "script": "tests/zz_step.py", "args": [{"lit": "fail"}], "timeout_min": 1, "fields": []},
    "t.pick": {"label": "Pick", "group": "Find clients", "script": "tests/zz_step.py", "args": [{"lit": "make"}, {"field": "kind"}], "timeout_min": 2,
               "fields": [{"name": "kind", "label": "Kind", "type": "choice", "required": True, "choices": [{"value": "dentists", "label": "Dentists"}, {"value": "plumbers", "label": "Plumbers"}]},
                          {"name": "n", "label": "How many", "type": "int", "min": 1, "max": 50, "default": 10}]},
    "dev.run": {"label": "Run a command", "group": "Dev", "script": "tests/zz_step.py", "args": [], "fields": []},
    "dse.doctor": {"label": "System check", "group": "Setup", "script": "tests/zz_step.py", "args": [], "fields": []},
}
CAT = {"version": 1, "tools": TOOLS}
checker = M._checker(R)

TMP = Path(tempfile.mkdtemp(prefix="zz-mytools-"))
M.MINE = TMP / "my-tools"
M.SHARED = M.MINE / "shared"
M.base_catalog = lambda r=None: (R, copy.deepcopy(CAT))

GOOD = {"name": "Make and count", "help": "Makes a list then counts it.",
        "inputs": [{"name": "word", "label": "Which word", "type": "text", "from": {"step": 1, "field": "word"}}],
        "steps": [{"tool": "t.make", "label": "Make it", "values": {"word": "{{word}}"}}, {"tool": "t.count", "label": "Count it", "values": {"file": "{{prev.file}}"}}]}

# ---------------------------------------------------------------- validation
clean, pr = M.validate(GOOD, TOOLS, checker)
check("a good recipe passes with no problems", not pr and len(clean["steps"]) == 2, str(pr))


def problems(**ch):
    s = copy.deepcopy(GOOD)
    for k, v in ch.items():
        s[k] = v
    return M.validate(s, TOOLS, checker)[1]


check("a Dev tool is refused in a step", any("not a tool a recipe may use" in x for x in problems(steps=[{"tool": "dev.run", "values": {}}])))
check("a Setup tool is refused", any("not a tool a recipe may use" in x for x in problems(steps=[{"tool": "dse.doctor", "values": {}}])))
check("another recipe, a studio tool or an extra cannot be a step", all(any("not a tool a recipe may use" in x for x in problems(steps=[{"tool": k, "values": {}}])) for k in ("my.x", "shared.x", "studio.x", "extra.x")))
check("an unknown tool is refused", any("does not exist" in x for x in problems(steps=[{"tool": "t.nope", "values": {}}])))
check("a value the tool does not have is refused", any("no value called" in x for x in problems(steps=[{"tool": "t.make", "values": {"word": "{{word}}", "zzz": "x"}}])))
check("a placeholder mixed into text is refused", any("whole value" in x for x in problems(steps=[{"tool": "t.make", "values": {"word": "pre-{{word}}"}}])))
check("a placeholder for an input that does not exist is refused", any("not one of the recipe's inputs" in x for x in problems(steps=[{"tool": "t.make", "values": {"word": "{{nope}}"}}])))
check("prev.file in the first step is refused", any("does not run before" in x for x in problems(steps=[{"tool": "t.count", "values": {"file": "{{prev.file}}"}}], inputs=[])))
check("step2.file inside step 2 (itself) is refused", any("does not run before" in x for x in problems(steps=[GOOD["steps"][0], {"tool": "t.count", "values": {"file": "{{step2.file}}"}}])))
check("a previous file can only go to a file value", any("only a file value" in x for x in problems(steps=[GOOD["steps"][0], {"tool": "t.make", "values": {"word": "{{prev.file}}"}}])))
check("a fixed file name is refused (files come from an input or a previous step)", any("not a fixed name" in x for x in problems(steps=[GOOD["steps"][0], {"tool": "t.count", "values": {"file": "a.csv"}}])))
check("a fixed value is checked by the tool's own rule", any("characters" in x or "not allowed" in x for x in problems(inputs=[], steps=[{"tool": "t.make", "values": {"word": "UPPER 1"}}])), str(problems(inputs=[], steps=[{"tool": "t.make", "values": {"word": "UPPER 1"}}])))
check("a missing required value is named", any("is needed" in x for x in problems(inputs=[], steps=[{"tool": "t.make", "values": {}}])))
check("an input no step uses is refused", any("never used" in x for x in problems(inputs=GOOD["inputs"] + [{"name": "extra", "label": "x", "type": "text"}])))
check("more than 8 steps is refused", any("1 to 8 steps" in x for x in problems(steps=[{"tool": "t.fail", "values": {}}] * 9)))
check("no steps is refused", any("1 to 8 steps" in x for x in problems(steps=[])))
check("a bad name is refused", any("name needs" in x for x in problems(name="ab")))
check("a type mismatch between an input and a file value is refused", any("same kind" in x for x in problems(inputs=[{"name": "word", "label": "w", "type": "file"}])))
check("a number as a fixed value is accepted for an int field", not M.validate({"name": "Pick some", "inputs": [], "steps": [{"tool": "t.pick", "values": {"kind": "dentists", "n": 5}}]}, TOOLS, checker)[1])
check("a fixed choice outside the list is refused", bool(M.validate({"name": "Pick some", "inputs": [], "steps": [{"tool": "t.pick", "values": {"kind": "bakers"}}]}, TOOLS, checker)[1]))
check("not an object", M.validate("x", TOOLS)[1] == ["the recipe is not an object"])

# ---------------------------------------------------------------- the catalog entry
e = M.tool_entry("my.make-and-count", clean, TOOLS, " (mine)")
check("it becomes a tool in the My tools group", e["group"] == "My tools" and e["label"] == "Make and count (mine)")
check("its form copies the rules of the value it feeds (pattern, max)", e["fields"][0]["pattern"] == "[a-z]{1,20}" and e["fields"][0]["max"] == 20 and e["fields"][0]["type"] == "text", str(e["fields"]))
check("its command runs the recipe by key with one option per input", e["args"] == [{"lit": "mytool"}, {"lit": "run"}, {"lit": "my.make-and-count"}, {"opt": "--in-word", "field": "word"}])
check("the help lists the steps so you see what it does before you press Run", "1. Make it." in e["help"] and "2. Count it." in e["help"] and "Nothing is sent" in e["help"])
check("its time limit adds up the steps and its outputs come from the steps", e["timeout_min"] == 2 and e["outputs"] == [{"glob": "tests/zz-out/*.csv", "upload": True}])
pk = {"name": "Pick and make", "inputs": [{"name": "kind", "label": "Kind of business", "type": "choice", "from": {"step": 1, "field": "kind"}}],
      "steps": [{"tool": "t.pick", "values": {"kind": "{{kind}}"}}]}
ep = M.tool_entry("my.pick", M.validate(pk, TOOLS, checker)[0], TOOLS, "")
check("a choice input gets the choices of the value it feeds", [c["value"] for c in ep["fields"][0]["choices"]] == ["dentists", "plumbers"])

# ---------------------------------------------------------------- files on this PC
M.MINE.mkdir(parents=True)
M.SHARED.mkdir(parents=True)
(M.MINE / "make-and-count.json").write_text(json.dumps({"slug": "make-and-count", "name": "Make and count", "spec": GOOD}), encoding="utf-8")
(M.MINE / "old-one.json").write_text(json.dumps({"slug": "old-one", "name": "Old", "spec": GOOD, "archived": True}), encoding="utf-8")
(M.MINE / "gone.json").write_text(json.dumps({"slug": "gone", "name": "Gone", "spec": GOOD, "removed_in_citadel": "2026-11-16"}), encoding="utf-8")
(M.MINE / "Bad Name.json").write_text("{}", encoding="utf-8")
(M.SHARED / "from-dbi.json").write_text(json.dumps({"slug": "from-dbi", "name": "From DBI", "spec": GOOD, "active": True}), encoding="utf-8")
(M.SHARED / "off.json").write_text(json.dumps({"slug": "off", "name": "Off", "spec": GOOD, "active": False}), encoding="utf-8")
(M.MINE / "broken.json").write_text(json.dumps({"slug": "broken", "name": "Broken", "spec": {"name": "Broken one", "steps": [{"tool": "dev.run", "values": {}}]}}), encoding="utf-8")
ent = M.entries(CAT)
check("active recipes become tools: mine, and the ones DBI shared", set(ent) == {"my.make-and-count", "shared.from-dbi"}, str(sorted(ent)))
check("archived, removed, switched off, badly named and invalid recipes are not offered", "my.old-one" not in ent and "my.gone" not in ent and "shared.off" not in ent and "my.broken" not in ent)
check("a shared recipe says it came from DBI", ent["shared.from-dbi"]["label"].endswith("(from DBI)"))
rep = M.check_report()
check("the check names the broken recipe and what is wrong", "FIX  my.broken" in rep and "not a tool a recipe may use" in rep and "OK   my.make-and-count" in rep, rep)

# ---------------------------------------------------------------- running a chain
lines = []
code = M.run("my.make-and-count", ["--in-word", "alpha"], lines.append)
out = "\n".join(lines)
check("a chain runs both steps and hands the file from step 1 to step 2", code == 0 and "made alpha" in out and "rows 3" in out and "step 1 made tests/zz-out/alpha.csv" in out and "all 2 step(s) ran" in out, out)
lines = []
code = M.run("my.make-and-count", ["--in-word", "UPPER"], lines.append)
check("a value the tool refuses stops the chain before anything runs", code == 1 and "refused" in "\n".join(lines) and "Step 2" not in "\n".join(lines), "\n".join(lines))
lines = []
code = M.run("my.make-and-count", [], lines.append)
check("a missing required input is named", code == 2 and "required" in "\n".join(lines))
FAILING = {"name": "Fail then make", "inputs": [], "steps": [{"tool": "t.fail", "values": {}}, {"tool": "t.make", "values": {"word": "never"}}]}
(M.MINE / "fail-first.json").write_text(json.dumps({"slug": "fail-first", "name": "Fail then make", "spec": FAILING}), encoding="utf-8")
lines = []
code = M.run("my.fail-first", [], lines.append)
check("a failing step stops the chain: the next step is not run", code == 1 and "exit code 3" in "\n".join(lines) and not (OUT / "never.csv").exists(), "\n".join(lines))
lines = []
check("an unknown recipe is said plainly", M.run("my.nope", [], lines.append) == 2 and "no active recipe" in lines[0])
NOFILE = {"name": "Count without a file", "inputs": [], "steps": [{"tool": "t.fail", "values": {}}, {"tool": "t.count", "values": {"file": "{{prev.file}}"}}]}
(M.MINE / "no-file.json").write_text(json.dumps({"slug": "no-file", "name": "Count without a file", "spec": NOFILE}), encoding="utf-8")

# ---------------------------------------------------------------- which file is handed on
from types import SimpleNamespace  # noqa: E402
fake_r = SimpleNamespace(snapshot=lambda g: {Path("x/a-enriched.md"): 200.0, Path("x/a-enriched.csv"): 100.0})
check("a tool that writes a list and a summary hands on the list, even when the summary is newer", M.newest_output(fake_r, ["x/*"], {}) == Path("x/a-enriched.csv"))
check("with only a summary, that is handed on", M.newest_output(SimpleNamespace(snapshot=lambda g: {Path("x/s.md"): 5.0}), ["x/*"], {}) == Path("x/s.md"))
check("files that did not change are not handed on", M.newest_output(fake_r, ["x/*"], {Path("x/a-enriched.csv"): 100.0, Path("x/a-enriched.md"): 200.0}) is None)

# ---------------------------------------------------------------- saving
rf = TMP / "r.json"
rf.write_text(json.dumps(GOOD), encoding="utf-8")
msg = M.save(str(rf))
check("save checks, then writes the recipe under a safe name", "Saved my tool 'make-and-count'" in msg and (M.MINE / "make-and-count.json").exists(), msg)
rf.write_text(json.dumps({**GOOD, "steps": [{"tool": "dev.run", "values": {}}]}), encoding="utf-8")
check("save refuses an invalid recipe and says why", M.save(str(rf)).startswith("Not saved") and "not a tool a recipe may use" in M.save(str(rf)))
check("save of something that is not JSON is said plainly", "not a recipe" in M.save(str(TMP / "nothing.json")))

# ---------------------------------------------------------------- the module itself
src = (ROOT / "dse" / "mytools.py").read_text(encoding="utf-8")
check("no em dash", chr(0x2014) not in src)
check("a recipe never sends: the module has no network or mail code", not any(w in src for w in ("smtplib", "requests", "urllib.request", "socket")))

shutil.rmtree(OUT, ignore_errors=True)
STEP.unlink(missing_ok=True)
shutil.rmtree(TMP, ignore_errors=True)
print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
