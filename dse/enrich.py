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
import html as htmllib
import json
import re
import socket
import subprocess
import time
import urllib.parse
import urllib.robotparser
from pathlib import Path

from . import enrich_providers as ep
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
            "provider_usage": {"api_calls": 0, "cache_hits": 0}, "field_sources": {}}


def enrich_site(website: str, icp_terms: list[str] | None = None, render: bool = True, given_email: str = "", given_name: str = "", today: dt.date | None = None,
                pause: float = PAGE_PAUSE, provider: dict | None = None, budget: "ep.Budget | None" = None, company: str = "") -> dict:
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
                out["field_sources"].setdefault("social_profiles", pg_url)
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
    if provider and budget is not None and need_more() and not given_email:
        calls_before, cache_before = budget.used, budget.cached
        try:
            found = ep.lookup(provider, out["domain"], company, budget, today)
        except ep.ProviderError as e:
            found = []
            out["provider_note"] = str(e)
        out["provider_usage"] = {"api_calls": budget.used - calls_before, "cache_hits": budget.cached - cache_before}
        if found:
            steps.append("paid")
            have = {x["email"] for x in out["emails"]}
            for f in found:
                src = f"{provider['name']} (your own API key" + (f", confidence {f['confidence']}" if f.get("confidence") not in (None, "") else "") + ")"
                if f["email"] not in have and f["email"].split("@")[1].endswith(out["domain"]):
                    out["emails"].append({"email": f["email"], "kind": f["kind"], "source": src})
                    have.add(f["email"])
                if f["name"] and title_rank(f["title"]) and f["name"] not in [x["name"] for x in out["people"]]:
                    out["people"].append({"name": f["name"], "title": f["title"], "rank": title_rank(f["title"]), "source": src})
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
         "tech_stack", "site_description", "site_active", "mx_ok", "icp_hits", "enrich_status", "steps", "lead_score", "lead_why", "enriched_on", "enrichment_audit"]


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
            "enrichment_audit": field_audit(site, row_email, best, best_src)}


def find_columns(headers: list[str]) -> dict[str, str]:
    return importer.map_headers(headers)


def enrich_rows(rows: list[dict], headers: list[str], icp_terms: list[str], render: bool, max_rows: int, today: dt.date | None = None, pause: float = PAGE_PAUSE,
                provider: dict | None = None, budget: "ep.Budget | None" = None) -> tuple[list[dict], dict]:
    today = today or dt.date.today()
    m = find_columns(headers)
    if "website" not in m:
        raise ValueError("I could not find a website or domain column. Name a column website, domain or url (Clay, Apollo and HubSpot exports already do).")
    out, stats = [], {"rows": 0, "skipped": 0, "ok": 0, "email": 0, "personal": 0, "decision_maker": 0, "form": 0, "phone": 0, "guess": 0, "failed": {}, "steps": {}, "provider_notes": []}
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
            site = seen_domains[dom]
        else:
            log(f"[{stats['rows']}/{min(len(rows), max_rows)}] {dom or '(no website)'}")
            try:
                site = enrich_site(dom, icp_terms, render, row_email, row_name, today, pause, provider, budget, (r.get(m.get("business", ""), "") or "").strip())
            except Exception as e:      # one bad site must never stop the list
                site = blank(dom)
                site["status"] = f"error: {type(e).__name__}"
            seen_domains[dom] = site
            if dom:
                time.sleep(pause)
        if site.get("provider_note") and site["provider_note"] not in stats["provider_notes"]:
            stats["provider_notes"].append(site["provider_note"])
        cols = row_columns(site, row_email, row_name, today)
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


def summary(stats: dict, rows: list[dict], name: str, budget: "ep.Budget | None" = None, provider_name: str = "") -> str:
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
    if provider_name and budget is not None:
        lines.append(f"- Paid lookups with your own {provider_name} key: {budget.used} used of a budget of {budget.limit}; {budget.cached} answered from the free 30-day cache" + (f"; stopped early: {budget.stopped}" if budget.stopped else ""))
    else:
        lines.append("- Cost: nothing. Only the free steps ran (no provider named).")
    for n_ in stats.get("provider_notes", []):
        lines.append(f"- Note: {n_}")
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
        out.append({"Company": r.get(m.get("business", ""), "") or "", "Website": r.get(m["website"], ""), "Full Name": r.get("decision_maker") or r.get(m.get("contact_name", ""), "") or "",
                    "Title": r.get("decision_maker_title") or r.get(m.get("contact_title", ""), "") or "", "Email": r.get("best_email", ""), "Phone": r.get("phone_found") or r.get(m.get("phone", ""), "") or "",
                    "City": r.get(m.get("city", ""), "") or "", "LinkedIn URL": r.get("linkedin_found") or r.get(m.get("linkedin", ""), "") or "", "Industry": r.get(m.get("industry", ""), "") or "",
                    "Employees": r.get(m.get("employees", ""), "") or "", "lead_score": r.get("lead_score", ""), "lead_why": r.get("lead_why", "")})
    return out


def enrich_file(src: str, icp: str = "", engine: str = "", max_rows: int = 100, render: bool = True, today: dt.date | None = None, pause: float = PAGE_PAUSE,
                provider: str = "", budget: int = ep.DEFAULT_BUDGET) -> str:
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
    prov, bud = None, None
    if provider:
        if not 0 <= budget <= 5000:
            raise ValueError("--budget is between 0 and 5000 paid lookups.")
        try:
            prov = ep.load(provider)
        except ep.ProviderError as e:
            raise ValueError(str(e)) from None
        bud = ep.Budget(budget)
    out_rows, stats = enrich_rows(rows, headers, terms, render, max_rows, today, pause, prov, bud)
    LISTS.mkdir(exist_ok=True)
    stem = re.sub(r"[^a-z0-9]+", "-", p.stem.lower()).strip("-")[:40] or "list"
    out_csv = LISTS / f"{(today or dt.date.today()).isoformat()}-enriched-{stem}.csv"
    write_csv(out_csv, out_rows, first=list(headers))
    text = summary(stats, out_rows, p.name, bud, provider)
    out_csv.with_suffix(".md").write_text(text, encoding="utf-8")
    extra = ""
    if engine:
        from .engines import load, engine_dir
        load(engine)
        imp = engine_dir(engine) / "imports"
        imp.mkdir(parents=True, exist_ok=True)
        dest = imp / f"enriched-{stem}.csv"
        write_csv(dest, import_ready(out_rows, headers))
        extra = f"\nImport-ready copy for your engine: {dest.relative_to(ROOT).as_posix()} (check it with: python dse.py import {engine})"
    return text + f"\nSaved: {out_csv.relative_to(ROOT).as_posix()} (and the summary next to it).{extra}"


def result_json(s: dict, sc: int | None = None) -> str:
    """One line a Ledger workflow can read: RESULT {json}. Plain values only (text, numbers); an empty value means it was not found."""
    em = s["emails"][0] if s["emails"] else {}
    pe = s["people"][0] if s["people"] else {}
    out = {"status": s["status"] or "", "domain": s["domain"] or "", "email": em.get("email", "") or (s["guesses"][0] if s["guesses"] else ""), "email_kind": em.get("kind", "") if em else ("guess" if s["guesses"] else ""),
           "owner": pe.get("name", ""), "owner_title": pe.get("title", ""), "phone": s["phones"][0] if s["phones"] else "", "contact_form": s["contact_form"] or "", "booking": s["booking"] or "",
           "linkedin": (s["socials"] or {}).get("linkedin", "") or "", "score": sc if sc is not None else ""}
    return "RESULT " + json.dumps(out, ensure_ascii=True, separators=(",", ":"))


def card(website: str, icp: str = "", render: bool = True, provider: str = "", budget: int = 1, result_line: bool = False) -> str:
    prov = None
    try:
        prov = ep.load(provider) if provider else None
    except ep.ProviderError as e:
        raise ValueError(str(e)) from None
    s = enrich_site(website, [t.strip() for t in icp.split(",") if t.strip()], render, provider=prov, budget=ep.Budget(budget) if prov else None)
    sc, why = score(s)
    L = [f"# {s['domain'] or website}: {s['status']}", ""]
    if s["status"] != "ok":
        return "\n".join(L) + "\n"
    L.append(f"Score {sc}/100. {why}")
    L.append(f"Steps run: {s['steps']}")
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
