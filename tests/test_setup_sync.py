"""Tests for the Setup checklist sync: what leaves the PC is only the System check's own lines, with anything key-like hidden.   python tests/test_setup_sync.py"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec_ = importlib.util.spec_from_file_location("setup_sync", ROOT / "bridge" / "setup_sync.py")
S = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(S)
from dse import doctor  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


good = {"area": "This PC", "name": "Engines", "state": "ok", "detail": "2 engine(s)", "fix": ""}
out = S.sanitize([good, {"area": "A", "name": "B", "state": "fix", "detail": "d", "fix": "restart it", "path": "C:/secret", "extra": 1}])
check("only the five known fields are kept", all(set(i) == {"area", "name", "state", "detail", "fix"} for i in out) and len(out) == 2)
check("lines with an unknown state or no shape are dropped", S.sanitize([{"area": "a", "name": "b", "state": "weird"}, "x", None, 5, {"state": "ok"}]) == [{"area": "", "name": "", "state": "ok", "detail": "", "fix": ""}])
KEY = "sk-ant-api03-" + "abcdEFGH12_-" * 4
HF = "hf_" + "abcdefghij1234567890"
JWT = "eyJ" + "a1b2c3d4e5" * 4
LONG = "x" * 60
dirty = S.sanitize([{"area": "a", "name": f"key {KEY}", "state": "ok", "detail": f"token {HF} jwt {JWT} blob {LONG}", "fix": f"run with {KEY}"}])[0]
blob = json.dumps(dirty)
check("a key, a Hugging Face token, a JWT and a long secret-looking string are hidden before anything leaves the PC", not any(x in blob for x in (KEY, HF, JWT, LONG)) and blob.count("[hidden]") >= 4, blob)
check("ordinary words are untouched", S.sanitize([good])[0]["detail"] == "2 engine(s)" and "20261119090000_hq_brief.sql" in S.sanitize([{"area": "a", "name": "n", "state": "fix", "detail": "", "fix": "run 20261119090000_hq_brief.sql in Supabase"}])[0]["fix"])
check("long text is cut", len(S.sanitize([{"area": "a" * 500, "name": "n" * 500, "state": "ok", "detail": "d " * 500, "fix": "f " * 500}])[0]["fix"]) <= 500)
check("at most 80 lines", len(S.sanitize([good] * 200)) == 80)
check("a missing list is fine", S.sanitize(None) == [] and S.sanitize([]) == [])
live = S.sanitize(doctor.collect(None, offline=True))
check("the real offline System check passes through intact", len(live) >= 5 and all(i["state"] in S.STATES for i in live), str(len(live)))
src = (ROOT / "bridge" / "setup_sync.py").read_text(encoding="utf-8")
check("the helper sends only through one function and nothing else", src.count("api.rpc(") == 1 and 'hq_setup_push' in src)
check("a missing database update is named in the helper's last line (the System check turns that into the exact fix)", "has not been run yet" in src and "20261122090000_setup_checklist.sql" in src)
check("no em dash", chr(0x2014) not in src)
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
check("it runs every 5 minutes and as a tool on demand", any(x["script"] == "bridge/setup_sync.py" and x["every_s"] == 300 for x in cat["periodic"]) and cat["tools"]["dse.setup_push"]["script"] == "bridge/setup_sync.py")
print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
