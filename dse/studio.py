"""Tool Studio: write your own tools in Python, with an AI to draft them, a guard on what the code may do, and your approval of the exact code before it runs.

    python dse.py studio config --enable          turn Tool Studio on, on THIS PC only (it is off until you do; --disable turns it off)
    python dse.py studio draft <slug> "what it should do"      an AI drafts the tool (Claude with your own key, else your Ollama model); saved as a DRAFT
    python dse.py studio revise <slug> "what to change"        the AI changes the draft; it must be tested and approved again
    python dse.py studio show <slug>                           the code, the form and the approval code, so you can read it
    python dse.py studio test <slug>                           run it once with its sample values under the guard
    python dse.py studio enable <slug> --approve <code>        switch it on for you (the code is the first 8 characters of the hash of the exact code you read)
    python dse.py studio disable <slug>
    python dse.py studio publish <slug>                        copy it to extras/<slug>/ for the toolkit repository: you review and commit it, everyone gets it with the next update
    python dse.py studio list

Where the safety lives:
  * Off until you switch it on, on your own PC (data/studio.json). Citadel can never switch it on.
  * The code is scanned (studio_guard.py), runs with a short list of builtins and an import hook, in a separate process with your keys removed from its environment,
    a time limit and capped output (studio_run.py), and reaches files and the web only through dse_sdk (studio_sdk.py).
  * A tool runs only after `test` passed AND you approved the exact code: change one character and it is switched off until tested and approved again.
  * Code NEVER travels through Citadel. A tool for everyone goes into the toolkit repository (extras/), where you review the commit, and arrives with the toolkit update.
  * This is a guard against mistakes and AI-written code, not a wall against a hostile author: that is why you read the code before you approve it.
Standard library only (Claude is used only if you set ANTHROPIC_API_KEY and installed `anthropic`).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path

from . import studio_guard
from .common import DATA, ROOT
from .procs import run_streaming

STUDIO = ROOT / "studio"
EXTRAS = ROOT / "extras"
WORK = DATA / "studio-work"
CONFIG = DATA / "studio.json"
LAUNCHER = ROOT / "dse" / "studio_run.py"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,24}$")
FIELD_TYPES = ("text", "int", "choice", "bool", "url", "date")
CONTROL_PREFIX = "dse.studio_"


# ------------------------------------------------------------------ the switch

def enabled() -> bool:
    try:
        return bool(json.loads(CONFIG.read_text(encoding="utf-8")).get("enabled"))
    except (OSError, ValueError):
        return False


def set_enabled(on: bool) -> str:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"enabled": bool(on)}, indent=1), encoding="utf-8")
    return "Tool Studio is ON for this PC." if on else "Tool Studio is OFF for this PC."


# ------------------------------------------------------------------ files and the approval hash

def folder(slug: str, extra: bool = False) -> Path:
    return (EXTRAS if extra else STUDIO) / slug


def code_hash(d: Path) -> str:
    h = hashlib.sha256()
    for name in ("tool.json", "tool.py"):
        try:
            h.update((d / name).read_bytes())
        except OSError:
            return ""
        h.update(b"\n--\n")
    return h.hexdigest()


def read_state(d: Path) -> dict:
    try:
        return json.loads((d / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(d: Path, st: dict) -> None:
    (d / "state.json").write_text(json.dumps(st, indent=1), encoding="utf-8")


def load(slug: str, extra: bool = False) -> dict:
    if not SLUG.match(slug or ""):
        raise ValueError(f"'{slug}' is not a tool name (lowercase letters, digits and -, 2 to 41 characters)")
    d = folder(slug, extra)
    try:
        m = json.loads((d / "tool.json").read_text(encoding="utf-8"))
        code = (d / "tool.py").read_text(encoding="utf-8")
    except (OSError, ValueError):
        raise ValueError(f"No tool '{slug}'. See: python dse.py studio list") from None
    return {"dir": d, "manifest": m, "code": code, "hash": code_hash(d), "state": read_state(d)}


def check_manifest(m) -> list[str]:
    p = []
    if not isinstance(m, dict):
        return ["the form description is not an object"]
    if not 3 <= len(str(m.get("label", ""))) <= 80:
        p.append("the label needs 3 to 80 characters")
    if len(str(m.get("help", ""))) > 600:
        p.append("the help text is longer than 600 characters")
    t = m.get("timeout_min", 5)
    if not isinstance(t, int) or not 1 <= t <= 30:
        p.append("timeout_min must be a whole number from 1 to 30")
    fs = m.get("fields", [])
    if not isinstance(fs, list) or len(fs) > 8:
        return p + ["at most 8 fields"]
    seen = set()
    for f in fs:
        if not isinstance(f, dict) or not NAME.match(str(f.get("name", ""))):
            p.append("every field needs a name of lowercase letters, digits and _")
            continue
        if f["name"] in seen:
            p.append(f"field {f['name']} is listed twice")
        seen.add(f["name"])
        if f.get("type") not in FIELD_TYPES:
            p.append(f"field {f['name']}: type must be one of {', '.join(FIELD_TYPES)}")
        if f.get("type") == "choice" and not (isinstance(f.get("choices"), list) and f["choices"]):
            p.append(f"field {f['name']}: a choice needs a list of choices")
        if f.get("type") == "text" and not (isinstance(f.get("max", 200), int) and 1 <= f.get("max", 200) <= 500):
            p.append(f"field {f['name']}: max must be 1 to 500")
    return p


# ------------------------------------------------------------------ catalog entries

def _entry(key: str, wid: str, m: dict) -> dict:
    fields = []
    for f in m.get("fields", []):
        g = {k: f[k] for k in ("name", "label", "type", "required", "default", "choices", "min", "max", "hint", "placeholder", "pattern") if k in f}
        g.setdefault("label", f["name"])
        g.setdefault("required", False)
        if g["type"] == "text":
            g.setdefault("max", 200)
        fields.append(g)
    args = [{"lit": "studio"}, {"lit": "run"}, {"lit": key}] + [{"opt": f"--in-{f['name']}", "field": f["name"]} for f in fields]
    return {"label": m["label"], "group": "Studio" if key.startswith("studio.") else "Extra tools", "help": str(m.get("help", "")), "script": "dse.py", "args": args,
            "fields": fields, "timeout_min": int(m.get("timeout_min", 5)), "outputs": [{"glob": f"data/studio-work/{wid}/*", "upload": True, "label": "results"}]}


def entries(cat: dict) -> dict:
    """Catalog entries: your approved studio tools (only while Tool Studio is on) and the extras that came with the toolkit (their recorded hash must match)."""
    out = {}
    if enabled() and STUDIO.is_dir():
        for d in sorted(STUDIO.iterdir()):
            if not (d.is_dir() and SLUG.match(d.name)):
                continue
            try:
                t = load(d.name)
            except ValueError:
                continue
            if t["state"].get("enabled") and t["state"].get("approved") == t["hash"] and not check_manifest(t["manifest"]) and not studio_guard.scan(t["code"]):
                out[f"studio.{d.name}"] = _entry(f"studio.{d.name}", d.name, t["manifest"])
    if EXTRAS.is_dir():
        for d in sorted(EXTRAS.iterdir()):
            if not (d.is_dir() and SLUG.match(d.name)):
                continue
            try:
                t = load(d.name, extra=True)
            except ValueError:
                continue
            if t["state"].get("sha") == t["hash"] and not check_manifest(t["manifest"]) and not studio_guard.scan(t["code"]):
                out[f"extra.{d.name}"] = _entry(f"extra.{d.name}", f"extra-{d.name}", t["manifest"])
    return out


def apply(cat: dict) -> dict:
    """Studio's own control tools exist only while Tool Studio is on, so a PC that never turned it on offers none of it."""
    if not enabled():
        for k in [k for k in cat["tools"] if k.startswith(CONTROL_PREFIX)]:
            cat["tools"].pop(k)
    else:
        for k, t in cat["tools"].items():
            if k.startswith(CONTROL_PREFIX):
                for f in t.get("fields", []):
                    if f.get("choices_from") == "studio_tools":
                        f["choices"] = tool_choices()
    return cat


def tool_choices() -> list[dict]:
    out = []
    for d in sorted(STUDIO.iterdir()) if STUDIO.is_dir() else []:
        if d.is_dir() and SLUG.match(d.name) and (d / "tool.json").is_file():
            try:
                label = json.loads((d / "tool.json").read_text(encoding="utf-8")).get("label", d.name)
            except ValueError:
                label = d.name
            out.append({"value": d.name, "label": f"{str(label)[:60]} ({d.name})"})
    return out


# ------------------------------------------------------------------ running under the guard

def _runner():
    spec = importlib.util.spec_from_file_location("dse_runner", ROOT / "bridge" / "runner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _env() -> dict:
    keep = ("SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "PATH", "WINDIR")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    return env


def execute(code_file: Path, wid: str, values: dict, timeout_s: int, emit=print) -> tuple[int, bool]:
    """One run in the sandbox launcher. The tool's work folder is data/studio-work/<wid>; a run starts with it empty."""
    work = WORK / wid
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    inputs = WORK / f"{wid}.inputs.json"
    inputs.write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")
    try:
        argv = [sys.executable, "-I", "-u", str(LAUNCHER), str(code_file), str(work), str(inputs), str(ROOT)]
        return run_streaming(argv, str(work), _env(), timeout_s, emit, cap_chars=200_000)
    finally:
        inputs.unlink(missing_ok=True)


def _values(m: dict, given: dict) -> tuple[dict, list[str]]:
    r = _runner()
    vals, problems = {}, []
    for f in m.get("fields", []):
        field = {"label": f.get("label", f["name"]), "required": False, **f, "name": f["name"]}
        try:
            v = r.check_value(field, given.get(f["name"], ""))
        except r.Bad as e:
            problems.append(str(e))
            continue
        vals[f["name"]] = v if v is not None else ""
    return vals, problems


def run(key: str, rest: list[str], emit=print) -> int:
    extra = key.startswith("extra.")
    slug = key.split(".", 1)[1]
    try:
        t = load(slug, extra)
    except ValueError as e:
        emit(str(e))
        return 2
    st = t["state"]
    if extra:
        ok = st.get("sha") == t["hash"]
        why = "this extra tool's files changed after it was published (re-publish it)"
    else:
        ok = enabled() and st.get("enabled") and st.get("approved") == t["hash"]
        why = "Tool Studio is off, or the tool is not approved for its current code (run: studio test, then studio enable --approve)"
    if not ok:
        emit(f"Not run: {why}.")
        return 2
    bad = studio_guard.scan(t["code"]) + check_manifest(t["manifest"])
    if bad:
        emit("Not run: " + "; ".join(bad))
        return 2
    given, it = {}, iter(rest)
    for a in it:
        if a.startswith("--in-"):
            given[a[5:]] = next(it, "")
    vals, problems = _values(t["manifest"], given)
    if problems:
        emit("Not run: " + "; ".join(problems))
        return 2
    wid = f"extra-{slug}" if extra else slug
    code, timed_out = execute(t["dir"] / "tool.py", wid, vals, int(t["manifest"].get("timeout_min", 5)) * 60, emit)
    if timed_out:
        emit(f"Stopped at the time limit of {t['manifest'].get('timeout_min', 5)} minute(s).")
        return 1
    return code


def test(slug: str, emit=print) -> str:
    t = load(slug)
    bad = studio_guard.scan(t["code"]) + check_manifest(t["manifest"])
    if bad:
        return "Test not run. Fix these first:\n- " + "\n- ".join(bad) + "\n"
    sample = t["manifest"].get("sample", {})
    vals, problems = _values(t["manifest"], {**{f["name"]: f.get("default", "") for f in t["manifest"].get("fields", [])}, **sample})
    if problems:
        return "Test not run: the sample values are not valid: " + "; ".join(problems) + "\n"
    lines: list[str] = []
    code, timed_out = execute(t["dir"] / "tool.py", slug, vals, int(t["manifest"].get("timeout_min", 5)) * 60, lines.append)
    shown = "\n".join(lines[-40:])
    ok = code == 0 and not timed_out
    st = t["state"]
    st["tested"] = t["hash"] if ok else ""
    write_state(t["dir"], st)
    made = sorted(p.name for p in (WORK / slug).glob("*")) if (WORK / slug).exists() else []
    head = f"Test {'PASSED' if ok else 'FAILED'} (exit {code}{', hit the time limit' if timed_out else ''}). Files it made: {', '.join(made) or 'none'}.\n"
    tail = f"\nApproval code for this exact code: {t['hash'][:8]}\nRead it with: python dse.py studio show {slug}\nThen: python dse.py studio enable {slug} --approve {t['hash'][:8]}\n" if ok else ""
    return head + "--- its output ---\n" + shown + "\n" + tail


def enable(slug: str, approve: str) -> str:
    if not enabled():
        return "Tool Studio is off on this PC. Turn it on first: python dse.py studio config --enable"
    t = load(slug)
    st = t["state"]
    if st.get("tested") != t["hash"]:
        return "Not enabled: this exact code has not passed a test. Run: python dse.py studio test " + slug
    if (approve or "").strip().lower() != t["hash"][:8]:
        return f"Not enabled: the approval code does not match this code (it is {t['hash'][:8]}). Read the code (studio show {slug}) and approve that."
    st.update(enabled=True, approved=t["hash"])
    write_state(t["dir"], st)
    return f"Enabled: studio.{slug} now appears in HQ Tools (group Studio) for you only. If you change the code it switches itself off until tested and approved again.\n"


def disable(slug: str) -> str:
    t = load(slug)
    st = t["state"]
    st.update(enabled=False)
    write_state(t["dir"], st)
    return f"Disabled: studio.{slug} is no longer offered.\n"


def publish(slug: str) -> str:
    t = load(slug)
    st = t["state"]
    if st.get("approved") != t["hash"]:
        return "Not published: enable it for yourself first (test, read, approve), so what you publish is code you have approved."
    dest = folder(slug, extra=True)
    dest.mkdir(parents=True, exist_ok=True)
    m = {**t["manifest"], "published_from": "studio"}
    (dest / "tool.json").write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (dest / "tool.py").write_text(t["code"], encoding="utf-8")
    write_state(dest, {"sha": code_hash(dest)})
    return (f"Published to extras/{slug}/ in the toolkit folder. Nothing has been sent anywhere. To give it to everyone:\n"
            f"  1. read extras/{slug}/tool.py once more (it is what every student's PC will run, under the same guard)\n"
            f"  2. git add extras/{slug} && git commit -m \"extra tool: {slug}\" && git push\n"
            "  3. students get it with the next toolkit update (git pull), and it shows in their HQ Tools as extra." + slug + "\n")


def show(slug: str) -> str:
    t = load(slug)
    st = t["state"]
    status = "ENABLED" if st.get("enabled") and st.get("approved") == t["hash"] else "tested, not enabled" if st.get("tested") == t["hash"] else "draft (not tested)"
    return (f"# {t['manifest'].get('label', slug)}  [{status}]\nApproval code for this exact code: {t['hash'][:8]}\n\n## Form\n{json.dumps(t['manifest'].get('fields', []), indent=1)}\n\n## Code (tool.py)\n{t['code']}\n")


def listing() -> str:
    rows = [f"Tool Studio is {'ON' if enabled() else 'OFF'} on this PC.", ""]
    for c in tool_choices():
        t = load(c["value"])
        st = t["state"]
        status = "enabled" if st.get("enabled") and st.get("approved") == t["hash"] else "tested" if st.get("tested") == t["hash"] else "draft"
        rows.append(f"- {c['value']}: {c['label']}: {status}")
    if len(rows) == 2:
        rows.append("No studio tools yet. Draft one: python dse.py studio draft my-tool \"what it should do\"")
    extra = sorted(p.name for p in EXTRAS.iterdir() if p.is_dir()) if EXTRAS.is_dir() else []
    if extra:
        rows += ["", "Extra tools that came with the toolkit: " + ", ".join(extra)]
    return "\n".join(rows) + "\n"


# ------------------------------------------------------------------ drafting with an AI

SDK_DOC = (ROOT / "dse" / "studio_sdk.py").read_text(encoding="utf-8").split('"""')[1] if (ROOT / "dse" / "studio_sdk.py").exists() else ""
SYSTEM = f"""You write small Python tools for a business toolkit. Answer with ONE JSON object and nothing else:
{{"manifest": {{"label": "...", "help": "...", "timeout_min": 5, "fields": [{{"name": "...", "label": "...", "type": "text|int|choice|bool|url|date", "required": true, "default": "...", "max": 200, "choices": [{{"value": "...", "label": "..."}}]}}], "sample": {{"field_name": "a safe example value"}}}}, "code": "python source"}}
RULES for the code (a guard rejects anything else):
- It is a script, not a function library. Start with: from dse_sdk import inputs, log, read_csv, write_csv, read_text, write_text, http_get
- Read the form's values from the dict `inputs` (all text, int or bool values already checked). Print results with log(...) and write result files with write_csv / write_text.
- Allowed imports ONLY: {', '.join(sorted(studio_guard.SAFE_MODULES - {'dse_sdk'}))}. No os, sys, subprocess, requests, socket, pathlib, urllib, open(), eval, exec, getattr.
- No attribute or name starting with an underscore, no text with a double underscore. Build text with f-strings or +, never "{{0.x}}".format.
- Never scrape LinkedIn, Instagram, Facebook, X or Google Maps, never send messages or emails, never ask for or store keys.
- Keep it short and plain. The sample values must make the tool run on its own with no network if possible.
This is the whole of dse_sdk:
{SDK_DOC}"""


def _default_brain(system: str, user: str) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        try:
            spec = importlib.util.spec_from_file_location("hq_ollama_model", ROOT / "chat" / "ollama_model.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            key = mod.user_setting("ANTHROPIC_API_KEY")
        except Exception:
            key = ""
    if key:
        try:
            import anthropic
            os.environ["ANTHROPIC_API_KEY"] = key
            resp = anthropic.Anthropic().messages.create(model=os.environ.get("CLAUDE_MODEL", "claude-opus-5-5"), max_tokens=6000, system=system, messages=[{"role": "user", "content": user}])
            return "".join(b.text for b in resp.content if b.type == "text")
        except ImportError:
            pass
    spec = importlib.util.spec_from_file_location("hq_ollama_model", ROOT / "chat" / "ollama_model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    model = mod.pick()[0]
    body = json.dumps({"model": model, "stream": False, "options": {"num_ctx": 8192, "temperature": 0.2}, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
    try:
        req = urllib.request.Request("http://localhost:11434/api/chat", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"No AI answered ({type(e).__name__}). Set ANTHROPIC_API_KEY (and pip install anthropic) or start Ollama with a model (ollama pull gemma3:4b).") from None


def parse_draft(text: str) -> tuple[dict, str]:
    """(manifest, code) from the model's answer: a JSON object, possibly wrapped in a code fence or in prose."""
    s = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, re.S)
    if m:
        s = m.group(1)
    else:
        a, b = s.find("{"), s.rfind("}")
        s = s[a:b + 1] if a >= 0 and b > a else s
    d = json.loads(s)
    if not isinstance(d, dict) or not isinstance(d.get("manifest"), dict) or not isinstance(d.get("code"), str):
        raise ValueError("the answer needs a manifest object and a code text")
    return d["manifest"], d["code"]


def draft(slug: str, describe: str, brain=None, base: dict | None = None) -> str:
    """Ask the AI for a tool, check it, and save it as a draft (never enabled). base: the existing tool to change (revise)."""
    if not SLUG.match(slug or ""):
        return f"'{slug}' is not a tool name (lowercase letters, digits and -, 2 to 41 characters)."
    if not (3 <= len((describe or "").strip()) <= 1500):
        return "Describe what the tool should do in 3 to 1,500 characters."
    d = folder(slug)
    if d.exists() and base is None:
        return f"studio/{slug} already exists. Pick another name, or change it with: python dse.py studio revise {slug} \"what to change\""
    brain = brain or _default_brain
    user = f"Make this tool: {describe.strip()}"
    if base:
        user = f"Here is the current tool.\nmanifest: {json.dumps(base['manifest'])}\ncode:\n{base['code']}\n\nChange it like this and return the whole tool again: {describe.strip()}"
    problems: list[str] = []
    for attempt in range(2):
        ask = user if not problems else user + "\n\nYour last answer was refused for these reasons. Fix them and answer again with the whole JSON object:\n- " + "\n- ".join(problems)
        try:
            manifest, code = parse_draft(brain(SYSTEM, ask))
        except (ValueError, RuntimeError) as e:
            if isinstance(e, RuntimeError):
                return str(e) + "\n"
            problems = [f"the answer could not be read as the JSON object ({e})"]
            continue
        problems = studio_guard.scan(code) + check_manifest(manifest)
        if not problems:
            d.mkdir(parents=True, exist_ok=True)
            manifest["group"] = "Studio"
            (d / "tool.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            (d / "tool.py").write_text(code.rstrip() + "\n", encoding="utf-8")
            st = read_state(d)
            st.update(enabled=False, approved="", tested="")
            write_state(d, st)
            return (f"Draft saved as studio/{slug}. It is NOT switched on.\n\n## What the AI made\n{show(slug)}\n"
                    f"Next: python dse.py studio test {slug}   (runs it once on its sample values), then read the code and approve it.\n")
    return "The AI's drafts were refused by the guard, so nothing was saved:\n- " + "\n- ".join(problems) + "\nTry again with a simpler description, or a stronger AI (Claude with your own key).\n"


def revise(slug: str, instruction: str, brain=None) -> str:
    return draft(slug, instruction, brain, base=load(slug))
