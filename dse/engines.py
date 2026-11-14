"""Engines: a member's own outreach businesses, each a settings file plus its own folders.

    engines/<slug>/engine.json        made by DBI Citadel (HQ Tools → My engines) and synced here by the runner
    engines/<slug>/send-lists/        dated lists; drafts/ holds new ones to spot-check first
    engines/<slug>/content/           idea seeds, inbox.csv (later phases)
    engines/<slug>/data/              the engine's own log and caches

`python dse.py daily <slug>` builds the next dated send lists for an engine:
find (or the engine's own seed list) → website check with the path's pack → drop anyone the engine already
has on any list → pick each lead's channel (the engine's order, within its daily caps) → draft the opener
from the engine's wording → engines/<slug>/send-lists/drafts/<date>.csv, ready for the cockpit/Send Desk.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

from . import check as chk
from . import places, podcasts
from .common import ROOT, log, read_csv, write_csv

ENGINES = ROOT / "engines"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
CHANNELS = ("Instagram DM", "Facebook message", "Email", "Website form")


def engine_dir(slug: str) -> Path:
    if not SLUG.match(slug or ""):
        sys.exit(f"Not an engine name: {slug!r}")
    return ENGINES / slug


def load(slug: str) -> dict:
    p = engine_dir(slug) / "engine.json"
    if not p.exists():
        have = ", ".join(all_slugs()) or "none yet (create one in Citadel: HQ Tools → My engines)"
        sys.exit(f"No engine '{slug}'. Engines on this PC: {have}")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg["slug"] = slug
    return cfg


def all_slugs(include_archived: bool = False) -> list[str]:
    if not ENGINES.exists():
        return []
    out = []
    for p in sorted(ENGINES.glob("*/engine.json")):
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if include_archived or not cfg.get("archived"):
            out.append(p.parent.name)
    return out


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def domain(url: str) -> str:
    u = (url or "").lower().strip()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.split("/")[0]


def already_listed(slug: str) -> tuple[set, set]:
    """Domains and names already on any of this engine's lists (sent, drafted or skipped): never list twice."""
    doms, names = set(), set()
    for p in (engine_dir(slug) / "send-lists").rglob("*.csv"):
        try:
            rows = read_csv(p)
        except Exception:
            continue
        for r in rows:
            d = domain(r.get("website", ""))
            if d:
                doms.add(d)
            n = norm(r.get("business") or r.get("name") or "")
            if n:
                names.add(n)
    return doms, names


def pick_channel(row: dict, order: list[str], left: dict) -> tuple[str, str]:
    """(channel, where) for a lead: the first channel in the engine's order that this lead has and that still
    has room today. Instagram needs a handle, Facebook a page, Email an address, Website form a website."""
    have = {
        "Instagram DM": row.get("instagram", ""),
        "Facebook message": row.get("facebook", ""),
        "Email": row.get("email", ""),
        "Website form": row.get("website", ""),
    }
    for ch in order:
        if have.get(ch) and left.get(ch, 0) > 0:
            return ch, have[ch]
    return "", ""


def fill(template: str, row: dict, cfg: dict) -> str:
    business = re.sub(r"\s*\([^)]*\)\s*$", "", row.get("business") or row.get("name") or "").strip()
    vals = {"business": business or "there", "city": (row.get("city") or "your area").strip(),
            "gap_line": row.get("gap_line") or row.get("gap_used") or "", "sender": cfg.get("sender_name", ""),
            "brand": cfg.get("brand_name", ""), "host": (row.get("host") or "").split(" ")[0] or "there"}
    try:
        return template.format(**vals).strip()
    except (KeyError, IndexError, ValueError) as e:
        return f"[opener template problem: {e}] " + template


def candidates(cfg: dict, need: int, render: bool) -> list[dict]:
    """New, checked leads for the engine: from the lead finder, Apple Podcasts, or the engine's own seed list."""
    slug, path = cfg["slug"], cfg.get("path", "smb")
    mode = cfg.get("source") if path == "custom" else None        # custom engines pick their own lead source
    raw = engine_dir(slug) / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    stamp = dt.date.today().isoformat()
    doms, names = already_listed(slug)

    def fresh(rows):
        out = []
        for r in rows:
            d, n = domain(r.get("website", "")), norm(r.get("business") or r.get("name") or "")
            if (d and d in doms) or (n and n in names):
                continue
            doms.add(d) if d else None
            names.add(n) if n else None
            out.append(r)
        return out

    if path == "broadcast" or mode == "podcasts":
        topics = cfg.get("topics") or ["business"]
        src = podcasts.find("; ".join(topics), cfg.get("genre", "business"), max(need * 3, 30), out=str(raw / f"{stamp}-podcasts.csv"))
        rows = [r for r in fresh(read_csv(src)) if str(r.get("gap_count", "0")) not in ("", "0")]
        for r in rows:
            r["gap_line"] = r.get("gap_used", "")
        return rows[:need]

    seeds = cfg.get("seed_urls") or []
    if seeds or path in ("ministry", "revenue") or mode == "seeds":
        rows = [{"business": u.get("name") or domain(u.get("url", "")), "website": u.get("url", ""), "city": u.get("city", "")}
                if isinstance(u, dict) else {"business": domain(u), "website": u, "city": ""} for u in seeds]
        rows = fresh(rows)[: need * 2]
        if not rows:
            log("  No unchecked seed websites left: add more in Citadel (My engines → this engine).")
            return []
        seed_csv = raw / f"{stamp}-seeds.csv"
        write_csv(seed_csv, rows)
        checked = chk.check_file(cfg.get("pack", path), str(seed_csv), render=render, out=str(raw / f"{stamp}-seeds-checked.csv"))
        return [r for r in read_csv(checked) if r.get("gap_line")][:need]

    kinds = cfg.get("kinds") or []
    cities = "; ".join(cfg.get("cities") or [])
    if not kinds or not cities:
        sys.exit("This engine needs at least one business type and one city (edit it in Citadel).")
    pool = []
    for kind in kinds:
        if len(pool) >= need:
            break
        src = places.find(kind, cities, float(cfg.get("miles", 25)), max(need * 3, 30), out=str(raw / f"{stamp}-{kind}.csv"))
        new = fresh(read_csv(src))
        if not new:
            continue
        new_csv = raw / f"{stamp}-{kind}-new.csv"
        write_csv(new_csv, new)
        checked = chk.check_file(cfg.get("pack", path), str(new_csv), render=render, out=str(raw / f"{stamp}-{kind}-checked.csv"))
        pool += [r for r in read_csv(checked) if r.get("gap_line")]
    return pool[:need]


def daily(slug: str, start: str | None = None, days: int = 1, per_day: int | None = None, render: bool = True) -> list[str]:
    cfg = load(slug)
    if cfg.get("archived"):
        sys.exit(f"Engine '{slug}' is archived.")
    if cfg.get("path") == "custom" and cfg.get("source", "none") == "none":
        print(f"'{cfg.get('name', slug)}' is a chat-and-notes engine: there are no lead lists to build. Open DBI-AI and pick it from the menu.")
        return []
    if cfg.get("path") in ("ascent", "authority", "gtm"):
        sys.exit(f"The {cfg['path']} path prospects through LinkedIn and calls; its tools come in a later phase.")
    per_day = per_day or int(cfg.get("per_day", 20))
    caps = {ch: int((cfg.get("caps") or {}).get(ch, 999)) for ch in CHANNELS}
    order = [c for c in (cfg.get("channels") or list(CHANNELS)) if c in CHANNELS]
    first = dt.date.fromisoformat(start) if start else dt.date.today() + dt.timedelta(days=1)
    dates = []
    d = first
    while len(dates) < days:
        if d.weekday() != 6 or cfg.get("sundays"):
            dates.append(d)
        d += dt.timedelta(days=1)
    log(f"Engine '{cfg.get('name', slug)}' ({cfg.get('path')}): {per_day} a day for {days} day(s) from {dates[0]}")
    pool = candidates(cfg, per_day * days, render)
    opener_tpl = cfg.get("opener") or chk.load_pack(cfg.get("pack", cfg.get("path", "smb"))).get("opener", "")
    if cfg.get("path") == "broadcast" or (cfg.get("path") == "custom" and cfg.get("source") == "podcasts"):
        opener_tpl = cfg.get("opener") or podcasts.OPENER.replace("{show}", "{business}").replace("{genre}", cfg.get("genre", "business"))
    written = []
    # Straight onto the engine's send lists (the Send Desk shows them; Skip anything that looks wrong), unless the
    # engine asks for drafts to spot-check first.
    out_dir = engine_dir(slug) / "send-lists" / ("drafts" if cfg.get("drafts_first") else "")
    for day in dates:
        left = dict(caps)
        rows = []
        while pool and len(rows) < per_day:
            r = pool.pop(0)
            ch, where = pick_channel(r, order, left)
            if not ch:
                continue
            left[ch] -= 1
            rows.append({"row": len(rows) + 1, "business": r.get("business", ""), "city": r.get("city", ""),
                         "channel": ch, "where": where, "gap_used": r.get("gap_line") or r.get("gap_used", ""),
                         "variant": cfg.get("variant") or f"{cfg.get('path')}-opener-v1",
                         "opener": fill(opener_tpl, r, cfg), "website": r.get("website", ""),
                         "gaps_found": r.get("gaps_found", ""), "email": r.get("email", ""), "phone": r.get("phone", ""),
                         "instagram": r.get("instagram", ""), "facebook": r.get("facebook", ""),
                         "category": r.get("category", ""), "host": r.get("host", ""),
                         "notes": "; ".join(x for x in (r.get("check_notes", ""), r.get("source", "")) if x)})
        if not rows:
            log(f"  {day}: no leads left with a usable channel")
            continue
        p = out_dir / f"{day.isoformat()}.csv"
        write_csv(p, rows, first=["row", "business", "city", "channel", "where", "gap_used", "variant", "opener"])
        written.append(str(p))
        by = {}
        for x in rows:
            by[x["channel"]] = by.get(x["channel"], 0) + 1
        print(f"{day}: {len(rows)} leads ({', '.join(f'{v} {k}' for k, v in by.items())}) -> {p.relative_to(ROOT).as_posix()}")
    if not written:
        print("No list written: no new leads with a usable channel. Add cities or business types in Citadel.")
    else:
        print("Spot-check the drafts, then move them from drafts/ into send-lists/." if cfg.get("drafts_first")
              else "Open them in the Send Desk (or the cockpit), check each lead, and Skip anything that looks wrong.")
    return written


def list_engines():
    slugs = all_slugs(include_archived=True)
    if not slugs:
        print("No engines on this PC yet. Create one in DBI Citadel: HQ Tools → My engines → New engine.")
        return
    for s in slugs:
        c = json.loads((ENGINES / s / "engine.json").read_text(encoding="utf-8"))
        lists = len(list((ENGINES / s / "send-lists").glob("*.csv"))) if (ENGINES / s / "send-lists").exists() else 0
        print(f"{s:<26} {c.get('name', '')[:30]:<30} {c.get('path', ''):<11} {lists} lists{'  (archived)' if c.get('archived') else ''}")
