"""Company registers and the catalog of lead sources.

  python dse.py directories                              every source, how we are allowed to use it, and whether it is built
  python dse.py registry build dentist,plumber           UK: downloads Companies House's free monthly file (471 MB) once and saves every ACTIVE company of those types
  python dse.py registry find dentist "Leeds; Bradford"  lists them by town, with how old each company is (a company 3 years old is a real business, not a shell)

Companies House (the UK register) is official open data (Open Government Licence). It has NO website, phone or email, so its leads are
companies to find a web presence for: perfect for "you have no website yet" offers, and for the next step (python dse.py enrich) that looks for the site.
The file is read straight from the public download page; nothing is scraped.
"""
from __future__ import annotations

import csv
import io
import re
import sys
import time
import zipfile
from pathlib import Path

import requests

from . import places as P
from .common import DATA, UA, log, out_path, write_csv

CH_PAGE = "https://download.companieshouse.gov.uk/en_output.html"
CH_FILE = "https://download.companieshouse.gov.uk/BasicCompanyDataAsOneFile-{date}.zip"
CH_COMPANY = "https://find-and-update.company-information.service.gov.uk/company/{number}"
SOURCE_LABEL = "Companies House (UK register)"

# our business type -> UK SIC 2007 codes (the register's own trade codes). Several types share a code (a hairdresser and a barber are both 96020).
SIC: dict[str, list[str]] = {
    "dentist": ["86230"], "chiropractor": ["86900"], "physical-therapy": ["86900"], "optometrist": ["47782"], "veterinarian": ["75000"],
    "hvac": ["43220"], "plumber": ["43220"], "roofer": ["43910"], "electrician": ["43210"], "landscaper": ["81300"],
    "cleaning": ["81210", "81221", "81222", "81229", "81299"], "pest-control": ["81291"],
    "general-contractor": ["41201", "41202", "43999", "43390"], "hair-salon": ["96020"], "barbershop": ["96020"], "spa": ["96040"],
    "law-office": ["69101", "69102", "69109"], "insurance": ["66220"], "real-estate": ["68310"], "gym": ["93130"], "movers": ["49420"],
    "interior-design": ["74100"], "home-care": ["88100"], "assisted-living": ["87300"], "nursing-home": ["87100"], "senior-services": ["88100"],
}

# name -> (what it is, countries, how we may use it, status)
CATALOG: list[tuple[str, str, str, str, str]] = [
    ("Foursquare Open Source Places", "places with phone, site, social", "world", "open data (Apache 2.0), needs the free HF_TOKEN", "built: --source foursquare"),
    ("Overture Maps Places", "places with phone, site, social", "world", "open data (CDLA Permissive 2.0), no token", "built: --source overture"),
    ("Companies House", "every UK company: name, town, postcode, trade code, age", "UK", "official open data (Open Government Licence), free monthly file, no key", "built: registry build/find"),
    ("OpenStreetMap (Overpass)", "places with tags for phone and site", "world", "open data (ODbL), public servers are fair-use and were failing on 18 Nov 2026", "not built: unreliable today, retry later"),
    ("Google Places API", "places, ratings, reviews", "world", "official API with a key, paid per call, limits on storing results", "not used: $0 mode (use by hand or with your own key later)"),
    ("Yelp, Yellow Pages, Trustpilot", "consumer directories", "US, UK and more", "their terms forbid scraping; Yelp's API limits lead-list use", "not used: look by hand"),
    ("Clutch, Sortlist and other agency directories", "agencies, with reviews", "world", "terms forbid scraping", "not used: look by hand or ask the agency"),
    ("Professional registers (lawyers, doctors, contractors, brokers)", "licensed people and firms", "by state and country", "each register has its own terms; many allow lookups, few allow bulk copies", "not built: needs a decision per register, say which path"),
    ("OpenCorporates", "company registers of many countries", "world", "free for lookups; bulk and commercial use is paid", "not used: $0 mode"),
    ("Our own technology detector (a free BuiltWith)", "what a website is built with and what it is missing (booking, chat, CRM, analytics, ...)", "world", "reads one public page, after robots.txt; no account, no key", "built: python dse.py tech"),
    ("BuiltWith and Wappalyzer APIs", "the same, for whole lists and the history of a site", "world", "paid API (the free tier is lookups only)", "not used: $0 mode; our detector covers one page per site"),
]


def catalog_lines() -> list[str]:
    out = ["Lead sources (terms were not re-read for every row: read a source's terms before you rely on it)"]
    for name, what, where, terms, status in CATALOG:
        out += [f"  {name}", f"      gives:  {what}   ({where})", f"      terms:  {terms}", f"      status: {status}"]
    return out


def _clean(row: dict) -> dict:
    return {(k or "").strip(): (v or "").strip() for k, v in row.items()}


def _date(text: str):
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", text or "")
    return (int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def age_years(incorporated: str, today=None) -> float:
    d = _date(incorporated)
    if not d:
        return 0.0
    t = today or time.localtime()
    return round((t.tm_year - d[0]) + (t.tm_mon - d[1]) / 12 + (t.tm_mday - d[2]) / 365, 1)


def registry_path(kind: str, country: str = "GB") -> Path:
    return DATA / f"registry-{country.lower()}-{kind}.csv"


def latest_file_date() -> str:
    """The date in the newest file name on Companies House's download page (they publish one every month)."""
    html = requests.get(CH_PAGE, timeout=30, headers=UA).text
    dates = sorted(set(re.findall(r"BasicCompanyDataAsOneFile-(\d{4}-\d{2}-\d{2})\.zip", html)))
    if not dates:
        sys.exit("Could not find the Companies House file on its download page. Try again later, or download it by hand and use --file.")
    return dates[-1]


def download(dst: Path) -> Path:
    date = latest_file_date()
    zpath = dst / f"BasicCompanyDataAsOneFile-{date}.zip"
    if zpath.exists():
        return zpath
    log(f"Downloading the Companies House file for {date} (about 470 MB, once a month)...")
    tmp = zpath.with_suffix(".part")
    with requests.get(CH_FILE.format(date=date), stream=True, timeout=60, headers=UA) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.replace(zpath)
    return zpath


def trade_words(kind: str) -> list[str]:
    """For a business type with no hand-made trade codes (any of the app's 500+ niches you typed): the word stems its register trade description must all contain."""
    from . import niches as NI
    info = P.custom_kinds().get(kind)
    term = (info.get("typed") or info["label"]) if info else (NI.term_for(kind) or "")
    return sorted({P._stem(w) for w in re.findall(r"[a-z]{3,}", term.lower())})


def known(kind: str) -> bool:
    return kind in SIC or bool(trade_words(kind))


def build(kinds: list[str], file: str = "", sic: str = "") -> None:
    """Save every ACTIVE company of each type from the monthly file, one pass for all types. A built-in type uses its trade codes; any other saved business type is matched by the
    words of its name against the register's trade descriptions; `sic` adds trade codes of your own (like 74100,43320) to every type named. `file` = a zip you already have."""
    extra = [c.strip() for c in re.split(r"[,;\s]+", sic or "") if c.strip()]
    badcode = [c for c in extra if not re.fullmatch(r"\d{5}", c)]
    if badcode:
        sys.exit(f"Trade codes are 5 digits (like 74100): {', '.join(badcode)}")
    bad = [k for k in kinds if not known(k) and not extra]
    if bad:
        sys.exit(f"No trade codes or words for: {', '.join(bad)}. Use a business type the app knows, or give trade codes: --sic 74100")
    DATA.mkdir(exist_ok=True)
    zpath = Path(file) if file else download(DATA)
    if not zpath.is_file():
        sys.exit(f"File not found: {zpath}")
    by_code: dict[str, list[str]] = {}
    words: dict[str, list[str]] = {}
    for k in kinds:
        for code in SIC.get(k, []) + extra:
            by_code.setdefault(code, []).append(k)
        if k not in SIC and trade_words(k):
            words[k] = trade_words(k)
    out: dict[str, list[dict]] = {k: [] for k in kinds}
    t = time.time()
    seen = 0
    with zipfile.ZipFile(zpath) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(name) as raw:
            for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")):
                seen += 1
                r = _clean(row)
                if r.get("CompanyStatus") != "Active":
                    continue
                codes = [r.get(f"SICCode.SicText_{i}", "")[:5] for i in (1, 2, 3, 4)]
                hit = [k for c in codes for k in by_code.get(c, [])]
                if words:
                    text = " ".join(r.get(f"SICCode.SicText_{i}", "") for i in (1, 2, 3, 4)).lower()
                    hit += [k for k, ws in words.items() if all(w in text for w in ws)]
                if not hit:
                    continue
                rec = {
                    "business": r.get("CompanyName", ""), "city": r.get("RegAddress.PostTown", ""), "state": r.get("RegAddress.County", ""),
                    "postcode": r.get("RegAddress.PostCode", ""), "company_number": r.get("CompanyNumber", ""),
                    "incorporated": r.get("IncorporationDate", ""), "sic": " | ".join(x for x in (r.get(f"SICCode.SicText_{i}", "") for i in (1, 2, 3, 4)) if x),
                    "company_type": r.get("CompanyCategory", ""),
                }
                for k in dict.fromkeys(hit):
                    out[k].append(rec)
    for k, rows in out.items():
        with open(registry_path(k), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["business", "city", "state", "postcode", "company_number", "incorporated", "sic", "company_type"])
            w.writeheader()
            w.writerows(rows)
        log(f"  {k}: {len(rows)} active UK companies saved")
    log(f"  read {seen} companies in {int(time.time() - t)} s from {zpath.name}")


def find(kind: str, towns: str, min_age: float = 1.0, cap: int = 100, out: str = "", keep_all: bool = False) -> str:
    """Companies of one type in the towns you name, oldest first among those at least `min_age` years old. No website here: see the module note."""
    src = registry_path(kind)
    if not src.exists():
        sys.exit(f"No register list for '{kind}' yet. Run: python dse.py registry build {kind}")
    want = [t.strip().lower() for t in re.split(r"[;|]", towns) if t.strip()]
    if not want:
        sys.exit("Give at least one town, like 'Leeds; Bradford'.")
    per = max(1, cap // len(want))
    rows = []
    with open(src, newline="", encoding="utf-8-sig") as f:
        everything = list(csv.DictReader(f))
    for town in want:
        mine = []
        for r in everything:
            if r["city"].strip().lower() != town:
                continue
            if not keep_all and P.CHAINS.search(r["business"]):
                continue
            age = age_years(r["incorporated"])
            if age < min_age:
                continue
            mine.append((age, r))
        mine.sort(key=lambda x: (-x[0], x[1]["business"]))
        for age, r in mine[:per]:
            rows.append({
                "business": r["business"].title(), "city": r["city"].title(), "state": r["state"].title(), "website": "", "phone": "", "email": "",
                "address": r["postcode"], "category": kind, "company_number": r["company_number"], "incorporated": r["incorporated"], "company_age_years": age,
                "sic": r["sic"], "companies_house_url": CH_COMPANY.format(number=r["company_number"]), "search_city": town.title(), "country": "GB",
                "source": f"{SOURCE_LABEL}, {time.strftime('%Y-%m-%d')}",
            })
        log(f"  {town.title()}: {len(mine)} companies at least {min_age:g} years old, kept {min(len(mine), per)}")
    dst = out or str(out_path("registry", kind, want[0] + (f"-plus{len(want) - 1}" if len(want) > 1 else "")))
    write_csv(dst, rows)
    print(f"{len(rows)} {kind} companies -> {dst}  (no websites in the register: run the enrich step to find them)")
    return dst
