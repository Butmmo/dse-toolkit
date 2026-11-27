"""Grid dedupe: find duplicate rows in a Ledger grid and merge them, with a preview first.

Duplicates are rows that share a website domain or an email address. The oldest row stays;
cells it is missing are filled from the rows it absorbs, and where two rows hold different
values the oldest row's value wins and the clash is reported, never hidden. Nothing is
changed in preview mode: the member reads the plan (also saved as
my-lists/dedupe-plan-<grid id>.json), then runs again with Merge now ticked to apply it.
Merging writes the fills first through hq_grid_set_cells, then removes the absorbed rows
through hq_grid_delete_rows (a one-time Citadel migration; if it has not been run, the run
stops before changing anything and says so).

The plan also flags rows whose domain or email appears in the member's OTHER grids
(cross-engine flags), so a lead living in two engines is visible before anyone merges.

Pure rules (normalising, grouping, merging) are separate from the grid calls and tested by
tests/test_grid_dedupe.py with a fake grid API.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import gridpush, gridrun

ROOT = Path(__file__).resolve().parents[1]
MAX_DETAIL_GROUPS = 30
DELETE_CHUNK = 100

_EMAIL = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")


def domain_of(value) -> str:
    """The bare domain of a website value: scheme, www, path and case removed. '' when unusable."""
    s = str(value or "").strip().lower()
    if not s:
        return ""
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s)
    s = s.split("/")[0].split("?")[0].split("#")[0]
    s = s.rsplit("@", 1)[-1].split(":")[0]
    if s.startswith("www."):
        s = s[4:]
    return s if "." in s and " " not in s else ""


def email_of(value) -> str:
    """The normalised email in a value, or '' when it does not look like one."""
    s = str(value or "").strip().lower()
    return s if _EMAIL.match(s) else ""


def _norm_label(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(label or "").lower()).strip()


def find_key_column(columns: list[dict], kind: str) -> dict | None:
    """The column a dedupe kind reads: the email column, or the website/domain column."""
    words = ("email", "e mail") if kind == "email" else ("website", "domain", "url", "site", "web")
    for col in columns:
        label = _norm_label(col.get("label", ""))
        if any(w in label for w in words):
            return col
    return None


def _cell(data: dict, key: str) -> str:
    v = (data or {}).get(key)
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v).strip()


def row_label(row: dict, columns: list[dict], key_col: dict | None) -> str:
    """A short human label for a row: its name-like cell, else its key value, else its first cell."""
    data = row.get("data") or {}
    for col in columns:
        if any(w in _norm_label(col.get("label", "")) for w in ("name", "business", "company")):
            text = _cell(data, col["key"])
            if text:
                return text
    if key_col:
        text = _cell(data, key_col["key"])
        if text:
            return text
    for col in columns:
        text = _cell(data, col["key"])
        if text:
            return text
    return "(empty row)"


def plan_groups(rows: list[dict], columns: list[dict], kind: str, key_col: dict) -> list[dict]:
    """Duplicate groups with their merge plan. The oldest row (rows arrive oldest first) stays."""
    key_of = domain_of if kind == "domain" else email_of
    by_key: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        k = key_of(_cell(row.get("data") or {}, key_col["key"]))
        if k:
            by_key.setdefault(k, []).append(i)
    groups = []
    for k, idxs in by_key.items():
        if len(idxs) < 2:
            continue
        keep = rows[idxs[0]]
        absorbed = [rows[i] for i in idxs[1:]]
        merged = dict(keep.get("data") or {})
        fills, conflicts = [], []
        for col in columns:
            ck = col["key"]
            current = _cell(merged, ck)
            for j, other in zip(idxs[1:], absorbed):
                value = _cell(other.get("data") or {}, ck)
                if not value:
                    continue
                if not current:
                    merged[ck] = (other.get("data") or {}).get(ck)
                    current = value
                    fills.append({"key": ck, "label": col["label"], "value": value, "raw": (other.get("data") or {}).get(ck), "from_row": j + 1})
                elif value != current:
                    conflicts.append({"label": col["label"], "kept": current, "dropped": value, "from_row": j + 1})
        groups.append({
            "key": k,
            "keep_id": keep["id"], "keep_row": idxs[0] + 1,
            "absorbed_ids": [r["id"] for r in absorbed],
            "absorbed_rows": [i + 1 for i in idxs[1:]],
            "fills": fills, "conflicts": conflicts,
        })
    return groups


def other_engine_keys(api, grids: list[dict], this_id: str, kind: str, wanted: set[str]) -> dict[str, list[str]]:
    """Where else each wanted key lives: key -> ['Workbook / Grid', ...] across the member's other grids."""
    key_of = domain_of if kind == "domain" else email_of
    found: dict[str, set[str]] = {}
    for g in grids:
        if g["id"] == this_id:
            continue
        col = find_key_column(gridpush.columns_of(g.get("doc")), kind)
        if col is None:
            continue
        where = f"{g.get('workbook', '')} / {g['name']}"
        for row in gridrun.read_rows(api, g["id"]):
            k = key_of(_cell(row.get("data") or {}, col["key"]))
            if k and k in wanted:
                found.setdefault(k, set()).add(where)
    return {k: sorted(v) for k, v in found.items()}


def build_plan(api, grid: dict, kind: str) -> dict:
    columns = gridpush.columns_of(grid.get("doc"))
    key_col = find_key_column(columns, kind)
    if key_col is None:
        what = "no email column" if kind == "email" else "no website or domain column"
        raise ValueError(f"This grid has {what} to dedupe by. Its columns: " + ", ".join(c["label"] for c in columns) + ".")
    rows = gridrun.read_rows(api, grid["id"])
    key_of = domain_of if kind == "domain" else email_of
    groups = plan_groups(rows, columns, kind, key_col)
    all_keys = {key_of(_cell(r.get("data") or {}, key_col["key"])) for r in rows}
    all_keys.discard("")
    also_in = other_engine_keys(api, gridpush._grids(api), grid["id"], kind, all_keys) if all_keys else {}
    for g in groups:
        g["keep_label"] = row_label(rows[g["keep_row"] - 1], columns, key_col)
        g["absorbed_labels"] = [row_label(rows[i - 1], columns, key_col) for i in g["absorbed_rows"]]
        g["also_in"] = also_in.get(g["key"], [])
    grouped_keys = {g["key"] for g in groups}
    flags = []
    for i, row in enumerate(rows):
        k = key_of(_cell(row.get("data") or {}, key_col["key"]))
        if k and k not in grouped_keys and k in also_in:
            flags.append({"key": k, "row": i + 1, "label": row_label(row, columns, key_col), "also_in": also_in[k]})
    return {
        "grid_id": grid["id"], "grid": grid["name"], "workbook": grid.get("workbook", ""),
        "kind": kind, "key_column": key_col["label"], "rows": len(rows),
        "groups": groups, "flags": flags,
    }


def render(plan: dict, applied: dict | None = None) -> str:
    place = f"{plan['workbook']} / {plan['grid']}"
    lines = [f"Grid: {place} ({plan['rows']} rows), dedupe by {plan['kind']} (column: {plan['key_column']})"]
    groups = plan["groups"]
    if not groups:
        lines.append("No duplicate rows found: every row has its own " + ("domain." if plan["kind"] == "domain" else "email."))
    else:
        absorbed = sum(len(g["absorbed_ids"]) for g in groups)
        lines.append(f"{len(groups)} duplicate group(s): {absorbed} row(s) would be merged away, {plan['rows'] - absorbed} row(s) would remain.")
        for n, g in enumerate(groups[:MAX_DETAIL_GROUPS], 1):
            lines.append("")
            lines.append(f"{n}. {g['key']} (also in: {', '.join(g['also_in'])})" if g["also_in"] else f"{n}. {g['key']}")
            lines.append(f"   Stays: row {g['keep_row']} ({g['keep_label']})")
            lines.append("   Merged away: " + ", ".join(f"row {r} ({l})" for r, l in zip(g["absorbed_rows"], g["absorbed_labels"])))
            for f in g["fills"]:
                lines.append(f"   Fills {f['label']}: {f['value']} (from row {f['from_row']})")
            for c in g["conflicts"]:
                lines.append(f"   Clash on {c['label']}: keeping '{c['kept']}', dropping '{c['dropped']}' (row {c['from_row']})")
        if len(groups) > MAX_DETAIL_GROUPS:
            lines.append(f"   ... and {len(groups) - MAX_DETAIL_GROUPS} more group(s), counted above. The saved plan file lists them all.")
    if plan["flags"]:
        lines.append("")
        lines.append("Also living in other engines (not duplicates in this grid):")
        for f in plan["flags"][:30]:
            lines.append(f"   Row {f['row']} ({f['label']}): {f['key']} is also in {', '.join(f['also_in'])}")
        if len(plan["flags"]) > 30:
            lines.append(f"   ... and {len(plan['flags']) - 30} more, listed in the saved plan file.")
    if applied is not None:
        lines.append("")
        lines.append(f"Merged: {applied['deleted']} row(s) removed, {applied['filled']} surviving row(s) filled in. The grid now holds {plan['rows'] - applied['deleted']} rows.")
    else:
        lines.append("")
        lines.append("Preview only: nothing was changed. The full plan is saved as dedupe-plan-" + plan["grid_id"] + ".json. Run again with Merge now ticked to apply it.")
    return "\n".join(lines) + "\n"


def run(grid_ref: str, kind: str = "domain", apply: bool = False, api=None, say=print) -> str:
    if kind not in ("domain", "email"):
        raise ValueError("Dedupe by domain or email.")
    api = api or gridpush.connect()
    if api is None:
        raise RuntimeError("This PC is not connected to Citadel yet (run the HQ Tools setup first).")
    grid = gridpush.resolve_grid(gridpush._grids(api), grid_ref)
    plan = build_plan(api, grid, kind)
    out_dir = ROOT / "my-lists"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"dedupe-plan-{grid['id']}.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
    if not apply or not plan["groups"]:
        return render(plan)
    # Deletes first: if the one-time migration has not been run, the first delete fails
    # before anything has changed, and the run stops with the reason.
    absorbed_ids = [rid for g in plan["groups"] for rid in g["absorbed_ids"]]
    deleted = 0
    for off in range(0, len(absorbed_ids), DELETE_CHUNK):
        chunk = absorbed_ids[off:off + DELETE_CHUNK]
        try:
            n = api.rpc("hq_grid_delete_rows", {"p_grid": grid["id"], "p_ids": chunk}, tries=2)
        except Exception as e:
            if off == 0:
                raise RuntimeError("Merging needs a one-time Citadel update first: the migration 20270122120000_grid_delete_rows.sql has not been run in Supabase yet, so rows cannot be removed. Nothing was changed.") from e
            raise
        deleted += int(n or 0)
    updates = [{"id": g["keep_id"], "cells": {f["key"]: f["raw"] for f in g["fills"]}} for g in plan["groups"] if g["fills"]]
    filled = 0
    for off in range(0, len(updates), 100):
        filled += gridrun.save_cells(api, grid["id"], updates[off:off + 100])
    return render(plan, {"deleted": deleted, "filled": filled})


def cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="dse.py grid dedupe")
    ap.add_argument("grid")
    ap.add_argument("--by", choices=["domain", "email"], default="domain")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    try:
        print(run(a.grid, a.by, a.apply), end="")
        return 0
    except (ValueError, RuntimeError) as e:
        print("grid dedupe: " + str(e)[:400])
        return 1
