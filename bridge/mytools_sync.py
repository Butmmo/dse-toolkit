"""My tools sync: the tools you made in Citadel (HQ Tools, My tools), and the ones DBI shared, onto this PC; whether each is ready, back.

    python bridge/mytools_sync.py          pull recipes into my-tools/ and report which are ready
    python bridge/mytools_sync.py --dry    show what would change

The runner runs this every minute (catalog.json "periodic"). A recipe is DATA (a name, inputs and steps that call tools this PC already has): it is checked here
against this PC's own tools before it is offered, and a recipe with a problem is simply not offered, with the reason sent back so Citadel can show it.
Recipe files you saved on this PC by hand are never touched or deleted. Recipes DBI shared are copies: one DBI withdrew is removed here. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from dse import mytools  # noqa: E402

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def _runner():
    spec = importlib.util.spec_from_file_location("dse_runner", HERE / "runner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(p: Path, data: dict, dry: bool) -> bool:
    old = None
    try:
        old = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if old == data:
        return False
    if not dry:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    r = _runner()
    api = r.Api(r.load_env())
    pulled = api.rpc("hq_tools_pull", {}) or {}
    mine, shared = pulled.get("mine", []) or [], pulled.get("shared", []) or []
    changed = 0
    live_mine = set()
    for t in mine:
        slug = t.get("slug", "")
        if not SLUG.match(slug) or not isinstance(t.get("spec"), dict):
            continue
        live_mine.add(slug)
        changed += _write(mytools.MINE / f"{slug}.json", {"slug": slug, "name": t.get("name", slug), "spec": t["spec"], "archived": bool(t.get("archived")),
                                                           "from_citadel": True, "citadel_updated_at": t.get("updated_at")}, a.dry)
    # a recipe deleted in Citadel stays on this PC, marked, and is no longer offered
    for p in sorted(mytools.MINE.glob("*.json")) if mytools.MINE.is_dir() else []:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if d.get("from_citadel") and p.stem not in live_mine and not d.get("removed_in_citadel"):
            changed += 1
            if not a.dry:
                d["removed_in_citadel"] = dt.date.today().isoformat()
                p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    live_shared = set()
    for t in shared:
        slug = t.get("slug", "")
        if not SLUG.match(slug) or not isinstance(t.get("spec"), dict):
            continue
        live_shared.add(slug)
        changed += _write(mytools.SHARED / f"{slug}.json", {"slug": slug, "name": t.get("name", slug), "spec": t["spec"], "active": True, "citadel_updated_at": t.get("updated_at")}, a.dry)
    for p in sorted(mytools.SHARED.glob("*.json")) if mytools.SHARED.is_dir() else []:
        if p.stem not in live_shared:
            changed += 1
            if not a.dry:
                p.unlink(missing_ok=True)
    if a.dry:
        print(f"{len(mine)} of your tools and {len(shared)} shared in Citadel, {changed} would change")
        return
    status = {}
    for c in mytools.check_all():
        if c["key"].startswith("my.") and c["key"][3:] in live_mine:
            status[c["key"][3:]] = {"ok": c["ok"], "steps": c["steps"], "problems": c["problems"][:3], "checked_at": dt.datetime.now().isoformat(timespec="seconds")}
    if status:
        api.rpc("hq_tools_status", {"p_status": status})
    if changed:
        print(f"{dt.datetime.now():%H:%M:%S} my tools sync: {changed} change(s) from Citadel ({len(mine)} yours, {len(shared)} shared)")


if __name__ == "__main__":
    main()
