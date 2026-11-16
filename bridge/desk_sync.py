"""Send Desk sync for your engines: your lists on your phone, your phone taps back into your log.

    python bridge/desk_sync.py          pull taps from the phone, then push the lists around today
    python bridge/desk_sync.py --dry    show what would happen, change nothing

The runner does this every minute in the background (catalog.json "periodic"). Order is fixed: PULL first (every tap
you made on the phone becomes a line in engines/<slug>/data/log.csv with the time you tapped), then acknowledge them,
then PUSH (lists from 2 days ago to 3 days ahead, plus every open reply, each with the status the log says).
Only your own engines (My engines) are touched. Nothing here sends a message. Stdlib only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from dse import desklog as dl  # noqa: E402
from dse import outreach  # noqa: E402

DAYS_BACK, DAYS_AHEAD = 2, 3
CAL_AHEAD = 14          # the Outreach Pack's touch calendar runs 14 days, so it is pushed further ahead than the lists


def _runner():
    spec = importlib.util.spec_from_file_location("dse_runner", HERE / "runner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def local_iso(ts: str) -> str:
    """Citadel's UTC time of the tap -> this PC's local time, the log's format."""
    try:
        d = dt.datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
        return d.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    except ValueError:
        return dl.local_now()


def engines_here() -> dict[str, dict]:
    out = {}
    for p in sorted(dl.ENGINES.glob("*/engine.json")) if dl.ENGINES.exists() else []:
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if not cfg.get("archived"):
            out[p.parent.name] = cfg
    return out


def build_items(today: dt.date) -> list[dict]:
    """The desk rows for every active engine: the window around today plus every open reply, with their current status."""
    lo, hi = (today - dt.timedelta(days=DAYS_BACK)).isoformat(), (today + dt.timedelta(days=DAYS_AHEAD)).isoformat()
    items = []
    for slug, cfg in engines_here().items():
        hist = dl.history(slug)
        for r in dl.load_lists(slug):
            ev = dl.latest(hist.get((r["_source"], r["_row_id"])))
            status = ev["status"] if ev else "to do"
            open_reply = status in ("replied", "booked")
            if not (lo <= r["_date"] <= hi or open_reply):
                continue
            items.append({
                "key": f"{slug}|{r['_source']}|{r['_row_id']}", "list_date": r["_date"], "engine": slug,
                "engine_label": cfg.get("name") or slug, "source": r["_source"], "row_id": r["_row_id"],
                "name": r.get("business") or r.get("name", ""), "person": r.get("host", ""), "city": r.get("city", ""),
                "channel": r.get("channel", ""), "where": r.get("where", ""), "website": r.get("website", ""),
                "message": r.get("opener", ""), "warmup": "", "gap": r.get("gap_used", ""),
                "notes": r.get("notes", "") or r.get("gaps_found", ""), "audit": "", "touch": r["touch"],
                "status": status, "category": (ev or {}).get("category", ""), "reply": (ev or {}).get("reply", ""),
                "next_step": (ev or {}).get("next_step", ""), "value": (ev or {}).get("value", "")})
        items += outreach.desk_items(slug, cfg, today, DAYS_BACK, CAL_AHEAD, hist)
    return items


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    r = _runner()
    api = r.Api(r.load_env())
    here = engines_here()
    if not here:
        return
    # PULL
    events = api.rpc("hq_member_desk_pull", {}) or []
    ack, per_engine = [], {}
    for e in events:
        slug = e.get("engine", "")
        if slug not in here:
            continue                                       # another PC owns this engine: leave the tap for it
        per_engine.setdefault(slug, []).append({
            "logged_at": local_iso(e.get("logged_at", "")), "list_date": e.get("list_date") or "", "source": e.get("source", ""),
            "row_id": e.get("row_id", ""), "name": e.get("name", ""), "channel": e.get("channel", ""), "touch": "",
            "status": e["status"], "category": e.get("category") or "", "reply": e.get("reply") or "",
            "next_step": e.get("next_step") or "", "value": e.get("value") or ""})
        ack.append(e["id"])
    if a.dry:
        print(f"would pull {len(ack)} tap(s) for {len(per_engine)} engine(s)")
    else:
        for slug, evs in per_engine.items():
            dl.append_events(slug, evs)
        if ack:
            api.rpc("hq_desk_ack", {"p_ids": ack})
    # PUSH
    today = dt.date.today()
    items = build_items(today)
    if a.dry:
        print(f"would push {len(items)} row(s) from {len(here)} engine(s)")
        return
    api.rpc("hq_member_desk_push", {"p_items": items, "p_from": (today - dt.timedelta(days=DAYS_BACK)).isoformat(),
                                     "p_to": (today + dt.timedelta(days=CAL_AHEAD)).isoformat()})
    if ack:
        print(f"{dt.datetime.now():%H:%M:%S} desk sync: {len(ack)} tap(s) from your phone logged")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        if "Could not find the function" in str(e) or "PGRST202" in str(e):
            sys.exit(0)            # the database update (member_desk SQL) has not been run yet: wait quietly
        sys.exit(f"desk sync: {e}")
