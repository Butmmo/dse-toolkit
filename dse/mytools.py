"""My tools (no code): your own tools made by chaining the tools that already exist.

    python dse.py mytool list                      your tools and the tools shared by DBI, and whether each is ready
    python dse.py mytool check [slug]              check every recipe (or one) against this PC's tools: plain words, changes nothing
    python dse.py mytool save recipe.json          save a recipe you wrote or were given (from a file)
    python dse.py mytool run my.<slug> --in-<name> value ...     what the runner does when you press Run in HQ Tools

A recipe is a small file (my-tools/<slug>.json, or my-tools/shared/<slug>.json for one DBI shared): a name, what it asks you each time (inputs), and up to 8 steps.
Each step is one of the toolkit's own tools with its values: a fixed value, "ask me" ({{name}}), or the file the step before produced ({{prev.file}}, {{step2.file}}).
It becomes one more tool in HQ Tools (group "My tools"), here and on your phone, and the Planner can find it like any other.

Why this is safe to share: a recipe is DATA. It can only call tools this PC already has, through the same checks as pressing them by hand (every value is checked by
the tool's own rules), never a Dev, Setup, Studio or other recipe, at most 8 steps, with the sum of their time limits. It never sends, posts or pays: no tool does.
A recipe from DBI shows its steps in the tool's help, so you see what it does before you press Run. Standard library only.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

from .common import DATA, ROOT
from .procs import kill_tree, run_streaming  # noqa: F401 (kill_tree re-exported for tests)

MINE = ROOT / "my-tools"
SHARED = MINE / "shared"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,24}$")
PLACE = re.compile(r"^\{\{(?:([a-z][a-z0-9_]{0,24})|(prev)\.file|step([1-8])\.file)\}\}$")
INPUT_TYPES = ("text", "int", "choice", "bool", "url", "date", "file")
DENY_GROUPS = {"Dev", "Setup", "Studio", "My tools"}
DENY_PREFIX = ("my.", "shared.", "extra.", "studio.", "dse.studio", "dse.mytool", "dev.")
MAX_STEPS, MAX_INPUTS, MAX_MINUTES = 8, 8, 120
COPY_FROM_FIELD = ("choices", "glob", "exclude", "min", "max", "suggestions", "pattern", "allow_custom", "custom_pattern", "hint", "placeholder", "default")


def allowed_tool(key: str, tool: dict) -> bool:
    return not key.startswith(DENY_PREFIX) and tool.get("group") not in DENY_GROUPS


def usable_tools(tools: dict) -> dict:
    """The tools a recipe step may call."""
    return {k: t for k, t in tools.items() if allowed_tool(k, t)}


# ------------------------------------------------------------------ checking a recipe

def validate(spec, tools: dict, checker=None) -> tuple[dict, list[str]]:
    """(clean recipe, problems in plain words). tools: the catalog's tools. checker(field, value) raises ValueError on a bad fixed value (the runner's own rule)."""
    problems: list[str] = []
    if not isinstance(spec, dict):
        return {}, ["the recipe is not an object"]
    name = str(spec.get("name", "")).strip()
    if not 3 <= len(name) <= 80:
        problems.append("the name needs 3 to 80 characters")
    help_ = str(spec.get("help", "")).strip()
    if len(help_) > 400:
        problems.append("the description is longer than 400 characters")

    inputs, used = [], set()
    raw_inputs = spec.get("inputs", [])
    if not isinstance(raw_inputs, list) or len(raw_inputs) > MAX_INPUTS:
        problems.append(f"at most {MAX_INPUTS} inputs")
        raw_inputs = []
    seen = set()
    for n, i in enumerate(raw_inputs, 1):
        if not isinstance(i, dict) or not NAME.match(str(i.get("name", ""))):
            problems.append(f"input {n}: the name must be lowercase letters, digits and _ (starting with a letter)")
            continue
        if i["name"] in seen:
            problems.append(f"input {i['name']} is listed twice")
            continue
        seen.add(i["name"])
        t = i.get("type", "text")
        if t not in INPUT_TYPES:
            problems.append(f"input {i['name']}: type must be one of {', '.join(INPUT_TYPES)}")
            continue
        clean = {"name": i["name"], "label": str(i.get("label") or i["name"])[:80], "type": t, "required": bool(i.get("required", True))}
        if t == "choice" and isinstance(i.get("choices"), list):
            ch = [{"value": str(c.get("value", ""))[:60], "label": str(c.get("label", c.get("value", "")))[:80]} for c in i["choices"][:30] if isinstance(c, dict) and c.get("value") not in (None, "")]
            if ch:
                clean["choices"] = ch
        for k in ("min", "max"):
            if isinstance(i.get(k), int) and not isinstance(i.get(k), bool):
                clean[k] = i[k]
        if isinstance(i.get("from"), dict) and isinstance(i["from"].get("step"), int) and isinstance(i["from"].get("field"), str):
            clean["from"] = {"step": i["from"]["step"], "field": i["from"]["field"]}
        if i.get("hint"):
            clean["hint"] = str(i["hint"])[:200]
        if i.get("default") not in (None, ""):
            clean["default"] = i["default"] if isinstance(i["default"], (int, float, bool)) else str(i["default"])[:200]
        inputs.append(clean)
    by_name = {i["name"]: i for i in inputs}

    steps, raw_steps = [], spec.get("steps", [])
    if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= MAX_STEPS:
        problems.append(f"a recipe needs 1 to {MAX_STEPS} steps")
        raw_steps = []
    usable = usable_tools(tools)
    for n, s in enumerate(raw_steps, 1):
        if not isinstance(s, dict) or not isinstance(s.get("tool"), str):
            problems.append(f"step {n}: no tool named")
            continue
        key = s["tool"]
        tool = usable.get(key)
        if tool is None:
            problems.append(f"step {n}: '{key}' is not a tool a recipe may use (it does not exist on this PC, or it is a Dev, Setup, Studio or recipe tool)")
            continue
        fields = {f["name"]: f for f in tool.get("fields", [])}
        values = s.get("values", {})
        if not isinstance(values, dict):
            problems.append(f"step {n}: values must be an object")
            continue
        clean_vals = {}
        for fname, v in values.items():
            f = fields.get(fname)
            if f is None:
                problems.append(f"step {n} ({tool.get('label', key)}): the tool has no value called '{fname}'")
                continue
            if isinstance(v, bool) or isinstance(v, (int, float)):
                v = v
            elif isinstance(v, str):
                v = v.strip()
            else:
                problems.append(f"step {n}: '{fname}' must be text, a number or yes/no")
                continue
            if isinstance(v, str) and "{{" in v:
                m = PLACE.match(v)
                if not m:
                    problems.append(f"step {n}: '{fname}' mixes text with a placeholder: a placeholder must be the whole value")
                    continue
                if m.group(1):
                    if m.group(1) not in by_name:
                        problems.append(f"step {n}: '{{{{{m.group(1)}}}}}' is not one of the recipe's inputs")
                        continue
                    used.add(m.group(1))
                    if (by_name[m.group(1)]["type"] == "file") != (f["type"] == "file"):
                        problems.append(f"step {n}: input '{m.group(1)}' and the tool's '{fname}' are not the same kind (a file goes only to a file value)")
                        continue
                else:
                    ref = n - 1 if m.group(2) else int(m.group(3))
                    if ref < 1 or ref >= n:
                        problems.append(f"step {n}: '{v}' points at a step that does not run before it")
                        continue
                    if f["type"] != "file":
                        problems.append(f"step {n}: only a file value can take the file a previous step made ('{fname}' is not a file)")
                        continue
            else:
                if f["type"] == "file":
                    problems.append(f"step {n}: '{fname}' is a file: take it from an input or from a previous step, not a fixed name")
                    continue
                if checker:
                    try:
                        checker(f, v)
                    except ValueError as e:
                        problems.append(f"step {n} ({tool.get('label', key)}): {e}")
                        continue
            clean_vals[fname] = v
        for fname, f in fields.items():
            if f.get("required") and fname not in clean_vals and f.get("default") in (None, ""):
                problems.append(f"step {n} ({tool.get('label', key)}): '{f.get('label', fname)}' is needed: give it a value or ask for it")
        steps.append({"tool": key, "label": str(s.get("label") or tool.get("label", key))[:80], "values": clean_vals})
    for i in inputs:
        if i["name"] not in used:
            problems.append(f"input '{i['name']}' is never used by a step")
        frm = i.get("from")
        if frm and not (1 <= frm["step"] <= len(steps) and any(frm["field"] == f["name"] for f in usable.get(steps[frm["step"] - 1]["tool"], {}).get("fields", []) if steps)):
            problems.append(f"input '{i['name']}': 'from' points at a value that does not exist")
    return {"name": name, "help": help_, "inputs": inputs, "steps": steps}, problems


# ------------------------------------------------------------------ the recipe as a catalog tool

def _field_for(inp: dict, steps: list, tools: dict) -> dict:
    f = {"name": inp["name"], "label": inp["label"], "type": inp["type"], "required": inp.get("required", True)}
    src = None
    frm = inp.get("from")
    if frm and 1 <= frm["step"] <= len(steps):
        src = next((x for x in tools.get(steps[frm["step"] - 1]["tool"], {}).get("fields", []) if x["name"] == frm["field"]), None)
    if src is None:        # no hint: the first value that takes this input
        for st in steps:
            for fname, v in st["values"].items():
                if v == "{{" + inp["name"] + "}}":
                    src = next((x for x in tools.get(st["tool"], {}).get("fields", []) if x["name"] == fname), None)
                    break
            if src:
                break
    if src:
        for k in COPY_FROM_FIELD:
            if k in src:
                f[k] = src[k]
    for k in ("choices", "min", "max", "hint", "default"):
        if k in inp:
            f[k] = inp[k]
    if f["type"] == "text":
        f.setdefault("max", 200)
    if f["type"] == "choice" and "choices" not in f:
        f["type"] = "text"
    return f


def tool_entry(key: str, spec: dict, tools: dict, label_suffix: str) -> dict:
    steps = spec["steps"]
    fields = [_field_for(i, steps, tools) for i in spec["inputs"]]
    does = " ".join(f"{n}. {s['label']}." for n, s in enumerate(steps, 1))
    outputs, minutes = [], 0
    for s in steps:
        t = tools.get(s["tool"], {})
        minutes += int(t.get("timeout_min", 30))
        for o in t.get("outputs", []):
            if o not in outputs:
                outputs.append(o)
    args = [{"lit": "mytool"}, {"lit": "run"}, {"lit": key}] + [{"opt": f"--in-{f['name']}", "field": f["name"]} for f in fields]
    return {"label": f"{spec['name']}{label_suffix}", "group": "My tools",
            "help": ((spec["help"] + " ") if spec["help"] else "") + f"Steps, in order: {does} Each step uses the toolkit's own tool with its usual checks. Nothing is sent.",
            "script": "dse.py", "args": args, "fields": fields, "timeout_min": min(MAX_MINUTES, max(1, minutes)), "outputs": outputs}


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def local_specs() -> dict[str, dict]:
    """{'my.<slug>' or 'shared.<slug>': file content} for every recipe file on this PC that is switched on."""
    out = {}
    for folder, prefix in ((MINE, "my."), (SHARED, "shared.")):
        for p in sorted(folder.glob("*.json")) if folder.is_dir() else []:
            if not SLUG.match(p.stem):
                continue
            d = _read(p)
            if isinstance(d, dict) and not d.get("archived") and not d.get("removed_in_citadel") and d.get("active", True):
                out[prefix + p.stem] = d
    return out


def entries(cat: dict) -> dict:
    """The catalog entries for the recipes that pass their structural check. The deep check (every fixed value against its tool's rule) is `mytool check`, and runs again at Run."""
    tools, out = cat.get("tools", {}), {}
    for key, d in local_specs().items():
        clean, problems = validate(d.get("spec", d), tools)
        if problems:
            continue
        out[key] = tool_entry(key, clean, tools, " (from DBI)" if key.startswith("shared.") else " (mine)")
    return out


# ------------------------------------------------------------------ running one

def _runner():
    spec = importlib.util.spec_from_file_location("dse_runner", ROOT / "bridge" / "runner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def base_catalog(r=None):
    r = r or _runner()
    return r, r.load_catalog(base_only=True)


def _checker(r):
    def check(field, value):
        try:
            r.check_value(field, value)
        except r.Bad as e:
            raise ValueError(str(e)) from None
    return check


def check_all(only: str = "") -> list[dict]:
    r, cat = base_catalog()
    out = []
    for key, d in local_specs().items():
        if only and only not in (key, key.split(".", 1)[1]):
            continue
        clean, problems = validate(d.get("spec", d), cat["tools"], _checker(r))
        out.append({"key": key, "name": clean.get("name") or d.get("name") or key, "ok": not problems, "problems": problems, "steps": len(clean.get("steps", []))})
    return out


def newest_output(r, globs: list[str], before: dict):
    """The file a step made that the next step should get: the newest one, a .csv before anything else (a tool that writes a list and a summary hands on the list)."""
    best = None
    for g in globs:
        for fp, m in r.snapshot([g]).items():
            if before.get(fp) != m and fp.suffix.lower() in (".csv", ".json", ".txt", ".md", ".xlsx"):
                rank = (fp.suffix.lower() == ".csv", m)
                if best is None or rank > best[0]:
                    best = (rank, fp)
    return best[1] if best else None


def run(key: str, rest: list[str], emit=print) -> int:
    d = local_specs().get(key)
    if d is None:
        emit(f"There is no active recipe '{key}' on this PC.")
        return 2
    r, cat = base_catalog()
    clean, problems = validate(d.get("spec", d), cat["tools"], _checker(r))
    if problems:
        emit("This recipe cannot run:\n- " + "\n- ".join(problems))
        return 2
    given = {}
    it = iter(rest)
    for a in it:
        if a.startswith("--in-"):
            given[a[5:]] = next(it, "")
    values = {}
    for i in clean["inputs"]:
        v = given.get(i["name"], "")
        if v == "" and i.get("default") not in (None, ""):
            v = str(i["default"])
        if v == "" and i.get("required", True):
            emit(f"'{i['label']}' is required.")
            return 2
        values[i["name"]] = v
    files: dict[int, str] = {}
    n_steps = len(clean["steps"])
    for n, st in enumerate(clean["steps"], 1):
        tool = cat["tools"][st["tool"]]
        params = {}
        for fname, v in st["values"].items():
            if isinstance(v, str) and v.startswith("{{"):
                m = PLACE.match(v)
                if m.group(1):
                    params[fname] = values.get(m.group(1), "")
                else:
                    ref = n - 1 if m.group(2) else int(m.group(3))
                    if ref not in files:
                        emit(f"Step {n} needs the file step {ref} makes, but step {ref} produced none.")
                        return 1
                    params[fname] = files[ref]
            else:
                params[fname] = v
        try:
            argv, _vals = r.build_command(cat, st["tool"], params)
        except r.Bad as e:
            emit(f"Step {n}/{n_steps} ({st['label']}) was refused: {e}")
            return 1
        emit(f"== Step {n}/{n_steps}: {st['label']} ==")
        globs = [o["glob"] for o in tool.get("outputs", [])]
        before = r.snapshot(globs)
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        code, timed_out = run_streaming(argv, str(ROOT), env, int(tool.get("timeout_min", 30)) * 60, emit)
        if timed_out:
            emit(f"Step {n} stopped at its time limit.")
            return 1
        if code != 0:
            emit(f"Step {n} ({st['label']}) failed with exit code {code}: the steps after it were not run.")
            return 1
        f = newest_output(r, globs, before)
        if f is not None:
            files[n] = f.relative_to(ROOT).as_posix()
            emit(f"-- step {n} made {files[n]}")
    emit(f"== Done: all {n_steps} step(s) ran ==")
    return 0


def save(path: str, shared: bool = False) -> str:
    d = _read(Path(path))
    if not isinstance(d, dict):
        return "That file is not a recipe (not valid JSON)."
    r, cat = base_catalog()
    spec = d.get("spec", d)
    clean, problems = validate(spec, cat["tools"], _checker(r))
    if problems:
        return "Not saved:\n- " + "\n- ".join(problems)
    slug = d.get("slug") or re.sub(r"[^a-z0-9]+", "-", clean["name"].lower()).strip("-")[:41]
    if not SLUG.match(slug):
        return f"'{slug}' is not a usable name for the file (lowercase letters, digits and -, 2 to 41 characters)."
    folder = SHARED if shared else MINE
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{slug}.json").write_text(json.dumps({"slug": slug, "name": clean["name"], "spec": clean}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return f"Saved {'shared' if shared else 'my'} tool '{slug}'. It appears in HQ Tools as {'shared' if shared else 'my'}.{slug} within a minute (the runner reads it by itself)."


def listing() -> str:
    checks = {c["key"]: c for c in check_all()}
    if not checks:
        return "No recipes yet. Make one in Citadel (HQ Tools, My tools) or save a recipe file: python dse.py mytool save recipe.json\n"
    lines = ["# My tools", ""]
    for k, c in checks.items():
        lines.append(f"- {k}: {c['name']}: " + (f"ready ({c['steps']} step(s))" if c["ok"] else "needs a fix: " + "; ".join(c["problems"][:2])))
    return "\n".join(lines) + "\n"


def check_report(only: str = "") -> str:
    res = check_all(only)
    if not res:
        return "Nothing to check" + (f" for '{only}'" if only else "") + ".\n"
    out = ["# My tools: check", ""]
    for c in res:
        out.append(f"{'OK  ' if c['ok'] else 'FIX '} {c['key']} ({c['name']}), {c['steps']} step(s)")
        out += [f"       - {p}" for p in c["problems"]]
    bad = sum(1 for c in res if not c["ok"])
    out += ["", f"{len(res) - bad} ready, {bad} need a fix. A tool with a problem is simply not offered in HQ Tools until it is fixed. This check changes nothing."]
    return "\n".join(out) + "\n"
