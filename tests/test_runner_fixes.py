"""19 Nov fixes: geocode retry, tzdata warning, runner.restart.   python tests/test_runner_fixes.py"""
import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


from dse import places as P, herald_send as S

# ---- geocode retry
class Resp:
    def __init__(self, code=200, ctype="application/json", data=None):
        self.status_code, self.headers, self._d = code, {"Content-Type": ctype}, data

    def json(self):
        if self._d is None:
            raise ValueError("Expecting value")
        return self._d


calls = []
def seq(*rs):
    it = iter(rs)
    def get(url, **kw):
        calls.append(kw)
        return next(it)
    return get

with mock.patch.object(P.time, "sleep"), mock.patch.object(P.requests, "get", seq(Resp(200, "text/html"), Resp(429, "text/html"), Resp(200, data=[{"lat": "1.5", "lon": "2.5"}]))):
    hits = P._nominatim("Tampa FL", "US")
check("a non-JSON reply, then a rate limit, then a good one: gives the hits", hits and hits[0]["lat"] == "1.5")
check("every try sends the same User-Agent", len({c["headers"]["User-Agent"] for c in calls}) == 1 and "DSEToolkit" in calls[0]["headers"]["User-Agent"])
waits = []
calls.clear()
with mock.patch.object(P.time, "sleep", side_effect=waits.append), mock.patch.object(P.requests, "get", seq(Resp(200, "text/html"), Resp(503, "text/html"), Resp(200, data=[]))):
    P._nominatim("Tampa FL", "US")
check("the waits grow and start with the 1 request a second rule", waits[0] >= 1.0 and waits == sorted(waits) and len(set(waits)) == len(waits), str(waits))
with mock.patch.object(P.time, "sleep"), mock.patch.object(P.requests, "get", lambda *a, **k: Resp(200, "text/html")):
    try:
        P._nominatim("Leeds", "GB")
        msg = ""
    except SystemExit as e:
        msg = str(e)
check("failing every time names the city and says a re-run resumes", "Leeds" in msg and "run it again" in msg, msg)

# ---- tzdata warning
w = S.tz_warning("Africa/Lagos")
check("the warning is loud, names the zone and the fix", "WARNING" in w and "Africa/Lagos" in w and "pip install tzdata" in w)
ok, why = S.decide({"id": 1, "lead_status": "new", "attempts": 0, "mailbox": {"id": "m", "timezone": "Nowhere/Land", "window_start": "09:00", "window_end": "17:00"}, "scheduled_day": "2026-11-19"},
                   S.dt.datetime.now(S.dt.timezone.utc), {}, {}, set(), True)
check("a missing zone is held with the TZ_MISSING reason the pass looks for", not ok and why.startswith(S.TZ_MISSING))
src = (ROOT / "dse" / "herald_send.py").read_text(encoding="utf-8")
check("the pass prints the warning through its log function", "out(tz_warning(" in src)
ps = (ROOT / "bridge" / "start-runner.ps1").read_text(encoding="utf-8")
check("start-runner.ps1 requires tzdata on Windows and tells exit 75 apart", "__import__('tzdata')" in ps and "-eq 75" in ps)
check("the installer and requirements include tzdata", "tzdata" in (ROOT / "bridge" / "install.ps1").read_text(encoding="utf-8") and "tzdata" in (ROOT / "requirements.txt").read_text(encoding="utf-8"))

# ---- runner.restart
spec_ = importlib.util.spec_from_file_location("dse_runner", ROOT / "bridge" / "runner.py")
R = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(R)
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
t = cat["tools"].get("runner.restart")
check("runner.restart is in the catalog with no values", t and t["fields"] == [] and t["label"] == "Restart the HQ runner")
fin = []
class Api:
    def finish(self, *a):
        fin.append(a)
r = R.run_job(Api(), cat, {"id": "job-1", "tool": "runner.restart", "params": {}})
check("it reports done to Citadel first, then asks for the restart", r["status"] == "done" and fin and fin[0][1] == "done" and R.RESTART_REQUESTED)
R.RESTART_REQUESTED = False
fin.clear()
r = R.run_job(Api(), cat, {"id": "job-2", "tool": "runner.restart", "params": {"x": 1}})
check("values are refused and no restart happens", r["status"] == "failed" and not R.RESTART_REQUESTED and fin[0][1] == "failed")
check("the exit code is the one the wrapper knows", R.RESTART_EXIT == 75)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
