"""HQ Tools runner: runs this PC's tools for jobs queued from DBI Citadel's HQ Tools page.
(One file for both DFamocious-HQ/_tools/bridge and dse-toolkit/bridge: keep the two copies identical.)

Design: websites/dbi-citadel-job-bridge.md. Standard-library Python only.

    python _tools/bridge/runner.py setup --url URL --key KEY   # once: token + settings, prints the PC code
    python _tools/bridge/runner.py setup --new                  # a fresh PC code (the old one stops working)
    python _tools/bridge/runner.py check          # test the connection (one heartbeat)
    python _tools/bridge/runner.py                # run forever (install.ps1 starts this at log-on)
    python _tools/bridge/runner.py --once         # run at most one job, then stop
    python _tools/bridge/runner.py dry pipeline.run engine=b "cities=Tampa FL" start=2026-11-20
                                                  # check values, print the command, run nothing

Safety rules (do not loosen):
- Only tools in catalog.json run. Citadel sends a tool key + values, never a command.
- Every value is checked against its field; commands are built here, run without a shell.
- File fields must point at a file inside this folder that matches the field's glob.
- The runner has no Supabase user and no service key: a random token (in .env) lets it
  call the hq_runner_* functions only.
- No tool in the catalog sends, posts, pushes or pays.
"""
from __future__ import annotations

import base64
import collections
import datetime as dt
import glob
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

VERSION = "1.1"
HERE = Path(__file__).resolve().parent
# The same file runs in two places: DFamocious-HQ/_tools/bridge/ (HQ) and dse-toolkit/bridge/ (every member's PC).
ROOT = HERE.parent if (HERE.parent / "dse.py").exists() else HERE.parents[1]
IS_TOOLKIT = ROOT == HERE.parent
TASK = "DSE Toolkit runner" if IS_TOOLKIT else "DFamocious-HQ bridge runner"
RUNNER_CMD = "bridge/runner.py" if IS_TOOLKIT else "_tools/bridge/runner.py"
ENV_FILE = Path(os.environ.get("HQ_BRIDGE_ENV", HERE / ".env"))
CATALOG_FILE = Path(os.environ.get("HQ_BRIDGE_CATALOG", HERE / "catalog.json"))
LOG_DIR = HERE / "logs"
POLL_S = 15
PROGRESS_S = 3
MAX_UPLOAD = 5 * 1024 * 1024
MAX_UPLOADS_PER_JOB = 15
FILES_PER_GLOB = 200
MIME = {".csv": "text/csv", ".md": "text/markdown", ".json": "application/json", ".txt": "text/plain",
        ".html": "text/html", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def say(*a):
    print(dt.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


# ----------------------------------------------------------------- config

def load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("HQ_SUPABASE_URL", "HQ_SUPABASE_KEY", "HQ_RUNNER_TOKEN", "HQ_RUNNER_ID"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    env.setdefault("HQ_RUNNER_ID", re.sub(r"[^A-Za-z0-9._-]", "-", socket.gethostname())[:64] or "hq-pc")
    return env


def load_catalog() -> dict:
    return resolve_fields(json.loads(CATALOG_FILE.read_text(encoding="utf-8")))


def engine_choices() -> list[dict]:
    """This PC's engines (engines/<slug>/engine.json, written by the engines sync), for "choices_from": "engines"."""
    out = []
    for p in sorted((ROOT / "engines").glob("*/engine.json")):
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if not cfg.get("archived"):
            out.append({"value": p.parent.name, "label": f"{cfg.get('name') or p.parent.name} ({cfg.get('path', '?')})"})
    return out


def channel_choices() -> list[dict]:
    """This PC's YouTube Launchpad channels (youtube/channels/<slug>/channel.json), for "choices_from": "channels"."""
    out = []
    for p in sorted((ROOT / "youtube" / "channels").glob("*/channel.json")):
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        out.append({"value": p.parent.name, "label": cfg.get("name") or p.parent.name})
    return out


def workspace_choices() -> list[dict]:
    """This PC's Dev workspaces (workspaces/<name>), for "choices_from": "workspaces"."""
    base = ROOT / "workspaces"
    if not base.is_dir():
        return []
    return [{"value": p.name, "label": p.name} for p in sorted(base.iterdir()) if p.is_dir() and re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,60}", p.name)]


def provider_choices() -> list[dict]:
    """Optional paid enrichment providers set up on this PC (enrich-providers/*.json), for "choices_from": "providers". Names only: never a key."""
    out = []
    for p in sorted((ROOT / "enrich-providers").glob("*.json")):
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,30}", str(cfg.get("name", ""))):
            out.append({"value": cfg["name"], "label": str(cfg.get("label", cfg["name"]))[:60]})
    return out


def pack_choices() -> list[dict]:
    """Website-check packs: the built-in ones (packs/*.json) and the ones you made yourself (data/custom-packs), for "choices_from": "packs"."""
    out = []
    for folder, mine in ((ROOT / "packs", False), (ROOT / "data" / "custom-packs", True)):
        for p in sorted(folder.glob("*.json")) if folder.is_dir() else []:
            try:
                label = str(json.loads(p.read_text(encoding="utf-8")).get("label") or p.stem)[:70]
            except ValueError:
                continue
            if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", p.stem):
                out.append({"value": p.stem, "label": label + (" (made by me)" if mine and "(my own)" not in label else "")})
    return out


def figure_choices(with_any: bool = True) -> list[dict]:
    """The Voices roster (voices/roster.json), for "choices_from": "figures" (with an Everyone entry) and "figure_ids" (a real figure only)."""
    out = [{"value": "any", "label": "Everyone in the library"}] if with_any else []
    try:
        fs = json.loads((ROOT / "voices" / "roster.json").read_text(encoding="utf-8"))["figures"]
    except (OSError, ValueError, KeyError):
        return out
    for f in sorted(fs, key=lambda x: x["name"].lower()):
        out.append({"value": f["id"], "label": f"{f['name']} ({f.get('era', '')})"})
    return out


def resolve_fields(cat: dict) -> dict:
    """Fill dynamic choice lists (engines) into the catalog, for both the published forms and the value checks."""
    eng = None
    for t in cat["tools"].values():
        for f in t.get("fields", []):
            if f.get("choices_from") == "engines":
                eng = engine_choices() if eng is None else eng
                f["choices"] = eng
            elif f.get("choices_from") == "channels":
                f["choices"] = channel_choices()
            elif f.get("choices_from") == "workspaces":
                f["choices"] = workspace_choices()
            elif f.get("choices_from") == "providers":
                f["choices"] = provider_choices()
            elif f.get("choices_from") == "packs":
                f["choices"] = pack_choices()
            elif f.get("choices_from") == "figures":
                f["choices"] = figure_choices(True)
            elif f.get("choices_from") == "figure_ids":
                f["choices"] = figure_choices(False)
    return cat


_OLL = {"t": 0.0, "v": None}


def ollama_model() -> str:
    """The chat model: the OLLAMA_MODEL setting (even one saved after this runner started), else the best installed (chat/ollama_model.py)."""
    try:
        import importlib.util as iu
        spec = iu.spec_from_file_location("hq_ollama_model", HERE.parent / "chat" / "ollama_model.py")
        mod = iu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.pick()[0]
    except Exception:
        return os.environ.get("OLLAMA_MODEL", "gemma3:1b")


def ollama_info() -> dict:
    """Is Ollama running, and can the chat model read pictures? (asks Ollama itself: /api/show lists capabilities.)
    Citadel's DBI-AI page only offers the picture button when this says vision is true."""
    if time.time() - _OLL["t"] < 60 and _OLL["v"] is not None:
        return _OLL["v"]
    model = ollama_model()
    info = {"running": False, "model": model, "vision": False}
    try:
        with urllib.request.urlopen("http://localhost:11434/api/version", timeout=2) as r:
            info["running"] = True
            info["ollama"] = str(json.loads(r.read()).get("version", ""))[:20]
        body = json.dumps({"model": model}).encode()
        req = urllib.request.Request("http://localhost:11434/api/show", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            info["vision"] = "vision" in (json.loads(r.read()).get("capabilities") or [])
    except Exception:
        pass
    try:        # what the DBI-AI model menu can offer: every installed model (and whether it reads pictures), and whether Claude is ready
        import importlib.util as iu
        spec = iu.spec_from_file_location("hq_ollama_model", HERE.parent / "chat" / "ollama_model.py")
        mod = iu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        info["models"] = mod.models_info()
        info["claude"] = bool(mod.claude_ready())
    except Exception:
        info.setdefault("models", [])
        info.setdefault("claude", False)
    _OLL.update(t=time.time(), v=info)
    return info


def public_catalog(cat: dict) -> dict:
    """What Citadel sees: labels and form fields only (no scripts or argument templates)."""
    keep = ("label", "group", "help", "fields", "timeout_min")
    resolve_fields(cat)
    return {"version": cat.get("version", 1),
            "ollama": ollama_info(),
            "tools": {k: {f: t[f] for f in keep if f in t} for k, t in cat["tools"].items()}}


# ----------------------------------------------------------------- Supabase calls

class Api:
    def __init__(self, env: dict):
        missing = [k for k in ("HQ_SUPABASE_URL", "HQ_SUPABASE_KEY", "HQ_RUNNER_TOKEN") if not env.get(k)]
        if missing:
            sys.exit(f"Missing in {ENV_FILE}: {', '.join(missing)}. Run: python {RUNNER_CMD} setup")
        self.url = env["HQ_SUPABASE_URL"].rstrip("/")
        self.key = env["HQ_SUPABASE_KEY"]
        self.token = env["HQ_RUNNER_TOKEN"]
        self.runner_id = env["HQ_RUNNER_ID"]

    def rpc(self, name: str, body: dict, tries: int = 3):
        data = json.dumps({"p_token": self.token, **body}).encode("utf-8")
        last = None
        for i in range(tries):
            req = urllib.request.Request(
                f"{self.url}/rest/v1/rpc/{name}", data=data, method="POST",
                headers={"apikey": self.key, "Authorization": f"Bearer {self.key}",
                         "Content-Type": "application/json", "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    raw = r.read()
                    return json.loads(raw) if raw.strip() else None
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", "replace")[:500]
                if e.code < 500:            # our mistake or bad token: retrying won't help
                    raise RuntimeError(f"{name}: HTTP {e.code} {msg}") from None
                last = RuntimeError(f"{name}: HTTP {e.code} {msg}")
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                last = RuntimeError(f"{name}: {e}")
            time.sleep(min(30, 2 ** (i + 1)))
        raise last

    def beat(self, catalog=None, files=None, started=False):
        return self.rpc("hq_runner_beat", {"p_runner_id": self.runner_id, "p_version": VERSION,
                                           "p_catalog": catalog, "p_files": files, "p_started": started})

    def claim(self):
        return self.rpc("hq_runner_claim", {"p_runner_id": self.runner_id})

    def progress(self, job_id, log) -> bool:
        return bool(self.rpc("hq_runner_progress", {"p_job": job_id, "p_log": log}, tries=1))

    def add_file(self, job_id, name, mime, raw: bytes):
        return self.rpc("hq_runner_add_file", {"p_job": job_id, "p_name": name, "p_mime": mime,
                                               "p_b64": base64.b64encode(raw).decode("ascii")})

    def finish(self, job_id, status, exit_code, log, error, outputs):
        return self.rpc("hq_runner_finish", {"p_job": job_id, "p_status": status, "p_exit": exit_code,
                                             "p_log": log, "p_error": error, "p_outputs": outputs}, tries=8)


# ----------------------------------------------------------------- files the forms can pick

def files_for(pattern: str, exclude: str | None = None) -> list[dict]:
    hits = []
    for p in glob.glob(str(ROOT / pattern), recursive=True):
        fp = Path(p)
        if exclude and re.search(exclude, fp.relative_to(ROOT).as_posix()):
            continue
        if fp.is_file():
            hits.append((fp.stat().st_mtime, fp))
    hits.sort(reverse=True)
    return [{"p": fp.relative_to(ROOT).as_posix(), "m": int(m)} for m, fp in hits[:FILES_PER_GLOB]]


def file_index(cat: dict) -> dict:
    specs = {f["glob"]: f.get("exclude") for t in cat["tools"].values() for f in t.get("fields", []) if f.get("type") == "file"}
    return {g: files_for(g, x) for g, x in sorted(specs.items())}


# ----------------------------------------------------------------- checking values

class Bad(ValueError):
    pass


def check_value(field: dict, value):
    name, kind = field["name"], field["type"]
    if value is None or value == "":
        if field.get("required"):
            raise Bad(f"{field.get('label', name)} is required")
        return field.get("default")
    if kind == "bool":
        if isinstance(value, bool):
            return value
        if str(value).lower() in ("true", "1", "yes", "on"):
            return True
        if str(value).lower() in ("false", "0", "no", "off"):
            return False
        raise Bad(f"{name}: not yes/no")
    if kind == "int":
        try:
            v = int(str(value).strip())
        except ValueError:
            raise Bad(f"{name}: not a whole number") from None
        if v < field.get("min", -10**9) or v > field.get("max", 10**9):
            raise Bad(f"{name}: must be {field.get('min')}-{field.get('max')}")
        return v
    s = str(value).strip()
    if s.startswith("-"):
        raise Bad(f"{name}: may not start with '-'")
    if any(c in s for c in "\r\n\x00"):
        raise Bad(f"{name}: one line only")
    if kind == "choice":
        allowed = [c["value"] for c in field["choices"]]
        if s not in allowed:
            # "allow_custom": the form offers "Other: type my own". Only for fields whose tool can honour a value of your own, and only plain words.
            if field.get("allow_custom") and re.fullmatch(field.get("custom_pattern") or r"[A-Za-z][A-Za-z0-9 &'/-]{1,59}", s):
                return s
            raise Bad(f"{name}: must be one of {', '.join(allowed)}" + (" (or your own, using letters, numbers and spaces)" if field.get("allow_custom") else ""))
        return s
    if kind == "date":
        try:
            dt.date.fromisoformat(s)
        except ValueError:
            raise Bad(f"{name}: use YYYY-MM-DD") from None
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            raise Bad(f"{name}: use YYYY-MM-DD")
        return s
    if kind == "url":
        if not re.fullmatch(r"https?://[^\s\"'<>`|;]{3,300}", s):
            raise Bad(f"{name}: not a web address")
        return s
    if kind == "text":
        if len(s) > field.get("max", 200):
            raise Bad(f"{name}: too long")
        if field.get("pattern") and not re.fullmatch(field["pattern"], s):
            raise Bad(f"{name}: has characters that are not allowed")
        return s
    if kind == "file":
        allowed = {f["p"] for f in files_for(field["glob"], field.get("exclude"))}
        if s not in allowed:
            raise Bad(f"{name}: not one of the files the form offers ({field['glob']})")
        full = (ROOT / s).resolve()
        if ROOT.resolve() not in full.parents or not full.is_file():
            raise Bad(f"{name}: outside this folder")
        return s
    raise Bad(f"{name}: unknown field type {kind}")


def build_command(cat: dict, tool_key: str, params: dict) -> tuple[list[str], dict]:
    tool = cat["tools"].get(tool_key)
    if not tool:
        raise Bad(f"unknown tool {tool_key}")
    if not isinstance(params, dict):
        raise Bad("values must be an object")
    fields = {f["name"]: f for f in tool["fields"]}
    extra = set(params) - set(fields)
    if extra:
        raise Bad(f"unknown values: {', '.join(sorted(extra))}")
    vals = {n: check_value(f, params.get(n)) for n, f in fields.items()}
    script = (ROOT / tool["script"]).resolve()
    if ROOT.resolve() not in script.parents or not script.is_file():
        raise Bad(f"script missing: {tool['script']}")
    argv = [sys.executable, "-u", str(script)]
    for a in tool["args"]:
        if "lit" in a:
            argv.append(a["lit"])
        elif "flag" in a:
            if vals.get(a["field"]):
                argv.append(a["flag"])
        elif "opt" in a:
            v = vals.get(a["field"])
            if v is not None and v != "":
                argv += [a["opt"], str(v)]
        else:
            v = vals.get(a["field"])
            if v is None or v == "":
                raise Bad(f"{a['field']} is required")
            argv.append(str(v))
    return argv, vals


# ----------------------------------------------------------------- running a job

def snapshot(globs: list[str]) -> dict:
    snap = {}
    for g in globs:
        for p in glob.glob(str(ROOT / g), recursive=True):
            fp = Path(p)
            if fp.is_file():
                snap[fp] = fp.stat().st_mtime
    return snap


def kill_tree(proc: subprocess.Popen):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.kill()


def run_job(api: Api | None, cat: dict, job: dict, dry: bool = False) -> dict:
    job_id, tool_key = job["id"], job["tool"]
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"{dt.datetime.now():%Y-%m-%d-%H%M%S}-{tool_key}-{str(job_id)[:8]}.log"
    lines: collections.deque[str] = collections.deque(maxlen=400)

    def tail() -> str:
        return "\n".join(lines)

    try:
        argv, vals = build_command(cat, tool_key, job.get("params") or {})
    except Bad as e:
        say(f"job {job_id}: refused: {e}")
        if api:
            api.finish(job_id, "failed", None, "", f"Refused by the PC runner: {e}", [])
        return {"status": "failed", "error": str(e)}

    tool = cat["tools"][tool_key]
    shown = " ".join(argv[2:]).replace(str(ROOT) + os.sep, "")
    if dry:
        print(shown)
        return {"status": "dry"}

    say(f"job {job_id}: {tool_key} -> {shown}")
    lines.append(f"$ python {shown}")
    out_specs = tool.get("outputs", [])
    before = snapshot([o["glob"] for o in out_specs])
    started = time.time()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen(argv, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, env=env, creationflags=flags)
    logf = open(log_path, "w", encoding="utf-8")
    logf.write(f"$ python {shown}\n")

    def reader():
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            lines.append(line)
            logf.write(line + "\n")
            logf.flush()

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    cancelled = timed_out = False
    limit = tool.get("timeout_min", 30) * 60
    sent, last_sent = None, 0.0
    while proc.poll() is None:
        time.sleep(PROGRESS_S)
        now_tail = tail()
        # Send the log when it changed (every 3 s at most); otherwise ask about Cancel every 15 s.
        if api and (now_tail != sent or time.time() - last_sent >= POLL_S):
            try:
                if api.progress(job_id, now_tail):
                    cancelled = True
                sent, last_sent = now_tail, time.time()
            except Exception as e:                       # network blip: keep running
                say(f"progress not sent: {e}")
        if cancelled:
            lines.append("-- Cancel pressed in Citadel: stopping --")
            kill_tree(proc)
            break
        if time.time() - started > limit:
            timed_out = True
            lines.append(f"-- Time limit of {tool.get('timeout_min', 30)} minutes reached: stopping --")
            kill_tree(proc)
            break
    proc.wait()
    t.join(timeout=10)
    logf.close()
    code = proc.returncode

    outputs = collect_outputs(api, job_id, out_specs, before) if not cancelled else []
    if cancelled:
        status, error = "cancelled", "Cancelled from Citadel."
    elif timed_out:
        status, error = "failed", f"Stopped after the {tool.get('timeout_min', 30)}-minute time limit."
    elif code != 0:
        status, error = "failed", f"The tool stopped with exit code {code}. See the log."
    else:
        status, error = "done", None
    took = int(time.time() - started)
    lines.append(f"-- {status} in {took // 60}m {took % 60}s; full log on the PC: {log_path.relative_to(ROOT).as_posix()} --")
    if api:
        api.finish(job_id, status, code, tail(), error, outputs)
    say(f"job {job_id}: {status} ({took}s, {len(outputs)} outputs)")
    return {"status": status, "exit": code, "outputs": outputs}


def collect_outputs(api, job_id, specs, before) -> list[dict]:
    out, uploads = [], 0
    for spec in specs:
        changed = [fp for fp, m in snapshot([spec["glob"]]).items() if before.get(fp) != m]
        if not changed:
            continue
        changed.sort(key=lambda p: p.as_posix())
        if not spec.get("upload"):
            folder = os.path.commonpath([str(p.parent) for p in changed])
            out.append({"kind": "pc", "label": spec.get("label", spec["glob"]), "count": len(changed),
                        "path": Path(folder).relative_to(ROOT).as_posix()})
            continue
        for fp in changed:
            rel = fp.relative_to(ROOT).as_posix()
            size = fp.stat().st_size
            item = {"kind": "file", "name": fp.name, "path": rel, "size": size}
            if size <= MAX_UPLOAD and uploads < MAX_UPLOADS_PER_JOB and api:
                try:
                    item["file_id"] = api.add_file(job_id, fp.name, MIME.get(fp.suffix.lower(), "application/octet-stream"),
                                                   fp.read_bytes())
                    uploads += 1
                except Exception as e:
                    item["note"] = f"not uploaded: {e}"[:200]
            else:
                item["note"] = "on this PC only (too big or too many files)"
            out.append(item)
    return out


# ----------------------------------------------------------------- commands

def set_env_value(key: str, value: str):
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [l for l in lines if not l.startswith(key + "=")] + [f"{key}={value}"]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_setup(args: list[str]):
    """setup [--url URL --key KEY] [--new]  (the HQ Tools page shows the full line to copy)"""
    new = "--new" in args
    rest = [a for a in args if a != "--new"]
    opts = dict(zip(rest[::2], rest[1::2]))
    if new and ENV_FILE.exists():   # a fresh code: forget the old token
        keep = [l for l in ENV_FILE.read_text(encoding="utf-8").splitlines() if not l.startswith("HQ_RUNNER_TOKEN=")]
        ENV_FILE.write_text("\n".join(keep) + "\n", encoding="utf-8")
    url, key = opts.get("--url", ""), opts.get("--key", "")
    if url:
        if not re.fullmatch(r"https://[a-z0-9-]+\.supabase\.co/?", url):
            sys.exit("--url must look like https://xxxx.supabase.co (copy it from the HQ Tools page)")
        set_env_value("HQ_SUPABASE_URL", url.rstrip("/"))
    if key:
        if not re.fullmatch(r"[A-Za-z0-9._-]{20,400}", key):
            sys.exit("--key does not look right (copy the whole line from the HQ Tools page)")
        set_env_value("HQ_SUPABASE_KEY", key)
    env = load_env()
    if env.get("HQ_RUNNER_TOKEN"):
        token = env["HQ_RUNNER_TOKEN"]
        print(f"A token already exists in {ENV_FILE}.")
    else:
        token = secrets.token_urlsafe(48)
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else [
            "# HQ Tools runner settings. Never share or upload this file.",
            "# Citadel's Supabase project URL and its publishable (anon) key: the same two values",
            "# as VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY in Vercel. NOT the service-role key.",
            "HQ_SUPABASE_URL=",
            "HQ_SUPABASE_KEY=",
        ]
        lines.append(f"HQ_RUNNER_TOKEN={token}")
        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"New runner token written to {ENV_FILE}.")
    h = hashlib.sha256(token.encode("utf-8")).hexdigest()
    print("\nThis PC's code (a fingerprint of the token, safe to paste into Citadel):\n")
    print(f"    {h}\n")
    print("In DBI Citadel: HQ Tools, then 'Connect a PC', paste the code, name the PC.")
    env = load_env()
    if env.get("HQ_SUPABASE_URL") and env.get("HQ_SUPABASE_KEY"):
        print(f"After pressing Connect in Citadel, type this here and press Enter: python {RUNNER_CMD} check")
    else:
        print("Citadel's connection values are missing. Copy the full 'setup --url ... --key ...' line from the "
              "HQ Tools page (Connect a PC) and run it here instead.")


def cmd_check():
    env, cat = load_env(), load_catalog()
    api = Api(env)
    r = api.beat(public_catalog(cat), file_index(cat))
    print(f"Connected as '{api.runner_id}'. Supabase time: {r.get('server_time')}. {len(cat['tools'])} tools published.")


def cmd_dry(args):
    cat = load_catalog()
    if not args:
        sys.exit("usage: runner.py dry <tool> name=value ...")
    params = dict(a.split("=", 1) for a in args[1:])
    res = run_job(None, cat, {"id": "dry", "tool": args[0], "params": params}, dry=True)
    if res["status"] != "dry":
        sys.exit(1)


_LOCK = None


def single_instance():
    """Only one runner per PC: a second copy would fail the first one's job on start-up."""
    global _LOCK
    LOG_DIR.mkdir(exist_ok=True)
    _LOCK = open(LOG_DIR / "runner.lock", "a+")
    try:
        if os.name == "nt":
            import msvcrt
            _LOCK.seek(0)
            msvcrt.locking(_LOCK.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(_LOCK.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("Another bridge runner is already running on this PC. Stop it first "
                 f"(Stop-ScheduledTask -TaskName '{TASK}').")


def start_periodic(cat: dict):
    """Background helpers from catalog.json "periodic" (e.g. the Send Desk sync every 60 s). Each is a Python
    script inside this folder, run as its own process on a timer, so a long tool job never holds it up."""
    for spec in cat.get("periodic", []):
        script = (ROOT / spec.get("script", "")).resolve()
        every = max(30, int(spec.get("every_s", 60)))
        if ROOT.resolve() not in script.parents or script.suffix != ".py" or not script.is_file():
            say(f"periodic helper skipped (not a script in this folder): {spec.get('script')}")
            continue

        def run_forever(script=script, every=every):
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HQ_BRIDGE_ENV": str(ENV_FILE)}
            while True:
                try:
                    r = subprocess.run([sys.executable, "-u", str(script)], cwd=str(ROOT), capture_output=True,
                                       timeout=300, env=env, stdin=subprocess.DEVNULL)
                    out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
                    if r.returncode != 0 or (out and "0 phone taps logged" not in out):
                        say(out.splitlines()[-1] if out else f"{script.name} exited {r.returncode}")
                except Exception as e:
                    say(f"{script.name}: {e}")
                time.sleep(every)

        threading.Thread(target=run_forever, daemon=True, name=f"periodic-{script.stem}").start()
        say(f"periodic helper on: {script.relative_to(ROOT).as_posix()} every {every}s")


def loop(once=False):
    single_instance()
    env = load_env()
    api = Api(env)
    cat = load_catalog()
    files = file_index(cat)
    try:
        api.beat(public_catalog(cat), files, started=True)
    except RuntimeError as e:
        if "not recognised" in str(e):
            sys.exit("Citadel does not know this PC yet (not connected, disconnected, or access removed). "
                     "Run setup and paste its code in Citadel > HQ Tools > Connect a PC. Retrying in 30 s.")
        raise
    say(f"runner '{api.runner_id}' v{VERSION} online with {len(cat['tools'])} tools; checking every {POLL_S}s")
    if not once:
        start_periodic(cat)
    last_files_json, last_full = json.dumps(files, sort_keys=True), time.time()
    wait = POLL_S
    while True:
        try:
            cat = load_catalog()                          # edits to catalog.json apply without a restart
            files = file_index(cat)
            fj = json.dumps(files, sort_keys=True)
            full = fj != last_files_json or time.time() - last_full > 600
            api.beat(public_catalog(cat) if full else None, files if full else None)
            if full:
                last_files_json, last_full = fj, time.time()
            job = api.claim()
            if job:
                run_job(api, cat, job)
                last_full = 0                              # outputs may have added files: resend
                if once:
                    return
                continue
            if once:
                say("no job waiting")
                return
            wait = POLL_S
        except RuntimeError as e:
            if "not recognised" in str(e):
                sys.exit("Citadel does not know this PC (not connected, disconnected, or HQ Tools access removed). Run setup and paste the code in Citadel.")
            say(f"problem: {e}; trying again in {wait}s")
            wait = min(300, wait * 2)
        except KeyboardInterrupt:
            say("stopped")
            return
        try:
            time.sleep(wait)
        except KeyboardInterrupt:
            say("stopped")
            return


def main():
    a = sys.argv[1:]
    if a[:1] == ["setup"]:
        cmd_setup(a[1:])
    elif a[:1] == ["check"]:
        cmd_check()
    elif a[:1] == ["dry"]:
        cmd_dry(a[1:])
    elif a in ([], ["--once"]):
        loop(once=bool(a))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
