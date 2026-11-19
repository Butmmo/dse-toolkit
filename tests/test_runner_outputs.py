"""A tool whose outputs are bare glob strings (dse.enrich and ten more) must not stop the runner.   python tests/test_runner_outputs.py"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


spec_ = importlib.util.spec_from_file_location("dse_runner", ROOT / "bridge" / "runner.py")
R = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(R)

check("a bare glob string becomes a {glob, upload} entry", R.norm_outputs(["a/*.csv"]) == [{"glob": "a/*.csv", "upload": True}])
check("an entry that is already a dict is kept as it is", R.norm_outputs([{"glob": "b/*.md", "upload": False, "label": "x"}]) == [{"glob": "b/*.md", "upload": False, "label": "x"}])
check("none or empty gives an empty list", R.norm_outputs(None) == [] and R.norm_outputs([]) == [])
raw = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
strs = [k for k, t in raw["tools"].items() if any(isinstance(o, str) for o in t.get("outputs", []))]
check("the real catalog does have string outputs (so this matters)", "dse.enrich" in strs, str(strs))
check("every real tool's outputs are usable after normalising", all(all("glob" in o for o in R.norm_outputs(t.get("outputs"))) for t in raw["tools"].values()))

# run_job on a tool with string outputs: it must get past the output setup (this raised TypeError before) and finish
ran = []


class Api:
    def finish(self, *a):
        ran.append(a)


cat = {"tools": {"t.str": {"label": "t", "script": "dse.py", "args": [{"lit": "nothing-here"}], "fields": [], "timeout_min": 1, "outputs": ["my-lists/*-zz-never-*.csv"]}}}
err = None
try:
    res = R.run_job(Api(), cat, {"id": "j1", "tool": "t.str", "params": {}})
except TypeError as e:
    err, res = str(e), {}
check("run_job on a tool with string outputs does not raise", err is None, str(err))
check("and the job is finished and reported (failed here: the command does not exist)", len(ran) == 1 and ran[0][1] == "failed", str(ran))

# an unexpected error in one job fails that job and the runner carries on
def explode(api, cat, job, dry=False):
    raise TypeError("string indices must be integers")


ran.clear()
orig = R.run_job
R.run_job = explode
err = None
try:
    R.run_job_safely(Api(), {"tools": {}}, {"id": "boom", "tool": "x", "params": {}})
except Exception as e:
    err = repr(e)
R.run_job = orig
check("an unexpected error in a job does not escape (it would stop the runner)", err is None, str(err))
check("and that job is reported as failed, with the reason", len(ran) == 1 and ran[0][0] == "boom" and ran[0][1] == "failed" and "string indices" in ran[0][4], str(ran))
sys.exit(1 if fails else 0)
