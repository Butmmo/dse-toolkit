"""What a business's website is built with and what it is missing: our own free version of BuiltWith / Wappalyzer.

  python dse.py tech https://example-dentist.com            one site: the technology it uses and what is missing
  python dse.py tech my-leads.csv                           every row with a website: adds tech_* columns (same rows, same order)

It downloads ONE page (the homepage, like a visitor, after checking the site's robots.txt) and reads its source and response headers against the
fingerprint file dse/tech_rules.json: site platform, booking tool, chat, forms and CRM, analytics, ad and call tracking, email tools, payments and financing,
review widgets, hosting. Nothing is scraped from BuiltWith or any directory, and no account or key is needed. The paid BuiltWith API is not used (the sources
list says so: python dse.py directories).

Everything it says is about the HOMEPAGE: "no online booking detected" can mean the booking page is deeper in the site, so check before you quote it to a
business. The gap lines are written that way on purpose. A site drawn entirely by JavaScript shows little in its source; unless you pass --fast the page is
also opened in hidden Edge (same as the website check) so those sites are read too.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import re
import time
from datetime import date
from pathlib import Path

import requests

from . import pagecache
from .common import UA, log, norm_url, out_path, read_csv, render_dom, write_csv

RULES = json.loads(Path(__file__).with_name("tech_rules.json").read_text(encoding="utf-8"))
CATEGORIES = [k for k in RULES if not k.startswith("_")]
GENERIC_BOOKING = "Calendar link or button"
DIY_BUILDERS = {"Wix", "Squarespace", "GoDaddy Website Builder", "Weebly", "Carrd", "Duda", "Linktree-style page"}

COLUMNS = {   # category -> output column
    "platform": "tech_platform", "booking": "tech_booking", "chat": "tech_chat", "forms_crm": "tech_forms_crm", "analytics": "tech_analytics",
    "ads_tracking": "tech_ads_tracking", "email_marketing": "tech_email", "payments_financing": "tech_payments", "reviews": "tech_reviews", "hosting": "tech_hosting",
}
FLAG_COLUMNS = ["tech_mobile_ready", "tech_https", "tech_structured_data", "tech_copyright_year", "tech_gaps", "tech_gap_count", "tech_status", "tech_scanned_on"]


def _match(sig: str, low: str, headers: dict[str, str]) -> bool:
    if sig.startswith("h:"):
        _, name, text = (sig.split(":", 2) + [""])[:3]
        val = headers.get(name.lower())
        return val is not None and text.lower() in val.lower()
    if sig.startswith("rx:"):
        try:
            return re.search(sig[3:], low, re.I) is not None
        except re.error:
            return False
    return sig.lower() in low


def detect(html: str, headers: dict[str, str] | None = None) -> dict[str, list[str]]:
    """{category: [technology, ...]} found in a page's source and response headers. Pure: no network."""
    low = (html or "").lower()
    hdr = {k.lower(): v for k, v in (headers or {}).items()}
    out: dict[str, list[str]] = {}
    for cat in CATEGORIES:
        found = [name for name, sigs in RULES[cat].items() if any(_match(s, low, hdr) for s in sigs)]
        if cat == "booking" and len(found) > 1 and GENERIC_BOOKING in found:
            found.remove(GENERIC_BOOKING)              # a real booking tool beats "there is a book-now link"
        out[cat] = found
    return out


def copyright_year(html: str) -> int | None:
    best = None
    for m in re.finditer(r"(?:©|&copy;|&#169;|copyright)[^0-9]{0,30}((?:19|20)\d{2})(?:\s*(?:-|–|to)\s*((?:19|20)\d{2}))?", html or "", re.I):
        y = int(m.group(2) or m.group(1))
        best = y if best is None or y > best else best
    return best


def profile(html: str, headers: dict[str, str] | None, final_url: str) -> dict:
    """Everything we say about a site: the technologies by category plus a few plain facts."""
    prof = detect(html, headers)
    prof["https"] = (final_url or "").lower().startswith("https://")
    prof["mobile_ready"] = re.search(r"<meta[^>]+name=[\"']viewport[\"']", html or "", re.I) is not None
    prof["structured_data"] = "application/ld+json" in (html or "").lower()
    prof["copyright_year"] = copyright_year(html)
    return prof


def gaps(prof: dict, today: date | None = None) -> list[str]:
    """What is missing, in plain words. Every line says 'detected' or 'found' because we read the homepage only."""
    today = today or date.today()
    out = []
    if not prof["https"]:
        out.append("the site is not served over https, so browsers warn visitors")
    if not prof["mobile_ready"]:
        out.append("no mobile-friendly setting found, so the page may not fit a phone")
    if not prof["booking"]:
        out.append("no online booking tool detected on the homepage")
    if not prof["chat"]:
        out.append("no chat or text-message button detected")
    if not prof["forms_crm"]:
        out.append("no contact form or CRM form detected on the homepage")
    if not prof["analytics"]:
        out.append("no analytics detected, so they may not see which pages bring enquiries")
    if not prof["ads_tracking"]:
        out.append("no ad or call tracking detected")
    if not prof["email_marketing"]:
        out.append("no email sign-up tool detected")
    if not prof["reviews"]:
        out.append("no review widget or review link detected")
    if not prof["structured_data"]:
        out.append("no structured data (schema) found, which helps search and AI answers describe the business")
    y = prof.get("copyright_year")
    if y and y <= today.year - 2:
        out.append(f"the footer says (c) {y}, so the site looks out of date")
    diy = [p for p in prof["platform"] if p in DIY_BUILDERS]
    if diy:
        out.append(f"built on {diy[0]}, a do-it-yourself site builder")
    return out


def columns(prof: dict, status: str = "ok", today: date | None = None) -> dict:
    """The tech_* columns for one site."""
    today = today or date.today()
    g = gaps(prof, today) if status == "ok" else []
    row = {col: ", ".join(prof[cat]) for cat, col in COLUMNS.items()}
    row.update({"tech_mobile_ready": "yes" if prof["mobile_ready"] else "no", "tech_https": "yes" if prof["https"] else "no",
                "tech_structured_data": "yes" if prof["structured_data"] else "no", "tech_copyright_year": prof["copyright_year"] or "",
                "tech_gaps": " | ".join(g), "tech_gap_count": len(g), "tech_status": status, "tech_scanned_on": today.isoformat()})
    return row


def empty_columns(status: str, today: date | None = None) -> dict:
    row = {col: "" for col in COLUMNS.values()}
    row.update({c: "" for c in FLAG_COLUMNS})
    row.update({"tech_status": status, "tech_gap_count": 0, "tech_scanned_on": (today or date.today()).isoformat()})
    return row


def _plain_text_len(html: str) -> int:
    return len(re.sub(r"\s+", " ", re.sub(r"(?is)<(script|style)\b.*?</\1>|<[^>]+>", " ", html or "")).strip())


def scan(website: str, render: bool = True, today: date | None = None) -> tuple[dict, dict]:
    """(columns, profile) for one site. One page: the homepage, if the site's robots.txt allows it."""
    url = norm_url(website)
    if not url:
        return empty_columns("no website", today), {}
    try:
        from . import enrich
        if not enrich.robots_ok(url):
            return empty_columns("robots.txt says no", today), {}
    except Exception:                                  # robots check is a courtesy: never the reason a scan fails
        pass
    try:
        r = pagecache.get(url, timeout=15)
    except Exception:
        return empty_columns("unreachable", today), {}
    html = r.text if "text" in r.headers.get("content-type", "text") else ""
    if r.status_code in (403, 429) or r.status_code >= 500 or (render and _plain_text_len(html) < 300):
        dom = render_dom(r.url) if render else ""
        if dom:
            html = html + "\n" + dom
        elif r.status_code >= 400:
            return empty_columns(f"blocked ({r.status_code})" if r.status_code in (403, 429) else f"error {r.status_code}", today), {}
    elif r.status_code >= 400:
        return empty_columns(f"error {r.status_code}", today), {}
    prof = profile(html, dict(r.headers), r.url)
    return columns(prof, "ok", today), prof


def card(website: str, render: bool = True) -> str:
    cols, prof = scan(website, render)
    if cols["tech_status"] != "ok":
        return f"{website}: {cols['tech_status']}"
    lines = [f"{website}"]
    for cat, col in COLUMNS.items():
        lines.append(f"  {cat.replace('_', ' '):<20} {cols[col] or '-'}")
    lines.append(f"  {'mobile / https':<20} {cols['tech_mobile_ready']} / {cols['tech_https']}")
    lines.append(f"  missing ({cols['tech_gap_count']}):")
    lines += [f"    - {g}" for g in cols["tech_gaps"].split(" | ") if g]
    return "\n".join(lines)


def find_site_column(rows: list[dict]) -> str:
    keys = list(rows[0].keys()) if rows else []
    for want in ("website", "site", "url", "web", "domain"):
        for k in keys:
            if k.strip().lower() == want:
                return k
    return ""


def tech_file(src: str, max_rows: int = 100, render: bool = True, out: str = "", today: date | None = None, workers: int = 8) -> str:
    """Add the tech_* columns to every row that has a website (up to max_rows), keeping every row and its order."""
    rows = read_csv(src)
    col = find_site_column(rows)
    if not col:
        raise SystemExit("No website column found (looking for: website, site, url, web, domain).")
    todo = [i for i, r in enumerate(rows) if norm_url(r.get(col, ""))][:max_rows]
    t = time.time()
    with cf.ThreadPoolExecutor(workers) as ex:
        results = list(ex.map(lambda i: scan(rows[i][col], render, today)[0], todo))
    done = dict(zip(todo, results))
    for i, r in enumerate(rows):
        r.update(done.get(i) or empty_columns("no website" if not norm_url(r.get(col, "")) else "not scanned (over the limit)", today))
    dst = out or str(out_path("tech", Path(src).stem))
    write_csv(dst, rows)
    ok = sum(1 for c in results if c["tech_status"] == "ok")
    log(f"{len(todo)} sites scanned in {int(time.time() - t)} s, {ok} read ok")
    print(f"{len(rows)} rows -> {dst}")
    return dst
