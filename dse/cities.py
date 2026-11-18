"""Which towns to search: rates every town in a country by how many prospects of one business type it really holds, in 7 to 10 tiers.

  python dse.py cities dentist --country GB                 builds data/cities-gb-dentist.csv (tier 1 = the richest towns) and prints a summary
  python dse.py find dentist --country GB --cities-file data/cities-gb-dentist.csv            searches the towns marked include = Y
  python dse.py find dentist --country GB --cities-file data/cities-gb-dentist.csv --tiers 1-3   or just the towns in tiers 1 to 3

The ratings come from the business lists you built (python dse.py build ...), not from guesses: a prospect is an independent business (not a chain)
with a website. A suburb within `cover` miles of a bigger town is folded into it (the search radius of that town already reaches it), so the list
does not send you to 40 suburbs of the same city. The number of tiers grows with the size of the pool: 7 for a small pool up to 10 for a big one.
The CSV is yours to edit: change include, change a tier, delete a row, or add a town (leave lat and lon blank and it is looked up when you search).
An existing file is never overwritten unless you ask (--refresh), so your edits are safe.
"""
from __future__ import annotations

import csv
import math
import re
import sys
from pathlib import Path

from . import countries as C
from . import places as P
from .common import DATA, log

COLUMNS = ["tier", "city", "region", "pool", "places", "folded", "lat", "lon", "include", "note"]
DEFAULT_COVER_MILES = 10.0
DEFAULT_MIN_POOL = 3
DEFAULT_INCLUDE_TIERS = 3        # towns in tiers 1 to 3 are marked include = Y at first


def tier_count(total_pool: int) -> int:
    """7 tiers for a small pool, up to 10 for a big one: more prospects in a country means finer steps are worth it."""
    return 7 if total_pool < 1_000 else 8 if total_pool < 10_000 else 9 if total_pool < 100_000 else 10


def assign_tiers(pools: list[int], n: int) -> list[int]:
    """Tier 1 = the biggest pool, tier n = the smallest, spaced on a log scale (a town of 400 is not 'twice' a town of 200 in any way that matters)."""
    if not pools:
        return []
    hi, lo = math.log(max(pools)), math.log(max(1, min(pools)))
    span = hi - lo
    if span < 1e-9:
        return [1] * len(pools)
    return [1 + min(n - 1, int(n * (hi - math.log(max(1, p))) / span)) for p in pools]


def fold(towns: list[dict], cover_miles: float) -> list[dict]:
    """Biggest first; a town within cover_miles of one already kept is added to it instead of listed. Uses a grid so a whole country stays fast."""
    if not towns:
        return []
    mean_lat = sum(t["lat"] for t in towns) / len(towns)
    cell = cover_miles / 69.0 / max(0.3, math.cos(math.radians(mean_lat)))
    grid: dict[tuple[int, int], list[dict]] = {}
    kept: list[dict] = []
    for t in sorted(towns, key=lambda x: (-x["pool"], x["city"])):
        cx, cy = int(t["lat"] // cell), int(t["lon"] // cell)
        home = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for k in grid.get((cx + dx, cy + dy), []):
                    if P._miles(t["lat"], t["lon"], k["lat"], k["lon"]) <= cover_miles and (home is None or k["pool"] > home["pool"]):
                        home = k
        if home:
            home["pool"] += t["pool"]
            home["places"] += t["places"]
            home["folded"] += 1 + t["folded"]
        else:
            k = dict(t)
            kept.append(k)
            grid.setdefault((cx, cy), []).append(k)
    return kept


def rank(kind: str, country: str, source: str = "foursquare", tiers: int = 0, cover_miles: float = DEFAULT_COVER_MILES, min_pool: int = DEFAULT_MIN_POOL) -> list[dict]:
    """Rows (tier, city, region, pool, ...) for every town with at least min_pool prospects, best first. Needs the business lists built for this country."""
    country = C.one(country)
    kind = P.resolve_kind(kind)
    files = [(s, P.extract_path(kind, country, s)) for s in P.sources_for(source)]
    files = [(s, f) for s, f in files if f.exists()]
    if not files:
        sys.exit(f"No business list for '{kind}' in {country} yet. Run: python dse.py build {kind} --country {country}" + ("" if source == "foursquare" else f" --source {source}"))
    chain = (P.CHAINS.pattern + "|" + P.NOT_A_SITE.pattern).replace("'", "''")
    con = P._con()
    union = " UNION ALL BY NAME ".join(f"SELECT name, locality, region, latitude, longitude, website FROM '{f.as_posix()}'" for _, f in files)
    # the same business can be in both sources: keep one per name and spot
    rel = con.sql(f"""
        WITH u AS (SELECT * FROM ({union})
                   WHERE locality IS NOT NULL AND trim(locality) <> '' AND latitude IS NOT NULL AND longitude IS NOT NULL
                   QUALIFY row_number() OVER (PARTITION BY lower(name), round(latitude, 3), round(longitude, 3)) = 1)
        SELECT trim(locality) AS city, coalesce(max(region), '') AS region, count(*) AS places,
               sum(CASE WHEN website IS NOT NULL AND trim(website) <> '' AND NOT regexp_matches(coalesce(name, '') || ' ' || website, '{chain}', 'i') THEN 1 ELSE 0 END) AS pool,
               avg(latitude) AS lat, avg(longitude) AS lon
        FROM u GROUP BY lower(trim(locality)), trim(locality), coalesce(region, '')""")
    towns = [{"city": c, "region": r, "places": int(n), "pool": int(p), "lat": float(la), "lon": float(lo), "folded": 0}
             for c, r, n, p, la, lo in rel.fetchall() if p and p > 0]
    kept = [k for k in fold(towns, cover_miles) if k["pool"] >= min_pool]
    kept.sort(key=lambda k: (-k["pool"], k["city"]))
    n = max(7, min(10, tiers)) if tiers else tier_count(sum(k["pool"] for k in kept))
    for k, t in zip(kept, assign_tiers([k["pool"] for k in kept], n)):
        k["tier"] = t
        k["include"] = "Y" if t <= DEFAULT_INCLUDE_TIERS else "N"
        k["note"] = f"{k['folded']} nearby towns folded in" if k["folded"] else ""
        k["lat"], k["lon"] = round(k["lat"], 4), round(k["lon"], 4)
    return kept


def file_for(kind: str, country: str) -> Path:
    return DATA / f"cities-{country.lower()}-{kind}.csv"


def from_file_name(path: str) -> tuple[str, str] | None:
    """('GB', 'dentist') from a cities file named cities-gb-dentist.csv (what `cities` writes), else None. Lets a search take its type and country from the file."""
    m = re.fullmatch(r"cities-([a-z]{2})-(.+)\.csv", Path(path).name.lower())
    return (m.group(1).upper(), m.group(2)) if m else None


def summary(rows: list[dict]) -> list[str]:
    if not rows:
        return ["No towns with enough prospects."]
    n = max(r["tier"] for r in rows)
    lines = [f"{len(rows)} towns in {n} tiers (tier 1 = the biggest pool of independent businesses with a website):"]
    for t in range(1, n + 1):
        in_t = [r for r in rows if r["tier"] == t]
        if in_t:
            lines.append(f"  tier {t:<2} {len(in_t):>5} towns  {sum(r['pool'] for r in in_t):>7} prospects   e.g. " + ", ".join(r["city"] for r in in_t[:3]))
    return lines


def suggest(kind: str, country: str, source: str = "foursquare", tiers: int = 0, refresh: bool = False,
            cover_miles: float = DEFAULT_COVER_MILES, min_pool: int = DEFAULT_MIN_POOL) -> str:
    """Write the editable cities file (never over an existing one unless refresh) and print the summary. Returns the file path."""
    country = C.one(country)
    kind = P.resolve_kind(kind)
    dst = file_for(kind, country)
    if dst.exists() and not refresh:
        log(f"{dst} already exists, so your edits are kept. Use --refresh to rebuild it from the latest lists.")
        return str(dst)
    rows = rank(kind, country, source, tiers, cover_miles, min_pool)
    DATA.mkdir(exist_ok=True)
    with open(dst, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print("\n".join(summary(rows)))
    print(f"-> {dst}  (open it, change include Y/N or any tier, add towns; then: python dse.py find {kind} --country {country} --cities-file {dst})")
    return str(dst)


def parse_tiers(spec: str) -> set[int]:
    """'1-3', '2', '1,3-4' -> {1, 2, 3} ... Raises ValueError for anything else."""
    out: set[int] = set()
    for part in (spec or "").replace(" ", "").split(","):
        if not part:
            continue
        m = re.fullmatch(r"(\d{1,2})(?:-(\d{1,2}))?", part)
        if not m:
            raise ValueError(f"'{part}' is not a tier. Write tiers like 1-3 or 2 or 1,3-4.")
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        if a < 1 or b < a:
            raise ValueError(f"'{part}' is not a valid tier range.")
        out.update(range(a, b + 1))
    if not out:
        raise ValueError("Give at least one tier, like 1-3.")
    return out


def _num(x: str):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load(path: str, tiers: str = "") -> list[tuple[str, float | None, float | None]]:
    """The towns to search from a cities file: the ones marked include = Y, or (with tiers like '1-3') every row in those tiers. Blank lat/lon are looked up later."""
    p = Path(path)
    if not p.is_file():
        sys.exit(f"Cities file not found: {path}. Make one with: python dse.py cities <type> --country <code>")
    try:
        want = parse_tiers(tiers) if tiers else None
    except ValueError as e:
        sys.exit(str(e))
    out = []
    with open(p, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            city = (r.get("city") or "").strip()
            if not city:
                continue
            t = _num(r.get("tier"))
            take = (t is not None and int(t) in want) if want is not None else (r.get("include") or "").strip().upper() in ("Y", "YES", "TRUE", "1", "X")
            if take:
                region = (r.get("region") or "").strip()
                lat, lon = _num(r.get("lat")), _num(r.get("lon"))
                out.append((city, lat, lon) if lat is not None and lon is not None else (f"{city}, {region}" if region else city, None, None))
    return out
