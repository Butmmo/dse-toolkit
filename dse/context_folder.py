"""Engine context folders: tell an engine to read a folder of earlier work, so the tools can pick it up with you.

    python dse.py context <engine> --add <folder> [--label "Interior designers work"]     attach a folder (only its PATH is stored) and read it
    python dse.py context <engine> --scan                                                 read the attached folders again
    python dse.py context <engine> --show                                                 what the engine understood from them
    python dse.py context <engine> --remove <folder>                                      detach a folder (the folder itself is never touched)
    python dse.py context <engine> --suggest                                              what the folders suggest for this engine's settings (nothing is changed)
    python dse.py context <engine> --adopt <lead-list.csv> [--apply]                      bring a lead list from the folder into the engine (preview unless --apply)

What it reads: markdown, text, JSON, CSV and spreadsheets (the first sheet's header and row count), inside the folder and a few levels down.
README, CONTEXT, AGENTS, CLAUDE, HANDOVER and numbered "00-" files are read first, because that is where the story of the work usually is.
It writes engines/<engine>/context/digest.md and digest.json: a short summary of each file, the headings, the JSON keys, the CSV columns and
row counts, which CSVs look like lead lists, the prices and the niche, offer and goal lines it found. DBI-AI chat uses the digest when you ask
about this engine.

What it never does (these are rules, not options):
  * it never reads _private-keys, _memory-vault/encrypted, .ssh, .aws, .gnupg, .env files, key files, files named like passwords, secrets, tokens or credentials
  * it never opens an encrypted file or an archive, and it never asks for or stores a password: encrypted files are only LISTED as "not read".
    If you want an encrypted file understood, decrypt it yourself into a plain folder and attach that folder
  * it hides anything that looks like a key, token or password in what it stores
  * it never changes, moves or deletes anything in your folder, and it never imports lead lists for you: it only says which CSVs look like lead lists
  * the digest stays on this PC. Text reaches an AI only when you chat with your own key, and then only a short part of it
Folders can be anywhere on this PC (a folder you copied over, or one inside the HQ folder). A relative path is looked for from where you are, then the
toolkit, then the HQ folder above it. Stdlib only (a spreadsheet is read only if openpyxl is installed).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import shutil
from collections import Counter
from pathlib import Path

from .common import ROOT
from .engines import engine_dir, load

HQ_ROOT = ROOT.parent
MAX_DEPTH = 5
MAX_FILES = 400
MAX_READ = 60_000               # bytes read from one file
MAX_SUMMARY = 320               # characters kept as a file's summary
DIGEST_MD_MAX = 60_000          # characters in digest.md
PRIORITY_RX = re.compile(r"^(readme|context|agents|claude|handover|notes|plan|00-)", re.I)

FORBIDDEN_DIRS = {"_private-keys", ".ssh", ".gnupg", ".aws", ".git", "node_modules", "__pycache__", ".venv", "venv", "encrypted"}
SECRET_NAME = re.compile(r"(^\.env|password|passwd|secret|credential|token|private[-_ ]?key|id_rsa|id_ed25519|\.pem$|\.key$|\.pfx$|\.p12$|\.kdbx$|\.keystore$)", re.I)
ENCRYPTED_EXT = {".enc", ".gpg", ".pgp", ".age", ".vault", ".aes", ".sealed", ".crypt"}
ARCHIVE_EXT = {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz"}
TEXT_EXT = {".md", ".markdown", ".txt", ".rst"}
DATA_EXT = {".json", ".csv", ".tsv", ".yaml", ".yml", ".toml", ".xlsx"}

LEAD_COLS = {"business", "company", "website", "url", "domain", "email", "phone", "city", "name", "instagram", "facebook", "linkedin", "owner", "contact"}

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z ]*PRIVATE KEY-----|$)"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b[A-Fa-f0-9]{40,}\b"),
    re.compile(r"(?i)\b(api[_ -]?key|secret|token|passw(?:or)?d|pwd|authorization)\b\s*[:=]\s*[\"']?[^\s\"',;]{6,}"),
]


def redact(text: str) -> str:
    """Hide anything that looks like a key, token or password."""
    t = text or ""
    for rx in SECRET_PATTERNS:
        t = rx.sub(lambda m: (m.group(1) + ": [hidden]") if m.lastindex and m.group(1) and rx.pattern.startswith("(?i)") else "[hidden]", t)
    return t


# ------------------------------------------------------------------ folders

def resolve_folder(text: str) -> Path:
    raw = (text or "").strip().strip('"').strip("'")
    if not raw:
        raise ValueError("Tell me which folder to read.")
    p = Path(os.path.expanduser(raw))
    tries = [p] if p.is_absolute() else [Path.cwd() / p, ROOT / p, HQ_ROOT / p]
    for t in tries:
        if t.is_dir():
            return t.resolve()
    raise ValueError(f"I cannot find the folder '{raw}'. Give the full path, or a path inside the HQ folder.")


def unsafe_reason(path: Path) -> str | None:
    """Why a folder must not be attached, or None when it is fine."""
    parts = [x.lower() for x in path.parts]
    for bad in ("_private-keys", ".ssh", ".gnupg", ".aws"):
        if bad in parts:
            return f"it is inside '{bad}', which is never read"
    low = "/".join(parts)
    if "_memory-vault/encrypted" in low or ("_memory-vault" in parts and "encrypted" in parts):
        return "it is the encrypted memory vault, which is never read"
    real = [x for x in path.parts if x not in (path.anchor, "\\", "/")]
    if len(real) <= 2 and not (HQ_ROOT == path or ROOT == path):
        return "it is too broad (a drive or a user folder): choose the folder that holds this one piece of work"
    if path.name.lower() in ("desktop", "documents", "downloads", "onedrive", "pictures", "videos") and len(real) <= 3:
        return "it is too broad (a whole Desktop, Documents or Downloads folder): choose the folder that holds this one piece of work"
    if path == HQ_ROOT or path == ROOT:
        return "it is the whole HQ or toolkit folder: choose the folder that holds this one piece of work"
    return None


def classify(path: Path) -> tuple[str, str]:
    """(kind, why) where kind is text, json, csv, sheet, config or skip."""
    name, ext = path.name, path.suffix.lower()
    if name.startswith(".") and not name.lower().startswith(".context"):
        return "skip", "hidden file"
    if SECRET_NAME.search(name):
        return "skip", "named like a secret or a key (never read)"
    if ext in ENCRYPTED_EXT:
        return "skip", "encrypted (never opened; no password is asked for)"
    if ext in ARCHIVE_EXT:
        return "skip", "an archive (never opened)"
    if ext in TEXT_EXT:
        return "text", ""
    if ext == ".json" or ext == ".jsonl":
        return "json", ""
    if ext in (".csv", ".tsv"):
        return "csv", ""
    if ext == ".xlsx":
        return "sheet", ""
    if ext in (".yaml", ".yml", ".toml"):
        return "config", ""
    return "skip", "not a text or data file"


def _read(path: Path, limit: int = MAX_READ) -> str:
    with path.open("rb") as f:
        raw = f.read(limit)
    return raw.decode("utf-8", errors="ignore").lstrip("﻿")


def _para(text: str) -> str:
    for block in re.split(r"\n\s*\n", text):
        b = " ".join(x.strip() for x in block.splitlines() if x.strip() and not x.strip().startswith(("#", "|", "---", "```")))
        if len(b) > 25:
            return b[:MAX_SUMMARY]
    return ""


def summarise_text(text: str, fallback: str) -> dict:
    t = redact(text)
    heads = [m.group(2).strip() for m in re.finditer(r"^(#{1,3})\s+(.+?)\s*#*\s*$", t, re.M)][:8]
    return {"title": heads[0] if heads else fallback, "headings": heads[1:8], "summary": _para(t)}


KEEP_VALUES = {"name", "title", "purpose", "offer", "niche", "brand", "description", "goal", "status", "price", "path", "audience", "city", "cities"}


def summarise_json(text: str, fallback: str) -> dict:
    try:
        data = json.loads(text)
    except ValueError:
        return {"title": fallback, "keys": [], "summary": "(a JSON file that could not be read whole: it may be long)"}
    out: dict = {"title": fallback, "keys": [], "summary": ""}
    if isinstance(data, list):
        out["summary"] = f"a list of {len(data)} items"
        if data and isinstance(data[0], dict):
            out["keys"] = [str(k) for k in list(data[0])[:20]]
        return out
    if isinstance(data, dict):
        out["keys"] = [str(k) for k in list(data)[:25]]
        facts = []
        for k, v in data.items():
            if str(k).lower() in KEEP_VALUES and isinstance(v, (str, int, float)):
                facts.append(f"{k}: {redact(str(v))[:100]}")
        out["summary"] = "; ".join(facts[:8])
    return out


def summarise_csv(path: Path) -> dict:
    delim = "\t" if path.suffix.lower() == ".tsv" else ","
    try:
        with path.open(encoding="utf-8-sig", errors="ignore", newline="") as f:
            rd = csv.reader(f, delimiter=delim)
            head = next(rd, [])
            n = sum(1 for _ in zip(range(20_000), rd))
    except (OSError, csv.Error):
        return {"title": path.name, "columns": [], "rows": 0, "lead_list": False, "summary": "could not be read as a table"}
    cols = [c.strip() for c in head][:30]
    hits = {c.lower() for c in cols} & LEAD_COLS
    lead = len(hits) >= 2 and n >= 5
    cities: list[str] = []
    if lead and any(c.lower() == "city" for c in cols):
        try:
            with path.open(encoding="utf-8-sig", errors="ignore", newline="") as f:
                dr = csv.DictReader(f, delimiter=delim)
                key = next(c for c in dr.fieldnames or [] if (c or "").strip().lower() == "city")
                cities = [f"{c} ({k})" for c, k in Counter((r.get(key) or "").strip() for _i, r in zip(range(5000), dr) if (r.get(key) or "").strip()).most_common(5)]
        except (OSError, csv.Error, StopIteration):
            cities = []
    return {"title": path.name, "columns": cols, "rows": n, "lead_list": lead, "cities": cities,
            "summary": f"{n} rows; columns: {', '.join(cols[:12])}" + (" ... " if len(cols) > 12 else "")}


def summarise_sheet(path: Path) -> dict:
    try:
        import openpyxl  # type: ignore
    except ImportError:
        return {"title": path.name, "columns": [], "rows": 0, "lead_list": False, "summary": "a spreadsheet (install openpyxl to read its first sheet)"}
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        head = [str(c.value).strip() for c in next(ws.iter_rows(min_row=1, max_row=1), []) if c.value is not None][:30]
        n = max(0, (ws.max_row or 1) - 1)
        names = wb.sheetnames
        wb.close()
    except Exception:
        return {"title": path.name, "columns": [], "rows": 0, "lead_list": False, "summary": "a spreadsheet that could not be opened"}
    lead = len({c.lower() for c in head} & LEAD_COLS) >= 2 and n >= 5
    return {"title": path.name, "columns": head, "rows": n, "lead_list": lead, "summary": f"{len(names)} sheet(s): {', '.join(names[:6])}; first sheet {n} rows; columns: {', '.join(head[:12])}"}


PRICE_RX = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:/|per|a)\s?(?:mo|month|year|hour|yr)\b)?(?:\s(?:setup|set-up|one-time|upfront)\b)?", re.I)
LINE_KEYS = {"niche": re.compile(r"\bniche\b", re.I), "offer": re.compile(r"\boffer(s|ing)?\b", re.I), "goal": re.compile(r"\bgoal(s)?\b", re.I)}
LABELLED = {k: re.compile(r"^(?:%s)[a-z ]{0,24}:\s*(.+)$" % w, re.I) for k, w in (("niche", "niche|market|audience|buyer"), ("offer", "offer|price|pricing|package"), ("goal", "goal|target|aim|next step"))}


def tidy(line: str) -> str:
    """One line of markdown as plain words: no bold marks, links, code ticks, headings, bullets or numbering."""
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
    t = re.sub(r"[*_`]+", "", t)
    t = re.sub(r"^\s*(?:[-*+>#]+|\d{1,2}[.)])\s*", "", t)
    return re.sub(r"\s+", " ", t).strip()


def sentence(text: str, limit: int = 140) -> str:
    """The text cut at the end of a sentence (or a word) inside the limit."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    m = list(re.finditer(r"[.!?;](\s|$)", cut))
    if m and m[-1].start() > 40:
        return cut[: m[-1].start() + 1]
    return cut.rsplit(" ", 1)[0].rstrip(",;:") + "..."


def extract_signals(red: str, signals: dict) -> None:
    """Prices with their words, and the niche, offer and goal lines, tidy and short. Labelled lines ('Goal: ...') come first, then plain sentences."""
    for m in PRICE_RX.findall(red)[:10]:
        m = re.sub(r"\s+", " ", m.strip())
        if m and m not in signals["prices"] and len(signals["prices"]) < 10:
            signals["prices"].append(m)
    fence = False
    labelled: dict[str, list[str]] = {k: [] for k in LINE_KEYS}
    plain: dict[str, list[str]] = {k: [] for k in LINE_KEYS}
    for raw in red.splitlines():
        if raw.strip().startswith("```"):
            fence = not fence
            continue
        if fence or raw.count("|") >= 2:
            continue
        ln = tidy(raw)
        if not (12 < len(ln) <= 400) or ln.endswith("?") or ln.startswith("http"):
            continue
        for k, rx in LABELLED.items():
            m = rx.match(ln)
            if m and len(m.group(1)) > 8:
                v = sentence(m.group(1).strip())
                if v not in labelled[k]:
                    labelled[k].append(v)
        for k, rx in LINE_KEYS.items():
            if rx.search(ln) and not LABELLED[k].match(ln):
                v = sentence(ln)
                if len(v) >= 20 and v not in plain[k]:
                    plain[k].append(v)
    for k in LINE_KEYS:
        for v in labelled[k] + plain[k]:
            if v not in signals[k] and len(signals[k]) < 5:
                signals[k].append(v)


def scan_folder(root: Path) -> dict:
    """Read one folder (read-only) into a digest of what is in it."""
    root = root.resolve()
    files, skipped, signals = [], [], {"prices": [], "niche": [], "offer": [], "goal": []}
    seen_real = str(root)
    total = 0
    newest = 0.0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        depth = len(Path(dirpath).relative_to(root).parts)
        keep = []
        for d in sorted(dirnames):
            full = Path(dirpath) / d
            if d.lower() in FORBIDDEN_DIRS or d.startswith(".") or full.is_symlink():
                skipped.append({"path": str(full.relative_to(root)).replace(os.sep, "/") + "/", "reason": "a folder that is never read" if d.lower() in FORBIDDEN_DIRS else "hidden or linked folder"})
            elif depth + 1 > MAX_DEPTH:
                skipped.append({"path": str(full.relative_to(root)).replace(os.sep, "/") + "/", "reason": f"deeper than {MAX_DEPTH} levels"})
            elif not os.path.realpath(full).startswith(seen_real):
                skipped.append({"path": str(full.relative_to(root)).replace(os.sep, "/") + "/", "reason": "leads outside the folder"})
            else:
                keep.append(d)
        dirnames[:] = keep
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            rel = str(p.relative_to(root)).replace(os.sep, "/")
            kind, why = classify(p)
            if p.is_symlink():
                skipped.append({"path": rel, "reason": "a link"})
                continue
            if kind == "skip":
                if why and why != "not a text or data file" and why != "hidden file":
                    skipped.append({"path": rel, "reason": why})
                continue
            total += 1
            if total > MAX_FILES:
                skipped.append({"path": rel, "reason": f"more than {MAX_FILES} files: the rest are not read"})
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            newest = max(newest, st.st_mtime)
            rec: dict = {"path": rel, "kind": kind, "size": st.st_size, "modified": dt.datetime.fromtimestamp(st.st_mtime).date().isoformat(),
                         "priority": bool(PRIORITY_RX.match(p.name)) and depth <= 1}
            try:
                if kind == "text":
                    txt = _read(p)
                    rec.update(summarise_text(txt, p.name))
                    extract_signals(redact(txt), signals)
                elif kind in ("json", "config"):
                    rec.update(summarise_json(_read(p), p.name) if kind == "json" else {"title": p.name, "summary": _para(redact(_read(p, 4000)))})
                elif kind == "csv":
                    rec.update(summarise_csv(p))
                elif kind == "sheet":
                    rec.update(summarise_sheet(p))
            except OSError:
                skipped.append({"path": rel, "reason": "could not be read"})
                continue
            files.append(rec)
    files.sort(key=lambda r: (not r["priority"], r["path"].count("/"), r["path"].lower()))
    return {"root": str(root), "files": files, "skipped": skipped[:80], "signals": signals,
            "newest": dt.datetime.fromtimestamp(newest).date().isoformat() if newest else "", "file_count": len(files)}


# ------------------------------------------------------------------ the engine's attached folders

def _cfg_path(slug: str) -> Path:
    return engine_dir(slug) / "engine.json"


def _save_cfg(slug: str, cfg: dict) -> None:
    cfg = {k: v for k, v in cfg.items() if k != "slug"}
    tmp = _cfg_path(slug).with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(_cfg_path(slug))


def attached(slug: str) -> list[dict]:
    return list(load(slug).get("context_folders") or [])


def attach(slug: str, folder: str, label: str = "") -> Path:
    cfg = load(slug)
    p = resolve_folder(folder)
    why = unsafe_reason(p)
    if why:
        raise ValueError(f"I will not attach '{p}': {why}.")
    old = next((x for x in (cfg.get("context_folders") or []) if x.get("path") == str(p)), None)
    items = [x for x in (cfg.get("context_folders") or []) if x.get("path") != str(p)]
    # attaching the same folder again keeps its name and date unless you give a new name
    items.append({"path": str(p), "label": (label or (old or {}).get("label") or p.name)[:60], "added": (old or {}).get("added") or dt.date.today().isoformat()})
    cfg["context_folders"] = items[:8]
    _save_cfg(slug, cfg)
    return p


def detach(slug: str, folder: str) -> bool:
    cfg = load(slug)
    raw = (folder or "").strip().strip('"')
    keep, gone = [], False
    for x in cfg.get("context_folders") or []:
        if x.get("path") == raw or Path(x.get("path", "")).name.lower() == Path(raw).name.lower() or (x.get("label") or "").lower() == raw.lower():
            gone = True
        else:
            keep.append(x)
    cfg["context_folders"] = keep
    _save_cfg(slug, cfg)
    return gone


def _md(slug: str, digests: list[dict]) -> str:
    L = [f"# What the engine '{slug}' understood from its folders", "",
         f"Read on {dt.date.today().isoformat()}. This file is written by the Engine context tool. It is a summary, never a copy: secrets are hidden and encrypted files are only listed.", ""]
    for d in digests:
        L += [f"## {d['label']}", f"Folder: {d['root']}", f"{d['file_count']} readable files; newest change {d['newest'] or 'unknown'}.", ""]
        pri = [f for f in d["files"] if f["priority"]]
        if pri:
            L.append("### Read first (the story of the work)")
            for f in pri[:12]:
                L.append(f"- {f['path']}: {f.get('title', '')}. {f.get('summary', '')}".strip())
            L.append("")
        rest = [f for f in d["files"] if not f["priority"]]
        if rest:
            L.append("### Other files")
            for f in rest[:120]:
                extra = f.get("summary") or ""
                if f.get("headings"):
                    extra = (extra + " Headings: " + "; ".join(f["headings"][:4])).strip()
                if f.get("keys"):
                    extra = (extra + " Keys: " + ", ".join(f["keys"][:8])).strip()
                L.append(f"- {f['path']} ({f['kind']}): {extra}".rstrip(": "))
            L.append("")
        leads = [f for f in d["files"] if f.get("lead_list")]
        if leads:
            L.append("### These look like lead lists (not imported: check them with 'My engine: check my file')")
            for f in leads[:10]:
                L.append(f"- {f['path']}: {f['rows']} rows; columns: {', '.join(f.get('columns', [])[:10])}")
            L.append("")
        sg = d["signals"]
        if any(sg.values()):
            L.append("### Signals found")
            for k, label in (("prices", "Prices mentioned"), ("niche", "Niche lines"), ("offer", "Offer lines"), ("goal", "Goal lines")):
                if sg[k]:
                    L.append(f"- {label}: " + " | ".join(sg[k]))
            L.append("")
        if d["skipped"]:
            L.append("### Not read")
            for s in d["skipped"][:40]:
                L.append(f"- {s['path']}: {s['reason']}")
            L.append("")
        if not pri:
            L.append("Tip: add a README.md or CONTEXT.md to this folder saying who the work is for, what the offer is, what is done and what comes next. The engine reads those first.")
            L.append("")
    out = "\n".join(L)
    return out[:DIGEST_MD_MAX]


def scan(slug: str) -> list[dict]:
    items = attached(slug)
    digests = []
    for it in items:
        p = Path(it["path"])
        if not p.is_dir():
            digests.append({"label": it.get("label") or p.name, "root": str(p), "files": [], "skipped": [{"path": str(p), "reason": "the folder is not there any more"}], "signals": {"prices": [], "niche": [], "offer": [], "goal": []}, "newest": "", "file_count": 0})
            continue
        why = unsafe_reason(p)
        if why:
            digests.append({"label": it.get("label") or p.name, "root": str(p), "files": [], "skipped": [{"path": str(p), "reason": why}], "signals": {"prices": [], "niche": [], "offer": [], "goal": []}, "newest": "", "file_count": 0})
            continue
        d = scan_folder(p)
        d["label"] = it.get("label") or p.name
        digests.append(d)
    out = engine_dir(slug) / "context"
    out.mkdir(parents=True, exist_ok=True)
    (out / "digest.json").write_text(json.dumps({"engine": slug, "read_on": dt.date.today().isoformat(), "folders": digests}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "digest.md").write_text(_md(slug, digests) + "\n", encoding="utf-8")
    return digests


def digest_for_chat(slug: str, budget: int = 3500) -> str:
    """A short part of the digest for DBI-AI chat: the story files first, then the signals. Empty when nothing is attached or read."""
    p = engine_dir(slug) / "context" / "digest.json"
    if not p.is_file():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return ""
    L = []
    for d in data.get("folders", []):
        L.append(f"Folder '{d.get('label')}' ({d.get('file_count', 0)} readable files, newest {d.get('newest') or 'unknown'}):")
        for f in [x for x in d.get("files", []) if x.get("priority")][:6]:
            L.append(f"- {f['path']}: {f.get('title', '')}. {f.get('summary', '')}".strip())
        for f in [x for x in d.get("files", []) if not x.get("priority")][:10]:
            L.append(f"- {f['path']}: {(f.get('summary') or '')[:120]}".rstrip(": "))
        sg = d.get("signals") or {}
        for k in ("prices", "niche", "offer", "goal"):
            if sg.get(k):
                L.append(f"{k}: " + " | ".join(sg[k][:4]))
        if any(f.get("lead_list") for f in d.get("files", [])):
            L.append("It also holds lead lists (not imported).")
    return redact("\n".join(L))[:budget]


def report(slug: str, add: str = "", label: str = "", remove: str = "", do_scan: bool = False, show: bool = False) -> str:
    load(slug)
    L = []
    if add:
        p = attach(slug, add, label)
        L.append(f"Attached: {p}")
        do_scan = True
    if remove:
        L.append("Detached." if detach(slug, remove) else f"No attached folder matches '{remove}'. (Your folder itself is never touched.)")
    if do_scan:
        digests = scan(slug)
        n = sum(d["file_count"] for d in digests)
        sk = sum(len(d["skipped"]) for d in digests)
        L.append(f"Read {len(digests)} folder(s): {n} readable file(s), {sk} not read.")
        L.append(f"Saved: engines/{slug}/context/digest.md and digest.json")
    items = attached(slug)
    if show or not (add or remove or do_scan):
        if not items:
            L.append(f"The engine '{slug}' has no folders attached. Attach one: python dse.py context {slug} --add <folder>")
        else:
            for it in items:
                L.append(f"- {it.get('label')}: {it.get('path')} (attached {it.get('added')})")
            md = engine_dir(slug) / "context" / "digest.md"
            if md.is_file():
                L += ["", md.read_text(encoding="utf-8")]
            else:
                L.append(f"Not read yet: python dse.py context {slug} --scan")
    if add or do_scan:
        L += ["", "DBI-AI chat now uses a short part of this when you ask about this engine. Nothing leaves this PC unless you chat with your own key."]
    return "\n".join(L)


# ------------------------------------------------------------------ suggest and adopt (the digest stays on this PC, so this is done here)

MAX_ADOPT_BYTES = 5_000_000
MAX_SEEDS = 500


def lead_lists(slug: str) -> list[dict]:
    """Lead-list candidates from the engine's digest: {folder, label, path (relative), rows, columns, cities}."""
    p = engine_dir(slug) / "context" / "digest.json"
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return []
    out = []
    for d in data.get("folders", []):
        for x in d.get("files", []):
            if x.get("lead_list"):
                out.append({"folder": d.get("root", ""), "label": d.get("label", ""), "path": x["path"], "rows": x.get("rows", 0), "columns": x.get("columns", []), "cities": x.get("cities", []), "kind": x.get("kind", "csv")})
    return out


def engine_mode(cfg: dict) -> str:
    """How this engine gets its leads: import, pasted, seeds, podcasts, finder, or none (a chat-and-notes engine)."""
    path = cfg.get("path", "smb")
    mode = cfg.get("source") if path == "custom" else {"gtm": "import", "authority": "pasted"}.get(path)
    if path == "custom" and (mode or "none") == "none":
        return "none"
    if mode in ("import", "pasted"):
        return mode
    if path == "broadcast" or mode == "podcasts":
        return "podcasts"
    if path in ("ministry", "revenue", "ascent") or mode == "seeds":
        return "seeds"
    return "finder"


def suggest(slug: str) -> str:
    """What the attached folders suggest for this engine. Nothing is changed."""
    cfg = load(slug)
    p = engine_dir(slug) / "context" / "digest.json"
    if not attached(slug):
        return f"No folders attached to '{slug}'. Attach one first: python dse.py context {slug} --add <folder>"
    if not p.is_file():
        return f"Not read yet: python dse.py context {slug} --scan"
    data = json.loads(p.read_text(encoding="utf-8"))
    sg = {k: [] for k in ("prices", "niche", "offer", "goal")}
    cities: Counter = Counter()
    for d in data.get("folders", []):
        for k in sg:
            sg[k] += [x for x in (d.get("signals") or {}).get(k, []) if x not in sg[k]]
        for x in d.get("files", []):
            for c in x.get("cities", []):
                m = re.match(r"(.+) \((\d+)\)$", c)
                if m:
                    cities[m.group(1)] += int(m.group(2))
    L = [f"What the folders suggest for '{slug}' (nothing was changed; edit the engine in Citadel, My engines):", ""]
    L.append(f"- Cities in the lead lists: {', '.join(f'{c} ({n})' for c, n in cities.most_common(6))}" if cities else "- Cities: none found in the lead lists.")
    cur = cfg.get("cities") or []
    if cities and cur:
        L.append(f"  This engine's cities today: {', '.join(cur)}.")
    for k, label in (("niche", "Niche lines"), ("offer", "Offer lines"), ("goal", "Goal lines")):
        if sg[k]:
            L.append(f"- {label}: " + " | ".join(sg[k][:4]))
    if sg["prices"]:
        L.append("- Prices mentioned: " + ", ".join(sg["prices"][:8]))
    leads = lead_lists(slug)
    mode = engine_mode(cfg)
    if leads:
        L.append(f"- {len(leads)} lead list(s) you could bring in (this engine takes its leads by: {mode}):")
        for x in leads[:8]:
            L.append(f"    {x['label']}:{x['path']} ({x['rows']} rows)")
        L.append(f"  Preview one: python dse.py context {slug} --adopt \"<label>:<path>\"   (add --apply to do it)")
    else:
        L.append("- No lead lists found in the folders.")
    if not any(sg.values()) and not leads and not cities:
        L.append("- Nothing to suggest yet. A CONTEXT.md in the folder (who it is for, the offer and price, what is done, what is next) gives the engine the most.")
    return "\n".join(L)


def _find_in_folders(slug: str, ref: str) -> Path:
    """The file named by '<label>:<relative path>', a relative path, or a full path, but only inside an attached folder."""
    items = attached(slug)
    if not items:
        raise ValueError("No folders are attached to this engine yet.")
    ref = (ref or "").strip().strip('"')
    label = ""
    if ":" in ref and not re.match(r"^[A-Za-z]:[\\/]", ref):
        label, ref = ref.split(":", 1)
    roots = [Path(i["path"]) for i in items if not label or (i.get("label") or "").lower() == label.strip().lower() or Path(i["path"]).name.lower() == label.strip().lower()]
    cands = []
    for r in roots:
        q = Path(ref)
        cands.append(q if q.is_absolute() else r / q)
    for q in cands:
        try:
            real = q.resolve()
        except OSError:
            continue
        if real.is_file() and any(str(real).lower().startswith(str(r.resolve()).lower()) for r in roots):
            return real
    raise ValueError(f"I cannot find '{ref}' inside the folders attached to this engine. Use the path shown by --suggest, for example \"Label:leads.csv\".")


def _rows(path: Path) -> tuple[list[str], list[dict]]:
    delim = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(encoding="utf-8-sig", errors="ignore", newline="") as f:
        dr = csv.DictReader(f, delimiter=delim)
        rows = [r for _i, r in zip(range(20_000), dr)]
        return [h for h in (dr.fieldnames or [])], rows


def _col(headers: list[str], *names: str) -> str:
    low = {h.strip().lower(): h for h in headers if h}
    for n in names:
        if n in low:
            return low[n]
    for h in low:
        if any(n in h for n in names):
            return low[h]
    return ""


def adopt(slug: str, ref: str, apply: bool = False) -> str:
    """Bring a lead list from an attached folder into the engine. Preview unless apply. The original file is only ever copied from."""
    cfg = load(slug)
    mode = engine_mode(cfg)
    if mode == "none":
        raise ValueError("This engine is a chat-and-notes engine: it has no lead lists to bring in.")
    src = _find_in_folders(slug, ref)
    kind, why = classify(src)
    if kind != "csv":
        raise ValueError(f"Only CSV lead lists can be brought in ({src.name}: {why or kind}). Save the sheet as a CSV first.")
    if src.stat().st_size > MAX_ADOPT_BYTES:
        raise ValueError("That file is bigger than 5 MB. Split it first.")
    headers, rows = _rows(src)
    web = _col(headers, "website", "url", "domain", "site")
    name = _col(headers, "business", "company", "name")
    city = _col(headers, "city")
    with_site = [r for r in rows if (r.get(web) or "").strip()] if web else []
    L = [f"Lead list: {src.name}: {len(rows)} rows, {len(with_site)} with a website. Engine '{slug}' takes its leads by: {mode}."]
    target = ""
    if mode in ("import", "pasted"):
        folder = engine_dir(slug) / ("imports" if mode == "import" else "pasted")
        dest = folder / f"adopted-{src.name}"
        n = 2
        while dest.exists():
            dest = folder / f"adopted-{src.stem}-{n}{src.suffix}"
            n += 1
        target = f"copy to engines/{slug}/{folder.name}/{dest.name}"
        if apply:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    elif mode == "seeds":
        if not web:
            raise ValueError("This engine works from website addresses, and that list has no website column.")
        have = {re.sub(r"^https?://(www\.)?", "", (u.get("url") if isinstance(u, dict) else u or "").lower()).strip("/") for u in list(cfg.get("seed_urls") or []) + list(cfg.get("local_seed_urls") or [])}
        add = []
        for r in with_site:
            u = (r.get(web) or "").strip()
            key = re.sub(r"^https?://(www\.)?", "", u.lower()).strip("/")
            if key and key not in have and len(have) + len(add) < MAX_SEEDS:
                have.add(key)
                add.append({"url": u if u.lower().startswith("http") else "https://" + u, "name": (r.get(name) or "").strip()[:80], "city": (r.get(city) or "").strip()[:60]})
        target = f"add {len(add)} new website(s) to the engine's seed list (kept on this PC) ({len(with_site) - len(add)} already there or over the limit of {MAX_SEEDS})"
        if apply and add:
            cfg["local_seed_urls"] = list(cfg.get("local_seed_urls") or []) + add        # kept apart from Citadel's list so a sync never drops them
            _save_cfg(slug, cfg)
    else:
        dest = engine_dir(slug) / "adopted" / src.name
        n = 2
        while dest.exists():
            dest = engine_dir(slug) / "adopted" / f"{src.stem}-{n}{src.suffix}"
            n += 1
        target = f"keep a copy at engines/{slug}/adopted/{dest.name} for reference"
        L.append("This engine finds its own leads (by business type and city), so the list is kept for reference and the engine's settings are NOT changed.")
        L.append("To work those rows, make an engine that takes website addresses (Revenue or Ascent), or use Lead enrichment on the file.")
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    L.append(("Done: " if apply else "Preview (nothing changed): would ") + target + ".")
    if not apply:
        L.append(f"To do it: python dse.py context {slug} --adopt \"{ref}\" --apply")
    L.append("Your original file is never changed or moved.")
    return "\n".join(L)
