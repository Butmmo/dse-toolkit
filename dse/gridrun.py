"""Run column: fill ONE column of a grid, row by row, on this PC (Citadel: grid column menu > Run column).

    python dse.py grid run <grid> <column> [--mode empty|stale|all] [--limit N] [--dry]

The column has a RUN SETTING, made in Citadel (column menu > Run settings), one of:
  ask an AI       a question written with the row's own cells in {braces}, for example   Write a one-line opener for {Company} in {City}
                  The model is the one the member picked for this source in Citadel: a Claude tier (their own key, python dse.py claude setup, paid to Anthropic by them,
                  counted against their daily token limit, python dse.py claude limit), one of their local Ollama models (free, on their PC), or Automatic (Claude Haiku when a
                  Claude key is connected, else the PC's best local model). Older columns saved as haiku or sonnet keep meaning Claude Haiku or Sonnet. The AI is told to answer
                  with only the cell's value, or UNKNOWN when it cannot tell (the cell is then left as it is).
  read a website  one fact (best email, phone, decision maker, social link ...) read from the business's OWN public website in another column: the same free, polite reader as Lead enrichment.
What a run does:
  * a column can have SEVERAL sources, tried in order for each row (a waterfall): the first that gives an answer that fits the column fills the cell, so a paid answer is only asked for
    when the free website reading found nothing. Up to five.
  * mode empty (the default) works only on rows whose cell is empty; mode stale works on rows never run and still empty PLUS rows OUT OF DATE (see below); mode all ("force") redoes every row. --limit N takes only the first N (test on a few before running them all).
  * OUT-OF-DATE ROWS: a run leaves a small fingerprint on every row it fills or tries (a hash of the cells the sources read and of the sources themselves, under the key _<column key>). A row is out of date when
    that fingerprint no longer matches what the row and the sources are now. A value typed by hand, or filled before fingerprints existed, has none and is never called out of date. A row tried with no answer
    keeps its fingerprint, so it is not paid for again until its inputs change. The fingerprint is the same text and hash as in Citadel (src/lib/crm-run.ts): a shared test value keeps them equal.
  * a row with nothing to read (no website, or every column named in the question empty) is skipped and counted.
  * answers are saved in small batches while it works, so Stop (or a crash) keeps everything done so far; it only ever writes into THIS column of rows of YOUR grid, through this PC's own connection.
  * every answer is turned into the column's type (a number, a date, a choice, a link ...); one that does not fit is left out and counted, never stored as junk.
  * it reports "PROGRESS done/total failed N skipped N" lines, which Citadel shows with a Stop button, and ends with "FINISHED ...".
Needs this PC connected to Citadel and the database file 20261224090000_grid_run_column.sql. Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import gridpush

MAX_ROWS = 5000
MAX_STEPS = 5
SEP_PART, SEP_STEP, SEP_FIELD = "\x1f", "\x1d", "\x1e"      # the separators of the fingerprint text (the same as SEP in src/lib/crm-run.ts)
READ_PAGE = 500
BATCH = 10
MAX_CELL = {"text": 500, "longtext": 2000}
SITE_FIELDS = ("email", "phone", "decision_maker", "decision_title", "linkedin", "instagram", "facebook", "booking", "contact_form", "tech", "description")
MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
CLAUDE_TIERS = {"haiku": "haiku", "sonnet": "sonnet", "claude": "sonnet", "claude:haiku": "haiku", "claude:sonnet": "sonnet", "claude:opus": "opus"}
PROVIDER_MODELS = {"openai": "gpt-5-mini", "openai:mini": "gpt-5-mini", "openai:full": "gpt-5",
                   "gemini": "gemini-2.5-flash", "gemini:flash": "gemini-2.5-flash", "gemini:pro": "gemini-2.5-pro"}
OLLAMA_MODEL_RE = re.compile(r"^ollama:[A-Za-z0-9][A-Za-z0-9._:/-]{0,59}$")


def clean_model(v) -> str:
    """The model stored on an AI source, made safe. The same rules as the grid (src/lib/crm-grid.ts cleanRunModel): the values Citadel's model menu
    stores pass through, the legacy haiku/sonnet of older columns keep their meaning, and anything else becomes haiku, as before this choice existed."""
    s = str(v or "")
    if s in ("haiku", "sonnet", "auto", "claude", "claude:haiku", "claude:sonnet", "claude:opus",
             "openai", "openai:mini", "openai:full", "gemini", "gemini:flash", "gemini:pro") or OLLAMA_MODEL_RE.match(s):
        return s
    return "haiku"


def is_claude_model(m) -> bool:
    """True when this model choice is answered by Claude (and so uses the member's key and daily limit)."""
    return str(m or "") in CLAUDE_TIERS


def provider_of(m) -> str:
    """'openai', 'gemini' or '' for a stored model choice: which member-owned key answers it ('' for Claude and the local models)."""
    s = str(m or "")
    return s.split(":")[0] if s in PROVIDER_MODELS else ""
STOP_AFTER_FAILS = 5                   # this many answers in a row failing means something is wrong (key, credit, network): stop instead of hammering
SYSTEM = ("You fill in ONE cell of a spreadsheet for a business. Reply with ONLY the value for the cell: no explanation, no quotes, no label, no markdown. "
          "Keep it short and plain. If the information given is not enough to answer, reply with exactly: UNKNOWN")
API = "https://api.anthropic.com/v1/messages"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


# ------------------------------------------------------------------ the grid and its column

def parse_columns(doc_text: str | None) -> list[dict]:
    """Every column of the grid with what a run needs: key, label, type, choices and the run setting. Formula columns hold no values, so they are left out."""
    try:
        d = json.loads(doc_text or "{}")
    except ValueError:
        return []
    out = []
    for c in d.get("custom", []) if isinstance(d, dict) else []:
        if not isinstance(c, dict) or not re.fullmatch(r"c_[a-z0-9_]{1,40}", str(c.get("key", ""))) or c.get("type") == "formula":
            continue
        run = c.get("run") if isinstance(c.get("run"), dict) else None
        out.append({"key": c["key"], "label": str(c.get("label") or c["key"]), "type": c.get("type") or "text",
                    "options": [o for o in (c.get("options") or []) if isinstance(o, dict)], "run": clean_run(run)})
    return out


def clean_step(run: dict | None) -> dict | None:
    """One source. The same rules as the grid (src/lib/crm-grid.ts cleanRunStep): anything incomplete or odd is no source at all."""
    if not isinstance(run, dict):
        return None
    if run.get("kind") == "ai":
        prompt = re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", str(run.get("prompt") or ""))).strip()[:1000]
        return {"kind": "ai", "prompt": prompt, "model": clean_model(run.get("model"))} if prompt else None
    if run.get("kind") == "site":
        frm, field = re.sub(r"\s+", " ", str(run.get("from") or "")).strip()[:40], str(run.get("field") or "")
        return {"kind": "site", "from": frm, "field": field} if frm and field in SITE_FIELDS else None
    return None


def clean_run(run: dict | None) -> dict | None:
    """A run setting: a first source and, optionally, more tried in order after it (src/lib/crm-grid.ts cleanRun). Returned as {first source..., "then": [more]}."""
    first = clean_step(run)
    if not first:
        return None
    more = run.get("then") if isinstance(run.get("then"), list) else []
    then = [x for x in (clean_step(m) for m in more) if x][: MAX_STEPS - 1]
    return {**first, "then": then} if then else first


def steps_of(run: dict | None) -> list[dict]:
    """The sources in the order they are tried."""
    if not run:
        return []
    return [{k: v for k, v in run.items() if k != "then"}] + list(run.get("then") or [])


def find_column(columns: list[dict], ref: str) -> dict:
    ref = (ref or "").strip()
    for c in columns:
        if c["key"] == ref:
            return c
    hits = [c for c in columns if norm(c["label"]) == norm(ref)]
    if len(hits) == 1:
        return hits[0]
    raise ValueError(f"The grid has no column called '{ref}'. Its columns: " + ", ".join(c["label"] for c in columns[:12]) + ".")


def cell_text(col: dict, data: dict) -> str:
    """What a cell shows, as text (a choice by its label, Yes/No for a tick)."""
    v = (data or {}).get(col["key"])
    if v is None or v == "" or v is False:
        return ""
    if v is True:
        return "Yes"
    if col["type"] == "select":
        for o in col["options"]:
            if o.get("value") == v:
                return str(o.get("label") or v)
    return str(v).strip()


def prompt_refs(prompt: str) -> list[str]:
    seen: list[str] = []
    for m in re.finditer(r"\{([^{}]{1,40})\}", prompt or ""):
        n = re.sub(r"\s+", " ", m.group(1)).strip()
        if n and not any(norm(n) == norm(x) for x in seen):
            seen.append(n)
    return seen


def build_prompt(prompt: str, columns: list[dict], data: dict) -> str:
    by = {norm(c["label"]): c for c in columns}
    return re.sub(r"\{([^{}]{1,40})\}", lambda m: cell_text(by[norm(m.group(1))], data) if norm(m.group(1)) in by else "", prompt)


def step_has_inputs(step: dict, columns: list[dict], data: dict) -> bool:
    by = {norm(c["label"]): c for c in columns}
    names = prompt_refs(step["prompt"]) if step["kind"] == "ai" else [step["from"]]
    return any(norm(n) in by and cell_text(by[norm(n)], data) != "" for n in names)


def has_inputs(run: dict, columns: list[dict], data: dict) -> bool:
    """A row can run when ANY source has something to read."""
    return any(step_has_inputs(st, columns, data) for st in steps_of(run))


def step_problem(step: dict, col: dict, columns: list[dict]) -> str:
    by = {norm(c["label"]): c for c in columns}
    if step["kind"] == "ai":
        refs = prompt_refs(step["prompt"])
        if not refs:
            return "The question names no column. Put a column name in { }, for example {Company}."
        missing = [r for r in refs if norm(r) not in by]
        if missing:
            return "The question uses a column the grid does not have: " + ", ".join("{" + m + "}" for m in missing) + "."
        if any(by[norm(r)]["key"] == col["key"] for r in refs):
            return "The question cannot use the column it fills."
        return ""
    src = by.get(norm(step["from"]))
    if not src:
        return f"The website column '{step['from']}' is not in the grid."
    if src["key"] == col["key"]:
        return "The website column cannot be the column being filled."
    return ""


def problem(col: dict, columns: list[dict]) -> str:
    """Why this column cannot be run (empty text: it can). Mirrors the grid's own check; with several sources the message says which."""
    if not col["run"]:
        return "That column has no run setting yet. In Citadel open its column menu and choose Run settings."
    steps = steps_of(col["run"])
    for i, st in enumerate(steps):
        bad = step_problem(st, col, columns)
        if bad:
            return f"Source {i + 1}: {bad}" if len(steps) > 1 else bad
    return ""


def fnv1a32(text: str) -> str:
    """FNV-1a, 32 bits, of the text's UTF-8 bytes, as 8 hex digits (the same function as in Citadel)."""
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


def fp_key(col: dict) -> str:
    return "_" + col["key"]


def input_columns(run: dict | None, columns: list[dict]) -> list[dict]:
    """The cells a run reads, in the order the sources first use them, each once."""
    by = {norm(c["label"]): c for c in columns}
    out: list[dict] = []
    for st in steps_of(run):
        names = prompt_refs(st["prompt"]) if st["kind"] == "ai" else [st["from"]]
        for n in names:
            c = by.get(norm(n))
            if c and not any(x["key"] == c["key"] for x in out):
                out.append(c)
    return out


def steps_signature(run: dict | None) -> str:
    return SEP_STEP.join(SEP_FIELD.join(["ai", st["prompt"], st["model"]] if st["kind"] == "ai" else ["site", st["from"], st["field"]]) for st in steps_of(run))


def fingerprint(col: dict, columns: list[dict], data: dict) -> str:
    """What a run read for this row, as a short hash: the sources plus the cells they use. The same text and hash as Citadel's fingerprint."""
    parts = ["v1", steps_signature(col["run"])] + [f"{c['key']}={cell_text(c, data).strip()}" for c in input_columns(col["run"], columns)]
    return fnv1a32(SEP_PART.join(parts))


def stored_fp(col: dict, data: dict) -> str | None:
    v = (data or {}).get(fp_key(col))
    return v if isinstance(v, str) and v else None


def is_out_of_date(col: dict, columns: list[dict], data: dict) -> bool:
    fp = stored_fp(col, data)
    return fp is not None and fp != fingerprint(col, columns, data)


def pick_rows(rows: list[dict], col: dict, columns: list[dict], mode: str, limit: int = 0) -> dict:
    """Which rows to work on, with the same answers as the grid shows before you press Run: empty ones, or (stale) never-run empty ones plus out-of-date ones, or all; that have something to read; the first `limit`."""
    def empty(r):
        return cell_text(col, r.get("data") or {}) == ""

    def stale(r):
        d = r.get("data") or {}
        return empty(r) if stored_fp(col, d) is None else is_out_of_date(col, columns, d)

    chosen = [r for r in rows if mode == "all" or (stale(r) if mode == "stale" else empty(r))]
    ready = [r for r in chosen if has_inputs(col["run"], columns, r.get("data") or {})]
    cap = min(limit, MAX_ROWS) if limit and limit > 0 else MAX_ROWS
    return {"rows": ready[:cap], "skipped": len(chosen) - len(ready), "empty": sum(1 for r in rows if empty(r)), "total": len(rows),
            "outdated": sum(1 for r in rows if is_out_of_date(col, columns, r.get("data") or {}))}


# ------------------------------------------------------------------ turning an answer into a cell value

def coerce(col: dict, text: str):
    """The value to store for this column, or None when the answer does not fit the column's type (it is then left out)."""
    t = re.sub(r"^[\"'`]+|[\"'`]+$", "", (text or "").strip()).strip()
    if not t or t.upper() == "UNKNOWN":
        return None
    ty = col["type"]
    if ty == "number":
        try:
            f = float(re.sub(r"[\s,$€£₦%]", "", t))
        except ValueError:
            return None
        return int(f) if f.is_integer() else f
    if ty == "date":
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
        if not m:
            return None
        import datetime as dt
        try:
            dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
        return t
    if ty == "checkbox":
        return True if re.fullmatch(r"(?i)yes|y|true|1", t) else None        # "No" leaves the cell empty, which is how a Yes/No column shows No
    if ty == "select":
        for o in col["options"]:
            if norm(o.get("value")) == norm(t) or norm(o.get("label")) == norm(t):
                return o.get("value")
        return None
    if ty == "email":
        return t.lower() if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", t) else None
    if ty == "phone":
        return t if re.fullmatch(r"[+\d][\d\s().-]{5,24}", t) else None
    if ty == "url":
        if re.search(r"\s", t):
            return t[:500] if t.startswith("@") else None
        if re.match(r"(?i)https?://", t) or t.startswith("@"):
            return t[:500]
        return ("https://" + t)[:500] if re.search(r"\.[a-z]{2,}", t, re.I) else t[:500]
    if ty == "longtext":
        return re.sub(r"[ \t]+", " ", t)[: MAX_CELL["longtext"]]
    return re.sub(r"\s+", " ", t)[: MAX_CELL["text"]]


def site_value(site: dict, field: str) -> str:
    """One fact out of what the website reader found (dse/enrich.py enrich_site)."""
    s = site or {}
    people = s.get("people") or []
    emails = s.get("emails") or []
    socials = s.get("socials") or {}
    if field == "email":
        return str(emails[0].get("email", "")) if emails and isinstance(emails[0], dict) else ""
    if field == "phone":
        return str((s.get("phones") or [""])[0] or "")
    if field == "decision_maker":
        return str(people[0].get("name", "")) if people and isinstance(people[0], dict) else ""
    if field == "decision_title":
        return str(people[0].get("title", "")) if people and isinstance(people[0], dict) else ""
    if field in ("linkedin", "instagram", "facebook"):
        return str(socials.get(field, "") or "")
    if field == "tech":
        return ", ".join(str(x) for x in (s.get("tech") or []))
    if field in ("booking", "contact_form", "description"):
        return str(s.get(field, "") or "")
    return ""


# ------------------------------------------------------------------ the real helpers (replaced by fakes in the tests)

def claude_key() -> str:
    from . import claudekey
    return claudekey.current_key()


def openai_key() -> str:
    from . import openaikey
    return openaikey.current_key()


def gemini_key() -> str:
    from . import geminikey
    return geminikey.current_key()


def _cost():
    import importlib.util
    p = Path(__file__).resolve().parents[1] / "chat" / "claude_cost.py"
    spec = importlib.util.spec_from_file_location("hq_claude_cost", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ask_claude(prompt: str, tier: str, key: str | None = None, http=None) -> tuple[str, int, int, str]:
    """One question to Claude with this PC's own key. Returns (text, tokens in, tokens out, model id). Raises RuntimeError with a plain reason."""
    key = key or claude_key()
    if not key:
        raise RuntimeError("Claude is not connected on this PC. Run: python dse.py claude setup")
    model = MODELS.get(tier, MODELS["haiku"])
    body = json.dumps({"model": model, "max_tokens": 300, "system": SYSTEM, "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    if http is None:
        def http(url, hdrs, data):        # noqa: E306
            req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.status, r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8", "replace")
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                raise RuntimeError(f"Could not reach Anthropic ({e})") from None
    code, raw = http(API, headers, body)
    try:
        d = json.loads(raw)
    except ValueError:
        d = {}
    if code != 200:
        why = str((d.get("error") or {}).get("message", "")) or f"HTTP {code}"
        raise RuntimeError(("Claude says: " + why)[:200].replace(key, "..."))
    text = "".join(b.get("text", "") for b in d.get("content", []) if isinstance(b, dict) and b.get("type") == "text").strip()
    u = d.get("usage") or {}
    return text, int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0)), str(d.get("model") or model)


def ask_openai(prompt: str, model_value: str, key: str | None = None, http=None) -> tuple[str, int, int, str]:
    """One question to ChatGPT with this PC's own OpenAI key. Returns (text, tokens in, tokens out, model id). Raises RuntimeError with a plain reason."""
    key = key or openai_key()
    if not key:
        raise RuntimeError("ChatGPT is not connected on this PC. Run: python dse.py openai setup")
    model = PROVIDER_MODELS.get(model_value, PROVIDER_MODELS["openai"])
    body = json.dumps({"model": model, "max_completion_tokens": 300, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}).encode("utf-8")
    headers = {"Authorization": "Bearer " + key, "content-type": "application/json"}
    if http is None:
        def http(url, hdrs, data):        # noqa: E306
            req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.status, r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8", "replace")
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                raise RuntimeError(f"Could not reach OpenAI ({e})") from None
    code, raw = http("https://api.openai.com/v1/chat/completions", headers, body)
    try:
        d = json.loads(raw)
    except ValueError:
        d = {}
    if code != 200:
        why = str((d.get("error") or {}).get("message", "")) or f"HTTP {code}"
        raise RuntimeError(("OpenAI says: " + why)[:200].replace(key, "..."))
    text = str(((d.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    u = d.get("usage") or {}
    return text, int(u.get("prompt_tokens", 0) or 0), int(u.get("completion_tokens", 0) or 0), str(d.get("model") or model)


def ask_gemini(prompt: str, model_value: str, key: str | None = None, http=None) -> tuple[str, int, int, str]:
    """One question to Gemini with this PC's own Google key. Returns (text, tokens in, tokens out, model id). Raises RuntimeError with a plain reason."""
    key = key or gemini_key()
    if not key:
        raise RuntimeError("Gemini is not connected on this PC. Run: python dse.py gemini setup")
    model = PROVIDER_MODELS.get(model_value, PROVIDER_MODELS["gemini"])
    body = json.dumps({"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 300}}).encode("utf-8")
    headers = {"x-goog-api-key": key, "content-type": "application/json"}
    if http is None:
        def http(url, hdrs, data):        # noqa: E306
            req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.status, r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8", "replace")
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                raise RuntimeError(f"Could not reach Google ({e})") from None
    code, raw = http(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers, body)
    try:
        d = json.loads(raw)
    except ValueError:
        d = {}
    if code != 200:
        why = str((d.get("error") or {}).get("message", "")) or f"HTTP {code}"
        raise RuntimeError(("Google says: " + why)[:200].replace(key, "..."))
    cand = (d.get("candidates") or [{}])[0]
    text = "".join(str(p.get("text") or "") for p in ((cand.get("content") or {}).get("parts") or []) if isinstance(p, dict)).strip()
    u = d.get("usageMetadata") or {}
    return text, int(u.get("promptTokenCount", 0) or 0), int(u.get("candidatesTokenCount", 0) or 0), model


def ask_ollama(prompt: str, name: str, http=None) -> tuple[str, int, int, str]:
    """One question to a local Ollama model on this PC (free). Returns (text, tokens in, tokens out, model name). Raises RuntimeError with a plain reason."""
    body = json.dumps({"model": name, "stream": False, "system": SYSTEM, "messages": [{"role": "user", "content": prompt}], "options": {"num_predict": 400}}).encode("utf-8")
    if http is None:
        def http(url, data):        # noqa: E306
            req = urllib.request.Request(url, data=data, headers={"content-type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    return r.status, r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8", "replace")
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                raise RuntimeError(f"Ollama is not answering on this PC ({e}). Start Ollama, or pick a different model in the column's Run settings in Citadel.") from None
    code, raw = http("http://localhost:11434/api/chat", body)
    try:
        d = json.loads(raw)
    except ValueError:
        d = {}
    if code != 200:
        why = str(d.get("error") or "") or f"HTTP {code}"
        raise RuntimeError(("Ollama says: " + why)[:200])
    text = str((d.get("message") or {}).get("content", "")).strip()
    return text, int(d.get("prompt_eval_count", 0) or 0), int(d.get("eval_count", 0) or 0), name


def _ollama_pick(task: str = "") -> str:
    """The PC's best local model, by the same choice the HQ chat makes (chat/ollama_model.py)."""
    try:
        import importlib.util
        p = Path(__file__).resolve().parents[1] / "chat" / "ollama_model.py"
        spec = importlib.util.spec_from_file_location("hq_ollama_model", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.pick(task=task)[0]
    except Exception:
        return "gemma3:1b"


def resolve_model(step: dict, key_present=None) -> str:
    """The model an AI source will actually use. 'auto' becomes Claude Haiku when a Claude key is connected on this PC (cheap, and the member
    connected Claude on purpose), else the PC's best local model. Every other stored choice is used as it stands."""
    m = clean_model((step or {}).get("model"))
    if m != "auto":
        return m
    has = key_present() if key_present else claude_key()
    return "claude:haiku" if has else "ollama:" + _ollama_pick()


def ask_any(prompt: str, model: str, key: str | None = None, http=None, ollama_http=None) -> tuple[str, int, int, str]:
    """One question to the model the member chose for the source: a local Ollama model, a Claude tier, a ChatGPT or Gemini model
    on the member's own key for that provider, or (as a safety net) Automatic."""
    m = clean_model(model)
    if m.startswith("ollama:"):
        return ask_ollama(prompt, m.split(":", 1)[1], http=ollama_http)
    if m == "auto":
        return ask_any(prompt, resolve_model({"model": "auto"}, key_present=(lambda: key or claude_key())), key=key, http=http, ollama_http=ollama_http)
    if m in PROVIDER_MODELS:
        return (ask_openai if provider_of(m) == "openai" else ask_gemini)(prompt, m, key=key, http=http)
    return ask_claude(prompt, CLAUDE_TIERS.get(m, "haiku"), key=key, http=http)


def read_site(website: str) -> dict:
    from . import enrich
    return enrich.enrich_site(website, render=False)


# ------------------------------------------------------------------ the run

def read_rows(api, grid_id: str) -> list[dict]:
    rows: list[dict] = []
    for off in range(0, 20000, READ_PAGE):
        part = api.rpc("hq_grid_rows", {"p_grid": grid_id, "p_offset": off, "p_limit": READ_PAGE}, tries=2) or []
        rows.extend(part)
        if len(part) < READ_PAGE:
            break
    return rows


def save_cells(api, grid_id: str, updates: list[dict]) -> int:
    return int(api.rpc("hq_grid_set_cells", {"p_grid": grid_id, "p_updates": updates}, tries=2) or 0)


def run(grid_ref: str, col_ref: str, mode: str = "empty", limit: int = 0, dry: bool = False, say=print, api=None, ask=None, site=None, cost=None, key_present=None, sleep=time.sleep) -> str:
    if mode not in ("empty", "stale", "all"):
        raise ValueError("mode must be empty, stale or all.")
    api = api or gridpush.connect()
    grid = gridpush.resolve_grid(gridpush._grids(api), grid_ref)
    columns = parse_columns(grid.get("doc"))
    col = find_column(columns, col_ref)
    why = problem(col, columns)
    if why:
        raise ValueError(why)
    steps = steps_of(col["run"])
    rows = read_rows(api, grid["id"])
    pick = pick_rows(rows, col, columns, mode, limit)
    todo = pick["rows"]
    kind = f"tries {len(steps)} sources in order" if len(steps) > 1 else "asks an AI" if steps[0]["kind"] == "ai" else "reads the website"
    head = f"{grid.get('workbook', '')}/{grid['name']}: column '{col['label']}' {kind} for {len(todo)} of {pick['total']} rows ({'every row' if mode == 'all' else 'empty or out-of-date rows' if mode == 'stale' else 'empty rows only'}{f', first {limit}' if limit else ''}); {pick['skipped']} skipped (nothing to read){f'; {pick["outdated"]} out of date' if mode == 'stale' else ''}."
    if dry or not todo:
        return head + ("\nDry run: nothing was asked and nothing was saved.\n" if dry else "\nNothing to run.\n")
    say(head)
    uses_ai = any(st["kind"] == "ai" for st in steps)
    uses_site = any(st["kind"] == "site" for st in steps)
    resolved = [resolve_model(st, key_present=key_present) if st["kind"] == "ai" else None for st in steps]
    needs_claude = any(is_claude_model(m) for m in resolved)
    if needs_claude:
        if not (key_present() if key_present else claude_key()):
            raise RuntimeError("Claude is not connected on this PC. Run: python dse.py claude setup")
        cost = cost or _cost()
        if cost.over_limit() and not uses_site:
            raise RuntimeError(f"Today's Claude limit ({cost.limit():,} tokens, set by you) is used up. Raise it with: python dse.py claude limit <tokens>")
    for m in resolved:
        prov = provider_of(m or "")
        if prov == "openai" and not openai_key():
            raise RuntimeError("ChatGPT is not connected on this PC. Run: python dse.py openai setup")
        if prov == "gemini" and not gemini_key():
            raise RuntimeError("Gemini is not connected on this PC. Run: python dse.py gemini setup")
    if uses_ai:
        ask = ask or (lambda p, m: ask_any(p, m))
    if uses_site:
        site = site or read_site
    by = {norm(c["label"]): c for c in columns}
    total = len(todo)
    done = failed = no_answer = misfit = filled = 0
    skipped = pick["skipped"]
    streak = 0
    pending: list[dict] = []
    site_cache: dict[str, dict] = {}
    by_source = [0] * len(steps)
    note = ""

    def flush() -> None:
        nonlocal failed, filled, pending
        if not pending:
            return
        try:
            save_cells(api, grid["id"], pending)
            filled += sum(1 for u in pending if col["key"] in u["cells"])
        except Exception:               # one bad row must not lose the batch: save them one at a time
            for u in pending:
                try:
                    save_cells(api, grid["id"], [u])
                    filled += 1 if col["key"] in u["cells"] else 0
                except Exception:
                    failed += 1
        pending = []

    for r in todo:
        data = r.get("data") or {}
        value, used = None, None
        attempted = errored = 0
        fitted = ai_blocked = False
        last_err = ""
        for si, st in enumerate(steps):               # the waterfall: the first source that gives an answer that fits wins
            if not step_has_inputs(st, columns, data):
                continue
            if st["kind"] == "ai" and is_claude_model(resolved[si]) and cost is not None and cost.over_limit():
                ai_blocked = True
                continue
            try:
                if st["kind"] == "ai":
                    text, tin, tout, model = ask(build_prompt(st["prompt"], columns, data), resolved[si])
                    if is_claude_model(resolved[si]) and cost is not None:
                        try:
                            cost.record(model, tin, tout)
                        except Exception:
                            pass
                else:
                    src = cell_text(by[norm(st["from"])], data)
                    if src not in site_cache:
                        site_cache[src] = site(src)
                    text = site_value(site_cache[src], st["field"])
            except Exception as e:                    # this source failed for this row: the next one is still tried
                errored += 1
                last_err = str(e)
                continue
            attempted += 1
            if not (text or "").strip() or text.strip().upper() == "UNKNOWN":
                continue
            v = coerce(col, text)
            if v is None:
                fitted = True                         # an answer came but did not fit the column type
                continue
            value, used = v, si
            break
        if value is None and ai_blocked:
            note = f"STOPPED: today's Claude limit ({cost.limit():,} tokens) was reached. Raise it with: python dse.py claude limit <tokens>"
            break
        fp = fingerprint(col, columns, data)
        if value is not None:
            streak = 0
            by_source[used] += 1
            pending.append({"id": r["id"], "cells": {col["key"]: value, fp_key(col): fp}})
        elif attempted == 0 and errored > 0:          # every source that was tried failed: a failed row, and a run of them in a row stops it
            failed += 1
            streak += 1
            if streak >= STOP_AFTER_FAILS:
                note = f"STOPPED: {streak} rows in a row failed. Last problem: {last_err[:160]}"
                done += 1
                break
        else:
            streak = 0
            if fitted:
                misfit += 1
            else:
                no_answer += 1
            pending.append({"id": r["id"], "cells": {fp_key(col): fp}})        # tried with these inputs and nothing came of it: not asked again until they change
        done += 1
        if len(pending) >= BATCH:
            flush()
        if done % 3 == 0 or done == total:
            say(f"PROGRESS {done}/{total} failed {failed} skipped {skipped}")
    flush()
    say(f"PROGRESS {done}/{total} failed {failed} skipped {skipped}")
    order = ("1st", "2nd", "3rd", "4th", "5th")
    out = (f"FINISHED {filled} filled, {failed} failed, {skipped} skipped, {no_answer} no answer" + (f", {misfit} did not fit the column type" if misfit else "")
           + (", by source: " + ", ".join(f"{order[i]} {n}" for i, n in enumerate(by_source)) if len(steps) > 1 else ""))
    return (note + "\n" if note else "") + out + "\n"


def cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="dse.py grid run")
    ap.add_argument("grid")
    ap.add_argument("column")
    ap.add_argument("--mode", default="empty", choices=["empty", "stale", "all"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    try:
        print(run(a.grid, a.column, a.mode, a.limit, a.dry, say=lambda m: print(m, flush=True)), end="")
        return 0
    except (ValueError, RuntimeError) as e:
        msg = str(e)
        print("grid run: " + ("the database update 20261224090000_grid_run_column.sql has not been run yet (ask the super admin)" if "hq_grid_" in msg and "function" in msg.lower() else msg[:300]))
        return 1


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
