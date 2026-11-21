"""Research public business signals for a lead CSV and draft evidence-led outreach locally."""
from __future__ import annotations

import csv
import datetime as dt
import html
from html.parser import HTMLParser
import importlib.util
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import importer
from .common import LISTS, ROOT

USER_AGENT = "DFamociousHQ/1.0 (local user-requested business research)"
OUT_FIELDS = ["herald_findings", "herald_sources", "herald_checked_at", "herald_status",
              "research_findings", "research_sources", "research_searched_at", "research_status",
              "outreach_subject", "outreach_body", "outreach_evidence", "outreach_model"]
PRESENCE_FIELDS = ["presence_signals", "presence_sources", "presence_checked_at", "presence_status"]
SOCIAL_DOMAINS = ("linkedin.com", "instagram.com", "facebook.com", "x.com", "twitter.com", "youtube.com", "tiktok.com")
STOP = {"the", "and", "for", "with", "company", "business", "services", "service", "inc", "llc", "ltd", "co"}


class Results(HTMLParser):
    """Extract result links and snippets from DuckDuckGo's public HTML search page."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items: list[dict] = []
        self.current: dict | None = None
        self.target = ""
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set((a.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self.current = {"url": a.get("href", ""), "title": "", "snippet": ""}
            self.items.append(self.current)
            self.target, self.depth = "title", 1
        elif tag in ("a", "td", "div") and classes & {"result__snippet", "result-snippet"} and self.current:
            self.target, self.depth = "snippet", 1
        elif self.target:
            self.depth += 1

    def handle_endtag(self, _tag):
        if self.target:
            self.depth -= 1
            if self.depth <= 0:
                self.target, self.depth = "", 0

    def handle_data(self, data):
        if self.target and self.current:
            self.current[self.target] += data


def _tokens(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9]{2,}", (text or "").lower()) if x not in STOP}


def _clean_url(url: str) -> str:
    url = html.unescape((url or "").strip())
    if url.startswith("//"):
        url = "https:" + url
    parsed = urllib.parse.urlparse(url)
    if "duckduckgo.com" in (parsed.hostname or ""):
        q = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
        if q:
            url = urllib.parse.unquote(q)
    p = urllib.parse.urlparse(url)
    return url if p.scheme in ("https", "http") and p.hostname else ""


def search(query: str, limit: int = 2) -> list[dict]:
    """Fetch result snippets only. Search-result targets are recorded but never crawled here."""
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read(1_500_000).decode("utf-8", errors="replace")
    parser = Results()
    parser.feed(raw)
    out, seen = [], set()
    for item in parser.items:
        target = _clean_url(item.get("url", ""))
        title = re.sub(r"\s+", " ", html.unescape(item.get("title", ""))).strip()
        snippet = re.sub(r"\s+", " ", html.unescape(item.get("snippet", ""))).strip()
        if target and title and target not in seen:
            seen.add(target)
            out.append({"title": title[:240], "snippet": snippet[:700], "url": target})
        if len(out) >= limit:
            break
    return out


def queries_for(row: dict) -> list[tuple[str, str]]:
    company = (row.get("business") or row.get("company") or row.get("Company") or row.get("name") or "").strip()
    city = (row.get("city") or row.get("City") or "").strip()
    product = (row.get("product") or row.get("service") or row.get("industry") or row.get("Industry") or "").strip()
    if not company:
        company = (row.get("website") or row.get("domain") or "").strip()
    suffix = f" {city}" if city else ""
    q = [("business", f'"{company}"{suffix} {product} products services'[:220]),
         ("news", f'"{company}"{suffix} news announcement launch'[:220])]
    return [(kind, text) for kind, text in q if company]


def gather(row: dict, max_signals: int = 6) -> tuple[list[dict], list[str]]:
    company = (row.get("business") or row.get("company") or row.get("Company") or row.get("name") or "").strip()
    searched_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    terms = _tokens(company)
    found, seen = [], set()
    errors = []
    for kind, query in queries_for(row):
        try:
            results = search(query)
        except Exception as e:
            errors.append(type(e).__name__)
            continue
        for item in results:
            key = item["url"]
            if key in seen:
                continue
            seen.add(key)
            text = f"{item['title']} {item['snippet']} {key}".lower()
            match = len(terms & _tokens(text))
            if terms and match == 0:
                continue
            host = urllib.parse.urlparse(key).hostname or ""
            social = any(host == d or host.endswith("." + d) for d in SOCIAL_DOMAINS)
            found.append({"id": f"S{len(found)+1:02d}", "type": "social search result" if social or kind == "social" else kind,
                          "title": item["title"], "snippet": item["snippet"], "url": key,
                          "query": query, "provider": "DuckDuckGo public web results", "retrieved_at": searched_at,
                          "match_terms": sorted(terms & _tokens(text))})
        time.sleep(1.0)
    return found[:max_signals], errors


def presence_queries_for(row: dict) -> list[tuple[str, str]]:
    """Search only for public professional/business social presence, not personal-life content."""
    company = (row.get("business") or row.get("company") or row.get("Company") or row.get("name") or "").strip()
    contact = (row.get("contact_name") or row.get("decision_maker") or row.get("person") or "").strip()
    city = (row.get("city") or row.get("City") or "").strip()
    if not company:
        company = (row.get("website") or row.get("domain") or "").strip()
    suffix = f" {city}" if city else ""
    queries = [("business_profile", f'"{company}"{suffix} site:linkedin.com/company OR site:instagram.com OR site:facebook.com OR site:x.com OR site:youtube.com OR site:tiktok.com'[:300]),
               ("business_posts", f'"{company}"{suffix} site:linkedin.com/posts OR site:instagram.com/p OR site:facebook.com/posts OR site:x.com'[:300])]
    if contact and company:
        queries.append(("professional_contact", f'"{contact}" "{company}" site:linkedin.com/in OR site:linkedin.com/posts'[:260]))
    return [(kind, query) for kind, query in queries if company]


def gather_presence(row: dict, max_signals: int = 8) -> tuple[list[dict], list[str]]:
    company = (row.get("business") or row.get("company") or row.get("Company") or row.get("name") or "").strip()
    contact = (row.get("contact_name") or row.get("decision_maker") or row.get("person") or "").strip()
    company_terms, contact_terms = _tokens(company), _tokens(contact)
    checked_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    found, seen, errors = [], set(), []
    for kind, query in presence_queries_for(row):
        try:
            results = search(query)
        except Exception as e:
            errors.append(type(e).__name__)
            continue
        for item in results:
            url = item["url"]
            if url in seen:
                continue
            text = f"{item['title']} {item['snippet']} {url}".lower()
            terms = _tokens(text)
            company_matches = company_terms & terms
            contact_matches = contact_terms & terms
            # When a named contact was supplied, require both the business and person to match.
            if not company_matches or (kind == "professional_contact" and contact_terms and not contact_matches):
                continue
            seen.add(url)
            found.append({"id": f"P{len(found)+1:02d}", "type": kind, "title": item["title"], "snippet": item["snippet"],
                          "url": url, "query": query, "provider": "DuckDuckGo public web results", "retrieved_at": checked_at,
                          "matched_company_terms": sorted(company_matches), "matched_contact_terms": sorted(contact_matches)})
        time.sleep(1.0)
    return found[:max_signals], errors


def _ollama_model() -> str:
    """Honor a configured model; otherwise prefer a capable local Qwen model for research drafting."""
    spec = importlib.util.spec_from_file_location("hq_ollama_model", ROOT / "chat" / "ollama_model.py")
    if not spec or not spec.loader:
        return ""
    ollama_model = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ollama_model)
    installed = ollama_model.installed()
    if not installed:
        return ""
    preferred = os.environ.get("OLLAMA_MODEL", "").strip()
    if preferred and preferred in installed:
        return preferred
    saved = ollama_model.user_setting()
    if saved and saved in installed:
        return saved
    qwen = sorted((m for m in installed if "qwen" in m.lower()),
                  key=lambda m: ("14b" not in m.lower(), "coder" not in m.lower(), "7b" not in m.lower(), m.lower()))
    return qwen[0] if qwen else ollama_model.pick(have=installed)[0]


def draft(row: dict, signals: list[dict], model: str) -> dict:
    if not signals or not model:
        return {}
    evidence = [{"id": s["id"], "title": s["title"], "snippet": s["snippet"], "url": s["url"]} for s in signals[:5]]
    company = (row.get("business") or row.get("company") or row.get("Company") or "").strip()
    user = {"company": company, "city": row.get("city") or row.get("City") or "", "offer": row.get("offer") or row.get("gap_line") or row.get("lead_why") or "",
            "evidence": evidence}
    payload = json.dumps({"model": model, "stream": False, "keep_alive": "30m", "format": "json",
        "options": {"num_ctx": 8192, "num_predict": 450, "temperature": 0.2},
        "messages": [{"role": "system", "content": (
            "Draft one honest, concise first-contact business email based ONLY on the supplied evidence and offer. "
            "Search snippets can be wrong: do not state a claim as fact unless its source ID is returned. Never claim prior contact, "
            "personal familiarity, urgency, private knowledge, or guaranteed results. If evidence is weak, return empty subject/body. "
            "Do not include citations in the email text. Return JSON only with subject, body, evidence_ids. The body should be under 90 words, "
            "plain and low-pressure, with one clear question and an easy opt-out."
        )}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}]}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request("http://localhost:11434/api/chat", payload, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        data = json.loads(response.read())
    content = (data.get("message") or {}).get("content", "")
    try:
        result = json.loads(content)
    except (ValueError, TypeError):
        return {}
    ids = {s["id"] for s in signals}
    used = [x for x in result.get("evidence_ids", []) if isinstance(x, str) and x in ids]
    subject = re.sub(r"\s+", " ", str(result.get("subject", ""))).strip()[:120]
    body = str(result.get("body", "")).strip()[:1200]
    if not subject or not body or not used:
        return {}
    return {"outreach_subject": subject, "outreach_body": body, "outreach_evidence": ", ".join(used), "outreach_model": model}


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def enrich_file(source: str, engine: str = "", max_rows: int = 100, use_ai: bool = True) -> str:
    p = Path(source)
    if not p.is_absolute():
        p = (ROOT / source) if (ROOT / source).is_file() else p
    if not p.is_file():
        raise ValueError(f"I could not find the CSV: {source}")
    headers, rows = importer.read_rows(p)
    if not rows:
        raise ValueError("That CSV has no rows.")
    if not 1 <= max_rows <= 50:
        raise ValueError("--max must be between 1 and 50 leads for this first research stage.")
    model = _ollama_model() if use_ai else ""
    normalized_rows, _report = importer.normalize(p)
    out, errors, drafted = [], [], 0
    for i, original in enumerate(rows[:max_rows], 1):
        row = dict(original)
        normalized = normalized_rows[i-1] if i <= len(normalized_rows) else {}
        for key in ("business", "website", "city", "industry", "contact_name", "contact_title", "email"):
            if normalized.get(key) and not row.get(key):
                row[key] = normalized[key]
        print(f"[{i}/{min(len(rows), max_rows)}] researching {row.get('business') or row.get('website') or 'lead'}", file=sys.stderr, flush=True)
        signals, row_errors = gather(row)
        errors.extend(row_errors)
        row["herald_findings"] = row["research_findings"] = "\n".join(f"[{s['id']}] {s['title']} | {s['snippet']}" for s in signals)
        sources_json = json.dumps(signals, ensure_ascii=False, separators=(",", ":"))
        row["herald_sources"] = row["research_sources"] = sources_json
        checked_at = signals[0]["retrieved_at"] if signals else dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        row["herald_checked_at"] = row["research_searched_at"] = checked_at
        row["herald_status"] = row["research_status"] = "business evidence found" if signals else "no matching business results"
        row.update({k: "" for k in ("outreach_subject", "outreach_body", "outreach_evidence", "outreach_model")})
        if model and signals:
            try:
                generated = draft(row, signals, model)
                if generated:
                    row.update(generated)
                    row["herald_status"] = row["research_status"] = "draft ready for human review"
                    drafted += 1
            except Exception as e:
                errors.append(type(e).__name__)
        out.append(row)
        if i < min(len(rows), max_rows):
            time.sleep(0.8)
    for original in rows[max_rows:]:
        untouched = dict(original)
        for f in OUT_FIELDS:
            untouched.setdefault(f, "")
        untouched.setdefault("research_status", "not processed: lead limit reached")
        out.append(untouched)
    LISTS.mkdir(exist_ok=True)
    stem = re.sub(r"[^a-z0-9]+", "-", p.stem.lower()).strip("-")[:40] or "list"
    date = dt.date.today().isoformat()
    dest = LISTS / f"{date}-researched-{stem}.csv"
    _write_csv(dest, out)
    report = [f"# Lead signals: {p.name}", "", f"- Searched: {min(len(rows), max_rows)} of {len(rows)} rows",
              f"- Leads with public results: {sum(bool(r['research_sources']) for r in out[:min(len(rows), max_rows)])}",
              f"- Local AI drafts ready for review: {drafted}", f"- Local model: {model or 'not used / unavailable'}", "",
              "## Review before use", "", "Search snippets are leads for human review, not verified facts. Open the linked source before using a claim in outreach. Nothing was sent.", ""]
    if errors:
        report += ["Search/model errors: " + ", ".join(errors[:12]), ""]
    dest.with_suffix(".md").write_text("\n".join(report), encoding="utf-8")
    extra = ""
    if engine:
        from .engines import load, engine_dir
        load(engine)
        imports = engine_dir(engine) / "imports"
        imports.mkdir(parents=True, exist_ok=True)
        imported = imports / f"researched-{stem}.csv"
        _write_csv(imported, out)
        extra = f"\nEngine import copy: {imported.relative_to(ROOT).as_posix()}"
    return ("\n".join(report) + f"\nSaved: {dest.relative_to(ROOT).as_posix()} and its Markdown run summary.{extra}\n")


def enrich_presence_file(source: str, engine: str = "", max_rows: int = 100) -> str:
    """Create an independent Presence social-evidence CSV; never draft or send outreach."""
    p = Path(source)
    if not p.is_absolute():
        p = (ROOT / source) if (ROOT / source).is_file() else p
    if not p.is_file():
        raise ValueError(f"I could not find the CSV: {source}")
    _headers, rows = importer.read_rows(p)
    if not rows:
        raise ValueError("That CSV has no rows.")
    if not 1 <= max_rows <= 50:
        raise ValueError("--max must be between 1 and 50 leads for this Presence research stage.")
    normalized_rows, _report = importer.normalize(p)
    out, errors = [], []
    for i, original in enumerate(rows[:max_rows], 1):
        row = dict(original)
        normalized = normalized_rows[i - 1] if i <= len(normalized_rows) else {}
        for key in ("business", "website", "city", "contact_name"):
            if normalized.get(key) and not row.get(key):
                row[key] = normalized[key]
        print(f"[{i}/{min(len(rows), max_rows)}] checking public social presence for {row.get('business') or row.get('website') or 'lead'}", file=sys.stderr, flush=True)
        signals, row_errors = gather_presence(row)
        errors.extend(row_errors)
        row["presence_signals"] = json.dumps(signals, ensure_ascii=False, separators=(",", ":"))
        row["presence_sources"] = "\n".join(f"[{s['id']}] {s['title']} | {s['url']}" for s in signals)
        row["presence_checked_at"] = signals[0]["retrieved_at"] if signals else dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        row["presence_status"] = "public professional/social results found" if signals else "no matching public social results"
        out.append(row)
        if i < min(len(rows), max_rows):
            time.sleep(0.8)
    for original in rows[max_rows:]:
        untouched = dict(original)
        for f in PRESENCE_FIELDS:
            untouched.setdefault(f, "")
        untouched.setdefault("presence_status", "not processed: lead limit reached")
        out.append(untouched)
    LISTS.mkdir(exist_ok=True)
    stem = re.sub(r"[^a-z0-9]+", "-", p.stem.lower()).strip("-")[:40] or "list"
    dest = LISTS / f"{dt.date.today().isoformat()}-presence-signals-{stem}.csv"
    _write_csv(dest, out)
    report = [f"# Presence public social signals: {p.name}", "", f"- Checked: {min(len(rows), max_rows)} of {len(rows)} rows",
              f"- Rows with public social results: {sum(bool(r['presence_signals']) for r in out[:min(len(rows), max_rows)])}",
              "- No outreach copy was drafted or sent.", "", "## Review before use", "",
              "Results are search snippets, not verified identity or reputation. Review each source directly. Only public professional and business-related results are included; do not infer sensitive or personal traits.", ""]
    if errors:
        report += ["Search errors: " + ", ".join(errors[:12]), ""]
    dest.with_suffix(".md").write_text("\n".join(report), encoding="utf-8")
    shelf = {"kind": "presence-signals", "v": 1, "business": f"{p.stem} ({min(len(rows), max_rows)} leads)"[:120],
             "made": dt.date.today().isoformat(), "source": "Public professional/business social search", "signals": []}
    for row in out[:min(len(rows), max_rows)]:
        for signal in json.loads(row.get("presence_signals") or "[]"):
            if len(shelf["signals"]) >= 60:
                break
            shelf["signals"].append({"business": str(row.get("business") or row.get("company") or "")[:120], **signal})
    dest.with_name(dest.stem + "-shelf.json").write_text(json.dumps(shelf, ensure_ascii=False, indent=2), encoding="utf-8")
    extra = ""
    if engine:
        from .engines import load, engine_dir
        load(engine)
        imports = engine_dir(engine) / "imports"
        imports.mkdir(parents=True, exist_ok=True)
        imported = imports / f"presence-signals-{stem}.csv"
        _write_csv(imported, out)
        extra = f"\nEngine import copy: {imported.relative_to(ROOT).as_posix()}"
    return "\n".join(report) + f"\nSaved: {dest.relative_to(ROOT).as_posix()}, its Markdown summary, and Presence shelf JSON.{extra}\n"
