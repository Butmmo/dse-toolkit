"""Local-business lead lists from Foursquare Open Source Places (free, Apache 2.0 licence).

  python dse.py build dentist,plumber          once per business type (and monthly): saves data/places-us-<kind>.parquet
  python dse.py find dentist "Tampa FL; Orlando FL" [--miles 25] [--max 100]

`build` needs a free Hugging Face read token in the HF_TOKEN environment variable, after accepting the
dataset's terms at https://huggingface.co/datasets/foursquare/fsq-os-places (README, "One-time: business data").
Never scrape Google Maps pages: it breaks Google's terms and risks the student's accounts.
"""
from __future__ import annotations

import concurrent.futures as cf
import csv
import math
import os
import re
import sys
import time

import requests

from .common import DATA, DEAD_TEXT, UA, log, out_path, write_csv

HF = "hf://datasets/foursquare/fsq-os-places"
GEOCACHE = DATA / "geocode-cache.csv"

# kind -> (what it is, Foursquare category names it matches exactly)
KINDS: dict[str, tuple[str, list[str]]] = {
    # SMB Optimization (local businesses; Google reviews are the opening angle)
    "dentist": ("Dentists", ["Dentist"]),
    "chiropractor": ("Chiropractors", ["Chiropractor"]),
    "physical-therapy": ("Physical therapy clinics", ["Physical Therapy Clinic"]),
    "optometrist": ("Optometrists", ["Optometrist"]),
    "veterinarian": ("Vets", ["Veterinarian"]),
    "hvac": ("HVAC contractors", ["Heating, Ventilating and Air Conditioning Contractor"]),
    "plumber": ("Plumbers", ["Plumber"]),
    "roofer": ("Roofers", ["Roofer"]),
    "electrician": ("Electricians", ["Electrician"]),
    "landscaper": ("Landscapers", ["Landscaper and Gardener"]),
    "cleaning": ("Cleaning services", ["Professional Cleaning Service"]),
    "pest-control": ("Pest control", ["Pest Control Service"]),
    "general-contractor": ("General contractors", ["General Contractor"]),
    "hair-salon": ("Hair salons", ["Hair Salon"]),
    "barbershop": ("Barbershops", ["Barbershop"]),
    "spa": ("Spas", ["Spa"]),
    "law-office": ("Law offices", ["Law Office", "Immigration Attorney"]),
    "insurance": ("Insurance agencies", ["Insurance Agency"]),
    "real-estate": ("Real estate agencies", ["Real Estate Agency"]),
    "gym": ("Gyms", ["Gym"]),
    "movers": ("Movers", ["Mover", "Movers"]),
    "interior-design": ("Interior design studios", ["Interior Designer", "Interior Design Studio"]),
    # CareBridge (home care agencies and assisted living)
    "home-care": ("Home health care agencies", ["Home Health Care Service"]),
    "assisted-living": ("Assisted living", ["Assisted Living Service", "Assisted Living"]),
    "nursing-home": ("Nursing homes", ["Nursing Home"]),
    "senior-services": ("Senior services", ["Senior Citizen Service"]),
}
# Words a real business of that type uses on its own website. Foursquare sometimes stores the wrong website for
# a place (a dentist listing pointing at an insurance site), so a lead is kept only if its site says one of these.
KIND_WORDS: dict[str, str] = {
    "dentist": r"dent|teeth|tooth|smile|orthodont|implant|hygien",
    "chiropractor": r"chiropract|spine|spinal|adjustment|back pain",
    "physical-therapy": r"physical therap|physiotherap|rehab|sports injur",
    "optometrist": r"optomet|eye (exam|care|doctor)|vision|glasses|contact lens",
    "veterinarian": r"veterinar|\bvet\b|animal hospital|\bpets?\b",
    "hvac": r"hvac|heating|cooling|air condition|furnace|heat pump",
    "plumber": r"plumb|drain|water heater|sewer",
    "roofer": r"roof|shingle|gutter",
    "electrician": r"electric|wiring|generator",
    "landscaper": r"landscap|lawn|garden|irrigation",
    "cleaning": r"clean|maid|janitor|housekeep",
    "pest-control": r"pest|termite|exterminat|rodent|mosquito",
    "general-contractor": r"contract|remodel|renovat|construction",
    "hair-salon": r"hair|salon|stylist",
    "barbershop": r"barber|haircut|shave|beard",
    "spa": r"\bspa\b|massage|facial|skin care|skincare",
    "law-office": r"\blaw\b|attorney|lawyer|legal",
    "insurance": r"insurance|coverage",
    "real-estate": r"real estate|realtor|homes for sale|listings",
    "gym": r"\bgym\b|fitness|workout|personal training",
    "movers": r"\bmov(ing|ers?)\b|relocat",
    "interior-design": r"interior|design|decor",
    "home-care": r"home care|homecare|in-home|caregiv|senior|elder|companion|home health",
    "assisted-living": r"assisted living|senior living|memory care|residents",
    "nursing-home": r"nursing|skilled|rehab|long-term care",
    "senior-services": r"senior|aging|elder|older adult",
}

# National chains and franchises: not the independent owners DSE sells to (kept with --all).
CHAINS = re.compile(r"u-?haul|penske|two men and a truck|allied van|mayflower|united van|atlas van|bekins|pods\b|"
                    r"aspen dental|western dental|heartland dental|great clips|supercuts|sport clips|fantastic sams|"
                    r"planet fitness|la fitness|anytime fitness|orangetheory|24 hour fitness|massage envy|hand & stone|"
                    r"state farm|allstate|farmers insurance|geico|progressive|nationwide|keller williams|re/max|remax|"
                    r"coldwell banker|century 21|berkshire hathaway|compass real|roto-rooter|mr\. rooter|terminix|orkin|"
                    r"servpro|servicemaster|molly maid|merry maids|brightstar|home instead|visiting angels|comfort keepers|"
                    r"right at home|amedisys|brookdale|sunrise senior|senior helpers|griswold|synergy home ?care|interim health|"
                    r"homewatch caregivers|always best care|home helpers|firstlight|caring senior service|bayada|maxim health|"
                    r"accentcare|kindred at home|encompass health|lhc group|bright horizons|seniors helping seniors|nurse next door|"
                    r"assisting hands|care ?patrol|amada senior|homecare ?assistance|banfield|vca animal|petsmart|pearle vision|"
                    r"lenscrafters|walmart|target optical|costco|jiffy|midas|meineke|firestone", re.I)
NOT_A_SITE = re.compile(r"yelp\.com|google\.com|mapquest|yellowpages|facebook\.com|instagram\.com|bbb\.org|nextdoor|"
                        r"healthgrades|zocdoc|vitals\.com|caring\.com|aplaceformom", re.I)


def _con():
    import duckdb
    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs;")
    return con


def extract_path(kind: str):
    return DATA / f"places-us-{kind}.parquet"


def build(kinds: list[str]):
    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("Set HF_TOKEN first (README, 'One-time: business data'). It's a free Hugging Face read token.")
    bad = [k for k in kinds if k not in KINDS]
    if bad:
        sys.exit(f"Unknown business type(s): {', '.join(bad)}. Run: python dse.py kinds")
    DATA.mkdir(exist_ok=True)
    r = requests.get("https://huggingface.co/api/datasets/foursquare/fsq-os-places/tree/main/release",
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    dt = sorted(x["path"].split("dt=")[1] for x in r.json() if "dt=" in x["path"])[-1]
    con = _con()
    con.sql(f"CREATE SECRET hf (TYPE huggingface, TOKEN '{token}')")
    cats = con.sql(f"SELECT category_id, category_name FROM '{HF}/release/dt={dt}/categories/parquet/*.parquet'").fetchall()
    for kind in kinds:
        names = {n.lower() for n in KINDS[kind][1]}
        ids = [cid for cid, name in cats if (name or "").lower() in names]
        if not ids:
            log(f"  {kind}: no Foursquare category found, skipped")
            continue
        t = time.time()
        dst = extract_path(kind).as_posix()
        con.sql(f"""
            COPY (
              SELECT fsq_place_id, name, latitude::DOUBLE AS latitude, longitude::DOUBLE AS longitude, address, locality,
                     region, postcode, tel, website, email, facebook_id, instagram, fsq_category_labels, date_refreshed
              FROM '{HF}/release/dt={dt}/places/parquet/*.parquet'
              WHERE country = 'US' AND date_closed IS NULL
                AND list_has_any(fsq_category_ids, [{', '.join(repr(i) for i in ids)}])
            ) TO '{dst}' (FORMAT parquet)""")
        n = con.sql(f"SELECT count(*) FROM '{dst}'").fetchall()[0][0]
        log(f"  {kind}: {n} US places saved in {int(time.time() - t)} s (release {dt})")
    (DATA / "places-release.txt").write_text(dt + "\n", encoding="utf-8")


def geocode(place: str) -> tuple[float, float]:
    """'Tampa FL' -> (lat, lon) via OpenStreetMap Nominatim (free, max 1 request a second), cached."""
    DATA.mkdir(exist_ok=True)
    cache = {}
    if GEOCACHE.exists():
        with open(GEOCACHE, newline="", encoding="utf-8") as f:
            cache = {r["place"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)}
    key = place.strip().lower()
    if key in cache:
        return cache[key]
    time.sleep(1.1)
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": place + ", USA", "format": "json", "limit": 1, "countrycodes": "us"},
                     headers={"User-Agent": "DSEToolkit/1.0 (local lead research)"}, timeout=20)
    hits = r.json()
    if not hits:
        sys.exit(f"Could not find the city '{place}'. Write it like 'Tampa FL'.")
    cache[key] = (float(hits[0]["lat"]), float(hits[0]["lon"]))
    new = not GEOCACHE.exists()
    with open(GEOCACHE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["place", "lat", "lon"])
        w.writerow([key, *cache[key]])
    return cache[key]


def _miles(a, b, c, d):
    rad = math.radians
    h = math.sin(rad(c - a) / 2) ** 2 + math.cos(rad(a)) * math.cos(rad(c)) * math.sin(rad(d - b) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def site_live(url: str, words: str = "") -> bool:
    """Opens, isn't parked or for sale, and (when `words` is given) talks about the right kind of business."""
    try:
        r = requests.get(url, timeout=12, headers=UA, allow_redirects=True)
    except Exception:
        return False
    if r.status_code in (403, 429):
        return True                          # blocks scripts, opens in a browser: the check reads it with Edge
    if r.status_code >= 400:
        return False
    t = r.text[:200000].lower()
    if len(t) <= 300 or any(d in t[:30000] for d in DEAD_TEXT):
        return False
    visible = re.sub(r"<[^>]+>", " ", t)
    if words and len(visible.split()) > 150 and not re.search(words, visible):
        return False                         # a full page that never mentions the trade: wrong website for this place
    return True


def find(kind: str, cities: str, miles: float = 25.0, cap: int = 100, keep_all: bool = False, out: str = "") -> str:
    if kind not in KINDS:
        sys.exit(f"Unknown business type '{kind}'. Run: python dse.py kinds")
    src = extract_path(kind)
    if not src.exists():
        sys.exit(f"No business data for '{kind}' yet. Run once: python dse.py build {kind}")
    con = _con()
    names = [n.lower() for n in KINDS[kind][1]]
    places = [c.strip() for c in re.split(r"[;|]", cities) if c.strip()]
    if not places:
        sys.exit("Give at least one city, like 'Tampa FL; Orlando FL'.")
    per_city = max(1, cap // len(places))
    rows, seen = [], set()
    for place in places:
        lat, lon = geocode(place)
        dlat, dlon = miles / 69.0, miles / (69.0 * max(0.2, math.cos(math.radians(lat))))
        rel = con.sql(f"""SELECT * FROM '{src.as_posix()}'
                          WHERE latitude BETWEEN {lat - dlat} AND {lat + dlat} AND longitude BETWEEN {lon - dlon} AND {lon + dlon}""")
        city_rows = []
        for p in (dict(zip(rel.columns, row)) for row in rel.fetchall()):
            dist = _miles(lat, lon, p["latitude"], p["longitude"])
            if dist > miles or p["fsq_place_id"] in seen:
                continue
            labels = list(p["fsq_category_labels"]) if p["fsq_category_labels"] is not None else []
            if not any(str(l).split(">")[-1].strip().lower() in names for l in labels):
                continue
            web = (p["website"] or "").strip()
            if web and not web.startswith("http"):
                web = "https://" + web
            if NOT_A_SITE.search(web):
                web = ""
            if not keep_all and (CHAINS.search(p["name"] or "") or CHAINS.search(web)):
                continue
            dom = re.sub(r"^www\.", "", web.split("/")[2].lower()) if web else ""
            if dom and dom in seen:
                continue
            seen.add(p["fsq_place_id"])
            if dom:
                seen.add(dom)
            city_rows.append({
                "business": p["name"], "city": p["locality"] or "", "state": p["region"] or "", "website": web,
                "phone": p["tel"] or "", "email": p["email"] or "",
                "instagram": f"https://instagram.com/{p['instagram']}" if p["instagram"] else "",
                "facebook": f"https://facebook.com/{p['facebook_id']}" if p["facebook_id"] else "",
                "address": ", ".join(x for x in (p["address"], p["locality"], f"{p['region'] or ''} {p['postcode'] or ''}".strip()) if x),
                "category": KINDS[kind][0], "distance_mi": round(dist, 1), "search_city": place,
                "last_refreshed": str(p["date_refreshed"] or ""),
                "source": f"Foursquare Open Source Places, {time.strftime('%Y-%m-%d')}",
            })
        found = len(city_rows)
        city_rows.sort(key=lambda r: (r["website"] == "", r["last_refreshed"][:4] < "2021", r["distance_mi"]))
        kept, pool = [], [r for r in city_rows if r["website"]]
        for i in range(0, len(pool), 40):        # Foursquare keeps closed businesses: keep only live websites
            if len(kept) >= per_city:
                break
            batch = pool[i:i + 40]
            with cf.ThreadPoolExecutor(16) as ex:
                for r, live in zip(batch, ex.map(lambda u: site_live(u, KIND_WORDS.get(kind, "")), (b["website"] for b in batch))):
                    if live and len(kept) < per_city:
                        kept.append(r)
        rows += kept
        log(f"  {place}: {found} independent {KINDS[kind][0].lower()} in range, kept {len(kept)} with a live website")
    dst = out or str(out_path(kind, places[0] + (f"-plus{len(places) - 1}" if len(places) > 1 else "")))
    write_csv(dst, rows)
    print(f"{len(rows)} {KINDS[kind][0].lower()} -> {dst}")
    return dst
