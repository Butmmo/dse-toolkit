"""Engines sync: your engines from DBI Citadel (HQ Tools → My engines) onto this PC, and their progress back.

    python bridge/engines_sync.py          pull engines into engines/<slug>/engine.json, report lists/rows back
    python bridge/engines_sync.py --dry    show what would change

The runner runs this every minute in the background (catalog.json "periodic"), so engines you create or edit
on your phone are ready here within a minute. Folders and lists are never deleted: an engine archived in
Citadel is only marked archived here. Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ENGINES = ROOT / "engines"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def _runner():
    spec = importlib.util.spec_from_file_location("dse_runner", HERE / "runner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def engine_json(e: dict) -> dict:
    cfg = dict(e.get("config") or {})
    cfg.update({"name": e["name"], "path": e["path"], "archived": bool(e.get("archived")),
                "citadel_updated_at": e.get("updated_at")})
    cfg.setdefault("pack", "smb" if e["path"] == "custom" else e["path"])
    return cfg


def status_of(slug: str) -> dict:
    d = ENGINES / slug / "send-lists"
    lists = sorted(p for p in d.glob("*.csv")) if d.exists() else []
    drafts = sorted((d / "drafts").glob("*.csv")) if (d / "drafts").exists() else []
    rows = 0
    for p in lists + drafts:
        try:
            with open(p, encoding="utf-8-sig", newline="") as f:
                rows += max(0, sum(1 for _ in csv.reader(f)) - 1)
        except OSError:
            pass
    dates = [p.stem[:10] for p in lists if re.match(r"\d{4}-\d{2}-\d{2}", p.stem)]
    st = {"lists": len(lists), "drafts": len(drafts), "rows": rows, "last_list": max(dates) if dates else None,
          "checked_at": dt.datetime.now().isoformat(timespec="seconds")}
    try:                                   # results and follow-ups due: never let a problem here stop the sync
        sys.path.insert(0, str(ROOT))
        from dse import followups, outcomes
        st["results"] = outcomes.summary(slug)
        st["followups_due"] = followups.due_count(slug)
    except Exception:
        pass
    return st


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    r = _runner()
    api = r.Api(r.load_env())
    engines = api.rpc("hq_engines_pull", {}) or []
    changed = 0
    for e in engines:
        slug = e.get("slug", "")
        if not SLUG.match(slug):
            continue
        d = ENGINES / slug
        new = engine_json(e)
        p = d / "engine.json"
        old = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        if old == new:
            continue
        changed += 1
        if a.dry:
            print(f"would {'update' if old else 'create'} {slug}")
            continue
        for sub in ("send-lists/drafts", "content", "data"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # An engine deleted in Citadel stays on this PC (its lists are never deleted) but is archived and marked, so the tools stop offering it.
    live = {e.get("slug") for e in engines}
    gone = []
    if ENGINES.exists():
        for d in sorted(ENGINES.iterdir()):
            f = d / "engine.json"
            if d.is_dir() and f.is_file() and SLUG.match(d.name) and d.name not in live:
                try:
                    cfg = json.loads(f.read_text(encoding="utf-8"))
                except ValueError:
                    continue
                if not cfg.get("removed_in_citadel"):
                    gone.append((d.name, f, cfg))
    for slug, f, cfg in gone:
        if a.dry:
            print(f"would archive {slug} (deleted in Citadel)")
            continue
        cfg.update({"archived": True, "removed_in_citadel": dt.date.today().isoformat()})
        f.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        changed += 1
        print(f"{dt.datetime.now():%H:%M:%S} engines sync: '{slug}' was deleted in Citadel; kept on this PC and archived (files are in engines/{slug})")
    if a.dry:
        print(f"{len(engines)} engines in Citadel, {changed} would change")
        return
    status = {e["slug"]: status_of(e["slug"]) for e in engines if SLUG.match(e.get("slug", "")) and (ENGINES / e["slug"]).exists()}
    if status:
        api.rpc("hq_engines_status", {"p_status": status})
    if changed:
        print(f"{dt.datetime.now():%H:%M:%S} engines sync: {changed} engine(s) updated from Citadel")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(f"engines sync: {e}")
