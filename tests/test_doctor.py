"""Scenario tests for the System check.   python tests/test_doctor.py"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import doctor as D  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def by(items, text):
    return [i for i in items if text.lower() in i["name"].lower()]


NOW = 1_000_000.0
TOOLS = {k: {} for k in D.EXPECTED_TOOLS}
PERIODIC = [{"script": "bridge/brief_sync.py", "every_s": 900}, {"script": "bridge/crm_sync.py", "every_s": 300}, {"script": "bridge/voices_sync.py", "every_s": 21600}]

# ---------------------------------------------------------------- the runner
r = D.check_runner({}, NOW, {}, PERIODIC, TOOLS)
check("no status at all: the runner is not running or too old to report, and the fix is to restart it", r[0]["state"] == "fix" and "restart" in r[0]["fix"].lower() or "start it again" in r[0]["fix"].lower(), str(r))
st = {"started_at": NOW - 3600, "heartbeat": NOW - 20, "runner_id": "office-pc", "tools": 103, "helpers": [h["script"] for h in PERIODIC]}
r = D.check_runner(st, NOW, {"bridge/runner.py": NOW - 7200}, PERIODIC, TOOLS)
check("a live runner with nothing newer on disk is all OK", [i["state"] for i in r] == ["ok", "ok", "ok"] or all(i["state"] == "ok" for i in r), str([(i["name"], i["state"]) for i in r]))
r = D.check_runner({**st, "heartbeat": NOW - 900}, NOW, {}, PERIODIC, TOOLS)
check("a runner that has not reported for 15 minutes is not running", by(r, "is running")[0]["state"] == "fix" and "15 minutes" in by(r, "is running")[0]["detail"])
r = D.check_runner(st, NOW, {"bridge/runner.py": NOW - 60, "dse/brief.py": NOW - 30}, PERIODIC, TOOLS)
check("files changed after the runner started: restart, naming the files", by(r, "latest code")[0]["state"] == "fix" and "bridge/runner.py" in by(r, "latest code")[0]["detail"])
r = D.check_runner({**st, "helpers": ["bridge/brief_sync.py"]}, NOW, {}, PERIODIC, TOOLS)
check("a helper added after the runner started is named: helpers only start with the runner", by(r, "background helpers are started")[0]["state"] == "fix" and "crm_sync" in by(r, "background helpers are started")[0]["detail"])
r = D.check_runner(st, NOW, {}, PERIODIC, {"chat.ask": {}})
check("a tool list without the newest tools means the toolkit is old, and says which features are missing", by(r, "tool list")[0]["state"] == "fix" and "Daily Brief" in by(r, "tool list")[0]["detail"] and "Update the toolkit" in by(r, "tool list")[0]["fix"])

# ---------------------------------------------------------------- the database
class Api:
    def __init__(self, missing=(), token_bad=False, boom=False):
        self.missing, self.token_bad, self.boom, self.calls = set(missing), token_bad, boom, []

    def rpc(self, name, body, tries=1):
        self.calls.append((name, body))
        if self.boom:
            raise OSError("network down")
        if self.token_bad:
            raise RuntimeError(f"{name}: HTTP 401 invalid token")
        if name in self.missing:
            raise RuntimeError(f'{name}: HTTP 404 {{"code":"PGRST202","message":"Could not find the function public.{name}"}}')
        if name == "hq_brief_push":
            raise RuntimeError(f'{name}: HTTP 400 {{"message":"hq: the brief must be an object"}}')   # the function ran and refused the empty call
        return []


a = Api()
out = D.check_database(a)
check("every update the toolkit depends on is asked about", {c[0] for c in a.calls} == {p[0] for p in D.PROBES})
check("a function that answers, or refuses the empty call itself, is in place", all(i["state"] == "ok" for i in out), str([(i["name"], i["state"]) for i in out if i["state"] != "ok"]))
bad_calls = [c for c in a.calls if c[0] in ("hq_brief_push", "hq_crm_push", "hq_crm_ack", "hq_brief_notify")]
check("the calls are ones the function refuses before it can write (wrong type or empty)", dict(bad_calls)["hq_brief_push"] == {"p_brief": []} and dict(bad_calls)["hq_crm_push"] == {"p_rows": {}} and dict(bad_calls)["hq_crm_ack"] == {"p_acks": {}} and dict(bad_calls)["hq_brief_notify"] == {"p_title": "", "p_body": ""})
out = D.check_database(Api(missing={"hq_brief_notify", "hq_crm_pull"}))
bn = by(out, "phone notifications")[0]
check("a missing function names the exact SQL file and where to run it", bn["state"] == "fix" and "20261119120000_brief_notify.sql" in bn["detail"] and "SQL Editor" in bn["fix"] and "_collected-copies/sql-to-run/20261119120000_brief_notify.sql" in bn["fix"], str(bn))
pull = by(out, "two-way sync")[0]
check("the CRM file says to run it again, because it grew after first use", pull["state"] == "fix" and "run it again" in pull["fix"], str(pull))
check("what is in place is still reported as in place", by(out, "Daily Brief")[0]["state"] == "ok")
out = D.check_database(Api(token_bad=True))
check("a refused token is one line about the connection, not a wall of 'missing'", len(out) == 1 and out[0]["state"] == "fix" and "connect" in out[0]["fix"].lower(), str(out))
out = D.check_database(Api(boom=True))
check("a network failure is the same one line, never 'missing'", len(out) == 1 and out[0]["name"] == "Connection to Citadel")
out = D.check_database(None)
check("a PC that is not set up says how to connect it", len(out) == 1 and "setup" in out[0]["fix"])

# ---------------------------------------------------------------- the helpers
hs = {"bridge/brief_sync.py": {"last_run": NOW - 400, "ok": True, "seconds": 1.2, "last_line": ""},
      "bridge/crm_sync.py": {"last_run": NOW - 100, "ok": True, "seconds": 0.5, "last_line": "crm sync: the database update 20261119100000_crm_sync.sql has not been run yet (ask the super admin)"}}
out = D.check_helpers(PERIODIC, hs, NOW - 7200, NOW)
check("a helper that ran recently is OK", by(out, "Daily Brief")[0]["state"] == "ok")
crm = by(out, "CRM sync")[0]
check("a helper that reports a missing database update is a fix, with the message and the SQL folder", crm["state"] == "fix" and "has not been run yet" in crm["detail"] and "sql-to-run" in crm["fix"], str(crm))
check("a helper that never ran since the runner started long ago is a fix", by(out, "Voices")[0]["state"] == "fix" and "has not run since" in by(out, "Voices")[0]["detail"])
out = D.check_helpers(PERIODIC, {"bridge/brief_sync.py": {"last_run": NOW - 5000, "ok": True, "seconds": 1, "last_line": ""}}, NOW - 9000, NOW)
check("a helper that has stalled (no run for far longer than its interval) is a fix", by(out, "Daily Brief")[0]["state"] == "fix" and "stalled" in by(out, "Daily Brief")[0]["detail"])
out = D.check_helpers(PERIODIC, {}, NOW - 30, NOW)
check("just after a restart a helper that has not run yet is not an alarm", all(i["state"] == "unknown" for i in out))
out = D.check_helpers(PERIODIC, {"bridge/brief_sync.py": {"last_run": NOW - 10, "ok": False, "seconds": 1, "last_line": "Traceback"}}, NOW - 9000, NOW)
check("a failed run is a fix", by(out, "Daily Brief")[0]["state"] == "fix")

# ---------------------------------------------------------------- the report
items = [D.item("A", "One", "fix", "it is broken", "do this"), D.item("A", "Two", "ok", "fine"), D.item("B", "Three", "optional", "not needed", "pip install x"), D.item("B", "Four", "unknown", "cannot tell")]
rep = D.render(items)
check("fixes come first, with why and fix, and the count", rep.index("Needs a fix") < rep.index("Working") and "1 thing(s) need a fix" in rep and "Why: it is broken" in rep and "Fix: do this" in rep)
check("optional and unknown things are separate and never counted as problems", "Optional (nothing breaks without them)" in rep and "Could not check from here" in rep and "pip install x" in rep)
check("when all is well it says so", "Everything that matters is working." in D.render([D.item("A", "Two", "ok", "fine")]))
check("it says it changes nothing", "changes nothing" in rep)
check("time words are plain", D.ago(30) == "30 seconds ago" and D.ago(600) == "10 minutes ago" and D.ago(7200) == "2 hours ago" and D.ago(3 * 86400) == "3 days ago")
check("the real offline check runs on this PC without touching the network", "# System check" in D.render(D.collect(None, offline=True)))
check("no em dash in the module", chr(0x2014) not in (ROOT / "dse" / "doctor.py").read_text(encoding="utf-8"))

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
