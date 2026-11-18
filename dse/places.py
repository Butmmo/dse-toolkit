"""Local-business lead lists from Foursquare Open Source Places (free, Apache 2.0 licence).

  python dse.py build dentist,plumber          once per business type (and monthly): saves data/places-us-<kind>.parquet
  python dse.py find dentist "Tampa FL; Orlando FL" [--miles 25] [--max 100]

`build` needs a free Hugging Face read token in the HF_TOKEN environment variable, after accepting the
dataset's terms at https://huggingface.co/datasets/foursquare/fsq-os-places (README, "One-time: business data").
Never scrape Google Maps pages: it breaks Google's terms and risks the student's accounts.
"""
from __future__ import annotations

import concurrent.futures as cf
from pathlib import Path
import csv
import json
import math
import os
import re
import sys
import time

import requests

from . import countries as C
from . import niches as NI
from . import overture as OV
from . import pagecache
from .common import DATA, DEAD_TEXT, UA, log, out_path, write_csv

HF = "hf://datasets/foursquare/fsq-os-places"
FSQ_LABEL = "Foursquare Open Source Places"
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

# The app's whole niche list (512 business types) is built in too, after the hand-made ones above (which win on any clash). See dse/niches.py.
HAND_MADE = frozenset(KINDS)
for _e in NI.entries():
    if _e["id"] not in KINDS:
        KINDS[_e["id"]] = (_e["name"], list(_e["fsq"]))
        KIND_WORDS[_e["id"]] = _e.get("words", "")

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
# Directories, marketplaces and social profiles: a listing there is not the business's own website. The second half was found by a real audit (UK tree
# surgeons whose "website" was a yell.com, thomsonlocal.com or ratedpeople.com page). Hosts are matched whole, so a business called Bark & Bite is not bark.com.
NOT_A_SITE = re.compile(r"yelp\.com|google\.com|mapquest|yellowpages|facebook\.com|instagram\.com|bbb\.org|nextdoor|"
                        r"healthgrades|zocdoc|vitals\.com|caring\.com|aplaceformom|"
                        r"(?://|\.)(?:yell\.com|thomsonlocal\.com|ratedpeople\.com|checkatrade\.com|mybuilder\.com|trustatrader\.com|freeindex\.co\.uk|192\.com|bark\.com|"
                        r"cylex[a-z.-]*|scoot\.co\.uk|hotfrog[a-z.]*|misterwhat\.[a-z.]+|europages\.[a-z.]+|gelbeseiten\.de|11880\.com|pagesjaunes\.fr|paginasamarillas\.es|"
                        r"paginegialle\.it|goudengids\.nl|tripadvisor\.[a-z.]+|trustpilot\.com|linkedin\.com|twitter\.com|x\.com|youtube\.com|tiktok\.com|pinterest\.[a-z.]+|"
                        r"gumtree\.com|houzz\.[a-z.]+|angi\.com|homeadvisor\.com|thumbtack\.com|porch\.com|buildzoom\.com|networx\.com|ebay\.[a-z.]+|amazon\.[a-z.]+|"
                        r"businessmagnet\.co\.uk|local\.yahoo\.com|bing\.com|wikipedia\.org)(?:/|$)", re.I)


# ---- business types you define yourself (any Foursquare category), saved on this PC
CUSTOM_KINDS = DATA / "custom-kinds.json"
CATEGORY_CACHE = DATA / "fsq-categories.csv"


def hf_token() -> str:
    t = os.environ.get("HF_TOKEN", "")
    if not t and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                t = str(winreg.QueryValueEx(k, "HF_TOKEN")[0])
        except OSError:
            t = ""
    return t


def custom_kinds() -> dict:
    try:
        return json.loads(CUSTOM_KINDS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def kind_info(kind: str) -> tuple[str, list[str], str] | None:
    """(label, Foursquare category names, words a real site of that type uses) for a built-in or a saved custom business type."""
    if kind in KINDS:
        return KINDS[kind][0], KINDS[kind][1], KIND_WORDS.get(kind, "")
    c = custom_kinds().get(kind)
    return (c["label"], c["names"], c.get("words", "")) if c else None


def _stem(w: str) -> str:
    w = w.lower()
    for suf in ("ers", "ies", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[:-len(suf)] + ("y" if suf == "ies" else "")
    return w


def categories() -> list[tuple[str, str]]:
    """Foursquare's category list (id, name), cached on this PC. Needs the free HF_TOKEN once (README, One-time: business data)."""
    if not CATEGORY_CACHE.exists():
        token = hf_token()
        if not token:
            sys.exit("To look up a business type of your own, set HF_TOKEN once (README, 'One-time: business data': a free Hugging Face read token).")
        r = requests.get("https://huggingface.co/api/datasets/foursquare/fsq-os-places/tree/main/release", headers={"Authorization": f"Bearer {token}"}, timeout=30)
        r.raise_for_status()
        dt = sorted(x["path"].split("dt=")[1] for x in r.json() if "dt=" in x["path"])[-1]
        con = _con()
        con.sql(f"CREATE SECRET hf (TYPE huggingface, TOKEN '{token}')")
        cats = con.sql(f"SELECT category_id, category_name FROM '{HF}/release/dt={dt}/categories/parquet/*.parquet'").fetchall()
        DATA.mkdir(exist_ok=True)
        with open(CATEGORY_CACHE, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "name"])
            w.writerows((i, n) for i, n in cats if n)
    with open(CATEGORY_CACHE, newline="", encoding="utf-8") as f:
        return [(r["id"], r["name"]) for r in csv.DictReader(f)]


def _same(a: str, b: str) -> bool:           # photography, photographer and photographers are one word here
    a, b = _stem(a), _stem(b)
    return a == b or a.startswith(b) or b.startswith(a) or len(os.path.commonprefix([a, b])) >= 7


def builtin_match(term: str) -> str | None:
    """The built-in or saved business type a typed word means (dentists, Interior Designers, 'hair salon'), or None. Matches the id, the name, or every word of what you typed."""
    t = re.sub(r"\s+", " ", (term or "").lower()).strip()
    slug_t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    allk = {k: v["label"] for k, v in custom_kinds().items()}
    allk.update({k: v[0] for k, v in KINDS.items()})
    if slug_t in allk:
        return slug_t
    exact = NI.lookup(t)                         # the app's own niche name or finder term ("stump grinding", "tree service")
    if exact:
        return exact
    want = re.findall(r"[a-z]{3,}", t)
    if not want:
        return None
    hits = []
    for k, label in allk.items():
        have = re.findall(r"[a-z]{3,}", (label + " " + k.replace("-", " ")).lower())
        if all(any(_same(w, h) for h in have) for w in want):
            hits.append((len(have), k))
    hits.sort()
    if len(hits) > 1:                                         # a word that fits several types is not guessed, unless exactly one is a hand-made type ("roofing")
        hand = [h for h in hits if h[1] in HAND_MADE]
        if len(hand) == 1:
            return hand[0][1]
    return hits[0][1] if len(hits) == 1 else None


def match_categories(term: str, cats: list[tuple[str, str]]) -> list[str]:
    """Category names that fit what you typed: an exact name, else every word you typed appears in the name."""
    t = re.sub(r"\s+", " ", term.lower()).strip()
    names = sorted({n for _, n in cats})
    exact = [n for n in names if n.lower() == t or _stem(n.lower()) == _stem(t)]
    if exact:
        return exact[:1]
    want = [_stem(w) for w in re.findall(r"[a-z]{3,}", t)]
    return [n for n in names if want and all(any(_same(w, x) for x in re.findall(r"[a-z]{3,}", n.lower())) for w in want)]


def resolve_kind(term: str, words: str = "") -> str:
    """A built-in business type, one saved before, or a new one you typed: found among Foursquare's categories and saved. Never guesses between several."""
    term = re.sub(r"\s+", " ", (term or "").strip())
    if not term or term.startswith("-") or len(term) > 60:
        sys.exit("Give a business type: pick one from the list or type your own (like 'wedding photographers').")
    known = builtin_match(term)
    if known:
        return known
    s = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", term.lower())).strip("-")
    found = match_categories(term, categories())
    if not found:
        sys.exit(f"Foursquare has no business category like '{term}'. Try a simpler word (for example 'photographer'), or browse: python dse.py categories photo")
    if len(found) > 8:
        sys.exit(f"'{term}' is too broad: it fits {len(found)} Foursquare categories (like {', '.join(found[:4])}). Add a word to say which kind, for example 'wedding photographers' instead of 'photography'.")
    site_words = "|".join(sorted({re.escape(_stem(w)) for w in re.findall(r"[a-z]{3,}", (term + " " + " ".join(found)).lower())}))
    data = custom_kinds()
    data[s] = {"label": term[:1].upper() + term[1:], "names": found, "words": site_words, "typed": term}
    DATA.mkdir(exist_ok=True)
    CUSTOM_KINDS.write_text(json.dumps(data, indent=1), encoding="utf-8")
    log(f"Your business type '{term}' is saved. It covers {len(found)} Foursquare categor{'y' if len(found) == 1 else 'ies'}: {', '.join(found)}.")
    return s


def _con():
    import duckdb
    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs;")
    return con


SOURCES = ("foursquare", "overture", "both")


def sources_for(source: str) -> list[str]:
    """'foursquare', 'overture' or 'both' -> the list of data sources to use. Anything else is refused."""
    s = (source or "foursquare").strip().lower()
    if s not in SOURCES:
        sys.exit(f"Unknown data source '{source}'. Use foursquare, overture or both.")
    return ["foursquare", "overture"] if s == "both" else [s]


def extract_path(kind: str, country: str = "US", source: str = "foursquare"):
    """The saved business list for one type in one country. The US Foursquare file keeps its old name (places-us-<kind>), others are places-<cc>-<kind>; Overture files are overture-<cc>-<kind>."""
    if source == "overture":
        return OV.extract_path(kind, country)
    return DATA / f"places-{country.lower()}-{kind}.parquet"


def site_words_for(country: str, own: str, builtin: str) -> str:
    """Words a business website must use. Your own words always apply; the built-in English ones only where sites are in English."""
    return own or (builtin if C.english(country) else "")


def build(kinds: list[str], country: str = "US", source: str = "foursquare"):
    """Save the business lists for one source, or both. Foursquare needs the free HF_TOKEN; Overture needs nothing."""
    for s_ in sources_for(source):
        if s_ == "overture":
            OV.build([k for k in kinds if kind_info(k)], country)
        else:
            _build_foursquare(kinds, country)


def _build_foursquare(kinds: list[str], country: str = "US"):
    """Save the Foursquare places of each type for one country or a group of countries (one scan of the dataset per type, then split per country)."""
    codes = C.resolve(country)
    token = hf_token()
    if not token:
        sys.exit("Set HF_TOKEN first (README, 'One-time: business data'). It's a free Hugging Face read token.")
    bad = [k for k in kinds if not kind_info(k)]
    if bad:
        sys.exit(f"Unknown business type(s): {', '.join(bad)}. Run: python dse.py kinds (or type your own in the lead tool: it is saved for you)")
    DATA.mkdir(exist_ok=True)
    r = requests.get("https://huggingface.co/api/datasets/foursquare/fsq-os-places/tree/main/release",
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    dt = sorted(x["path"].split("dt=")[1] for x in r.json() if "dt=" in x["path"])[-1]
    con = _con()
    con.sql(f"CREATE SECRET hf (TYPE huggingface, TOKEN '{token}')")
    cats = con.sql(f"SELECT category_id, category_name FROM '{HF}/release/dt={dt}/categories/parquet/*.parquet'").fetchall()
    for kind in kinds:
        names = {n.lower() for n in kind_info(kind)[1]}
        ids = [cid for cid, name in cats if (name or "").lower() in names]
        if not ids:
            log(f"  {kind}: no Foursquare category found, skipped")
            continue
        t = time.time()
        tmp = (DATA / f"_building-{kind}.parquet").as_posix()
        in_list = ", ".join(repr(c) for c in codes)
        con.sql(f"""
            COPY (
              SELECT country, fsq_place_id, name, latitude::DOUBLE AS latitude, longitude::DOUBLE AS longitude, address, locality,
                     region, postcode, tel, website, email, facebook_id, instagram, fsq_category_labels, date_refreshed
              FROM '{HF}/release/dt={dt}/places/parquet/*.parquet'
              WHERE country IN ({in_list}) AND date_closed IS NULL
                AND list_has_any(fsq_category_ids, [{', '.join(repr(i) for i in ids)}])
            ) TO '{tmp}' (FORMAT parquet)""")
        cols = "fsq_place_id, name, latitude, longitude, address, locality, region, postcode, tel, website, email, facebook_id, instagram, fsq_category_labels, date_refreshed"
        for cc in codes:
            dst = extract_path(kind, cc).as_posix()
            con.sql(f"COPY (SELECT {cols} FROM '{tmp}' WHERE country = '{cc}') TO '{dst}' (FORMAT parquet)")
            n = con.sql(f"SELECT count(*) FROM '{dst}'").fetchall()[0][0]
            log(f"  {kind}: {n} {C.NAMES[cc]} places saved ({cc}, release {dt})")
        Path(tmp).unlink(missing_ok=True)
        log(f"  {kind}: done in {int(time.time() - t)} s")
    (DATA / "places-release.txt").write_text(dt + "\n", encoding="utf-8")


def geocode(place: str, country: str = "US") -> tuple[float, float]:
    """'Tampa FL' -> (lat, lon) via OpenStreetMap Nominatim (free, max 1 request a second), cached. The US keeps its old cache keys; other countries are cached as 'GB|leeds'."""
    DATA.mkdir(exist_ok=True)
    cache = {}
    if GEOCACHE.exists():
        with open(GEOCACHE, newline="", encoding="utf-8") as f:
            cache = {r["place"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)}
    key = place.strip().lower() if country == "US" else f"{country}|{place.strip().lower()}"
    if key in cache:
        return cache[key]
    time.sleep(1.1)
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": place + ", USA" if country == "US" else place, "format": "json", "limit": 1, "countrycodes": country.lower()},
                     headers={"User-Agent": "DSEToolkit/1.0 (local lead research)"}, timeout=20)
    hits = r.json()
    if not hits:
        sys.exit(f"Could not find the city '{place}'" + (". Write it like 'Tampa FL'." if country == "US" else f" in {C.NAMES.get(country, country)}. Try the city name alone."))
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


SITE_TITLES: dict[str, str] = {}               # url -> the page's title, filled by site_live (the audit sheet shows it)
EVIDENCE_STRONG = ("title", "body")            # the site says the trade in its title or headings, or repeats it in the page
EVIDENCE_WEAK = ("weak", "thin", "blocked")    # mentioned once or twice, page too short to tell, or the site blocks scripts: kept, but not confirmed


def site_live(url: str, words: str = "") -> str:
    """'' when the site is dead, parked or for sale, or a full page that never mentions the trade. Otherwise how strongly it says it is that business:
    'title' (in the page title, a heading or the description), 'body' (3 or more times in the page), 'weak' (once or twice), 'thin' (page too short to tell),
    'blocked' (the site blocks scripts: the check reads it with Edge), or 'unchecked' (no words to look for). A non-empty answer means live, so old callers that
    only want a yes or no still work."""
    try:
        r = pagecache.get(url, timeout=12)
    except Exception:
        return ""
    if r.status_code in (403, 429):
        return "blocked"
    if r.status_code >= 400:
        return ""
    raw = r.text[:200000]
    t = raw.lower()
    if len(t) <= 300 or any(d in t[:30000] for d in DEAD_TEXT):
        return ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip() if m else ""
    if re.search(r"\bfor sale\b", title.lower()) and re.search(r"\.[a-z]{2,}\b", title.lower()):
        return ""                                # "TheAirportHotel.com for sale": a parked domain whose page text our list of phrases did not catch
    SITE_TITLES[url] = title[:120]
    visible = re.sub(r"<[^>]+>", " ", t)
    if not words:
        return "unchecked"
    heads = " ".join(re.sub(r"<[^>]+>", " ", h) for h in re.findall(r"(?is)<h[12][^>]*>(.*?)</h[12]>", t)) + " " + title.lower()
    meta = re.search(r"(?is)<meta[^>]+name=[\"']description[\"'][^>]*content=[\"'](.*?)[\"']", t)
    heads += " " + (meta.group(1) if meta else "")
    if re.search(words, heads):
        return "title"
    hits = len(re.findall(words, visible))
    if hits >= 3:
        return "body"
    if hits >= 1:
        return "weak"
    if len(visible.split()) > 150:
        return ""                            # a full page that never mentions the trade: wrong website for this place
    return "thin"


def own_words(text: str) -> str:
    """Your own words as a pattern: 'wedding, bride' -> wedding|bride (letters, digits and spaces only, so nothing you type can break the pattern)."""
    ws = [re.escape(w.strip().lower()) for w in re.split(r"[,;]", text or "") if 2 <= len(w.strip()) <= 40]
    return "|".join(ws[:12])


def find(kind: str, cities: str, miles: float = 25.0, cap: int = 100, keep_all: bool = False, out: str = "", words: str = "", skip: str = "", country: str = "US", source: str = "foursquare", cities_file: str = "", tiers: str = "", strict: bool = False) -> str:
    """kind: a built-in or saved business type, or one you type (found among Foursquare's categories, saved, and its data built on first use).
    words: your own words the business's website must use (replaces the built-in ones). skip: words that put a business out when they are in its name."""
    try:
        country = C.one(country)
    except ValueError as e:
        sys.exit(str(e))
    kind = resolve_kind(kind)
    info = kind_info(kind)
    if cities_file:
        from . import cities as CT
        places = CT.load(cities_file, tiers)
    else:
        places = [(c.strip(), None, None) for c in re.split(r"[;|]", cities) if c.strip()]
    if not places:
        sys.exit("Give at least one city, like 'Tampa FL; Orlando FL', or a cities file with some cities marked to use.")
    paths = []
    for s_ in sources_for(source):
        src = extract_path(kind, country, s_)
        if not src.exists():
            log(f"No {s_} business data for '{kind}' in {country} yet: building it now (once, a few minutes).")
            build([kind], country, s_)
        if src.exists():
            paths.append((s_, src))
    if not paths:
        sys.exit(f"No business data for '{kind}' in {country} from {source}. Check the business type, or try --source foursquare.")
    con = _con()
    names = [n.lower() for n in info[1]] + [n.lower() for n in (OV.category_names(kind) if "overture" in [s_ for s_, _ in paths] else [])]
    site_words = site_words_for(country, own_words(words), info[2])
    skip_re = re.compile(own_words(skip), re.I) if own_words(skip) else None
    per_city = max(1, cap // len(places))
    rows, seen = [], set()
    for place, lat, lon in places:
        if lat is None or lon is None:
            lat, lon = geocode(place, country)
        dlat, dlon = miles / 69.0, miles / (69.0 * max(0.2, math.cos(math.radians(lat))))
        box = f"latitude BETWEEN {lat - dlat} AND {lat + dlat} AND longitude BETWEEN {lon - dlon} AND {lon + dlon}"
        rel = con.sql(" UNION ALL BY NAME ".join(f"SELECT *, '{OV.SOURCE_LABEL if s_ == 'overture' else FSQ_LABEL}' AS _src FROM '{path.as_posix()}' WHERE {box}" for s_, path in paths))
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
            if skip_re and skip_re.search(p["name"] or ""):
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
                "category": info[0], "distance_mi": round(dist, 1), "search_city": place,
                "last_refreshed": str(p["date_refreshed"] or ""),
                "source": f"{p['_src']}, {time.strftime('%Y-%m-%d')}",
                **({"country": country} if country != "US" else {}),
            })
        found = len(city_rows)
        city_rows.sort(key=lambda r: (r["website"] == "", r["last_refreshed"][:4] < "2021", r["distance_mi"]))
        kept, pool = [], [r for r in city_rows if r["website"]]
        for i in range(0, len(pool), 40):        # Foursquare keeps closed businesses: keep only live websites
            if len(kept) >= per_city:
                break
            batch = pool[i:i + 40]
            with cf.ThreadPoolExecutor(16) as ex:
                for r, live in zip(batch, ex.map(lambda u: site_live(u, site_words), (b["website"] for b in batch))):
                    ev = live if isinstance(live, str) and live else ("unchecked" if live else "")      # a plain True from an old caller or a test
                    if strict and site_words and ev in EVIDENCE_WEAK:
                        continue                                                                       # --strict: only sites that say the trade clearly
                    if ev and len(kept) < per_city:
                        r["niche_match"] = ev
                        r["site_title"] = SITE_TITLES.get(r["website"], "")
                        kept.append(r)
        rows += kept
        log(f"  {place}: {found} independent {info[0].lower()} in range, kept {len(kept)} with a live website")
    dst = out or str(out_path(kind, places[0][0] + (f"-plus{len(places) - 1}" if len(places) > 1 else "")))
    write_csv(dst, rows)
    mix = {k: sum(1 for r in rows if r.get("niche_match") == k) for k in ("title", "body", "weak", "thin", "blocked", "unchecked")}
    print(f"{len(rows)} {info[0].lower()} -> {dst}")
    if rows and site_words:
        sure = mix["title"] + mix["body"]
        print(f"   their websites say the trade: {mix['title']} in the title or headings, {mix['body']} repeated in the page, {mix['weak']} once or twice, {mix['thin']} page too short to tell, "
              f"{mix['blocked']} blocked -> {round(100 * sure / len(rows))}% clearly the trade" + ("" if strict else " (add --strict to keep only those)"))
    return dst
