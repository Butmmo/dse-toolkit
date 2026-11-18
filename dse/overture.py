"""Local-business lead lists from Overture Maps Places: open data, no account and no token (licence CDLA Permissive 2.0, https://overturemaps.org).

A second source next to Foursquare (dse/places.py), saved in the same column layout so the same finder reads either one, or both:

  python dse.py build dentist --country uk --source overture
  python dse.py find dentist "Leeds" --country GB --source both

It reads Overture's public files on Amazon S3 directly (nothing is scraped). Every place in it was published for reuse, so the only rule is to credit
"Overture Maps Foundation" where you publish its data; the lead lists you build are for your own outreach.
"""
from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path

from . import countries as C
from .common import DATA, log

S3 = "s3://overturemaps-us-west-2/release"
MIN_CONFIDENCE = 0.5          # Overture's own advice: below 0.5 a place is often wrong or gone
SOURCE_LABEL = "Overture Maps Places"

# our business type -> Overture category names (taxonomy.primary). A name Overture does not have simply matches nothing.
KINDS: dict[str, list[str]] = {
    "dentist": ["dental_clinic", "general_dentistry", "cosmetic_dentistry", "pediatric_dentistry", "dentist"],
    "chiropractor": ["chiropractic"],
    "physical-therapy": ["physical_therapy"],
    "optometrist": ["optometry", "vision_or_eye_care_clinic"],
    "veterinarian": ["veterinarian", "veterinary_care"],
    "hvac": ["hvac_service"],
    "plumber": ["plumbing"],
    "roofer": ["roofing", "ceiling_and_roofing_repair_and_service"],
    "electrician": ["electrician"],
    "landscaper": ["landscaping", "gardener", "lawn_service"],
    "cleaning": ["cleaning_service", "home_cleaning", "office_cleaning", "carpet_cleaning"],
    "pest-control": ["pest_control_service"],
    "general-contractor": ["building_contractor", "altering_and_remodeling_contractor", "contractor"],
    "hair-salon": ["hair_salon", "hair_stylist"],
    "barbershop": ["barber"],
    "spa": ["spa", "day_spa", "health_spa", "medical_spa"],
    "law-office": ["attorney_or_law_firm", "immigration_law"],
    "insurance": ["insurance_agency"],
    "real-estate": ["real_estate_agent"],
    "gym": ["gym", "sport_or_fitness_facility"],
    "movers": ["mover"],
    "interior-design": ["interior_design"],
    "home-care": ["home_health_care"],
    "assisted-living": ["assisted_living_facility"],
    "nursing-home": ["skilled_nursing_facility", "nursing_home"],
    "senior-services": ["senior_citizen_service"],
}


CATEGORY_CACHE = DATA / "overture-categories.csv"
KIND_CACHE = DATA / "overture-kinds.json"
MAX_CATEGORIES = 8


def categories(con=None) -> list[str]:
    """Every Overture place category name (about 2,000), read once from the data and cached on this PC."""
    if not CATEGORY_CACHE.exists():
        con = con or _con()
        rel = latest_release(con)
        log("Reading Overture's list of business categories (once, a few minutes)...")
        rows = con.sql(f"SELECT DISTINCT taxonomy.\"primary\" FROM read_parquet('{S3}/{rel}/theme=places/type=place/*') WHERE taxonomy.\"primary\" IS NOT NULL").fetchall()
        DATA.mkdir(exist_ok=True)
        CATEGORY_CACHE.write_text(chr(10).join(["name"] + sorted(r[0] for r in rows)) + chr(10), encoding="utf-8")
    with open(CATEGORY_CACHE, newline="", encoding="utf-8") as f:
        return [r["name"] for r in csv.DictReader(f)]


def match_categories(term: str, names: list[str]) -> list[str]:
    """Category names that fit a typed business type: an exact name, else every word you typed appears in the name ('interior designer' fits interior_design)."""
    from . import places as P
    t = re.sub(r"\s+", " ", (term or "").lower()).strip()
    slug = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    if slug in names:
        return [slug]
    want = [w for w in re.findall(r"[a-z]{3,}", t)]
    return [n for n in names if want and all(any(P._same(w, x) for x in re.findall(r"[a-z]{3,}", n)) for w in want)]


def category_names(kind: str, fetch: bool = False) -> list[str]:
    """Overture category names for a business type. Built-in types are mapped by hand; any type you typed (the app's whole niche list) is matched by its words to Overture's
    category list. Without fetch=True a not-yet-matched custom type returns [] and nothing touches the network."""
    if kind in KINDS:
        return list(KINDS[kind])
    try:
        saved = json.loads(KIND_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    if kind in saved:
        return saved[kind]
    if not fetch:
        return []
    from . import niches as NI
    from . import places as P
    info = P.custom_kinds().get(kind)
    term = (info.get("typed") or info["label"]) if info else NI.term_for(kind)
    if not term:
        return []
    found = match_categories(term, categories())
    if not found or len(found) > MAX_CATEGORIES:
        log(f"  {kind}: {'no Overture category fits' if not found else f'too broad for Overture ({len(found)} categories like ' + ', '.join(found[:3]) + ')'}; add a word to say which kind. Skipped here.")
        return []
    saved[kind] = found
    DATA.mkdir(exist_ok=True)
    KIND_CACHE.write_text(json.dumps(saved, indent=1), encoding="utf-8")
    log(f"  {kind}: matched to Overture categories {', '.join(found)}")
    return found


def extract_path(kind: str, country: str = "US") -> Path:
    return DATA / f"overture-{country.lower()}-{kind}.parquet"


def _con():
    import duckdb
    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    return con


def latest_release(con) -> str:
    rels = {r[0].split("/release/")[1].split("/")[0] for r in con.sql(f"SELECT file FROM glob('{S3}/*/theme=places/type=place/*')").fetchall()}
    if not rels:
        raise SystemExit("Could not list Overture's releases (is the internet on?).")
    return sorted(rels)[-1]


def build(kinds: list[str], country: str = "US"):
    """Save the Overture places of each business type for a country or a group (one scan per type, then one file per country)."""
    codes = C.resolve(country)
    todo = [k for k in kinds if category_names(k, fetch=True)]
    for k in kinds:
        if k not in todo:
            log(f"  {k}: no Overture category, skipped")
    if not todo:
        return
    DATA.mkdir(exist_ok=True)
    con = _con()
    rel = latest_release(con)
    src = f"{S3}/{rel}/theme=places/type=place/*"
    in_list = ", ".join(repr(c) for c in codes)
    t = time.time()
    tmp = (DATA / "_building-overture.parquet").as_posix()
    cats = ", ".join(repr(n) for k in todo for n in category_names(k, fetch=True))
    con.sql(f"""
        COPY (
          SELECT addresses[1].country AS country, taxonomy."primary" AS cat, id AS fsq_place_id, names."primary" AS name,
                 ((bbox.ymin + bbox.ymax) / 2)::DOUBLE AS latitude, ((bbox.xmin + bbox.xmax) / 2)::DOUBLE AS longitude,
                 addresses[1].freeform AS address, addresses[1].locality AS locality, addresses[1].region AS region,
                 addresses[1].postcode AS postcode, phones[1] AS tel, websites[1] AS website, emails[1] AS email,
                 regexp_extract(array_to_string(socials, ' '), 'facebook[.]com/([^/?# ]+)', 1) AS facebook_id,
                 regexp_extract(array_to_string(socials, ' '), 'instagram[.]com/([^/?# ]+)', 1) AS instagram,
                 [taxonomy."primary"] AS fsq_category_labels,
                 try_cast(sources[1].update_time AS DATE) AS date_refreshed
          FROM read_parquet('{src}')
          WHERE addresses[1].country IN ({in_list}) AND taxonomy."primary" IN ({cats})
            AND coalesce(operating_status, 'active') = 'active' AND coalesce(confidence, 0) >= {MIN_CONFIDENCE}
        ) TO '{tmp}' (FORMAT parquet)""")
    log(f"  scanned Overture release {rel} once for {len(todo)} business type(s) in {int(time.time() - t)} s")
    cols = "fsq_place_id, name, latitude, longitude, address, locality, region, postcode, tel, website, email, facebook_id, instagram, fsq_category_labels, date_refreshed"
    for kind in todo:
        names = ", ".join(repr(n) for n in category_names(kind, fetch=True))
        for cc in codes:
            dst = extract_path(kind, cc).as_posix()
            con.sql(f"COPY (SELECT {cols} FROM '{tmp}' WHERE country = '{cc}' AND cat IN ({names})) TO '{dst}' (FORMAT parquet)")
            n = con.sql(f"SELECT count(*) FROM '{dst}'").fetchall()[0][0]
            log(f"  {kind}: {n} {C.NAMES[cc]} places saved ({cc})")
    Path(tmp).unlink(missing_ok=True)
    (DATA / "overture-release.txt").write_text(rel + chr(10), encoding="utf-8")
