"""Lead enrichment: turn a list of companies into reachable leads, from their OWN public websites, for free.

    python dse.py enrich leads.csv [--icp "emergency, 24/7"] [--engine my-engine] [--max 100] [--fast]     enrich a whole CSV
    python dse.py enrich --site https://some-business.com                                                 look at one website

Input: any CSV with a website or domain column (the same header spellings the Go-to-Market import understands: Clay, Apollo and HubSpot exports work as they are).
Everything in your file is kept. New columns are added, and what you gave is never overwritten.

The waterfall, per lead, stopping as soon as it has what it needs (the `steps` column shows which steps ran):
  given   what your file already had (an email, a name)
  home    the homepage: emails, phone, socials, forms, booking tool, tech, who runs it
  inner   the contact, about and team pages (only if an email or a decision maker is still missing)
  render  a hidden browser reads sites drawn by JavaScript (Wix, Squarespace, Showit ...) when the plain page gave nothing (skipped with --fast)
  guess   only when a named decision maker has no email AND the domain receives mail: likely addresses, clearly marked as guesses. They are never put in `email`.

Rules it follows:
  * only the lead's own website is read, politely (robots.txt respected, one second between pages, a short list of pages). No logged-in scraping, no Google Maps pages, no social networks
  * every found email and name carries the page it came from (`email_source`, `decision_maker_source`), so you can check any of them in one click
  * business contacts only: the point is to reach a company about its work, with a real sender name and an easy way to say no
  * the score and the 'why' come from the rules in dse/enrich_rules.json, nothing else
"""
from __future__ import annotations

import datetime as dt
import copy
import hashlib
import html as htmllib
import json
import math
import re
import socket
import subprocess
import time
import urllib.parse
import urllib.robotparser
from pathlib import Path

from . import enrich_providers as ep
from . import field_results as fr
from . import waterfall as wf
from . import importer
from .common import LISTS, ROOT, fetch, log, norm_url, read_csv, render_dom, write_csv
from .common import UA as _UA

RULES = json.loads((Path(__file__).with_name("enrich_rules.json")).read_text(encoding="utf-8"))
GENERIC = set(RULES["generic_locals"])
FREEMAIL = set(RULES["freemail"])
BOT = "DSEToolkit"
PAGE_PAUSE = 1.0
INNER_WORDS = ["contact", "about", "team", "staff", "people", "leadership", "our-story", "meet", "who-we-are"]
EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
JUNK = ("sentry", "wixpress", "example.", "domain.com", "email.com", "yourname", "your@", "name@", "user@", "@2x", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".css", ".js", "noreply", "no-reply", "donotreply")
PHONE_RX = re.compile(r"(?:\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b|\+44[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}\b")
NAME_RX = r"[A-Z][a-z'’-]+(?:\s+(?:[A-Z]\.|[A-Z][a-z'’-]+)){1,2}"
STOP = {"our", "the", "team", "contact", "meet", "call", "us", "home", "about", "services", "free", "get", "book", "request", "learn", "read", "more", "view", "and", "of", "for", "with",
        "founder", "owner", "director", "manager", "president", "ceo", "partner", "principal", "head", "chief", "officer", "general", "managing", "office", "practice", "senior", "lead"}
# Words that make two capitalised words a heading, a widget or a company, not a person ("Google Reviews", "Tree Services", "Meet Team"). Found on a real run (18 Nov 2026):
# a site's review widget was taken as its owner because a "Meet the Owner" heading sat next to it.
NOT_A_NAME = {"google", "reviews", "review", "facebook", "instagram", "twitter", "youtube", "linkedin", "yelp", "trustpilot", "checkatrade", "mybuilder", "ratedpeople", "testimonials",
              "testimonial", "gallery", "services", "service", "tree", "trees", "surgery", "surgeons", "care", "ltd", "limited", "llc", "inc", "company", "group", "solutions", "contact",
              "meet", "welcome", "latest", "recent", "featured", "customer", "customers", "client", "clients", "work", "projects", "project", "news", "blog", "quote", "quotes", "free",
              "privacy", "cookie", "cookies", "terms", "policy", "rights", "reserved", "copyright", "powered", "website", "web", "design", "designed", "marketing", "digital", "media",
              "find", "follow", "like", "share", "tweet", "call", "email", "phone", "address", "opening", "hours", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
# "Owned by Wayne Hargreaves", "run by Dave Smith", "founded by ...": small firms name the owner in a sentence, not next to a title (found on a real run, 19 Nov 2026).
OWNED_BY = re.compile(rf"\b(?P<cue>(?i:owned(?:\s+and\s+(?:run|operated|managed))?|run|operated|managed|founded|established|started))\s+(?i:by)\s+(?P<name>{NAME_RX})(?![A-Za-z'’-])")
NOT_AN_OWNER = {"council", "analytics", "wordpress", "wix", "squarespace", "hosting", "agency", "studio", "associates", "partners", "holdings", "network", "systems", "software", "technologies"}
HEADING_TITLE = re.compile(r"^(?:meet|our|about|the|why|welcome|get|contact|read|view|see)\b", re.I)
TITLE_ANY = re.compile("|".join(f"(?:{t['rx']})" for t in RULES["titles"]), re.I)
SOCIAL_ONLY = set(RULES["social_only_domains"])
BOOKING = re.compile(RULES["booking_rx"], re.I)


# ------------------------------------------------------------------ pure extraction (no network)

def to_text(html: str) -> str:
    h = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", html or "")
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr|td|section|article|header|footer|address|span|a)>", "\n", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = htmllib.unescape(h)
    return "\n".join(re.sub(r"[ \t ]+", " ", ln).strip() for ln in h.splitlines() if ln.strip())


def deobfuscate(s: str) -> str:
    s = urllib.parse.unquote(s or "")
    s = re.sub(r"\s*[\[\(\{]\s*at\s*[\]\)\}]\s*", "@", s, flags=re.I)
    s = re.sub(r"\s*[\[\(\{]\s*dot\s*[\]\)\}]\s*", ".", s, flags=re.I)
    return s


def email_kind(addr: str, site_domain: str = "") -> str:
    local, _, dom = addr.lower().partition("@")
    if local in GENERIC or re.fullmatch(r"(info|hello|contact|office|admin|support)\d*", local):
        return "generic"
    if dom in FREEMAIL:
        return "freemail"
    return "personal" if re.fullmatch(r"[a-z]{2,}(?:[._-][a-z]{1,})?[0-9]{0,2}", local) else "generic"


def extract_emails(html: str, site_domain: str = "") -> list[dict]:
    """Emails on a page: [{email, kind}], best first (own-domain personal, own-domain general, freemail), junk removed."""
    raw = deobfuscate(html)
    found: dict[str, str] = {}
    for e in EMAIL_RX.findall(raw):
        e = e.lower().strip(".")
        if any(j in e for j in JUNK) or e.endswith((".png", ".jpg", ".gif")):
            continue
        found.setdefault(e, email_kind(e, site_domain))
    own = site_domain.lower().removeprefix("www.")

    def rank(item):
        e, k = item
        same = e.split("@")[1].endswith(own) if own else True
        return (0 if same and k == "personal" else 1 if same and k == "generic" else 2 if k == "freemail" else 3, e)

    items = [(e, k) for e, k in found.items() if not own or e.split("@")[1].endswith(own) or k == "freemail"]
    return [{"email": e, "kind": k} for e, k in sorted(items, key=rank)][:6]


def extract_phones(html: str) -> list[str]:
    tel = [urllib.parse.unquote(m).strip() for m in re.findall(r"href=[\"']tel:([^\"']+)", html or "", re.I)]
    text = to_text(html)
    nums = tel + [m.group(0) for m in PHONE_RX.finditer(text)]
    out, seen = [], set()
    for n in nums:
        n = re.sub(r"\s+", " ", n).strip()
        digits = re.sub(r"\D", "", n)
        key = digits[-10:]                      # +1 813... and (813) ... are the same number
        if 10 <= len(digits) <= 13 and key not in seen:
            seen.add(key)
            out.append(n)
    return out[:3]


def extract_socials(html: str) -> dict:
    out = {"linkedin": "", "instagram": "", "facebook": "", "x": "", "youtube": ""}
    h = html or ""
    m = re.search(r"linkedin\.com/(company|in)/([A-Za-z0-9%._-]{2,80})", h)
    if m:
        out["linkedin"] = f"https://www.linkedin.com/{m.group(1)}/{m.group(2)}"
    m = re.search(r"instagram\.com/(?!p/|reel|explore|accounts|stories|share)([A-Za-z0-9._]{2,30})", h)
    if m:
        out["instagram"] = "https://instagram.com/" + m.group(1)
    m = re.search(r"facebook\.com/(pages/[^\"'<>\s?#]{3,120}|profile\.php\?id=\d+|(?!sharer|tr\?|plugins|dialog|pages|share|login|events|groups)[A-Za-z0-9._-]{3,60})", h)
    if m:
        out["facebook"] = "https://facebook.com/" + m.group(1).rstrip("/")
    m = re.search(r"(?:twitter|x)\.com/(?!share|intent|home)([A-Za-z0-9_]{2,20})", h)
    if m:
        out["x"] = "https://x.com/" + m.group(1)
    m = re.search(r"youtube\.com/(?:c/|channel/|@|user/)([A-Za-z0-9._-]{2,60})", h)
    if m:
        out["youtube"] = "https://youtube.com/" + ("@" if not m.group(0).split("/")[1].startswith(("c", "channel", "user")) else "") + m.group(1)
    return out


def detect_tech(html: str) -> list[str]:
    low = (html or "").lower()
    return [name for name, sigs in RULES["tech"].items() if any(s.lower() in low for s in sigs)]


def has_form(html: str) -> bool:
    for m in re.finditer(r"(?is)<form\b(.*?)</form>", html or ""):
        body = m.group(1)
        if re.search(r"type=[\"']?search|role=[\"']?search|name=[\"']?s[\"']|action=[\"'][^\"']*search", body, re.I):
            continue
        if re.search(r"<textarea|type=[\"']?email|name=[\"']?(email|message|phone)", body, re.I):
            return True
    return False


def meta_description(html: str) -> str:
    for rx in (r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"']([^\"']{10,300})", r"<meta[^>]+content=[\"']([^\"']{10,300})[\"'][^>]+name=[\"']description",
               r"<meta[^>]+property=[\"']og:description[\"'][^>]+content=[\"']([^\"']{10,300})"):
        m = re.search(rx, html or "", re.I)
        if m:
            return htmllib.unescape(m.group(1)).strip()
    return ""


def copyright_year(text: str) -> int | None:
    years = [int(y) for y in re.findall(r"(?:©|&copy;|\(c\)|copyright)[^\n]{0,40}?((?:19|20)\d{2})\b", text or "", re.I)]
    return max(years) if years else None


def title_rank(title: str) -> int | None:
    for t in RULES["titles"]:
        if re.search(rf"\b(?:{t['rx']})\b", title or "", re.I):
            return t["rank"]
    return None


def good_name(name: str) -> bool:
    words = re.split(r"\s+", name.strip())
    return 2 <= len(words) <= 3 and not any(w.lower().strip(".,") in STOP or w.lower().strip(".,") in NOT_A_NAME for w in words) and not re.search(r"\d", name)


def json_ld(html: str) -> list[dict]:
    out = []
    for m in re.finditer(r"(?is)<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", html or ""):
        try:
            data = json.loads(m.group(1).strip())
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                out.append(d)
                stack.extend(v for v in d.values() if isinstance(v, (dict, list)))
            elif isinstance(d, list):
                stack.extend(d)
    return out


def extract_people(html: str) -> list[dict]:
    """People with a senior title on the page: [{name, title, rank}], most senior first."""
    people: dict[str, dict] = {}

    def add(name, title):
        name, title = re.sub(r"\s+", " ", name or "").strip(" ,.-|:"), re.sub(r"\s+", " ", title or "").strip(" ,.-|:")
        r = title_rank(title)
        if r and good_name(name) and len(title) <= 60 and not HEADING_TITLE.match(title):
            cur = people.get(name)
            if not cur or r < cur["rank"]:
                people[name] = {"name": name, "title": title, "rank": r}

    for d in json_ld(html):
        t = d.get("@type")
        if (t == "Person" or (isinstance(t, list) and "Person" in t)) and d.get("name"):
            add(str(d["name"]), str(d.get("jobTitle") or ""))
    lines = to_text(html).splitlines()
    for i, ln in enumerate(lines):
        if len(ln) > 90:
            continue
        m = re.match(rf"^({NAME_RX})\s*[,|–\-:]\s*(.{{3,60}})$", ln)
        if m and TITLE_ANY.search(m.group(2)):
            add(m.group(1), m.group(2))
            continue
        m = re.match(rf"^(.{{3,60}}?)\s*[:–\-|,]\s*({NAME_RX})$", ln)
        if m and TITLE_ANY.search(m.group(1)):
            add(m.group(2), m.group(1))
            continue
        if re.fullmatch(NAME_RX, ln) and i + 1 < len(lines) and len(lines[i + 1]) <= 60 and TITLE_ANY.search(lines[i + 1]):
            add(ln, lines[i + 1])
    for ln in lines:
        for m in OWNED_BY.finditer(ln):
            nm = m.group("name")
            if any(w.lower().strip(".,") in NOT_AN_OWNER for w in nm.split()):
                continue
            add(nm, "Founder" if m.group("cue").lower().split()[0] in ("founded", "established", "started") else "Owner")
    return sorted(people.values(), key=lambda p: (p["rank"], p["name"]))


def email_guesses(name: str, domain: str) -> list[str]:
    parts = [re.sub(r"[^a-z]", "", w.lower()) for w in name.split() if not re.fullmatch(r"[A-Z]\.", w)]
    if len(parts) < 2 or not all(parts) or not domain:
        return []
    f, l = parts[0], parts[-1]
    return [f"{f}@{domain}", f"{f}.{l}@{domain}", f"{f[0]}{l}@{domain}"]


# ------------------------------------------------------------------ network helpers

_ROBOTS: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def robots_ok(url: str) -> bool:
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _ROBOTS:
        rp = urllib.robotparser.RobotFileParser()
        code, _u, text = fetch(base + "/robots.txt", timeout=10, tries=1)
        if code == 200 and text:
            rp.parse(text.splitlines())
            _ROBOTS[base] = rp
        else:
            _ROBOTS[base] = None            # no robots.txt (or none we can read): allowed
    rp = _ROBOTS[base]
    return True if rp is None else rp.can_fetch(BOT, url)


def resolves(domain: str) -> bool:
    host = domain.split(":")[0]
    try:
        socket.gethostbyname(host)
        return True
    except OSError:
        return False


def has_mx(domain: str) -> str:
    """'yes', 'no' or 'unknown', from the system's own DNS tool (nslookup)."""
    host = domain.split(":")[0]
    if re.fullmatch(r"[\d.]+", host) or host in ("localhost",):
        return "unknown"
    try:
        r = subprocess.run(["nslookup", "-type=mx", host], capture_output=True, timeout=10, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    out = r.stdout.decode("utf-8", "replace").lower()
    if "mail exchanger" in out:
        return "yes"
    if "non-existent" in out or "can't find" in out or "no mx" in out or "no answer" in out:
        return "no"
    return "unknown"


def inner_links(home_html: str, base: str, limit: int = 4) -> list[str]:
    seen, out = set(), []
    host = urllib.parse.urlparse(base).netloc
    for m in re.finditer(r"""href=["']([^"'#]+)["']""", home_html or "", re.I):
        href = m.group(1).strip()
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        full = urllib.parse.urljoin(base, href)
        pu = urllib.parse.urlparse(full)
        if pu.netloc.removeprefix("www.") != host.removeprefix("www.") or not pu.scheme.startswith("http"):
            continue
        path = pu.path.lower()
        if any(w in path for w in INNER_WORDS) and full.split("#")[0] not in seen and not re.search(r"\.(pdf|jpg|png|zip)$", path):
            seen.add(full.split("#")[0])
            out.append(full.split("#")[0])
    out.sort(key=lambda u: min((INNER_WORDS.index(w) for w in INNER_WORDS if w in u.lower()), default=99))
    return out[:limit]


# ------------------------------------------------------------------ one website

def blank(domain: str = "") -> dict:
    return {"status": "", "steps": "", "domain": domain, "emails": [], "phones": [], "contact_form": "", "booking": "", "socials": {}, "tech": [], "description": "",
            "people": [], "active": "", "copyright": None, "mx": "", "guesses": [], "icp_hits": [], "pages": [], "email_source": "", "people_source": "", "contact_page": "", "provider_note": "",
            "provider_usage": {"api_calls": 0, "cache_hits": 0}, "waterfall_metrics": {}, "waterfall_candidates": [], "field_sources": {}}


def run_field_waterfalls(out: dict, fields: dict, company: str, contact_name: str, today: dt.date, dry_run: bool) -> None:
    """Apply opt-in phone, person and firmographic provider waterfalls after first-party checks."""
    out.setdefault("firmographics", {})
    out.setdefault("field_waterfall_metrics", {})
    out.setdefault("field_waterfall_candidates", {})
    for field_name, cfg in fields.items():
        if not cfg.get("provider_configs"):
            continue
        if field_name == "phone" and out.get("phones"):
            continue
        if field_name == "person_identity" and out.get("people"):
            continue
        budget = cfg.setdefault("budget", ep.Budget(cfg["max_provider_calls"], cfg.get("spend_approval")))
        providers = cfg["provider_configs"]
        names = contact_name.split(maxsplit=1)
        identity = {"domain": out.get("domain", ""), "website": "https://" + out.get("domain", "") if out.get("domain") else "",
                    "company": company or out.get("domain", ""), "contact_name": contact_name,
                    "first_name": names[0] if names else "", "last_name": names[1] if len(names) > 1 else ""}
        chain = []
        for provider in providers:
            def run(provider=provider):
                if dry_run:
                    is_cached, candidates = ep.cached_field(provider, identity["domain"], field_name, today, identity["contact_name"])
                    if is_cached:
                        budget.cached += 1
                        return {"candidates": candidates, "cache_hits": 1}
                    if budget.used + budget.projected < budget.limit:
                        budget.projected += 1
                        return {"candidates": [], "projected": 1}
                    return {"candidates": []}
                calls_before, cache_before = budget.used, budget.cached
                try:
                    candidates = ep.lookup_field(provider, field_name, identity, budget, today)
                except ep.ProviderError as error:
                    error.waterfall_api_calls = budget.used - calls_before
                    error.waterfall_cache_hits = budget.cached - cache_before
                    raise
                return {"candidates": candidates, "api_calls": budget.used - calls_before,
                        "cache_hits": budget.cached - cache_before}
            chain.append({"name": provider["name"], "run": run})
        def accept(candidate, _name):
            return wf.accept_field_candidate(field_name, candidate, out["domain"], company, contact_name,
                                             cfg["minimum_confidence"], cfg["minimum_identity_score"])
        result = wf.execute_chain(chain, accept, lambda accepted: bool(accepted))
        provider_by_name = {p["name"]: p for p in providers}
        for rung in result["rungs"]:
            configured_provider = provider_by_name.get(rung.get("rung"), {})
            rung["cost_per_call"] = configured_provider.get("cost_per_call")
            rung["cost_currency"] = configured_provider.get("cost_currency", "")
        out["field_waterfall_metrics"][field_name] = {"field": field_name, "dry_run": dry_run,
            "minimum_confidence": cfg["minimum_confidence"], "minimum_identity_score": cfg["minimum_identity_score"],
            "max_provider_calls": budget.limit, "providers": result["rungs"], "stop_reason": result["stop_reason"]}
        out["field_waterfall_candidates"][field_name] = result["candidates"]
        if dry_run:
            continue
        for candidate in result["accepted"]:
            value = candidate["value"]
            source = f"provider:{candidate['waterfall_provider']}"
            if field_name == "phone":
                out["phones"].append(str(value).strip())
                out["field_sources"]["phone"] = candidate.get("source_url") or source
                break
            if field_name == "person_identity":
                person = {**value, "name": value.get("name", value.get("full_name", "")),
                          "title": value.get("title", value.get("current_position", "")), "source": candidate.get("source_url") or source,
                          "rank": title_rank(value.get("title", value.get("current_position", "")))}
                out["people"].append(person)
                out["field_sources"]["decision_maker"] = person["source"]
                break
            if field_name == "firmographics":
                out["firmographics"] = {**out["firmographics"], **value}
                out["field_sources"]["firmographics"] = candidate.get("source_url") or source
                break


def enrich_site(website: str, icp_terms: list[str] | None = None, render: bool = True, given_email: str = "", given_name: str = "", today: dt.date | None = None,
                pause: float = PAGE_PAUSE, provider: dict | None = None, budget: "ep.Budget | None" = None, company: str = "",
                providers: list[dict] | None = None, waterfall_config: dict | None = None, dry_run: bool = False,
                field_waterfalls: dict | None = None) -> dict:
    """Run the waterfall on one website. Returns the facts, with the page each came from."""
    today = today or dt.date.today()
    url = norm_url(website)
    dom = urllib.parse.urlparse(url).netloc.lower() if url else ""
    out = blank(dom.removeprefix("www."))
    steps = []
    if given_email or given_name:
        steps.append("given")
    if not url:
        out.update(status="no website", steps=">".join(steps))
        return out
    if out["domain"] in SOCIAL_ONLY or any(out["domain"].endswith("." + s) for s in SOCIAL_ONLY):
        out.update(status="no own website (a profile page)", steps=">".join(steps))
        return out
    if not resolves(dom):
        out.update(status="dead domain (does not resolve)", steps=">".join(steps))
        return out
    if not robots_ok(url):
        out.update(status="robots.txt asks not to be read", steps=">".join(steps))
        return out
    code, final, home = fetch(url, timeout=15, tries=2)
    if code == 0 or code >= 400 and not home:
        out.update(status=f"no answer from the site (HTTP {code})", steps=">".join(steps))
        return out
    steps.append("home")
    pages = [(final, home)]
    out["pages"].append(final)

    def absorb(pg_url: str, pg_html: str):
        for e in extract_emails(pg_html, out["domain"]):
            if e["email"] not in [x["email"] for x in out["emails"]]:
                out["emails"].append({**e, "source": pg_url})
        for ph in extract_phones(pg_html):
            if ph not in out["phones"]:
                out["phones"].append(ph)
                out["field_sources"].setdefault("phone", pg_url)
        for p in extract_people(pg_html):
            if p["name"] not in [x["name"] for x in out["people"]]:
                out["people"].append({**p, "source": pg_url})
        if has_form(pg_html) and not out["contact_form"]:
            out["contact_form"] = pg_url
            out["field_sources"]["contact_form"] = pg_url
        b = BOOKING.search(pg_html)
        if b and not out["booking"]:
            out["booking"] = b.group(0).lower() if "." in b.group(0) else "online booking"
            out["field_sources"]["booking"] = pg_url
        for k, v in extract_socials(pg_html).items():
            if v and not out["socials"].get(k):
                out["socials"][k] = v
                out["field_sources"].setdefault(f"social_profile:{k}", pg_url)
        for t in detect_tech(pg_html):
            if t not in out["tech"]:
                out["tech"].append(t)
                out["field_sources"].setdefault("technology", pg_url)
        if not out["description"]:
            out["description"] = meta_description(pg_html)
            if out["description"]:
                out["field_sources"]["site_description"] = pg_url

    def need_more() -> bool:
        personal = any(e["kind"] == "personal" for e in out["emails"])
        return not (personal and out["people"])

    absorb(final, home)
    if need_more():
        links = inner_links(home, final)
        done_any = False
        for link in links:
            if not robots_ok(link):
                continue
            time.sleep(pause)
            c, u, h = fetch(link, timeout=15, tries=1)
            if c == 200 and h:
                pages.append((u, h))
                out["pages"].append(u)
                absorb(u, h)
                done_any = True
                if "contact" in u.lower() and not out["contact_page"]:
                    out["contact_page"] = u
                if not need_more():
                    break
        if done_any:
            steps.append("inner")
    js_built = any(k in home.lower() for k in ("squarespace", "wix.com", "wixstatic", "showit", "webflow", "framer", "__next", "react-root"))
    if render and (js_built or len(to_text(home)) < 600) and not out["emails"] and not out["people"]:
        dom_html = render_dom(final)
        if dom_html:
            pages.append((final, dom_html))
            absorb(final, dom_html)
            steps.append("render")
    if not out["contact_page"]:
        out["contact_page"] = next((p for p in out["pages"] if "contact" in p.lower()), "")
    all_text = "\n".join(to_text(h) for _u, h in pages)
    out["emails"].sort(key=lambda e: {"personal": 0, "generic": 1, "freemail": 2}.get(e["kind"], 3))      # best across every page
    out["copyright"] = copyright_year(all_text) or copyright_year("\n".join(h for _u, h in pages))
    if out["copyright"]:
        out["active"] = "yes" if out["copyright"] >= today.year - 1 else "no"
    low_text = (all_text + "\n" + out["description"]).lower()
    out["icp_hits"] = [t for t in (icp_terms or []) if t and t.lower() in low_text]
    run_field_waterfalls(out, field_waterfalls or {}, company, given_name, today, dry_run)
    provider_chain = providers if providers is not None else ([provider] if provider else [])
    config = waterfall_config or dict(wf.DEFAULT)
    existing_has_email = bool(out["emails"])
    existing_has_personal = any(e.get("kind") == "personal" for e in out["emails"])
    existing_has_person = bool(out["people"])
    policy_satisfied = (existing_has_email if config["stop_when"] == "any_email" else existing_has_personal if config["stop_when"] == "personal_email"
                        else existing_has_personal and existing_has_person)
    should_run_provider = bool(provider_chain and budget is not None and not policy_satisfied and not given_email)
    out["provider_eligible"] = bool(provider_chain and not policy_satisfied and not given_email)

    def accept(candidate, _provider_name):
        return wf.accept_email(candidate, out["domain"], config["minimum_confidence"])

    def stop_after(accepted_candidates):
        all_emails = [*out["emails"], *accepted_candidates]
        has_personal = any(x.get("kind") == "personal" for x in all_emails)
        has_email = bool(all_emails)
        has_person = bool(out["people"]) or any(x.get("name") and title_rank(x.get("title", "")) for x in accepted_candidates)
        if config["stop_when"] == "any_email":
            return has_email
        if config["stop_when"] == "personal_email":
            return has_personal
        return has_personal and has_person

    if should_run_provider and dry_run:
        def preview_rung(provider_cfg):
            def run_preview():
                is_cached, found = ep.cached(provider_cfg, out["domain"], today)
                if is_cached:
                    budget.cached += 1
                    return {"candidates": found, "api_calls": 0, "cache_hits": 1, "projected": 0}
                if budget.used + budget.projected < budget.limit:
                    budget.projected += 1
                    return {"candidates": [], "api_calls": 0, "cache_hits": 0, "projected": 1}
                return {"candidates": [], "api_calls": 0, "cache_hits": 0, "projected": 0}
            return {"name": provider_cfg["name"], "run": run_preview}
        result = wf.execute_chain([preview_rung(p) for p in provider_chain], accept, stop_after)
        out["waterfall_metrics"] = {"field": "email", "dry_run": True, "providers": result["rungs"],
                                   "stop_when": config["stop_when"], "minimum_confidence": config["minimum_confidence"],
                                   "stop_reason": result["stop_reason"]}
        out["provider_usage"] = {"provider": ", ".join(p["name"] for p in provider_chain), "api_calls": 0,
                                 "cache_hits": sum(r["cache_hits"] for r in result["rungs"]),
                                 "projected_calls": sum(r["projected"] for r in result["rungs"]), "dry_run": True,
                                 "per_provider": result["rungs"]}
        out["provider_note"] = "Dry run: optional provider calls were not made."
    elif should_run_provider:
        notes = []
        def rung_for(provider_cfg):
            def run_lookup():
                calls_before, cache_before = budget.used, budget.cached
                try:
                    found = ep.lookup(provider_cfg, out["domain"], company, budget, today)
                except ep.ProviderError as error:
                    notes.append(str(error))
                    error.waterfall_api_calls = budget.used - calls_before
                    error.waterfall_cache_hits = budget.cached - cache_before
                    raise
                return {"candidates": found, "api_calls": budget.used - calls_before,
                        "cache_hits": budget.cached - cache_before}
            return {"name": provider_cfg["name"], "run": run_lookup}

        result = wf.execute_chain([rung_for(p) for p in provider_chain], accept, stop_after)
        provider_by_name = {provider_cfg["name"]: provider_cfg for provider_cfg in provider_chain}
        for rung in result["rungs"]:
            adapter = provider_by_name.get(rung.get("rung"), {})
            rung["cost_per_call"] = adapter.get("cost_per_call")
            rung["cost_currency"] = adapter.get("cost_currency", "")
        out["waterfall_candidates"] = result["candidates"]
        calls = sum(r["api_calls"] for r in result["rungs"])
        cache_hits = sum(r["cache_hits"] for r in result["rungs"])
        out["waterfall_metrics"] = {"field": "email", "dry_run": False, "providers": result["rungs"],
                                    "stop_when": config["stop_when"], "minimum_confidence": config["minimum_confidence"],
                                    "stop_reason": result["stop_reason"]}
        out["provider_usage"] = {"provider": ", ".join(p["name"] for p in provider_chain), "api_calls": calls,
                                 "cache_hits": cache_hits, "per_provider": result["rungs"]}
        if notes:
            out["provider_note"] = "; ".join(dict.fromkeys(notes))
        have = {x["email"] for x in out["emails"]}
        for candidate in result["accepted"]:
            provider_name = candidate["waterfall_provider"]
            source = f"{provider_name} (your own API key" + (f", confidence {candidate['confidence']}" if candidate.get("confidence") not in (None, "") else "") + ")"
            if candidate["email"] not in have:
                out["emails"].append({"email": candidate["email"], "kind": candidate["kind"], "source": source})
                have.add(candidate["email"])
            if candidate.get("name") and title_rank(candidate.get("title", "")) and candidate["name"] not in [x["name"] for x in out["people"]]:
                out["people"].append({"name": candidate["name"], "title": candidate["title"], "rank": title_rank(candidate["title"]), "source": source})
        if result["accepted"]:
            steps.append("paid")
        out["emails"].sort(key=lambda e: {"personal": 0, "generic": 1, "freemail": 2}.get(e["kind"], 3))
        out["people"].sort(key=lambda x: (x["rank"], x["name"]))
    best_person = out["people"][0] if out["people"] else None
    personal_found = any(e["kind"] == "personal" for e in out["emails"])
    if best_person and not personal_found and not given_email:
        out["mx"] = has_mx(out["domain"])
        if out["mx"] == "yes":
            out["guesses"] = email_guesses(best_person["name"], out["domain"])
            if out["guesses"]:
                steps.append("guess")
    out["steps"] = ">".join(steps)
    out["status"] = "ok"
    out["email_source"] = out["emails"][0]["source"] if out["emails"] else ""
    out["people_source"] = best_person["source"] if best_person else ""
    return out


# ------------------------------------------------------------------ scoring

def score(site: dict, given_email: str = "") -> tuple[int, str]:
    rules = {r["id"]: r for r in RULES["rules"]}
    pen = {r["id"]: r for r in RULES["penalties"]}
    fired: list[tuple[str, int]] = []

    def add(rid, mult=1, table=rules):
        r = table[rid]
        pts = r["points"] * mult
        if "cap" in r:
            pts = min(pts, r["cap"])
        fired.append((r["why"], pts))

    kinds = [e["kind"] for e in site["emails"]]
    if given_email:
        add("given_email")
    if "personal" in kinds:
        add("personal_email")
    elif "generic" in kinds or "freemail" in kinds:
        add("generic_email")
    if site["people"]:
        add("decision_maker")
    if site["contact_form"]:
        add("contact_form")
    if site["phones"]:
        add("phone")
    if site["booking"]:
        add("booking")
    if site["active"] == "yes":
        add("active_site")
    if site["socials"].get("linkedin"):
        add("linkedin")
    if site["socials"].get("instagram") or site["socials"].get("facebook"):
        add("social")
    if site["icp_hits"]:
        add("icp_hit", len(site["icp_hits"]))
    if site["active"] == "no" and site["copyright"] and site["copyright"] <= dt.date.today().year - 2:
        add("stale_site", table=pen)
    if site["status"] == "ok" and not (given_email or site["emails"] or site["contact_form"] or site["phones"]):
        add("no_route", table=pen)
    total = max(0, min(RULES["max"], sum(p for _w, p in fired)))
    if site["status"] != "ok":
        total = 15 if given_email else 0
    why = "; ".join(f"{w} ({p:+d})" for w, p in fired if p) or (site["status"] or "nothing found")
    return int(total), why


# ------------------------------------------------------------------ one row, one file

ADDED = ["found_email", "email_kind", "email_source", "other_emails", "email_guesses", "best_email", "best_email_source", "email_check", "phone_found", "decision_maker", "decision_maker_title",
         "decision_maker_source", "contact_form_url", "contact_page_url", "booking_tool", "linkedin_found", "instagram_found", "facebook_found", "x_found", "youtube_found",
         "tech_stack", "site_description", "site_active", "mx_ok", "icp_hits", "enrich_status", "steps", "lead_score", "lead_why", "enriched_on", "enrichment_audit", "field_results", "waterfall_metrics", "firmographics", "field_waterfall_metrics"]


def email_belongs(email: str, site_domain: str) -> bool:
    """True when an email is on the business's own domain, or a free mailbox (gmail, outlook: many small businesses use one). An address on another company's domain is
    usually the web or SEO agency that built the listing (seo@agency.co.uk on a tree surgeon's site)."""
    dom = (email or "").lower().rpartition("@")[2]
    site = (site_domain or "").lower().removeprefix("www.")
    if not dom or not site:
        return True
    return dom in FREEMAIL or dom.endswith(site) or site.endswith(dom)


def field_audit(site: dict, row_email: str, best_email: str, best_email_source: str) -> str:
    """Compact, machine-readable field provenance. It records evidence and decisions, never guessed certainty."""
    steps = [s for s in site.get("steps", "").split(">") if s]
    pages = site.get("pages") or []
    home = pages[0] if pages else ""
    def entry(value, source="", confidence="unverified", rejected=None):
        return {"status": "selected" if value else "not_found", "source": source if value else "", "evidence_url": source if source.startswith("http") else "",
                "confidence": confidence if value else "none", "rejected_input": rejected or ""}
    dm = site["people"][0] if site.get("people") else None
    email_rejected = "" if not row_email or best_email_source == "your file" else "input email belongs to a different domain"
    chosen_email = best_email or ""
    email_candidates = []
    if row_email:
        email_candidates.append({"rung": "input", "source": "your file", "selected": best_email_source == "your file", "outcome": "accepted" if best_email_source == "your file" else "rejected_domain_mismatch"})
    for e in site.get("emails", []):
        email_candidates.append({"rung": "provider" if not e.get("source", "").startswith("http") else ("inner" if e.get("source") != home else "home"),
                                 "source": e.get("source", ""), "selected": bool(chosen_email and e.get("email") == chosen_email), "outcome": "found"})
    if site.get("guesses"):
        email_candidates.append({"rung": "guess", "source": "pattern inference", "selected": False, "outcome": "unverified_guess_only"})
    audit = {
        "schema": "dbi.enrichment-field-audit.v1",
        "rungs_run": steps,
        "fields": {
            "best_email": {**entry(chosen_email, best_email_source, "unverified", email_rejected), "candidates": email_candidates},
            "phone": entry((site.get("phones") or [""])[0], (site.get("field_sources") or {}).get("phone", "")),
            "decision_maker": entry(dm.get("name", "") if dm else "", dm.get("source", "") if dm else "", "unverified"),
            "contact_form": entry(site.get("contact_form", ""), (site.get("field_sources") or {}).get("contact_form", "")),
            "booking": entry(site.get("booking", ""), (site.get("field_sources") or {}).get("booking", "")),
            "social_profiles": entry(bool(site.get("socials")), (site.get("field_sources") or {}).get("social_profiles", "")),
            "technology": entry(bool(site.get("tech")), (site.get("field_sources") or {}).get("technology", "")),
            "site_description": entry(site.get("description", ""), (site.get("field_sources") or {}).get("site_description", "")),
        },
        "provider_usage": {"api_calls": (site.get("provider_usage") or {}).get("api_calls", 0), "cache_hits": (site.get("provider_usage") or {}).get("cache_hits", 0),
                           "currency_cost": None, "cost_note": "Provider monetary pricing is not declared by the provider config; lookup counts only."}
    }
    return json.dumps(audit, ensure_ascii=False, separators=(",", ":"))


def _waterfall_cost(metrics: dict | None) -> dict | None:
    """Summarize actual configured provider attempts using declared local per-call prices."""
    if not isinstance(metrics, dict) or metrics.get("dry_run"):
        return None
    by_provider, currencies, unknown = {}, set(), []
    for rung in metrics.get("providers", []):
        if not isinstance(rung, dict):
            continue
        calls = max(0, int(rung.get("api_calls", 0) or 0))
        if not calls:
            continue
        name, raw = str(rung.get("rung", "unknown")), rung.get("cost_per_call")
        currency = str(rung.get("cost_currency", "")).upper()
        item = {"calls": calls, "cost_per_call": raw, "currency": currency or None}
        if raw is None or not currency:
            item["estimated_cost"] = None
            unknown.append(name)
        else:
            try:
                price = float(raw)
            except (TypeError, ValueError):
                price = float("nan")
            if not math.isfinite(price) or price < 0:
                item["estimated_cost"] = None
                unknown.append(name)
            else:
                item["estimated_cost"] = round(calls * price, 8)
                currencies.add(currency)
        by_provider[name] = item
    if not by_provider:
        return None
    complete = not unknown and len(currencies) == 1
    return {"attempted_calls": sum(item["calls"] for item in by_provider.values()),
            "estimated_cost": round(sum(item["estimated_cost"] for item in by_provider.values()), 8) if complete else None,
            "currency": next(iter(currencies)) if complete else None, "cost_estimated": complete,
            "unknown_price_providers": sorted(set(unknown)), "providers": by_provider,
            "basis": "configured cost_per_call; estimate, not vendor invoice"}


def shared_field_results(site: dict, row_email: str, best_email: str, best_email_source: str, today: dt.date) -> str:
    """Emit the shared contract while retaining enrichment_audit for older consumers."""
    observed = dt.datetime.combine(today, dt.time.min, tzinfo=dt.timezone.utc).isoformat().replace("+00:00", "Z")
    fields = []
    provider_usage = site.get("provider_usage") or {}
    calls = int(provider_usage.get("api_calls", 0) or 0)
    cache_hits = int(provider_usage.get("cache_hits", 0) or 0)
    provider_name = provider_usage.get("provider", "")
    waterfall_costs = {"email": _waterfall_cost(site.get("waterfall_metrics"))}
    waterfall_costs.update({name: _waterfall_cost(metrics) for name, metrics in
                            (site.get("field_waterfall_metrics") or {}).items()})

    def add(field: str, value, url: str = "", source_type: str = "company_website", source_name: str = "Company website",
            subject: str = "company", strength: str = "strong", verification: str = "not_checked", miss: str = ""):
        if url.startswith("provider:"):
            source_type, source_name, url = "configured_provider", url.removeprefix("provider:"), ""
        fields.append(fr.make_result(field=field, value=value if value not in ("", None, [], {}) else None,
                                     status="accepted" if value not in ("", None, [], {}) else "not_found",
                                     source_type=source_type if value not in ("", None, [], {}) else "",
                                     source_name=source_name if value not in ("", None, [], {}) else "", source_url=url if value else "",
                                     observed_at=observed if value else "", freshness_status="unknown" if value else "unknown",
                                     identity_subject=subject if value else "unknown", identity_match="retrieved from supplied company domain" if value else "",
                                     identity_strength=strength if value else "unknown", identity_score=1.0 if value and strength == "strong" else None,
                                     identity_score_kind="source-domain match cue; not a probability" if value else "",
                                     verification_status=verification if value else "not_applicable",
                                     verification_method="mailbox deliverability was not checked" if field == "best_email" and value else "",
                                     cost_amount=None if field == "best_email" and source_type == "configured_provider" else 0.0,
                                     cost_currency=None if field == "best_email" and source_type == "configured_provider" else "USD",
                                     cost_units="provider_api_calls" if field == "best_email" and source_type == "configured_provider" else "external_provider_fee",
                                     cost_quantity=float(calls) if field == "best_email" and source_type == "configured_provider" else None,
                                     cost_estimated=False,
                                     miss_reason=(miss or "No value found in the inspected company pages.") if not value else ""))

    email_source = best_email_source or ""
    if best_email_source == "your file":
        email_type, email_name = "input_csv", "Input CSV"
    elif best_email_source and best_email_source.startswith("http"):
        email_type, email_name = "company_website", "Company website"
    elif best_email_source:
        email_type, email_name = "configured_provider", best_email_source.split(" (your own API key", 1)[0]
    else:
        email_type, email_name = "", ""
    email_cost = waterfall_costs.get("email") if email_type == "configured_provider" else None
    email_candidates = [fr.source_ref(source_type="input_csv", source_name="Input CSV", status="accepted" if best_email_source == "your file" else "rejected",
                                       value=row_email)] if row_email else []
    email_candidates.extend(fr.source_ref(source_type="company_website" if str(e.get("source", "")).startswith("http") else "configured_provider",
                                          source_name=str(e.get("source", "")).split(" (your own API key", 1)[0] if not str(e.get("source", "")).startswith("http") else "Company website",
                                          source_url=e.get("source", "") if str(e.get("source", "")).startswith("http") else "",
                                          status="accepted" if e.get("email") == best_email and best_email_source != "your file" else "candidate", value=e.get("email"))
                            for e in site.get("emails", []))
    if site.get("guesses"):
        email_candidates.extend(fr.source_ref(source_type="pattern_guess", source_name="Email pattern inference", status="candidate", value=g) for g in site["guesses"])
    email_candidates.extend(fr.source_ref(source_type="configured_provider", source_name=c.get("waterfall_provider", ""),
                                          status="rejected", value={"email": c.get("email", ""), "reason": c.get("waterfall_reason", "")})
                            for c in site.get("waterfall_candidates", []) if c.get("waterfall_status") == "rejected")
    fields.append(fr.make_result(field="best_email", value=best_email or None, status="accepted" if best_email else "not_found",
                                 source_type=email_type, source_name=email_name, source_url=email_source if email_type == "company_website" else "",
                                 observed_at=observed if best_email else "", identity_subject="company" if best_email else "unknown",
                                 identity_match="input accepted by domain policy" if best_email_source == "your file" else "domain-scoped provider/site result" if best_email else "",
                                 identity_strength="moderate" if best_email else "unknown", verification_status="not_checked" if best_email else "not_found",
                                 verification_method="MX presence is checked separately; mailbox delivery is not verified" if best_email else "",
                                 cost_amount=email_cost.get("estimated_cost") if email_cost else None,
                                 cost_currency=email_cost.get("currency") if email_cost else None,
                                 cost_units="provider_api_attempts" if email_cost else "",
                                 cost_quantity=float(email_cost["attempted_calls"]) if email_cost else None,
                                 cost_estimated=email_cost.get("cost_estimated") if email_cost else None,
                                 miss_reason="No accepted email; guesses, if any, remain candidates only." if not best_email else "",
                                 candidates=email_candidates, metadata={"email_source_label": best_email_source, "provider_cache_hits": cache_hits,
                                                                      "waterfall_metrics": site.get("waterfall_metrics", {}),
                                                                      "provider_waterfall_cost": waterfall_costs.get("email")}))
    add("phone", (site.get("phones") or [None])[0], (site.get("field_sources") or {}).get("phone", ""))
    person = (site.get("people") or [None])[0]
    add("decision_maker", {"name": person.get("name"), "title": person.get("title", "")} if person else None,
        person.get("source", "") if person else "", strength="moderate", verification="not_checked",
        miss="No named person found on the inspected pages." if not person else "")
    add("decision_maker_title", person.get("title") if person else None, person.get("source", "") if person else "",
        strength="moderate", verification="not_checked", miss="No decision-maker title was found on the inspected pages." if not person or not person.get("title") else "")
    add("contact_form", site.get("contact_form"), (site.get("field_sources") or {}).get("contact_form", ""))
    add("booking", site.get("booking"), (site.get("field_sources") or {}).get("booking", ""))
    for platform in ("linkedin", "instagram", "facebook", "x", "youtube"):
        add(f"{platform}_profile", (site.get("socials") or {}).get(platform), (site.get("field_sources") or {}).get(f"social_profile:{platform}", ""), strength="moderate")
    add("technology", site.get("tech") or None, (site.get("field_sources") or {}).get("technology", ""), strength="moderate")
    add("site_description", site.get("description"), (site.get("field_sources") or {}).get("site_description", ""), strength="moderate")
    add("icp_term_hits", site.get("icp_hits") or None, "", source_type="heuristic_text_match", source_name="Inspected website text", strength="moderate")
    add("site_active", site.get("active"), "", source_type="copyright_year_heuristic", source_name="Inspected website text", strength="moderate",
        verification="heuristic_not_verified", miss="The inspected site did not provide a usable copyright year." if not site.get("active") else "")
    for waterfall_field, result_field in (("phone", "phone"), ("person_identity", "decision_maker"), ("firmographics", "firmographics")):
        metrics = (site.get("field_waterfall_metrics") or {}).get(waterfall_field)
        candidates = (site.get("field_waterfall_candidates") or {}).get(waterfall_field, [])
        if metrics:
            target = next((item for item in fields if item.get("field") == result_field), None)
            if target:
                target.setdefault("metadata", {})["provider_waterfall"] = metrics
                cost_detail = waterfall_costs.get(waterfall_field)
                if cost_detail:
                    target["metadata"]["provider_waterfall_cost"] = cost_detail
                    if target.get("source", {}).get("type") == "configured_provider":
                        target["cost"].update({"amount": cost_detail["estimated_cost"], "currency": cost_detail["currency"],
                                               "units": "provider_api_attempts", "quantity": float(cost_detail["attempted_calls"]),
                                               "estimated": cost_detail["cost_estimated"]})
                target["candidates"].extend(fr.source_ref(source_type="configured_provider", source_name=c.get("waterfall_provider", ""),
                    source_url=c.get("source_url", ""), status=c.get("waterfall_status", "candidate"),
                    value={"value": c.get("value"), "reason": c.get("waterfall_reason", "")}) for c in candidates)
            if waterfall_field == "firmographics":
                selected = next((c for c in candidates if c.get("waterfall_status") == "accepted"), None)
                cost_detail = waterfall_costs.get("firmographics")
                fields.append(fr.make_result(field="firmographics", value=site.get("firmographics") or None,
                    status="accepted" if site.get("firmographics") else "not_found",
                    source_type="configured_provider" if selected else "", source_name=selected.get("waterfall_provider", "") if selected else "",
                    source_url=selected.get("source_url", "") if selected else "", observed_at=observed if site.get("firmographics") else "",
                    identity_subject="company" if site.get("firmographics") else "unknown", identity_match="provider company identity policy" if site.get("firmographics") else "",
                    identity_strength="moderate" if site.get("firmographics") else "unknown", verification_status="provider_returned_unverified" if site.get("firmographics") else "not_found",
                    miss_reason="No configured provider returned identity-matched firmographic values." if not site.get("firmographics") else "",
                    cost_amount=cost_detail.get("estimated_cost") if selected and cost_detail else None,
                    cost_currency=cost_detail.get("currency") if selected and cost_detail else None,
                    cost_units="provider_api_attempts" if selected and cost_detail else "",
                    cost_quantity=float(cost_detail["attempted_calls"]) if selected and cost_detail else None,
                    cost_estimated=cost_detail.get("cost_estimated") if selected and cost_detail else None,
                    candidates=[fr.source_ref(source_type="configured_provider", source_name=c.get("waterfall_provider", ""), source_url=c.get("source_url", ""),
                        status=c.get("waterfall_status", "candidate"), value={"value": c.get("value"), "reason": c.get("waterfall_reason", "")}) for c in candidates],
                    metadata={"provider_waterfall": metrics, "provider_waterfall_cost": cost_detail}))
    if calls or cache_hits:
        fields.append(fr.make_result(field="provider_lookup", value={"provider": provider_name, "api_calls": calls, "cache_hits": cache_hits},
                                     status="candidate" if calls or cache_hits else "not_found", source_type="configured_provider", source_name=provider_name,
                                     observed_at=observed, verification_status="not_applicable", cost_units="provider_api_calls", cost_quantity=float(calls),
                                     cost_estimated=False, miss_reason=site.get("provider_note", ""),
                                     metadata={"pricing_note": "Provider calls are counted here; configured per-field cost estimates are attached to their field results when available."}))
    for result in fields:
        result.setdefault("metadata", {}).update({"lane": "website_enrichment",
            "provider_cost_shared_from_duplicate_domain": bool(site.get("provider_cost_shared_from_duplicate_domain"))})
    return fr.dump_results(fields)


def row_columns(site: dict, row_email: str, row_name: str, today: dt.date) -> dict:
    top = site["emails"][0] if site["emails"] else None
    dm = site["people"][0] if site["people"] else None
    trusted = bool(row_email) and email_belongs(row_email, site.get("domain", ""))
    note = ""
    if row_email and not trusted:
        note = f"{row_email} is on another domain than the website: probably an agency's address"
        if top:
            note += f"; using the address found on the site instead ({top['email']})"
    if row_email and (trusted or not top):
        best, best_src = row_email, "your file"
    else:
        best, best_src = (top["email"], top["source"]) if top else ("", "")
    sc, why = score(site, row_email if trusted else "")
    return {"found_email": top["email"] if top else "", "email_kind": top["kind"] if top else "", "email_source": top["source"] if top else "",
            "other_emails": "; ".join(e["email"] for e in site["emails"][1:4]), "email_guesses": "; ".join(site["guesses"]) + (" (guesses: verify before sending)" if site["guesses"] else ""),
            "best_email": best, "best_email_source": best_src, "email_check": note, "phone_found": site["phones"][0] if site["phones"] else "",
            "decision_maker": dm["name"] if dm else "", "decision_maker_title": dm["title"] if dm else "", "decision_maker_source": dm["source"] if dm else "",
            "contact_form_url": site["contact_form"], "contact_page_url": site["contact_page"], "booking_tool": site["booking"],
            "linkedin_found": site["socials"].get("linkedin", ""), "instagram_found": site["socials"].get("instagram", ""), "facebook_found": site["socials"].get("facebook", ""),
            "x_found": site["socials"].get("x", ""), "youtube_found": site["socials"].get("youtube", ""), "tech_stack": ", ".join(site["tech"]),
            "site_description": site["description"], "site_active": site["active"], "mx_ok": site["mx"], "icp_hits": ", ".join(site["icp_hits"]),
            "enrich_status": site["status"], "steps": site["steps"], "lead_score": sc, "lead_why": why, "enriched_on": today.isoformat(),
            "enrichment_audit": field_audit(site, row_email, best, best_src),
            "field_results": shared_field_results(site, row_email, best, best_src, today),
            "waterfall_metrics": json.dumps(site.get("waterfall_metrics", {}), ensure_ascii=False, separators=(",", ":")),
            "firmographics": json.dumps(site.get("firmographics", {}), ensure_ascii=False, separators=(",", ":")),
            "field_waterfall_metrics": json.dumps(site.get("field_waterfall_metrics", {}), ensure_ascii=False, separators=(",", ":"))}


def find_columns(headers: list[str]) -> dict[str, str]:
    return importer.map_headers(headers)


def _provider_spend(email_providers: list[dict], email_calls: int, field_configs: dict, leads: int,
                    maximum: float | None, allow_unknown: bool, dry_run: bool) -> tuple[dict, ep.SpendApproval | None]:
    projection = wf.spend_projection(email_providers, email_calls, field_configs, leads)
    if dry_run or not projection["possible_calls"]:
        return projection, None
    if projection["has_unknown_cost"] and not allow_unknown:
        names = ", ".join(projection["unknown_providers"])
        raise ValueError(f"Configured provider price is unknown for {names}. Review that provider's pricing and pass --allow-unknown-provider-cost to acknowledge charges outside the numeric estimate.")
    if maximum is None:
        currency = projection["currency"] or "known-price currency"
        raise ValueError(f"Configured providers may run. Review the estimate ({projection['estimate']:.4f} {currency} for up to {projection['possible_calls']} calls) and approve it with --max-provider-spend.")
    if maximum is not None and maximum < projection["estimate"] - 1e-9:
        raise ValueError(f"Configured-provider estimate is {projection['estimate']:.4f} {projection['currency']}, above the approved maximum of {maximum:.4f} {projection['currency']}. Lower provider-call caps or raise the approved maximum.")
    approval = ep.SpendApproval(maximum, projection["currency"], allow_unknown)
    return projection, approval


def provider_spend_preview(waterfall_config_path: str, lead_count: int, provider: str = "",
                           budget_override: int | None = None) -> str:
    """Read-only price/call-cap estimate; opens no lead list and makes no network requests."""
    if not 1 <= lead_count <= 2000:
        raise ValueError("Preview between 1 and 2000 leads.")
    if budget_override is not None and not 0 <= budget_override <= 5000:
        raise ValueError("Provider-call override must be between 0 and 5000.")
    config = wf.load_config(waterfall_config_path, provider, budget_override)
    providers = wf.provider_configs(config, dry_run=True) if config["providers"] else []
    fields = wf.load_field_waterfalls(waterfall_config_path, budget_override, dry_run=True)
    projection = wf.spend_projection(providers, config["max_provider_calls"], fields, lead_count)
    by_field = {}
    if providers:
        by_field["email"] = min(config["max_provider_calls"], lead_count * len(providers))
    for field_name, field_config in fields.items():
        rung_providers = field_config.get("provider_configs", [])
        by_field[field_name] = min(field_config["max_provider_calls"], lead_count * len(rung_providers))
    result = {"type": "configured_provider_spend_preview", "lead_count": lead_count,
              "maximum_possible_provider_calls": projection["possible_calls"],
              "maximum_estimated_spend": round(projection["estimate"], 8),
              "currency": projection["currency"] or None,
              "calls_by_field": by_field,
              "unknown_price_providers": projection["unknown_providers"],
              "unknown_price_acknowledgment_required": projection["has_unknown_cost"],
              "numeric_spend_approval_required": bool(projection["possible_calls"]),
              "pricing_basis": "local configured cost_per_call; conservative maximum assumes the most expensive configured rung for every possible attempt",
              "invoice": False, "network_requests": 0, "lead_data_read": False, "files_written": 0}
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def enrich_rows(rows: list[dict], headers: list[str], icp_terms: list[str], render: bool, max_rows: int, today: dt.date | None = None, pause: float = PAGE_PAUSE,
                provider: dict | None = None, budget: "ep.Budget | None" = None, providers: list[dict] | None = None,
                waterfall_config: dict | None = None, dry_run: bool = False, field_waterfalls: dict | None = None) -> tuple[list[dict], dict]:
    today = today or dt.date.today()
    m = find_columns(headers)
    if "website" not in m:
        raise ValueError("I could not find a website or domain column. Name a column website, domain or url (Clay, Apollo and HubSpot exports already do).")
    out, stats = [], {"rows": 0, "skipped": 0, "ok": 0, "email": 0, "personal": 0, "decision_maker": 0, "form": 0, "phone": 0, "guess": 0,
                      "failed": {}, "steps": {}, "provider_notes": [], "waterfall": {}, "provider_eligible": 0, "dry_run": dry_run, "field_waterfalls": {}}
    seen_domains: dict[str, dict] = {}
    for i, r in enumerate(rows):
        if stats["rows"] >= max_rows:
            stats["skipped"] += 1
            out.append(dict(r))
            continue
        stats["rows"] += 1
        raw_site = (r.get(m["website"]) or "").strip()
        dom = importer.clean_domain(raw_site)
        row_email = (r.get(m.get("email", ""), "") or "").strip().lower()
        row_name = (r.get(m.get("contact_name", ""), "") or "").strip()
        if dom in seen_domains:
            site = copy.deepcopy(seen_domains[dom])
            site["provider_cost_shared_from_duplicate_domain"] = True
            usage = site.get("provider_usage") or {}
            usage.update({"api_calls": 0, "cache_hits": 0, "reused_from_same_run": True})
            for metrics in [site.get("waterfall_metrics", {}), *(site.get("field_waterfall_metrics") or {}).values()]:
                if not isinstance(metrics, dict):
                    continue
                for rung in metrics.get("providers", []):
                    rung["api_calls"] = 0
                    rung["cache_hits"] = 0
                    rung["status"] = "reused_same_run"
            site["provider_usage"] = usage
        else:
            log(f"[{stats['rows']}/{min(len(rows), max_rows)}] {dom or '(no website)'}")
            try:
                site = enrich_site(dom, icp_terms, render, row_email, row_name, today, pause, provider, budget,
                                   (r.get(m.get("business", ""), "") or "").strip(), providers, waterfall_config, dry_run, field_waterfalls)
            except Exception as e:      # one bad site must never stop the list
                site = blank(dom)
                site["status"] = f"error: {type(e).__name__}"
            seen_domains[dom] = site
            for field_cfg in (field_waterfalls or {}).values():
                field_budget = field_cfg.get("budget")
                for warning in getattr(field_budget, "accounting_warnings", []):
                    if warning not in stats["provider_notes"]:
                        stats["provider_notes"].append(warning)
            stats["provider_eligible"] += bool(site.get("provider_eligible"))
            for rung in (site.get("waterfall_metrics") or {}).get("providers", []):
                name = rung.get("rung", "")
                total = stats["waterfall"].setdefault(name, {k: 0 for k in ("attempted", "api_calls", "cache_hits", "returned", "accepted", "rejected", "failures", "projected")})
                for key in total:
                    total[key] += int(rung.get(key, 0) or 0)
            for field_name, metrics in site.get("field_waterfall_metrics", {}).items():
                total = stats["field_waterfalls"].setdefault(field_name, {})
                for key in ("attempted", "api_calls", "cache_hits", "returned", "accepted", "rejected", "failures", "projected"):
                    total[key] = total.get(key, 0) + sum(int(rung.get(key, 0) or 0) for rung in metrics.get("providers", []))
            if dom:
                time.sleep(pause)
        if site.get("provider_note") and site["provider_note"] not in stats["provider_notes"]:
            stats["provider_notes"].append(site["provider_note"])
        cols = row_columns(site, row_email, row_name, today)
        cols["field_results"] = fr.merge_results(r.get("field_results"), cols["field_results"])
        out.append({**r, **cols})
        if site["status"] == "ok":
            stats["ok"] += 1
        else:
            stats["failed"][site["status"] or "unknown"] = stats["failed"].get(site["status"] or "unknown", 0) + 1
        stats["email"] += bool(cols["best_email"])
        stats["personal"] += cols["email_kind"] == "personal" or (bool(row_email) and email_kind(row_email) == "personal")
        stats["decision_maker"] += bool(cols["decision_maker"])
        stats["form"] += bool(cols["contact_form_url"])
        stats["phone"] += bool(cols["phone_found"])
        stats["guess"] += bool(site["guesses"])
        for s in site["steps"].split(">"):
            if s:
                stats["steps"][s] = stats["steps"].get(s, 0) + 1
    return out, stats


def summary(stats: dict, rows: list[dict], name: str, budget: "ep.Budget | None" = None, provider_name: str = "",
            dry_run: bool = False, provider_configs: list[dict] | None = None) -> str:
    n = stats["rows"]
    pc = lambda a: f"{a} ({100 * a // n}%)" if n else "0"  # noqa: E731
    top = sorted((r for r in rows if r.get("lead_score") not in (None, "")), key=lambda r: -int(r["lead_score"]))[:10]
    lines = [f"# Enrichment: {name}", "",
             f"- Leads looked at: {n}" + (f" ({stats['skipped']} more left for another run: raise --max)" if stats["skipped"] else ""),
             f"- Websites read: {pc(stats['ok'])}",
             f"- With an email: {pc(stats['email'])}, of which a personal address: {pc(stats['personal'])}",
             f"- With a named owner or senior person: {pc(stats['decision_maker'])}",
             f"- With a contact form: {pc(stats['form'])}; with a phone number: {pc(stats['phone'])}",
             f"- Likely-address guesses (marked, never put in the email column): {stats['guess']}"]
    if dry_run:
        lines.append("- Dry run only: no optional provider requests were made.")
        if budget is not None:
            lines.append(f"- Email waterfall projection: {stats['provider_eligible']} leads reached the provider-eligible stage; maximum projected calls {budget.projected} of a cap of {budget.limit}.")
    elif provider_name and budget is not None:
        lines.append(f"- Optional provider API calls: {budget.used} used of a cap of {budget.limit}; {budget.cached} cache hits (free); provider(s): {provider_name}" + (f"; stopped early: {budget.stopped}" if budget.stopped else ""))
    elif stats.get("field_waterfalls"):
        lines.append("- Configured field-provider calls are itemized below; monetary price is unknown unless a provider configuration declares it.")
    else:
        lines.append("- Cost: nothing. Only the free steps ran (no provider named).")
    if stats.get("waterfall"):
        lines += ["", "## Email waterfall rung results"]
        configs = {p.get("name"): p for p in (provider_configs or [])}
        for rung, counts in stats["waterfall"].items():
            details = (f"{counts['attempted']} attempted; {counts['api_calls']} API calls; {counts['cache_hits']} cache hits; "
                       f"{counts['returned']} candidates; {counts['accepted']} accepted; {counts['rejected']} rejected; {counts['failures']} errors")
            if dry_run:
                details += f"; {counts['projected']} maximum projected calls"
            cfg = configs.get(rung, {})
            if cfg.get("cost_per_call") is not None and cfg.get("cost_currency"):
                used = counts["projected"] if dry_run else counts["api_calls"]
                details += f"; configured call-price estimate {used * float(cfg['cost_per_call']):.4f} {cfg['cost_currency']}"
            else:
                details += "; monetary price unknown"
            lines.append(f"- {rung}: {details}")
    if stats.get("field_waterfalls"):
        lines += ["", "## Phone, person and firmographic waterfall results"]
        for field_name, counts in stats["field_waterfalls"].items():
            details = (f"{counts.get('attempted', 0)} rung attempts; {counts.get('api_calls', 0)} API calls; "
                         f"{counts.get('cache_hits', 0)} cache hits; {counts.get('returned', 0)} candidates; "
                         f"{counts.get('accepted', 0)} accepted; {counts.get('rejected', 0)} rejected; {counts.get('failures', 0)} errors; "
                         f"{counts.get('projected', 0)} projected calls")
            lines.append(f"- {field_name}: {details}.")
    for n_ in stats.get("provider_notes", []):
        lines.append(f"- Note: {n_}")
    for warning in getattr(budget, "accounting_warnings", []) if budget is not None else []:
        lines.append(f"- Usage-record warning: {warning}")
    if stats["steps"]:
        lines.append("- Waterfall: " + ", ".join(f"{k} {v}" for k, v in stats["steps"].items()) + " (leads that used each step)")
    if stats["failed"]:
        lines += ["", "## Could not read", *[f"- {k}: {v}" for k, v in sorted(stats["failed"].items(), key=lambda kv: -kv[1])]]
    if top:
        lines += ["", "## Best leads first"]
        for r in top:
            who = r.get("business") or r.get("Company") or r.get("company") or r.get("domain") or ""
            lines.append(f"- {int(r['lead_score'])}: {who or '(no name)'} {r.get('best_email', '')} | {r.get('decision_maker', '') or 'no named owner'} | {r.get('lead_why', '')}")
    lines += ["", "Every email and name has its source page in the file. Check a few before you send. Use a real sender name, say why you are writing, and make it easy to say no."]
    return "\n".join(lines) + "\n"


def import_ready(rows: list[dict], headers: list[str]) -> list[dict]:
    """The same leads in the columns the Go-to-Market import already understands, with the best email filled in."""
    m = find_columns(headers)
    out = []
    for r in rows:
        ready_row = {"Company": r.get(m.get("business", ""), "") or "", "Website": r.get(m["website"], ""), "Full Name": r.get("decision_maker") or r.get(m.get("contact_name", ""), "") or "",
                    "Title": r.get("decision_maker_title") or r.get(m.get("contact_title", ""), "") or "", "Email": r.get("best_email", ""), "Phone": r.get("phone_found") or r.get(m.get("phone", ""), "") or "",
                    "City": r.get(m.get("city", ""), "") or "", "LinkedIn URL": r.get("linkedin_found") or r.get(m.get("linkedin", ""), "") or "", "Industry": r.get(m.get("industry", ""), "") or "",
                    "Employees": r.get(m.get("employees", ""), "") or "", "lead_score": r.get("lead_score", ""), "lead_why": r.get("lead_why", "")}
        if r.get("waterfall_experiment_id"):
            for field in ("waterfall_experiment_id", "waterfall_experiment_variant", "waterfall_experiment_field",
                          "waterfall_experiment_providers", "waterfall_experiment_lead_id", "waterfall_config_sha256"):
                ready_row[field] = r.get(field, "")
        out.append(ready_row)
    return out


def enrich_file(src: str, icp: str = "", engine: str = "", max_rows: int = 100, render: bool = True, today: dt.date | None = None, pause: float = PAGE_PAUSE,
                provider: str = "", budget: int | None = None, waterfall_config_path: str = "", dry_run: bool = False,
                max_provider_spend: float | None = None, allow_unknown_provider_cost: bool = False) -> str:
    p = Path(src)
    if not p.is_absolute():
        p = (ROOT / src) if (ROOT / src).exists() else p
    if not p.is_file():
        raise ValueError(f"I could not find the file: {src}")
    headers, rows = importer.read_rows(p)
    if not rows:
        raise ValueError("That file has no rows.")
    if not 1 <= max_rows <= 2000:
        raise ValueError("--max is between 1 and 2000.")
    terms = [t.strip() for t in (icp or "").split(",") if t.strip()][:8]
    if budget is not None and not 0 <= budget <= 5000:
        raise ValueError("--budget is between 0 and 5000 paid lookups.")
    config = wf.load_config(waterfall_config_path, provider, budget)
    field_configs = wf.load_field_waterfalls(waterfall_config_path, budget, dry_run)
    provs, bud = [], None
    if config["providers"]:
        provs = wf.provider_configs(config, dry_run)
        bud = ep.Budget(config["max_provider_calls"])
    elif dry_run and not any(item.get("provider_configs") for item in field_configs.values()):
        raise ValueError("A dry run needs an ordered provider config or --provider.")
    if max_provider_spend is not None and (not math.isfinite(max_provider_spend) or not 0 <= max_provider_spend <= 10000000):
        raise ValueError("--max-provider-spend must be between 0 and 10000000.")
    experiment = config.get("waterfall_experiment") if isinstance(config.get("waterfall_experiment"), dict) else None
    experiment_context = None
    if experiment:
        experiment_id = str(experiment.get("id") or "").strip()
        variant = str(experiment.get("variant") or "").strip().upper()
        experiment_field = str(experiment.get("field") or "").strip()
        experiment_providers = experiment.get("providers")
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", experiment_id)
                or variant not in {"A", "B"}
                or experiment_field not in {"email", *wf.FIELD_TYPES}
                or not isinstance(experiment_providers, list) or len(experiment_providers) != 2
                or any(not isinstance(name, str) or not name.strip() for name in experiment_providers)):
            raise ValueError("This waterfall experiment config has incomplete or invalid identity metadata. Rebuild the A/B configs before running it.")
        if engine:
            raise ValueError("Keep experiment variant runs outside the Engine. Run both variants on the same source list, then assign the paired results to one variant per lead before importing into an Engine.")
        config_path = Path(waterfall_config_path)
        if not config_path.is_absolute():
            config_path = ROOT / config_path
        config_digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
        sample_rows = rows[:max_rows]
        lead_ids = [str(row.get("waterfall_experiment_lead_id") or row.get("source_row")
                         or row.get("lead_id") or row.get("id") or f"input-row:{row_number}").strip()
                    for row_number, row in enumerate(sample_rows, 2)]
        if len(set(lead_ids)) != len(lead_ids):
            raise ValueError("The bounded experiment sample contains duplicate stable lead IDs. Deduplicate the source list before spending on either variant.")
        source_digest = hashlib.sha256(p.read_bytes()).hexdigest()
        cohort_digest = hashlib.sha256(json.dumps(lead_ids, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        experiment_context = {"id": experiment_id, "variant": variant, "field": experiment_field,
                              "providers": [name.strip() for name in experiment_providers],
                              "config_sha256": config_digest, "source_sha256": source_digest,
                              "cohort_sha256": cohort_digest, "sample_limit": max_rows,
                              "sample_rows": len(sample_rows)}
        sample_manifest_path = LISTS / f"waterfall-experiment-{experiment_id}-cohort.json"
        if sample_manifest_path.exists():
            try:
                sample_manifest = json.loads(sample_manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise ValueError(f"Experiment cohort record {sample_manifest_path.name} cannot be read. Preserve it and inspect it before running either variant again.") from None
            expected = {key: experiment_context[key] for key in
                        ("id", "field", "providers", "source_sha256", "cohort_sha256", "sample_limit", "sample_rows")}
            recorded = {key: sample_manifest.get(key) for key in expected}
            if (sample_manifest.get("schema") != "dbi.waterfall-experiment-cohort.v1" or recorded != expected
                    or not isinstance(sample_manifest.get("variants"), dict)):
                raise ValueError("This experiment already has a different source list or sample cap recorded. Use the exact same CSV and --max for both variants; no provider calls were made.")
            if not dry_run and experiment_context["variant"] in sample_manifest.get("variants", {}):
                raise ValueError(f"Variant {variant} already has an output recorded for this experiment. Preserve that result; use a new experiment config for another run.")
    LISTS.mkdir(exist_ok=True)
    stem = re.sub(r"[^a-z0-9]+", "-", p.stem.lower()).strip("-")[:40] or "list"
    experiment_suffix = (f"-wfexp-{experiment_context['id']}-{experiment_context['variant'].lower()}"
                         f"{'-dry-run' if dry_run else ''}" if experiment_context else "")
    out_csv = LISTS / f"{(today or dt.date.today()).isoformat()}-enriched-{stem}{experiment_suffix}.csv"
    engine_dest = None
    if engine:
        from .engines import load, engine_dir
        load(engine)
        engine_dest = engine_dir(engine) / "imports" / f"enriched-{stem}{experiment_suffix}.csv"
    if experiment_context:
        collisions = [path.name for path in (out_csv, out_csv.with_suffix(".md"), engine_dest) if path and path.exists()]
        if collisions:
            raise ValueError("This experiment output already exists; it was left unchanged and no new enrichment was run: " + ", ".join(collisions))
    projection, approval = _provider_spend(provs, config["max_provider_calls"], field_configs,
        min(len(rows), max_rows), max_provider_spend, allow_unknown_provider_cost, dry_run)
    if bud:
        bud.spend_approval = approval
    for field_config in field_configs.values():
        field_config["spend_approval"] = approval
    out_rows, stats = enrich_rows(rows, headers, terms, render, max_rows, today, pause, None, bud, provs, config, dry_run, field_configs)
    if experiment:
        providers_json = json.dumps(experiment.get("providers", []), ensure_ascii=False, separators=(",", ":"))
        for row_number, row in enumerate(out_rows, 2):
            lead_id = (row.get("waterfall_experiment_lead_id") or row.get("source_row")
                       or row.get("lead_id") or row.get("id") or f"input-row:{row_number}")
            row["waterfall_experiment_lead_id"] = str(lead_id).strip()
            row["waterfall_experiment_id"] = str(experiment.get("id") or "")
            row["waterfall_experiment_variant"] = str(experiment.get("variant") or "")
            row["waterfall_experiment_field"] = str(experiment.get("field") or "")
            row["waterfall_experiment_providers"] = providers_json
            row["waterfall_config_sha256"] = config_digest
        stats["waterfall_experiment"] = experiment
    write_csv(out_csv, out_rows, first=list(headers))
    provider_names = ", ".join(config["providers"])
    text = summary(stats, out_rows, p.name, bud, provider_names, dry_run, provs)
    if experiment:
        text += (f"\nWaterfall experiment: {experiment.get('id', '')} / variant {experiment.get('variant', '')}; "
                 f"field {experiment.get('field', '')}; providers {', '.join(experiment.get('providers', []))}. "
                 f"Run config SHA-256: {experiment_context['config_sha256']}. "
                 f"Sample SHA-256: {experiment_context['cohort_sha256']} across {experiment_context['sample_rows']} rows; "
                 f"reuse the exact source CSV and --max for the other variant.")
    out_csv.with_suffix(".md").write_text(text, encoding="utf-8")
    extra = ""
    if engine:
        engine_dest.parent.mkdir(parents=True, exist_ok=True)
        write_csv(engine_dest, import_ready(out_rows, headers))
        extra = f"\nImport-ready copy for your engine: {engine_dest.relative_to(ROOT).as_posix()} (check it with: python dse.py import {engine})"
    if experiment_context and not dry_run:
        if sample_manifest_path.exists():
            sample_manifest = json.loads(sample_manifest_path.read_text(encoding="utf-8"))
        else:
            sample_manifest = {"schema": "dbi.waterfall-experiment-cohort.v1", "id": experiment_context["id"],
                               "field": experiment_context["field"], "providers": experiment_context["providers"],
                               "source_sha256": experiment_context["source_sha256"],
                               "cohort_sha256": experiment_context["cohort_sha256"],
                               "sample_limit": experiment_context["sample_limit"],
                               "sample_rows": experiment_context["sample_rows"], "variants": {}}
        sample_manifest.setdefault("variants", {})[experiment_context["variant"]] = {
            "config_sha256": experiment_context["config_sha256"],
            "result_csv": out_csv.relative_to(ROOT).as_posix(),
            "result_sha256": hashlib.sha256(out_csv.read_bytes()).hexdigest(),
        }
        temp_manifest = sample_manifest_path.with_suffix(".json.tmp")
        temp_manifest.write_text(json.dumps(sample_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_manifest.replace(sample_manifest_path)
        extra += f"\nMatched experiment sample record: {sample_manifest_path.relative_to(ROOT).as_posix()}"
    if projection["possible_calls"]:
        qualifier = "; includes unknown-priced providers" if projection["has_unknown_cost"] else ""
        text += f"\nConfigured-provider spend estimate: up to {projection['estimate']:.4f} {projection['currency'] or 'known-price currency'} across {projection['possible_calls']} calls{qualifier}. This is an estimate from your local configuration, not a provider invoice."
        if max_provider_spend is not None:
            text += f" Approved ceiling: {max_provider_spend:.4f} {projection['currency'] or 'known-price currency'}."
    return text + f"\nSaved: {out_csv.relative_to(ROOT).as_posix()} (and the summary next to it).{extra}"


def result_json(s: dict, sc: int | None = None) -> str:
    """One line a Ledger workflow can read: RESULT {json}. Plain values only (text, numbers); an empty value means it was not found."""
    em = s["emails"][0] if s["emails"] else {}
    pe = s["people"][0] if s["people"] else {}
    out = {"status": s["status"] or "", "domain": s["domain"] or "", "email": em.get("email", "") or (s["guesses"][0] if s["guesses"] else ""), "email_kind": em.get("kind", "") if em else ("guess" if s["guesses"] else ""),
           "owner": pe.get("name", ""), "owner_title": pe.get("title", ""), "phone": s["phones"][0] if s["phones"] else "", "contact_form": s["contact_form"] or "", "booking": s["booking"] or "",
           "linkedin": (s["socials"] or {}).get("linkedin", "") or "", "score": sc if sc is not None else ""}
    return "RESULT " + json.dumps(out, ensure_ascii=True, separators=(",", ":"))


def card(website: str, icp: str = "", render: bool = True, provider: str = "", budget: int | None = 1,
         result_line: bool = False, waterfall_config_path: str = "", dry_run: bool = False,
         max_provider_spend: float | None = None, allow_unknown_provider_cost: bool = False) -> str:
    config = wf.load_config(waterfall_config_path, provider, budget)
    field_configs = wf.load_field_waterfalls(waterfall_config_path, budget, dry_run)
    provs = wf.provider_configs(config, dry_run) if config["providers"] else []
    bud = ep.Budget(config["max_provider_calls"]) if provs else None
    if dry_run and not provs and not any(item.get("provider_configs") for item in field_configs.values()):
        raise ValueError("A dry run needs an ordered provider config or --provider.")
    projection, approval = _provider_spend(provs, config["max_provider_calls"], field_configs, 1,
        max_provider_spend, allow_unknown_provider_cost, dry_run)
    if bud:
        bud.spend_approval = approval
    for field_config in field_configs.values():
        field_config["spend_approval"] = approval
    s = enrich_site(website, [t.strip() for t in icp.split(",") if t.strip()], render, budget=bud,
                    providers=provs, waterfall_config=config, dry_run=dry_run, field_waterfalls=field_configs)
    sc, why = score(s)
    L = [f"# {s['domain'] or website}: {s['status']}", ""]
    if s["status"] != "ok":
        return "\n".join(L) + "\n"
    L.append(f"Score {sc}/100. {why}")
    L.append(f"Steps run: {s['steps']}")
    if s.get("waterfall_metrics"):
        L.append("Email waterfall: " + json.dumps(s["waterfall_metrics"], ensure_ascii=False, separators=(",", ":")))
    if s.get("field_waterfall_metrics"):
        L.append("Other field waterfalls: " + json.dumps(s["field_waterfall_metrics"], ensure_ascii=False, separators=(",", ":")))
    if bud is not None:
        L.extend(f"Usage-record warning: {warning}" for warning in getattr(bud, "accounting_warnings", []))
    for field_cfg in field_configs.values():
        L.extend(f"Usage-record warning: {warning}" for warning in getattr(field_cfg.get("budget"), "accounting_warnings", []))
    for e in s["emails"]:
        L.append(f"- Email ({e['kind']}): {e['email']}   from {e['source']}")
    if s["guesses"]:
        L.append("- Likely addresses (guesses, verify before sending): " + ", ".join(s["guesses"]))
    for p in s["people"][:3]:
        L.append(f"- Person: {p['name']}, {p['title']}   from {p['source']}")
    if s["phones"]:
        L.append("- Phone: " + ", ".join(s["phones"]))
    if s["contact_form"]:
        L.append("- Contact form: " + s["contact_form"])
    if s["booking"]:
        L.append("- Booking tool: " + s["booking"])
    L += [f"- {k}: {v}" for k, v in s["socials"].items() if v]
    if s["tech"]:
        L.append("- Built with: " + ", ".join(s["tech"]))
    if s["description"]:
        L.append("- Says: " + s["description"])
    return "\n".join(L) + "\n"
