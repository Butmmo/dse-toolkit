"""Tests for Tool Studio: the guard, the sandbox, the approval gate, drafting and publishing.   python tests/test_studio.py"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import studio as S  # noqa: E402
from dse import studio_guard as G  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


TMP = Path(tempfile.mkdtemp(prefix="zz-studio-"))
S.STUDIO, S.EXTRAS, S.WORK, S.CONFIG = TMP / "studio", TMP / "extras", TMP / "work", TMP / "studio.json"

# ---------------------------------------------------------------- the guard
GOOD = '''from dse_sdk import inputs, log, write_csv
rows = [{"word": inputs["word"], "n": i} for i in range(int(inputs["count"]))]
write_csv("out.csv", rows)
log("wrote", len(rows), "rows for", inputs["word"])
'''
check("a plain tool passes the guard", G.scan(GOOD) == [], str(G.scan(GOOD)))
BAD = {
    "import os": "import os\nos.system('dir')",
    "import subprocess": "import subprocess",
    "import socket": "import socket",
    "import requests": "import requests",
    "import urllib": "import urllib.request",
    "from pathlib": "from pathlib import Path",
    "relative import": "from . import x",
    "open()": "open('x.txt')",
    "eval": "eval('1+1')",
    "exec": "exec('x=1')",
    "compile": "compile('1','a','eval')",
    "__import__": "__import__('os')",
    "getattr": "getattr(1, 'real')",
    "dunder class": "x = ().__class__",
    "dunder subclasses": "x = ().__class__.__bases__[0].__subclasses__()",
    "dunder globals": "def f(): pass\nf.__globals__",
    "underscore attribute (a module's hidden os)": "import random\nrandom._os.system('dir')",
    "dunder text": "x = '__import__'",
    "format reaching in": "'{0.real}'.format(1)",
    "format_map": "'{a}'.format_map({'a': 1})",
    "globals()": "globals()",
    "input()": "input()",
    "global": "x = 1\ndef f():\n    global x",
    "async": "async def f(): pass",
    "breakpoint": "breakpoint()",
    "syntax error": "def (",
    "empty": "   ",
}
for name, code in BAD.items():
    check(f"the guard refuses: {name}", len(G.scan(code)) > 0, code)
check("too long is refused", G.scan("x = 1\n" * 20000)[0].startswith("the code is longer"))
check("allowed modules include json, csv, re, math, datetime", all(m in G.SAFE_MODULES for m in ("json", "csv", "re", "math", "datetime")))
check("no module that can reach the system is allowed", not ({"os", "sys", "subprocess", "socket", "shutil", "ctypes", "importlib", "pathlib", "urllib", "requests", "io", "builtins", "inspect", "pickle", "threading", "multiprocessing"} & G.SAFE_MODULES))

# ---------------------------------------------------------------- the sandbox: what a tool that passes the guard still cannot do
S.WORK.mkdir(parents=True)
(TMP / "code").mkdir()


def run_code(code, values=None, timeout=20, name="t"):
    f = TMP / "code" / f"{name}.py"
    f.write_text(code, encoding="utf-8")
    lines = []
    exit_code, timed = S.execute(f, name, values or {}, timeout, lines.append)
    return exit_code, timed, "\n".join(lines)


c, t, out = run_code(GOOD, {"word": "hi", "count": "3"})
check("a good tool runs, reads its inputs and writes a result file", c == 0 and "wrote 3 rows for hi" in out and (S.WORK / "t" / "out.csv").read_text(encoding="utf-8").count("\n") == 4, out)
c, t, out = run_code("from dse_sdk import log\nwhile True:\n    pass\n", timeout=3, name="loop")
check("a tool that never stops is killed at its time limit", t is True, out)
c, t, out = run_code("from dse_sdk import http_get\nhttp_get('https://www.linkedin.com/in/someone')\n")
check("LinkedIn (and Instagram, Facebook, X, Google Maps) are never fetched", c == 1 and "never fetched" in out, out)
c, t, out = run_code("from dse_sdk import http_get\nhttp_get('http://127.0.0.1:9/')\n")
check("your own network and this PC are never reached", c == 1 and "not on the public internet" in out, out)
c, t, out = run_code("from dse_sdk import http_get\nhttp_get('file:///C:/Windows/win.ini')\n")
check("only http and https addresses", c == 1 and "only http" in out, out)
c, t, out = run_code("from dse_sdk import read_text\nread_text('bridge/.env')\n")
check("the runner's settings file cannot be read", c == 1 and ("may read only" in out or "secret" in out), out)
c, t, out = run_code("from dse_sdk import read_text\nread_text('../outside.txt')\n")
check("a path leaving the toolkit is refused", c == 1 and "not a path inside" in out, out)
secret = ROOT / "data" / "zz-secret-token.txt"
secret.parent.mkdir(exist_ok=True)
secret.write_text("x", encoding="utf-8")
c, t, out = run_code("from dse_sdk import read_text\nread_text('data/zz-secret-token.txt')\n")
secret.unlink()
check("a file that looks like a secret cannot be read even under data/", c == 1 and "looks like a secret" in out, out)
c, t, out = run_code("from dse_sdk import write_text\nwrite_text('../x.csv', 'a')\n")
check("a result file cannot leave the work folder", c == 1 and "plain name" in out, out)
c, t, out = run_code("from dse_sdk import write_text\nwrite_text('run.bat', 'a')\n")
check("only csv, json, txt and md results can be written", c == 1 and "ending in" in out, out)
c, t, out = run_code("from dse_sdk import write_text\nfor i in range(25):\n    write_text('f%d.txt' % i, 'a')\n")
check("at most 20 result files", c == 1 and "at most 20" in out, out)
c, t, out = run_code("import os\n")
check("the launcher re-checks the code even if the parent did not", c == 2 and "Refused by the Tool Studio guard" in out, out)
c, t, out = run_code("import dse_sdk\nlog = dse_sdk.log\nlog(dse_sdk.socket)\n")
check("the tool gets only the sdk's public names, not its inner modules", c == 1 and "socket" in out and "AttributeError" in out, out)
c, t, out = run_code("from dse_sdk import socket\n")
check("importing a hidden name from the sdk fails", c == 1 and ("socket" in out), out)
c, t, out = run_code("print(len(str(1)))\nraise SystemExit(0)\n")
check("a tool may stop itself", c == 0, out)
import os as _os  # noqa: E402
_os.environ["HQ_TEST_SECRET"] = "shh"
_os.environ["HF_TOKEN"] = "hf_shh"
env = S._env()
check("your keys and settings are not passed to the tool's process", "HQ_TEST_SECRET" not in env and "HF_TOKEN" not in env and "ANTHROPIC_API_KEY" not in env)

# ---------------------------------------------------------------- drafting with a (fake) AI
MAN = {"label": "Word repeater", "help": "Repeats a word into a CSV.", "timeout_min": 2,
       "fields": [{"name": "word", "label": "A word", "type": "text", "required": True, "max": 30}, {"name": "count", "label": "How many", "type": "int", "min": 1, "max": 50, "default": 3}],
       "sample": {"word": "hello", "count": 4}}
answers = []


def brain(system, user):
    answers.append(user)
    return answers_q.pop(0)


answers_q = ["```json\n" + json.dumps({"manifest": MAN, "code": GOOD}) + "\n```"]
rep = S.draft("repeater", "repeat a word into a csv", brain)
check("a draft is saved, not enabled, and shown with its approval code", "Draft saved as studio/repeater" in rep and "NOT switched on" in rep and "Approval code" in rep, rep)
t = S.load("repeater")
check("the saved draft is off", not t["state"].get("enabled") and not t["state"].get("approved"))
check("drafting over an existing name is refused (revise is the way)", "already exists" in S.draft("repeater", "again", brain))

answers.clear()
answers_q = [json.dumps({"manifest": MAN, "code": "import os\nos.system('dir')"}), json.dumps({"manifest": MAN, "code": GOOD})]
rep = S.draft("second", "x tool please", brain)
check("a refused draft is sent back with the reasons, and the corrected one is saved", "Draft saved" in rep and len(answers) == 2 and "refused" in answers[1] and "import os is not allowed" in answers[1], rep)
answers_q = [json.dumps({"manifest": MAN, "code": "import os"}), json.dumps({"manifest": MAN, "code": "import os"})]
rep = S.draft("third", "x tool please", brain)
check("two refused drafts save nothing", "refused by the guard" in rep and not (S.STUDIO / "third").exists(), rep)
answers_q = ["I am sorry, here is some prose", "still prose"]
rep = S.draft("fourth", "x tool please", brain)
check("an answer that is not the JSON object saves nothing", "refused by the guard" in rep and not (S.STUDIO / "fourth").exists(), rep)
check("a bad name and a too-short description are refused before any AI is asked", "not a tool name" in S.draft("Bad Name", "x tool", brain) and "Describe what" in S.draft("fine-name", "x", brain))
answers.clear()
answers_q = [json.dumps({"manifest": MAN, "code": GOOD + "log('revised')\n"})]
rep = S.revise("repeater", "also say revised", brain)
check("revise sends the current tool to the AI and switches the tool off again", "Draft saved" in rep and "current tool" in answers[0] and "revised" in S.load("repeater")["code"])

# ---------------------------------------------------------------- the gate: test, approve, enable
check("nothing is enabled while Tool Studio is off", "off on this PC" in S.enable("repeater", "abcd1234") and not S.entries({}))
check("Tool Studio is off by default", S.enabled() is False)
S.set_enabled(True)
check("turning it on is a local switch", S.enabled() is True)
check("enabling before a test is refused", "has not passed a test" in S.enable("repeater", S.load("repeater")["hash"][:8]))
rep = S.test("repeater")
check("the test runs the tool on its sample values and shows the approval code", "Test PASSED" in rep and "out.csv" in rep and S.load("repeater")["hash"][:8] in rep, rep)
check("enabling with the wrong approval code is refused", "does not match" in S.enable("repeater", "00000000"))
check("enabling without the code is refused", "does not match" in S.enable("repeater", ""))
h = S.load("repeater")["hash"]
msg = S.enable("repeater", h[:8])
check("the exact code, tested and approved, is enabled", msg.startswith("Enabled") and "studio.repeater" in S.entries({}), msg)
ent = S.entries({})["studio.repeater"]
check("it appears as a tool in the Studio group with its form and result files", ent["group"] == "Studio" and [f["name"] for f in ent["fields"]] == ["word", "count"] and ent["outputs"][0]["glob"] == "data/studio-work/repeater/*" and ent["args"][:3] == [{"lit": "studio"}, {"lit": "run"}, {"lit": "studio.repeater"}])
lines = []
code = S.run("studio.repeater", ["--in-word", "abc", "--in-count", "2"], lines.append)
check("pressing Run executes it under the guard with the form's values", code == 0 and "wrote 2 rows for abc" in "\n".join(lines), "\n".join(lines))
lines = []
code = S.run("studio.repeater", ["--in-word", "abc", "--in-count", "999"], lines.append)
check("a value outside the form's limits is refused before the code runs", code == 2 and "Not run" in "\n".join(lines), "\n".join(lines))

# editing one character switches it off
p = S.STUDIO / "repeater" / "tool.py"
p.write_text(p.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
check("one changed character and it is no longer offered", "studio.repeater" not in S.entries({}))
lines = []
check("and it will not run until tested and approved again", S.run("studio.repeater", ["--in-word", "a"], lines.append) == 2 and "not approved" in "\n".join(lines), "\n".join(lines))
check("a manifest edit counts too", S.load("repeater")["hash"] != h)
S.test("repeater")
S.enable("repeater", S.load("repeater")["hash"][:8])
check("tested and approved again, it is back", "studio.repeater" in S.entries({}))
S.set_enabled(False)
check("turning Tool Studio off removes every studio tool at once", not [k for k in S.entries({}) if k.startswith("studio.")])
S.set_enabled(True)
check("disable switches one tool off", "Disabled" in S.disable("repeater") and "studio.repeater" not in S.entries({}))
S.enable("repeater", "x")

# a failing test is not approvable
(S.STUDIO / "broken").mkdir()
(S.STUDIO / "broken" / "tool.json").write_text(json.dumps(MAN), encoding="utf-8")
(S.STUDIO / "broken" / "tool.py").write_text("from dse_sdk import inputs\nraise ValueError('boom')\n", encoding="utf-8")
rep = S.test("broken")
check("a tool that fails its test says so, shows why, and cannot be enabled", "Test FAILED" in rep and "boom" in rep and "has not passed a test" in S.enable("broken", S.load("broken")["hash"][:8]), rep)
(S.STUDIO / "evil").mkdir()
(S.STUDIO / "evil" / "tool.json").write_text(json.dumps(MAN), encoding="utf-8")
(S.STUDIO / "evil" / "tool.py").write_text("import os\n", encoding="utf-8")
check("a tool the guard refuses is not tested at all", "Fix these first" in S.test("evil"))

# ---------------------------------------------------------------- control tools exist only while Tool Studio is on
CT = {"tools": {"dse.studio_test": {"fields": [{"name": "slug", "choices_from": "studio_tools", "choices": []}]}, "dse.doctor": {"fields": []}}}
S.set_enabled(False)
check("a PC that never turned Tool Studio on offers none of its control tools", list(S.apply(json.loads(json.dumps(CT)))["tools"]) == ["dse.doctor"])
S.set_enabled(True)
a = S.apply(json.loads(json.dumps(CT)))
check("with it on they are offered, and the tool picker lists your tools", "dse.studio_test" in a["tools"] and "repeater" in [c["value"] for c in a["tools"]["dse.studio_test"]["fields"][0]["choices"]])

# ---------------------------------------------------------------- publishing for everyone goes through the repository
S.set_enabled(True)
S.test("repeater")
S.enable("repeater", S.load("repeater")["hash"][:8])
check("publish refuses a tool you have not approved", "enable it for yourself first" in S.publish("broken"))
msg = S.publish("repeater")
check("publish copies the approved tool into extras/ and tells you to review and commit it", (S.EXTRAS / "repeater" / "tool.py").is_file() and "git add extras/repeater" in msg and "Nothing has been sent" in msg, msg)
ex = S.entries({})
check("extras are offered as extra.<name> (to everyone who has the toolkit)", "extra.repeater" in ex and ex["extra.repeater"]["group"] == "Extra tools" and ex["extra.repeater"]["outputs"][0]["glob"] == "data/studio-work/extra-repeater/*")
S.set_enabled(False)
check("extras do not need the Studio switch: they arrive reviewed, with the toolkit", "extra.repeater" in S.entries({}))
lines = []
code = S.run("extra.repeater", ["--in-word", "zz", "--in-count", "1"], lines.append)
check("an extra tool runs under the very same guard", code == 0 and "wrote 1 rows for zz" in "\n".join(lines), "\n".join(lines))
(S.EXTRAS / "repeater" / "tool.py").write_text("import os\nos.system('dir')\n", encoding="utf-8")
check("an extra whose files changed after publishing is not offered and does not run", "extra.repeater" not in S.entries({}))
lines = []
check("and says why", S.run("extra.repeater", [], lines.append) == 2 and "changed after it was published" in "\n".join(lines))

# ---------------------------------------------------------------- the module
src = "".join((ROOT / "dse" / n).read_text(encoding="utf-8") for n in ("studio.py", "studio_guard.py", "studio_sdk.py", "studio_run.py", "procs.py", "cli_tools.py"))
check("no em dash", chr(0x2014) not in src)
check("nothing in Tool Studio talks to Citadel", "hq_runner" not in src and "supabase" not in src.lower())

shutil.rmtree(TMP, ignore_errors=True)
print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
