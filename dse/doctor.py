"""The System check: what is on, what is missing, and the exact fix for each, in plain words.

    python dse.py doctor [--offline]

It looks at four things and never changes anything (no database writes, nothing sent):
  1. The runner on this PC: is it running, did it start AFTER the toolkit files last changed (a restart loads the new code and the new background helpers), do its tools include the newest ones.
  2. Your Citadel database: for each update this toolkit depends on, it asks the database whether the function exists, with a call that is refused before it can change anything.
     A missing function names the exact SQL file to run in Supabase. (--offline skips this.)
  3. The background helpers (Send Desk, engines, goals, DFY, Daily Brief, CRM, Voices): did each run lately, and what its last message said.
  4. This PC: business data, Voices library, Hugging Face token, Ollama, Python packages.
Each line is OK, NEEDS A FIX (with the fix) or OPTIONAL. Nothing is guessed: a thing that cannot be checked from here is said to be unknown, not fine.
"""
from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path

from .common import DATA, ROOT

BRIDGE = ROOT / "bridge"
SQL_DIR = "_collected-copies/sql-to-run"
RESTART = "Stop the runner (close its window, or end the task) and start it again: python bridge/runner.py (or the Start runner shortcut)."

# What the newest toolkit offers: tool key -> the feature it carries (a catalog without it is older than this toolkit)
EXPECTED_TOOLS = {"dse.brief": "the Daily Brief", "dse.crm": "CRM sync", "dse.voices_setup": "the Voices library", "dse.mypack": "your own website checks", "dse.call_prep": "the Call Desk",
                  "chat.ask": "DBI-AI"}

# Database probes: (function, the arguments of a call that the function refuses before changing anything, the SQL file, what it turns on)
PROBES = [
    ("hq_brief_push", {"p_brief": []}, "20261119090000_hq_brief.sql", "the Daily Brief on your Dashboard"),
    ("hq_brief_notify", {"p_title": "", "p_body": ""}, "20261119120000_brief_notify.sql", "phone notifications for your brief"),
    ("hq_crm_push", {"p_rows": {}}, "20261119100000_crm_sync.sql", "CRM sync (engines to your BPS CRM)"),
    ("hq_crm_pull", {"p_engines": []}, "20261119100000_crm_sync.sql", "CRM two-way sync"),
    ("hq_crm_ack", {"p_acks": {}}, "20261119100000_crm_sync.sql", "CRM two-way sync (acknowledgements)"),
    ("hq_chat_image_get", {"p_id": "00000000-0000-0000-0000-000000000000"}, "20261118100000_dbi_ai_images.sql", "pictures in DBI-AI"),
    ("hq_engines_pull", {}, "20261116090000_member_engines.sql", "your own engines created in Citadel"),
    ("hq_member_desk_pull", {}, "20261118120000_member_desk.sql", "the Send Desk on your phone"),
    ("hq_dfy_pull", {}, "20261118140000_dfy_bridge_payout_accounts.sql", "the DFY bridge and payout accounts (only matters on the HQ admin PC)"),
]

AGAIN = {"20261119100000_crm_sync.sql"}            # files that grew after first use: an older run of them is not enough
HELPER_NAMES = {"bridge/engines_sync.py": "your engines (Citadel to this PC)", "bridge/desk_sync.py": "the Send Desk (lists to your phone, taps back)", "bridge/goal_sync.py": "monthly goal suggestions",
                "bridge/dfy_sync.py": "DFY months from Citadel", "bridge/brief_sync.py": "the Daily Brief and its notifications", "bridge/crm_sync.py": "CRM sync",
                "bridge/voices_sync.py": "the Voices library"}


def item(area: str, name: str, state: str, detail: str = "", fix: str = "") -> dict:
    """state: ok | fix | optional | unknown"""
    return {"area": area, "name": name, "state": state, "detail": detail, "fix": fix}


def read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ago(seconds: float) -> str:
    s = int(max(0, seconds))
    if s < 90:
        return f"{s} seconds ago"
    if s < 5400:
        return f"{s // 60} minutes ago"
    if s < 36 * 3600:
        return f"{s // 3600} hours ago"
    return f"{s // 86400} days ago"


# ------------------------------------------------------------------ 1. the runner

def check_runner(status: dict, now: float, files: dict[str, float], periodic: list[dict], tools: dict) -> list[dict]:
    a = "Runner and tools"
    out = []
    if not status:
        out.append(item(a, "The runner", "fix", "This runner has never reported its status (it is not running, or it is an older version that does not report).",
                        RESTART + " If it was never set up: python bridge/runner.py setup"))
        return out
    age = now - status.get("heartbeat", 0)
    if age > 120:
        out.append(item(a, "The runner is running", "fix", f"It last reported {ago(age)}: it is not running now (the PC may have been off or the window closed).", "Start it: python bridge/runner.py"))
    else:
        out.append(item(a, "The runner is running", "ok", f"online as '{status.get('runner_id', '?')}', {status.get('tools', '?')} tools loaded"))
    started = status.get("started_at", 0)
    newer = sorted(k for k, m in files.items() if m > started + 1)
    if newer:
        out.append(item(a, "The runner has the latest code", "fix", f"It started {ago(now - started)}, but these changed after that: {', '.join(newer[:4])}. A restart loads the new code and the new background helpers.", RESTART))
    else:
        out.append(item(a, "The runner has the latest code", "ok", f"started {ago(now - started)}, nothing newer on disk"))
    running = set(status.get("helpers", []))
    new_helpers = [h.get("script", "") for h in periodic if h.get("script") and h["script"] not in running]
    if new_helpers:
        out.append(item(a, "All background helpers are started", "fix", f"Added since the runner started: {', '.join(new_helpers)}. Helpers are only started when the runner starts.", RESTART))
    missing = [f"{k} ({v})" for k, v in EXPECTED_TOOLS.items() if k not in tools]
    if missing:
        out.append(item(a, "The tool list is complete", "fix", "Missing: " + "; ".join(missing) + ". This toolkit is older than the one these features come from.", "Update the toolkit (git pull in the dse-toolkit folder, or download it again from github.com/Butmmo/dse-toolkit), then restart the runner."))
    else:
        out.append(item(a, "The tool list is complete", "ok", f"{len(tools)} tools, including the Brief, CRM sync, Voices and the Call Desk"))
    return out


# ------------------------------------------------------------------ 2. the database

def probe(api, name: str, args: dict) -> tuple[str, str]:
    """('exists' | 'missing' | 'unknown', detail). The call is one the function refuses before changing anything; a missing function is what the database answers with 'could not find'."""
    try:
        api.rpc(name, args, tries=1)
        return "exists", ""
    except RuntimeError as e:
        msg = str(e)
        if "PGRST202" in msg or "Could not find the function" in msg or "HTTP 404" in msg:
            return "missing", ""
        if "not recognised" in msg or "HTTP 401" in msg or ("HTTP 403" in msg and "hq:" not in msg):
            return "unknown", "Citadel did not accept this PC's token"
        return "exists", ""                      # the function ran and refused the empty call: it is there
    except Exception as e:
        return "unknown", f"{type(e).__name__}: {str(e)[:100]}"


def check_database(api) -> list[dict]:
    a = "Your Citadel database"
    if api is None:
        return [item(a, "Connection to Citadel", "fix", "This PC is not connected to Citadel (no runner settings found).", "python bridge/runner.py setup, then paste the code in Citadel > HQ Tools > Connect a PC.")]
    out = []
    first = True
    for fn, args, sql, what in PROBES:
        state, why = probe(api, fn, args)
        if first and state == "unknown":
            return [item(a, "Connection to Citadel", "fix", why or "Citadel did not answer.", "Check the internet, then: python bridge/runner.py check. If it says the PC is not recognised, connect it again in Citadel > HQ Tools.")]
        first = False
        if state == "exists":
            out.append(item(a, what[0].upper() + what[1:], "ok", f"{sql} is in place"))
        elif state == "missing":
            again = " If you ran an earlier copy of this file, run it again: the newest copy has more in it." if sql in AGAIN else ""
            out.append(item(a, what[0].upper() + what[1:], "fix", f"The database update {sql} has not been run (or only an older copy of it was).", f"Open Supabase > SQL Editor, paste the contents of {SQL_DIR}/{sql}, run it (safe to re-run). Then restart the runner.{again}"))
        else:
            out.append(item(a, what[0].upper() + what[1:], "unknown", why))
    return out


# ------------------------------------------------------------------ 3. the background helpers

def check_helpers(periodic: list[dict], status: dict, runner_started: float, now: float) -> list[dict]:
    a = "Background helpers"
    out = []
    for h in periodic:
        script = h.get("script", "")
        name = HELPER_NAMES.get(script, script)
        every = max(30, int(h.get("every_s", 60)))
        st = status.get(script)
        if not st:
            out.append(item(a, name, "fix" if runner_started and now - runner_started > 660 else "unknown",
                            "It has not run since the runner started." if runner_started else "No record of it running (the runner has not reported).", RESTART))
            continue
        since = now - st.get("last_run", 0)
        line = st.get("last_line", "")
        if not st.get("ok", True) or (line and ("has not been run yet" in line or "problem" in line.lower() or "Error" in line)):
            fix = RESTART if "update" not in line else f"Run the SQL file it names in Supabase ({SQL_DIR}), then it recovers by itself."
            out.append(item(a, name, "fix", f"Its last run {ago(since)} said: {line or 'it failed'}", fix))
        elif since > 3 * every + 120:
            out.append(item(a, name, "fix", f"It last ran {ago(since)} (it should run every {every // 60 or 1} minute(s)): it has stalled.", RESTART))
        else:
            out.append(item(a, name, "ok", f"ran {ago(since)}" + (f": {line}" if line else "")))
    return out


# ------------------------------------------------------------------ 4. this PC

def check_local(now: float) -> list[dict]:
    a = "This PC"
    out = []
    engines = [p.parent.name for p in (ROOT / "engines").glob("*/engine.json")] if (ROOT / "engines").is_dir() else []
    out.append(item(a, "Engines", "ok" if engines else "optional", f"{len(engines)} engine(s)" if engines else "No engine yet: create one in HQ Tools > My engines, and the brief, the Send Desk and CRM sync have something to work with."))
    brief = read_json(DATA / "brief.json")
    if brief.get("made"):
        out.append(item(a, "Your brief is being built", "ok", f"built {brief['made'].replace('T', ' ')}"))
    elif engines:
        out.append(item(a, "Your brief is being built", "fix", "No brief has been built on this PC.", "Run it once: HQ Tools > Daily Brief (or python dse.py brief). If it is built but never shows on the Dashboard, see the database lines above."))
    try:
        from . import voices
        n = sum(1 for f in voices.roster() if voices.load_index(f["id"]))
        out.append(item(a, "The Voices library", "ok" if n else "fix", f"{n} figure(s) with real passages" if n else "The library is empty (Dashboard passages and DBI-AI mentors have nothing to show).",
                        "" if n else "HQ Tools > Voices: set up the library (or python dse.py voices setup)."))
        bad = voices.failing(recorded_only=True)
        if bad:
            fresh = [x for x in bad if not x["tried"]]
            names = "; ".join(f"{x['label']} ({x['detail'][:60]})" for x in (fresh or bad)[:4]) + (f" and {len(fresh or bad) - 4} more" if len(fresh or bad) > 4 else "")
            if fresh:
                out.append(item(a, "Voices sources that fail their check", "fix", f"{len(fresh)} source(s): {names}.", "HQ Tools > Voices: repair a failing source (leave it on 'Repair every failing source'), or: python dse.py voices repair"))
            else:
                out.append(item(a, "Voices sources that fail their check", "optional", f"{len(bad)} source(s) still fail after a repair attempt: {names}.", "Nothing breaks: the rest of the library works. Setup tries them again by itself."))
    except Exception:
        pass
    token = os.environ.get("HF_TOKEN", "")
    if not token and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                token = str(winreg.QueryValueEx(k, "HF_TOKEN")[0])
        except OSError:
            token = ""
    out.append(item(a, "Business data token (lead finder)", "ok" if token else "optional", "a Hugging Face token is saved" if token else "No HF_TOKEN: the lead finder cannot download business data for a new business type.",
                    "" if token else "README, 'One-time: business data': create a free Hugging Face read token and save it as the user variable HF_TOKEN."))
    missing = [m for m in ("requests", "bs4", "openpyxl", "duckdb") if importlib.util.find_spec(m) is None]
    out.append(item(a, "Python packages", "ok" if not missing else "optional", "requests, beautifulsoup4, openpyxl and duckdb are installed" if not missing else f"Not installed: {', '.join(missing)}.",
                    "" if not missing else "pip install " + " ".join({"bs4": "beautifulsoup4"}.get(m, m) for m in missing)))
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
            models = [m.get("name", "") for m in json.loads(r.read()).get("models", [])]
        out.append(item(a, "Ollama (free local AI for DBI-AI)", "ok" if models else "optional", f"running with {', '.join(models[:4])}" if models else "running, but no model is installed.", "" if models else "ollama pull gemma3:4b"))
    except Exception:
        out.append(item(a, "Ollama (free local AI for DBI-AI)", "optional", "not running. DBI-AI then answers from the built-in library only.", "Start Ollama (it runs in the background once installed), or install it from ollama.com and run: ollama pull gemma3:4b"))
    return out


# ------------------------------------------------------------------ the report

def render(items: list[dict]) -> str:
    fixes = [i for i in items if i["state"] == "fix"]
    out = ["# System check", ""]
    out.append("Everything that matters is working." if not fixes else f"{len(fixes)} thing(s) need a fix. They are listed first, each with what to do.")
    if fixes:
        out += ["", "## Needs a fix"]
        for n, i in enumerate(fixes, 1):
            out += [f"{n}. {i['area']}: {i['name']}", f"   Why: {i['detail']}", f"   Fix: {i['fix']}"]
    for state, title in (("optional", "Optional (nothing breaks without them)"), ("unknown", "Could not check from here"), ("ok", "Working")):
        rows = [i for i in items if i["state"] == state]
        if rows:
            out += ["", f"## {title}"]
            for i in rows:
                out.append(f"- {i['area']}: {i['name']}" + (f": {i['detail']}" if i["detail"] else "") + (f". {i['fix']}" if state == "optional" and i["fix"] else ""))
    out += ["", "This check changes nothing: the database lines use calls the database refuses before they can write, and no message is sent."]
    return "\n".join(out) + "\n"


def collect(api=None, offline: bool = False, now: float | None = None) -> list[dict]:
    now = now or time.time()
    cat = read_json(BRIDGE / "catalog.json")
    status = read_json(DATA / "runner-status.json")
    helpers = read_json(DATA / "helpers.json")
    files = {}
    for rel in ("bridge/runner.py", "bridge/catalog.json", "dse/brief.py", "dse/crmsync.py", "dse/briefnotify.py", "dse/voices.py", "bridge/brief_sync.py", "bridge/crm_sync.py", "bridge/voices_sync.py"):
        try:
            files[rel] = (ROOT / rel).stat().st_mtime
        except OSError:
            pass
    items = check_runner(status, now, files, cat.get("periodic", []), cat.get("tools", {}))
    if not offline:
        items += check_database(api)
    items += check_helpers(cat.get("periodic", []), helpers, status.get("started_at", 0), now)
    items += check_local(now)
    return items


def run(offline: bool = False) -> str:
    api = None
    if not offline:
        try:
            spec = importlib.util.spec_from_file_location("dse_runner", BRIDGE / "runner.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            api = mod.Api(mod.load_env())
        except (SystemExit, Exception):
            api = None
    return render(collect(api, offline))
