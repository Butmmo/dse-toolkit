"""HQ Tools into grids: send a list (a lead list, or a tool's result such as an enriched list) into a grid of one of your Ledgers.

    python dse.py grid list                                       your grids: Ledger, grid name, how many columns, and which are keys
    python dse.py grid push <csv> <grid> [--key <column>] [--no-new-columns] [--overwrite] [--only a,b,c] [--dry]

<grid> is the grid's name (or "Ledger/grid name", or its id). What happens:
  * the CSV's headers are matched to the grid's columns by name (and by the usual other names: Website = URL = Domain, Email = Work email, Company = Business name ...);
  * a header the grid has no column for becomes a NEW column (text, email, link, number, date or yes/no, guessed from its values) unless you say --no-new-columns; --only lists the headers to bring;
  * with a KEY (default: the Email column, else the website) a lead is added once: sending it again fills the cells that are empty and keeps what you typed; --overwrite replaces cells instead;
  * --dry shows exactly what would happen and sends nothing.
Rows are marked as coming from a tool. Workflows of that Ledger start for the rows it adds, like for rows you type. Needs this PC to be connected to Citadel and the database file
20261213090000_hq_grids.sql. Nothing leaves your account; the CSV is never changed.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

MAX_ROWS = 5000
CHUNK = 200
TYPES = {"text", "longtext", "number", "date", "checkbox", "url", "email", "phone"}

# other names people use for the same thing: a header in one group fills a column whose name is in the same group
GROUPS = [
    {"email", "e mail", "email address", "work email", "contact email", "emails", "mail"},
    {"website", "url", "domain", "site", "web", "website url", "company website", "company domain", "homepage"},
    {"company", "company name", "business", "business name", "organisation", "organization", "account", "name"},
    {"phone", "telephone", "mobile", "tel", "phone number", "contact phone", "mobile phone", "work phone"},
    {"first name", "firstname", "given name"},
    {"last name", "lastname", "surname", "family name"},
    {"full name", "contact", "contact name", "person", "owner", "owner name", "decision maker"},
    {"job title", "title", "role", "position"},
    {"city", "town", "location"},
    {"country"},
    {"notes", "note", "comments", "comment", "description"},
    {"linkedin", "linkedin url", "linkedin profile", "profile link", "profile"},
]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def clean_label(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:40]


# ------------------------------------------------------------------ reading

def load_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    raw = path.read_bytes().decode("utf-8-sig", errors="replace")
    first = raw.split("\n", 1)[0]
    delim = max([",", ";", "\t"], key=first.count) if any(d in first for d in ",;\t") else ","
    rows = list(csv.reader(raw.splitlines(), delimiter=delim))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise ValueError("The file needs a header row and at least one row of data.")
    if len(rows) - 1 > MAX_ROWS:
        raise ValueError(f"Send up to {MAX_ROWS:,} rows at a time (this file has {len(rows) - 1:,}).")
    headers = [clean_label(h) for h in rows[0]]
    return headers, [r for r in rows[1:]]


def columns_of(doc_text: str | None) -> list[dict]:
    """The columns a grid has, from its stored column document."""
    try:
        d = json.loads(doc_text or "{}")
    except ValueError:
        return []
    out = []
    for c in d.get("custom", []) if isinstance(d, dict) else []:
        if isinstance(c, dict) and re.fullmatch(r"c_[a-z0-9_]{1,40}", str(c.get("key", ""))) and c.get("type") != "formula":
            out.append({"key": c["key"], "label": str(c.get("label") or c["key"]), "type": c.get("type") if c.get("type") in TYPES else "text"})
    return out


def resolve_grid(grids: list[dict], ref: str) -> dict:
    ref = (ref or "").strip()
    if not ref:
        raise ValueError("Name the grid, like: python dse.py grid push my-lists/leads.csv \"Dentists UK/Leads\"")
    for g in grids:
        if g["id"] == ref:
            return g
    low = ref.lower()
    both = [g for g in grids if f"{g.get('workbook', '')}/{g['name']}".lower() == low]
    if len(both) == 1:
        return both[0]
    named = [g for g in grids if g["name"].lower() == low]
    if len(named) == 1:
        return named[0]
    if len(named) > 1:
        raise ValueError("More than one grid is called that. Say which Ledger too, like: " + ", ".join(f'"{g.get("workbook", "")}/{g["name"]}"' for g in named[:4]))
    have = ", ".join(f'"{g.get("workbook", "")}/{g["name"]}"' for g in grids[:8]) or "none yet (make one in Citadel: Ledgers)"
    raise ValueError(f"I do not know a grid '{ref}'. Your grids: {have}.")


# ------------------------------------------------------------------ matching headers to columns

def infer_type(values: list[str]) -> str:
    v = [x.strip() for x in values if x.strip()][:200]
    if not v:
        return "text"
    allv = lambda rx: all(re.fullmatch(rx, x) for x in v)  # noqa: E731
    if allv(r"(?i)yes|no|y|n|true|false"):
        return "checkbox"
    if allv(r"-?[\d,]*\.?\d+") and all(re.search(r"\d", x) for x in v):
        return "number"
    if allv(r"\d{4}-\d{2}-\d{2}.*|\d{1,2}[/.-]\d{1,2}[/.-]\d{4}"):
        return "date"
    if sum(bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", x)) for x in v) / len(v) >= 0.8:
        return "email"
    if sum(bool(re.match(r"(?i)(https?://|www\.)", x)) for x in v) / len(v) >= 0.8:
        return "url"
    if any(len(x) > 120 for x in v):
        return "longtext"
    return "text"


def map_headers(headers: list[str], columns: list[dict], rows: list[list[str]], new_columns: bool = True, only: set[str] | None = None) -> dict:
    """{'mapped': {header index: column}, 'new': {header index: type}, 'ignored': [headers]}. A column is filled by one header only (the first that matches)."""
    by_label = {norm(c["label"]): c for c in columns}
    used: set[str] = set()
    mapped: dict[int, dict] = {}
    new: dict[int, str] = {}
    ignored: list[str] = []
    for i, h in enumerate(headers):
        if not h:
            continue
        if only is not None and norm(h) not in only:
            ignored.append(h)
            continue
        col = by_label.get(norm(h))
        if col is None:
            grp = next((g for g in GROUPS if norm(h) in g), None)
            if grp:
                col = next((c for c in columns if norm(c["label"]) in grp and c["key"] not in used), None)
        if col is not None and col["key"] not in used:
            used.add(col["key"])
            mapped[i] = col
        elif new_columns:
            new[i] = infer_type([r[i] if i < len(r) else "" for r in rows])
        else:
            ignored.append(h)
    return {"mapped": mapped, "new": new, "ignored": ignored}


def choose_key(requested: str, columns: list[dict]) -> str | None:
    """The column that says two rows are the same lead: the one asked for, else Email, else the website."""
    if requested:
        r = norm(requested)
        for c in columns:
            if c["key"] == requested or norm(c["label"]) == r:
                return c["key"]
        raise ValueError(f"The grid has no column called '{requested}'. Its columns: " + ", ".join(c["label"] for c in columns) + ".")
    for want in ("email", "website"):
        grp = next((g for g in GROUPS if want in g), {want})
        for c in columns:
            if norm(c["label"]) in grp or (want == "email" and c["type"] == "email"):
                return c["key"]
    return None


def convert(value: str, ctype: str):
    v = (value or "").strip()
    if v == "":
        return None
    if ctype == "number":
        t = v.replace(",", "")
        try:
            f = float(t)
            return int(f) if f.is_integer() else f
        except ValueError:
            return v
    if ctype == "checkbox":
        return True if re.fullmatch(r"(?i)yes|y|true|1", v) else False if re.fullmatch(r"(?i)no|n|false|0", v) else v
    if ctype == "date":
        m = re.match(r"(\d{4}-\d{2}-\d{2})", v)
        if m:
            return m.group(1)
        m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", v)
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m and int(m.group(2)) <= 12 else v
    return v[:2000]


# ------------------------------------------------------------------ the work

def connect():
    from . import crmsync
    return crmsync.connect()


def _grids(api) -> list[dict]:
    return api.rpc("hq_grid_list", {}, tries=2) or []


def list_grids(api=None) -> str:
    api = api or connect()
    if api is None:
        return "This PC is not connected to Citadel yet (run the HQ Tools setup first).\n"
    gs = _grids(api)
    if not gs:
        return "You have no grids yet. In Citadel open Ledgers, make a Ledger and add a grid; it appears here.\n"
    out = []
    for g in gs:
        cols = columns_of(g.get("doc"))
        out.append(f"{g.get('workbook', '')} / {g['name']}  ({len(cols)} columns: " + ", ".join(c["label"] for c in cols[:8]) + (", ..." if len(cols) > 8 else "") + ")")
    return "\n".join(out) + "\n"


def push(csv_path: Path, grid_ref: str, key: str = "", new_columns: bool = True, overwrite: bool = False, only: str = "", dry: bool = False, api=None, say=lambda *_: None) -> str:
    headers, rows = load_csv(csv_path)
    api = api or connect()
    if api is None:
        raise ValueError("This PC is not connected to Citadel yet (run the HQ Tools setup first).")
    grid = resolve_grid(_grids(api), grid_ref)
    cols = columns_of(grid.get("doc"))
    only_set = {norm(x) for x in only.split(",") if norm(x)} if only else None
    plan = map_headers(headers, cols, rows, new_columns, only_set)
    if not plan["mapped"] and not plan["new"]:
        raise ValueError("None of the file's headers matched a column of that grid, and new columns are off. Its columns: " + ", ".join(c["label"] for c in cols) + ".")
    # new columns first (the grid then has them), so the rows can use their keys
    created: dict[int, dict] = {}
    if plan["new"] and not dry:
        res = api.rpc("hq_grid_add_columns", {"p_grid": grid["id"], "p_cols": [{"label": headers[i], "type": t} for i, t in plan["new"].items()]}, tries=2) or []
        for (i, t), r in zip(plan["new"].items(), res):
            created[i] = {"key": r["key"], "label": r["label"], "type": r.get("type", t), "created": r.get("created", True)}
    elif plan["new"]:
        created = {i: {"key": "(new)", "label": headers[i], "type": t, "created": True} for i, t in plan["new"].items()}
    allcols = {**plan["mapped"], **created}
    keycol = choose_key(key, cols + [c for c in created.values() if c["key"] != "(new)"])
    payload = []
    for r in rows:
        row = {}
        for i, c in allcols.items():
            v = convert(r[i] if i < len(r) else "", c["type"])
            if v is not None and c["key"] != "(new)":
                row[c["key"]] = v
        payload.append(row)
    lines = [f"Grid: {grid.get('workbook', '')} / {grid['name']}", f"File: {csv_path.name}, {len(rows)} rows"]
    lines.append("Fills: " + (", ".join(f"{headers[i]} -> {c['label']}" for i, c in plan["mapped"].items()) or "(nothing existing)"))
    if created:
        lines.append(("Would make new columns: " if dry else "New columns: ") + ", ".join(f"{c['label']} ({c['type']})" + ("" if c.get("created", True) else " [already there]") for c in created.values()))
    if plan["ignored"]:
        lines.append("Left out: " + ", ".join(plan["ignored"]))
    kl = next((c["label"] for c in cols + list(created.values()) if c["key"] == keycol), None)
    lines.append(f"Key: {kl}: a lead already in the grid is filled in, not added again." if keycol else "Key: none, so every row is added (a second run would add them again). Use --key to avoid that.")
    if dry:
        lines.append("Dry run: nothing was sent.")
        return "\n".join(lines) + "\n"
    tot = {"added": 0, "updated": 0, "unchanged": 0, "skipped": 0, "invalid": 0}
    err = ""
    for i in range(0, len(payload), CHUNK):
        res = api.rpc("hq_grid_push", {"p_grid": grid["id"], "p_rows": payload[i:i + CHUNK], "p_key": keycol, "p_overwrite": bool(overwrite)}, tries=2) or {}
        for k in tot:
            tot[k] += int(res.get(k, 0))
        err = err or str(res.get("error", ""))
        say(f"sent {min(i + CHUNK, len(payload))} of {len(payload)}")
    lines.append(f"Done: {tot['added']} added, {tot['updated']} filled in or updated, {tot['unchanged']} already up to date, {tot['skipped']} skipped (empty or no key value)" + (f", {tot['invalid']} could not be added" if tot["invalid"] else "") + ".")
    if err:
        lines.append("First problem: " + err)
    return "\n".join(lines) + "\n"


def cli(argv: list[str]) -> int:
    if argv and argv[0] == "run":          # python dse.py grid run <grid> <column>: Run column (dse/gridrun.py)
        from . import gridrun
        return gridrun.cli(argv[1:])
    import argparse
    ap = argparse.ArgumentParser(prog="dse.py grid")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("push")
    p.add_argument("csv")
    p.add_argument("grid")
    p.add_argument("--key", default="")
    p.add_argument("--no-new-columns", action="store_true", dest="no_new")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--only", default="")
    p.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            print(list_grids(), end="")
            return 0
        root = Path(__file__).resolve().parents[1]
        path = Path(a.csv) if Path(a.csv).is_absolute() else root / a.csv
        if not path.is_file():
            raise ValueError(f"I cannot find {a.csv}.")
        print(push(path, a.grid, a.key, not a.no_new, a.overwrite, a.only, a.dry, say=lambda m: print(m, flush=True)), end="")
        return 0
    except (ValueError, RuntimeError) as e:
        msg = str(e)
        print("grid: " + ("the database update 20261213090000_hq_grids.sql has not been run yet (ask the super admin)" if "hq_grid_" in msg and "function" in msg.lower() else msg[:300]))
        return 1


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
