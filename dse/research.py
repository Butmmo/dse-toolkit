"""One research run: find the businesses, read their websites once, detect their technology, enrich, score, and keep every lead in one database with its history.

  python dse.py research run "stump grinding" "Leeds; Manchester" --country GB          find -> tech -> enrich -> one combined CSV, leads saved
  python dse.py research run --cities-file data/cities-gb-stump-grinding.csv --strict --new-only    only leads you have not had in an earlier run
  python dse.py research history                                                         every run: when, what, how many, how many were new
  python dse.py research leads --kind "stump grinding" --min-score 60 --csv top.csv      the lead database, filtered

Every step reads the same cached pages (dse/pagecache.py), so a website is downloaded once per run and, for a week, once across runs. The database
(data/leads.sqlite, git-ignored) keys a lead on its website's domain, or on name and city when it has none, so the same business found by two searches,
or by this month's run and next month's, is one row with first_seen, last_seen and times_seen.
"""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

from . import pagecache
from .common import DATA, ROOT, domain, log, read_csv, slug, write_csv

DB = DATA / "leads.sqlite"
KEEP = ["business", "website", "city", "state", "phone", "email", "best_email", "decision_maker", "category", "niche_match", "tech_platform", "tech_gap_count", "tech_gaps", "lead_score", "lead_why"]


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path or DB)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS leads (key TEXT PRIMARY KEY, kind TEXT, country TEXT, business TEXT, website TEXT, city TEXT, phone TEXT, email TEXT,
        niche_match TEXT, tech_gap_count INTEGER, lead_score INTEGER, lead_why TEXT, first_seen TEXT, last_seen TEXT, times_seen INTEGER DEFAULT 1, status TEXT DEFAULT 'new');
    CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, kind TEXT, country TEXT, cities TEXT, found INTEGER, new INTEGER, seen_before INTEGER,
        strict INTEGER, enriched INTEGER, pages_downloaded INTEGER, pages_reused INTEGER, out_file TEXT);
    """)
    return con


def lead_key(row: dict) -> str:
    d = domain(row.get("website", ""))
    if d:
        return d
    if not (row.get("business") or "").strip():
        return ""
    return slug(row["business"], 40) + "|" + slug(row.get("city", "") or row.get("search_city", ""), 30)


def _int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def known_keys(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute("SELECT key FROM leads")}


def save_leads(con: sqlite3.Connection, rows: list[dict], kind: str, country: str, today: str) -> tuple[int, int]:
    """Add or refresh every lead. Returns (new, seen_before)."""
    new = old = 0
    for r in rows:
        k = lead_key(r)
        if not k:
            continue
        vals = (kind, country, r.get("business", ""), r.get("website", ""), r.get("city", "") or r.get("search_city", ""), r.get("phone", ""), r.get("best_email", "") or r.get("email", ""),
                r.get("niche_match", ""), _int(r.get("tech_gap_count")), _int(r.get("lead_score")), r.get("lead_why", ""))
        if con.execute("SELECT 1 FROM leads WHERE key=?", (k,)).fetchone():
            con.execute("UPDATE leads SET kind=?, country=?, business=?, website=?, city=?, phone=?, email=?, niche_match=?, tech_gap_count=?, lead_score=?, lead_why=?, last_seen=?, "
                        "times_seen=times_seen+1 WHERE key=?", vals + (today, k))
            old += 1
        else:
            con.execute("INSERT INTO leads (key, kind, country, business, website, city, phone, email, niche_match, tech_gap_count, lead_score, lead_why, first_seen, last_seen) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (k,) + vals + (today, today))
            new += 1
    con.commit()
    return new, old


def run(kind: str = "", cities: str = "", country: str = "US", cities_file: str = "", tiers: str = "", cap: int = 100, strict: bool = False, new_only: bool = False,
        enrich: bool = True, icp: str = "", words: str = "", skip: str = "", source: str = "foursquare", max_rows: int = 100, db: Path | str | None = None, today: str = "") -> str:
    from . import enrich as EN, places as P, tech as T
    today = today or time.strftime("%Y-%m-%d")
    con = connect(db)
    before = known_keys(con)
    with pagecache.active():
        found = P.find(kind, cities, cap=cap, words=words, skip=skip, country=country, source=source, cities_file=cities_file, tiers=tiers, strict=strict)
        rows = read_csv(found)
        if new_only:
            rows = [r for r in rows if lead_key(r) not in before]
            write_csv(found, rows)
            log(f"  --new-only: {len(rows)} leads you have not had in an earlier run")
        final = found
        if rows:
            final = T.tech_file(found, max_rows=max_rows)
            if enrich:
                text = EN.enrich_file(final, icp=icp, max_rows=max_rows)
                m = re.search(r"Saved: (\S+)", text)
                if m:
                    final = str(ROOT / m.group(1))
        st = pagecache.stats()
    out_rows = read_csv(final) if rows else []
    kind_name = (out_rows[0].get("category") if out_rows else "") or kind
    new, old = save_leads(con, out_rows, kind_name, country, today)
    where = cities.split(";")[0].strip() if cities else Path(cities_file).stem
    stamp = Path(final).with_name(f"{today}-research-{slug(kind_name, 30)}-{slug(where, 24)}.csv")
    if out_rows:
        write_csv(stamp, out_rows, first=[c for c in KEEP if c in out_rows[0]])
    con.execute("INSERT INTO runs (at, kind, country, cities, found, new, seen_before, strict, enriched, pages_downloaded, pages_reused, out_file) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (time.strftime("%Y-%m-%d %H:%M"), kind_name, country, cities or cities_file, len(out_rows), new, old, int(strict), int(enrich), st["misses"], st["hits"], str(stamp) if out_rows else ""))
    con.commit()
    con.close()
    print(f"Research run: {len(out_rows)} leads, {new} new, {old} seen in an earlier run. Pages: {st['misses']} downloaded, {st['hits']} reused from the cache.")
    if out_rows:
        print(f"Combined list: {stamp}")
        print(f"Lead database: {Path(db or DB)}  (python dse.py research leads)")
    return str(stamp) if out_rows else ""


def history(db: Path | str | None = None) -> str:
    con = connect(db)
    rows = con.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 30").fetchall()
    n = con.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    con.close()
    if not rows:
        return 'No research runs yet. Start one: python dse.py research run "stump grinding" "Leeds" --country GB'
    lines = [f"{n} leads in the database. Last {len(rows)} runs:"]
    for r in rows:
        lines.append(f"  #{r['id']} {r['at']}  {r['kind']} ({r['country']}), {r['cities'][:40]}: {r['found']} leads, {r['new']} new, {r['seen_before']} seen before"
                     f"{', strict' if r['strict'] else ''}; pages {r['pages_downloaded']} downloaded / {r['pages_reused']} reused")
    return "\n".join(lines)


def leads(kind: str = "", min_score: int = 0, country: str = "", csv_out: str = "", db: Path | str | None = None) -> str:
    con = connect(db)
    q, args = "SELECT * FROM leads WHERE COALESCE(lead_score,0) >= ?", [min_score]
    if kind:
        q += " AND LOWER(kind) LIKE ?"
        args.append("%" + kind.lower() + "%")
    if country:
        q += " AND country = ?"
        args.append(country.upper())
    rows = [dict(r) for r in con.execute(q + " ORDER BY COALESCE(lead_score,0) DESC, last_seen DESC", args)]
    con.close()
    if not rows:
        return "No leads match."
    if csv_out:
        write_csv(csv_out, rows)
        return f"{len(rows)} leads -> {csv_out}"
    return "\n".join([f"{len(rows)} leads (best first):"] + [f"  {r['lead_score'] if r['lead_score'] is not None else '-':>3}  {r['business']} | {r['website']} | {r['city']} | first seen {r['first_seen']}, seen {r['times_seen']}x" for r in rows[:40]])
