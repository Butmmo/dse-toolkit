"""Website problem check: what a business's own website is missing, judged by a path's pack (packs/<pack>.json).

  python dse.py check smb my-lists/2026-11-14-dentist-tampa-fl.csv      every row with a website
  python dse.py check ministry https://stmaryparish.org                  one website, printed

Each check in a pack looks for evidence (words, links, tools) on the home page and a few inner pages the
pack names (contact, giving, booking ...). The checker leans towards "has it": anything that looks like the
thing counts, so a "missing" result is something the student can say with confidence. A site that doesn't
answer, or shows almost no text even in a real browser, is marked "check by hand", never guessed.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import re
import sys
import urllib.parse
from pathlib import Path

from bs4 import BeautifulSoup

from .common import DEAD_TEXT, JS_BUILDERS, ROOT, contacts_from, fetch, log, norm_url, out_path, read_csv, render_dom, write_csv

PACKS = ROOT / "packs"
HAND = "check by hand"


def load_pack(name: str) -> dict:
    p = PACKS / f"{name}.json"
    if not p.exists():
        sys.exit(f"No pack '{name}'. Packs: {', '.join(sorted(x.stem for x in PACKS.glob('*.json')))}")
    pack = json.loads(p.read_text(encoding="utf-8"))
    for c in pack.get("checks", []):
        c["_re"] = re.compile("|".join(c["look_for"]), re.I) if c.get("look_for") else None
    return pack


def _text(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def _get_page(url: str, render: bool) -> tuple[int, str, str, bool]:
    """(status, final url, html, rendered). Opens the page in hidden Edge when it blocks scripts or is drawn by JavaScript."""
    status, final, html = fetch(url)
    blocked = status == 0 or status in (401, 403, 429) or status >= 500
    low = html.lower()
    thin = len(_text(html)) < 300 if html else True
    if render and (blocked or any(b in low for b in JS_BUILDERS) or thin) and status not in (404, 410):
        dom = render_dom(final or url)
        if dom and len(_text(dom)) >= 80:
            return 200, final or url, dom, True
    return status, final, html, False


def _inner_links(home_html: str, base_url: str, words: list[str], limit: int = 4) -> list[str]:
    pat = re.compile("|".join(re.escape(w) for w in words), re.I)
    host = urllib.parse.urlparse(base_url).netloc.removeprefix("www.")
    out = []
    for a in BeautifulSoup(home_html, "html.parser").find_all("a", href=True):
        href, txt = a["href"], a.get_text(" ", strip=True)
        if href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        if pat.search(href) or pat.search(txt):
            u = urllib.parse.urljoin(base_url, href).split("#")[0]
            if urllib.parse.urlparse(u).netloc.removeprefix("www.") == host and u not in out and u.rstrip("/") != base_url.rstrip("/"):
                out.append(u)
        if len(out) >= limit:
            break
    return out


def _copyright_year(text: str) -> int | None:
    years = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?(\d{4})", text, re.I)]
    return max(years) if years else None


def check_site(website: str, pack: dict, render: bool = True) -> dict:
    url = norm_url(website)
    out: dict = {c["id"]: "" for c in pack["checks"]}
    out.update(gaps_found="", gap_count="", gap_line="", checked_pages="", check_notes="")
    if not url:
        out["check_notes"] = "no website"
        return out
    status, final, home, rendered = _get_page(url, render)
    low = home.lower()
    if status == 0 or status in (401, 403, 429) or status >= 500:
        out.update({c["id"]: HAND for c in pack["checks"]}, check_notes=f"site didn't answer (HTTP {status}); open it by hand")
        return out
    if status in (404, 410) or any(d in low[:20000] for d in DEAD_TEXT):
        out.update({c["id"]: HAND for c in pack["checks"]}, check_notes=f"dead or parked site (HTTP {status})")
        return out
    pages = [(final, home)]
    for u in _inner_links(home, final, pack.get("pages", []), limit=pack.get("max_pages", 4)):
        s, f, h, _ = _get_page(u, render and rendered)
        if s == 200 and h:
            pages.append((f, h))
    all_html = "\n".join(h for _, h in pages)
    all_text = "\n".join(_text(h) for _, h in pages)
    if len(all_text) < 200:
        out.update({c["id"]: HAND for c in pack["checks"]}, check_notes="almost no text even in a browser; open it by hand")
        return out
    found_gaps = []
    for c in pack["checks"]:
        kind = c.get("type", "present")
        if kind == "stale":
            y = _copyright_year(all_text) or _copyright_year(all_html)
            if y is None:
                out[c["id"]] = HAND
                continue
            stale = y < dt.date.today().year - c.get("years", 1)
            out[c["id"]] = f"no (© {y})" if stale else "yes"
            if stale:
                found_gaps.append((c, {"year": y}))
            continue
        # "scope": "text" searches only what a visitor reads (not scripts, styles or attributes): use it for wording checks.
        hit = c["_re"].search(all_text) if c.get("scope") == "text" else (c["_re"].search(all_html) or c["_re"].search(all_text))
        if kind == "present":                   # gap when nothing matching is found anywhere
            out[c["id"]] = "yes" if hit else "no"
            if not hit:
                found_gaps.append((c, {}))
        elif kind == "absent":                  # gap when the thing IS there (e.g. "we'll reply in 2-3 days")
            # a named group starting with q (for example (?P<q1>...)) picks the exact words to quote; otherwise the whole match
            picked = next((v for k, v in (hit.groupdict() if hit else {}).items() if k.startswith("q") and v), None)
            quote = re.sub(r"\s+", " ", picked or (hit.group(0) if hit else "")).strip()[:80]
            out[c["id"]] = f"no ({quote[:60]})" if hit else "yes"
            if hit:
                found_gaps.append((c, {"quote": quote}))
    # weight 0 = a filter, not a selling point: warn instead of counting it as a gap
    warnings = []
    for c, extra in [g for g in found_gaps if g[0].get("weight", 1) == 0]:
        warnings.append("not a fit? " + c.get("missing", c["label"]).format(**extra))
    found_gaps = [g for g in found_gaps if g[0].get("weight", 1) > 0]
    contacts = contacts_from(all_html)
    for k, v in contacts.items():
        out[f"found_{k}"] = v
    found_gaps.sort(key=lambda g: -g[0].get("weight", 1))
    out["gaps_found"] = "; ".join(c.get("missing", "Missing: " + c["label"]).format(**extra) for c, extra in found_gaps)
    out["gap_count"] = len(found_gaps)
    if found_gaps:
        c, extra = found_gaps[0]
        out["gap_line"] = c.get("gap_line", c["label"]).format(**extra)
    out["checked_pages"] = len(pages)
    out["check_notes"] = "; ".join(warnings + (["read in a real browser"] if rendered else []))
    return out


def opener(row: dict, pack: dict) -> str:
    tpl = pack.get("opener", "")
    if not tpl or not row.get("gap_line"):
        return ""
    first = (row.get("business") or row.get("company") or row.get("name") or "there").strip()
    return tpl.format(business=first, city=(row.get("city") or "your area").strip(), gap_line=row["gap_line"])


def check_file(pack_name: str, src: str, render: bool = True, out: str = "") -> str:
    pack = load_pack(pack_name)
    rows = read_csv(src)
    site_col = next((c for c in ("website", "website_url", "url", "site") if rows and c in rows[0]), None)
    if not site_col:
        sys.exit("The file needs a 'website' column.")
    log(f"Checking {len(rows)} websites with the {pack['label']} pack{'' if render else ' (fast: no browser)'}...")

    def one(r):
        res = check_site(r.get(site_col, ""), pack, render)
        log(f"  {r.get('business') or r.get(site_col)}: {res['gap_count'] or 0} gaps {res['check_notes']}".rstrip())
        return res

    with cf.ThreadPoolExecutor(6 if render else 12) as ex:
        results = list(ex.map(one, rows))
    for r, res in zip(rows, results):
        r.update(res)
        for k in ("email", "phone", "instagram", "facebook"):
            if not r.get(k) and res.get(f"found_{k}"):
                r[k] = res[f"found_{k}"]
            r.pop(f"found_{k}", None)
        r["gap_used"] = r.get("gap_line", "")
        r["opener"] = opener(r, pack)
        r["variant"] = pack.get("variant", f"{pack_name}-v1") if r["opener"] else ""
    rows.sort(key=lambda r: -(int(r["gap_count"]) if str(r.get("gap_count", "")).isdigit() else -1))
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", Path(src).stem)       # don't repeat the date in the new name
    dst = out or str(out_path(stem, "checked"))
    write_csv(dst, rows, first=["business", "city", "state", "website", "gap_count", "gaps_found", "gap_used", "opener"])
    with_gaps = sum(1 for r in rows if str(r.get("gap_count", "")).isdigit() and int(r["gap_count"]) > 0)
    print(f"{len(rows)} checked, {with_gaps} with at least one gap -> {dst}")
    return dst


def check_one(pack_name: str, url: str, render: bool = True):
    pack = load_pack(pack_name)
    res = check_site(url, pack, render)
    print(f"{url} ({pack['label']} pack)")
    for c in pack["checks"]:
        print(f"  {c['label']:<44} {res[c['id']] or '-'}")
    print(f"  Gaps: {res['gap_count'] or 0}. {res['check_notes']}")
    if res["gap_line"]:
        print(f"  Lead with: {res['gap_line']}")
