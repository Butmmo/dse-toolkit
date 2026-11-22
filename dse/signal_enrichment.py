"""Research public business signals for a lead CSV and draft evidence-led outreach locally."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import importlib.util
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

from . import importer
from . import business_profiles
from . import classification
from . import path_signals
from . import field_results as fr
from .common import LISTS, ROOT

USER_AGENT = "DFamociousHQ/1.0 (local user-requested business research)"
OUT_FIELDS = ["herald_findings", "herald_sources", "herald_checked_at", "herald_status",
              "research_findings", "research_sources", "research_searched_at", "research_status",
              "herald_company_findings", "herald_company_sources", "herald_person_findings", "herald_person_sources",
              "herald_business_assessment", "herald_role_assessment", "herald_legal_form_assessment", "herald_assessed_at", "herald_assessment_note",
              "herald_identity_summary",
              "herald_ai_review", "herald_ai_reviewed_at", "herald_ai_review_model",
              "outreach_subject", "outreach_body", "outreach_evidence", "outreach_evidence_detail", "outreach_personalization_basis", "outreach_model",
              "herald_role_candidates", "herald_people_candidates", "herald_signal_events", "enrichment_target_profile", "enrichment_target_decision_maker", "enrichment_target_role", "enrichment_target_legal_form", "enrichment_target_path", "enrichment_search_strategy", "field_results"]
PRESENCE_FIELDS = ["presence_signals", "presence_sources", "presence_checked_at", "presence_status",
                   "presence_comparison_status", "presence_change_summary", "presence_new_source_urls", "presence_changed_source_urls", "presence_not_returned_urls", "presence_previous_checked_at", "field_results"]
PRESENCE_HISTORY = ROOT / "data" / "presence-history.json"
PRESENCE_HISTORY_DAYS = 180
SOCIAL_DOMAINS = ("linkedin.com", "instagram.com", "facebook.com", "x.com", "twitter.com", "youtube.com", "tiktok.com")
STOP = {"the", "and", "for", "with", "company", "business", "services", "service", "inc", "llc", "ltd", "co"}
BRAVE_SEARCH_REQUESTS = 0


class SearchProviderError(RuntimeError):
    """A safe-to-display provider configuration or response error."""


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


def search(query: str, limit: int = 2, provider: str = "duckduckgo") -> list[dict]:
    """Fetch search snippets only; the selected provider is explicit and recorded."""
    global BRAVE_SEARCH_REQUESTS
    provider = (provider or "duckduckgo").strip().casefold()
    if provider not in ("duckduckgo", "brave"):
        raise SearchProviderError("Choose DuckDuckGo or Brave Search as the public search provider.")
    if provider == "brave":
        api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
        if not api_key:
            raise SearchProviderError("Brave Search was selected, but BRAVE_SEARCH_API_KEY is not set on this PC.")
        try:
            request_limit = int(os.environ.get("DSE_BRAVE_SEARCH_QUERY_LIMIT", "150"))
        except ValueError:
            request_limit = 150
        request_limit = max(1, min(1000, request_limit))
        if BRAVE_SEARCH_REQUESTS >= request_limit:
            raise SearchProviderError(f"Brave Search reached this run's query cap ({request_limit}).")
        BRAVE_SEARCH_REQUESTS += 1
        params = urllib.parse.urlencode({"q": query, "count": max(1, min(20, limit)), "safesearch": "moderate"})
        req = urllib.request.Request(
            "https://api.search.brave.com/res/v1/web/search?" + params,
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.loads(response.read(1_500_000))
        except urllib.error.HTTPError as error:
            raise SearchProviderError(f"Brave Search API returned HTTP {error.code}.") from None
        except (urllib.error.URLError, TimeoutError):
            raise SearchProviderError("Brave Search API could not be reached from this PC.") from None
        except (ValueError, TypeError):
            raise SearchProviderError("Brave Search API returned an unreadable response.") from None
        out, seen = [], set()
        for item in (data.get("web") or {}).get("results", []):
            target = _clean_url(item.get("url", ""))
            title = re.sub(r"\s+", " ", str(item.get("title", ""))).strip()
            snippet = re.sub(r"\s+", " ", str(item.get("description", ""))).strip()
            if target and title and target not in seen:
                seen.add(target)
                out.append({"title": title[:240], "snippet": snippet[:700], "url": target,
                            "provider": "Brave Search API", "publication_date_hint": item.get("page_age") or item.get("age") or ""})
            if len(out) >= limit:
                break
        return out

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
            out.append({"title": title[:240], "snippet": snippet[:700], "url": target,
                        "provider": "DuckDuckGo public web results"})
        if len(out) >= limit:
            break
    return out


def queries_for(row: dict, business_profile: str = "any", decision_maker: str = "any", legal_form: str = "any", decision_role: str = "signal_based", custom_role: str = "", path_key: str = "any") -> list[tuple[str, str]]:
    company = business_profiles.row_value(row, "business", "company", "name", "current_company")
    city = business_profiles.row_value(row, "city")
    product = business_profiles.row_value(row, "product", "service", "industry")
    if not company:
        company = business_profiles.row_value(row, "website", "domain")
    suffix = f" {city}" if city else ""
    bp, dm, lf = business_profiles.normalize_profiles(business_profile, decision_maker, legal_form)
    q = [("business", f'"{company}"{suffix} {product} products services'[:260]),
         ("news", f'"{company}"{suffix} news announcement launch'[:260])]
    if bp["terms"]:
        q.append(("business_profile", f'"{company}"{suffix} {bp["terms"]}'[:300]))
    if dm["terms"]:
        q.append(("decision_maker", f'"{company}"{suffix} {dm["terms"]}'[:300]))
    if lf["terms"]:
        q.append(("legal_form_search", f'"{company}" {lf["terms"]}'[:300]))
    path = path_signals.profile(path_key)
    if path_signals.known_path(path_key):
        q.append(("path_specific_signal", f'"{company}"{suffix} {path["query_terms"]}'[:300]))
    company_signal = business_profiles.row_value(row, "company_last_signal", "company_signal", "last_lead_signal", "last_signal", "recent_signal", "news_signal")
    person_signal = business_profiles.row_value(row, "decision_maker_last_signal", "person_last_signal", "contact_recent_signal", "person_last_lead_signal")
    signal_terms = re.sub(r"\s+", " ", company_signal)[:100] or "hiring funding launch expansion new product leadership"
    q.append(("company_signal", f'"{company}"{suffix} {signal_terms}'[:300]))
    roles = business_profiles.infer_decision_roles(company_signal, decision_role)
    if decision_role == "signal_based" and path_signals.known_path(path_key):
        roles = list(dict.fromkeys([*path_signals.profile(path_key)["roles"], *roles]))
    role_terms = " ".join([*(business_profiles.DECISION_ROLES[r]["terms"] for r in roles), custom_role.strip()[:80]])
    q.append(("decision_maker_role_discovery", f'"{company}" {role_terms} {signal_terms} site:linkedin.com/in OR site:linkedin.com/company'[:300]))
    if person_signal:
        person_roles = business_profiles.infer_decision_roles(person_signal, decision_role)
        person_role_terms = " ".join([*(business_profiles.DECISION_ROLES[r]["terms"] for r in person_roles), custom_role.strip()[:80]])
        q.append(("decision_maker_role_discovery_person_signal", f'"{company}" {person_role_terms} {person_signal[:100]} site:linkedin.com/in OR site:linkedin.com/company'[:300]))
    return [(kind, text) for kind, text in q if company]


def decision_maker_name(row: dict) -> str:
    first = business_profiles.row_value(row, "decision_maker_first_name", "contact_first_name", "first_name", "contact_first")
    last = business_profiles.row_value(row, "decision_maker_last_name", "contact_last_name", "last_name", "contact_last")
    full = business_profiles.row_value(row, "decision_maker_name", "decision_maker", "contact_name", "person")
    return f"{first} {last}".strip() or full


def _domain(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urllib.parse.urlparse(value if "://" in value else "//" + value)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return host


def _ratio(expected: set[str], observed: set[str]) -> tuple[float, list[str]]:
    matched = sorted(expected & observed)
    return (len(matched) / len(expected) if expected else 0.0), matched


def _publication_date(title: str, snippet: str, date_hint: str = "") -> dict:
    """Extract only an explicit or relative publication date; search time is not publication time."""
    text = html.unescape(f"{date_hint or ''} {title or ''} {snippet or ''}")
    now = dt.datetime.now(dt.timezone.utc).date()
    published = None
    precision = "unknown"
    basis = ""
    iso = re.search(r"\b(20\d{2})-(0?[1-9]|1[0-2])-([0-2]?\d|3[01])\b", text)
    if iso:
        try:
            published = dt.date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
            precision, basis = "day", iso.group(0)
        except ValueError:
            pass
    if not published:
        month_day = re.search(r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(20\d{2})\b", text, re.IGNORECASE)
        if month_day:
            value = f"{month_day.group(1).rstrip('.')[:3]} {month_day.group(2)} {month_day.group(3)}"
            for fmt in ("%b %d %Y",):
                try:
                    published = dt.datetime.strptime(value, fmt).date()
                    precision, basis = "day", month_day.group(0)
                    break
                except ValueError:
                    continue
    if not published:
        month_year = re.search(r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(20\d{2})\b", text, re.IGNORECASE)
        if month_year:
            try:
                published = dt.datetime.strptime(f"{month_year.group(1).rstrip('.')[:3]} {month_year.group(2)}", "%b %Y").date().replace(day=1)
                precision, basis = "month", month_year.group(0)
            except ValueError:
                pass
    if not published:
        relative = re.search(r"\b(\d{1,3})\s+(day|week|month|year)s?\s+ago\b", text, re.IGNORECASE)
        if relative:
            amount = int(relative.group(1))
            unit = relative.group(2).lower()
            days = amount if unit == "day" else amount * 7 if unit == "week" else amount * 30 if unit == "month" else amount * 365
            published = now - dt.timedelta(days=days)
            precision, basis = f"relative_{unit}", relative.group(0)
        elif re.search(r"\byesterday\b", text, re.IGNORECASE):
            published, precision, basis = now - dt.timedelta(days=1), "relative_day", "yesterday"
        elif re.search(r"\btoday\b", text, re.IGNORECASE):
            published, precision, basis = now, "relative_day", "today"
    if not published:
        return {"publication_date": "", "date_precision": "unknown", "date_evidence": "",
                "freshness_status": "undated", "age_days": None, "freshness_score": 0.0}
    age_days = (now - published).days
    status = "future_dated" if age_days < 0 else "recent" if age_days <= 90 else "aging" if age_days <= 365 else "stale"
    score = 0.0 if age_days < 0 else 1.0 if age_days <= 90 else 0.55 if age_days <= 365 else 0.15
    return {"publication_date": published.isoformat(), "date_precision": precision, "date_evidence": basis,
            "freshness_status": status, "age_days": max(0, age_days), "freshness_score": score}


def _source_identity(row: dict, kind: str, url: str, text: str) -> dict:
    """Attach explicit company/person match cues before evidence reaches assessments."""
    observed = _tokens(text)
    company = business_profiles.row_value(row, "business", "company", "name", "current_company", "website", "domain")
    company_terms = _tokens(company)
    company_ratio, company_matches = _ratio(company_terms, observed)
    city_terms = _tokens(business_profiles.row_value(row, "city"))
    _, city_matches = _ratio(city_terms, observed)
    target_domain = _domain(business_profiles.row_value(row, "website", "domain", "company_website"))
    source_domain = _domain(url)
    direct_domain = bool(target_domain and source_domain and (source_domain == target_domain or source_domain.endswith("." + target_domain)))

    if kind in ("decision_maker_profile", "decision_maker_signal"):
        person_terms = _tokens(decision_maker_name(row))
        person_ratio, person_matches = _ratio(person_terms, observed)
        current_company = _tokens(business_profiles.row_value(row, "decision_maker_current_company", "current_company") or company)
        previous_company = _tokens(business_profiles.row_value(row, "decision_maker_last_company", "last_company", "previous_company"))
        context_matches = []
        for expected in (current_company, previous_company):
            ratio, matches = _ratio(expected, observed)
            if expected and ratio >= (0.67 if len(expected) > 1 else 1.0):
                context_matches = matches
                break
        name_ok = bool(person_terms and person_ratio >= (0.67 if len(person_terms) > 1 else 1.0))
        context_ok = bool(context_matches)
        matched = name_ok and context_ok
        return {
            "identity_subject": "person",
            "identity_match": "person_name_and_company" if matched else "weak",
            "identity_strength": "strong" if matched and len(person_terms) > 1 else "moderate" if matched else "insufficient",
            "identity_score": round(min(1.0, 0.55 * person_ratio + (0.45 if context_ok else 0)), 2),
            "person_name_match_ratio": round(person_ratio, 2),
            "matched_person_terms": person_matches,
            "matched_person_company_terms": context_matches,
            "matched_company_terms": company_matches,
            "matched_city_terms": city_matches,
            "matched_domain": direct_domain,
        }

    name_ok = bool(company_terms and company_ratio >= (0.67 if len(company_terms) > 1 else 1.0))
    location_support = bool(city_matches and company_ratio >= 0.5)
    matched = direct_domain or name_ok or location_support
    identity_match = "direct_domain" if direct_domain else "company_name_and_location" if name_ok and city_matches else "company_name" if name_ok else "company_and_location" if location_support else "weak"
    score = 1.0 if direct_domain else min(0.95, company_ratio + (0.15 if city_matches else 0))
    return {
        "identity_subject": "company",
        "identity_match": identity_match,
        "identity_strength": "strong" if direct_domain or (name_ok and city_matches) else "moderate" if matched else "insufficient",
        "identity_score": round(score, 2),
        "company_name_match_ratio": round(company_ratio, 2),
        "matched_company_terms": company_matches,
        "matched_city_terms": city_matches,
        "matched_domain": direct_domain,
        "target_domain": target_domain,
    }


def decision_maker_queries_for(row: dict, decision_maker: str = "any", custom_role: str = "") -> list[tuple[str, str]]:
    """Target a named professional and keep personal-profile evidence distinct from company evidence."""
    company = business_profiles.row_value(row, "business", "company", "name", "current_company")
    if not company:
        company = business_profiles.row_value(row, "website", "domain")
    person = decision_maker_name(row)
    if not company or not person:
        return []
    dm = business_profiles.DECISION_MAKER_PROFILES[decision_maker]
    current_position = business_profiles.row_value(row, "current_position", "contact_title", "decision_maker_title")[:80]
    last_position = business_profiles.row_value(row, "last_position", "previous_position", "decision_maker_last_position")[:80]
    current_company = (business_profiles.row_value(row, "decision_maker_current_company", "current_company") or company)[:100]
    last_company = business_profiles.row_value(row, "last_company", "previous_company", "decision_maker_last_company")[:100]
    history = " ".join(x for x in (current_position, current_company, last_position, last_company, dm["terms"], custom_role.strip()[:80]) if x)
    person_signal = business_profiles.row_value(row, "decision_maker_last_signal", "person_last_signal", "contact_recent_signal", "person_last_lead_signal")
    supplied_signal = person_signal or business_profiles.row_value(row, "last_lead_signal", "last_signal")
    signal_terms = re.sub(r"\s+", " ", supplied_signal)[:100] or "recent post interview announcement speaking"
    profile_query = f'"{person}" "{current_company}" {history} site:linkedin.com/in OR site:linkedin.com/posts'
    signal_query = f'"{person}" "{current_company}" {signal_terms} site:linkedin.com/posts OR site:linkedin.com/in'
    if last_company and last_company.casefold() != current_company.casefold():
        profile_query += f' OR "{person}" "{last_company}" {last_position} site:linkedin.com/in'
    return [("decision_maker_profile", profile_query[:300]), ("decision_maker_signal", signal_query[:300])]


def gather(row: dict, max_signals: int = 6, business_profile: str = "any", decision_maker: str = "any", legal_form: str = "any", decision_role: str = "signal_based", custom_role: str = "", search_provider: str = "duckduckgo", path_key: str = "any") -> tuple[list[dict], list[str]]:
    company = business_profiles.row_value(row, "business", "company", "name", "current_company", "website", "domain")
    searched_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    terms = _tokens(company)
    person = decision_maker_name(row)
    person_signal = business_profiles.row_value(row, "decision_maker_last_signal", "person_last_signal", "contact_recent_signal", "person_last_lead_signal")
    company_signal = business_profiles.row_value(row, "company_last_signal", "company_signal", "last_lead_signal", "last_signal")
    role_candidates = ([decision_role] if decision_role != "signal_based" else list(dict.fromkeys(
        (business_profiles.infer_decision_roles(person_signal) if person_signal else [])
        + (business_profiles.infer_decision_roles(company_signal) if company_signal else [])
    )))
    path = path_signals.profile(path_key)
    if decision_role == "signal_based":
        role_candidates = list(dict.fromkeys([*path["roles"], *role_candidates]))
    if not role_candidates:
        role_candidates = business_profiles.infer_decision_roles("", decision_role)
    role_match_terms = set().union(*(_tokens(business_profiles.DECISION_ROLES[r]["terms"]) for r in role_candidates), _tokens(custom_role))
    found, seen = [], {}
    errors = []
    queries = queries_for(row, business_profile, decision_maker, legal_form, decision_role, custom_role, path_key) + decision_maker_queries_for(row, decision_maker, custom_role)
    for kind, query in queries:
        try:
            results = search(query, provider=search_provider)
        except SearchProviderError as e:
            if str(e) not in errors:
                errors.append(str(e))
            continue
        except Exception as e:
            errors.append(type(e).__name__)
            continue
        for item in results:
            key = item["url"]
            if key in seen:
                seen[key].setdefault("query_matches", []).append({"type": kind, "query": query})
                continue
            text = f"{item['title']} {item['snippet']} {key}".lower()
            identity = _source_identity(row, kind, key, text)
            if identity["identity_strength"] == "insufficient":
                continue
            if kind.startswith("decision_maker_role_discovery") and not (role_match_terms & _tokens(text)):
                continue
            host = urllib.parse.urlparse(key).hostname or ""
            host = host.lower().removeprefix("www.")
            social = any(host == d or host.endswith("." + d) for d in SOCIAL_DOMAINS)
            source = {"id": f"S{len(found)+1:02d}", "type": kind, "query_matches": [{"type": kind, "query": query}], "social_platform_result": social,
                          **identity,
                          **_publication_date(item["title"], item["snippet"], item.get("publication_date_hint", "")),
                          "source_host": host, "title": item["title"], "snippet": item["snippet"], "url": key,
                          "query": query, "provider": item.get("provider", "DuckDuckGo public web results"), "retrieved_at": searched_at,
                          "match_terms": sorted(terms & _tokens(text)),
                          "matched_person_terms": identity.get("matched_person_terms", []),
                          "matched_person_company_terms": identity.get("matched_person_company_terms", [])}
            found.append(source)
            seen[key] = source
        time.sleep(1.0)
    company_found = [s for s in found if not s["type"].startswith("decision_maker")]
    person_found = [s for s in found if s["type"].startswith("decision_maker")]
    if person_found and max_signals > 1:
        selected = company_found[:max_signals - min(2, len(person_found))] + person_found[:2]
        return selected[:max_signals], errors
    return company_found[:max_signals], errors


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
            parsed = urllib.parse.urlparse(url)
            host = (parsed.hostname or "").lower().removeprefix("www.")
            target_domain = _domain(str(row.get("website") or row.get("domain") or ""))
            direct_domain = bool(target_domain and (host == target_domain or host.endswith("." + target_domain)))
            company_ratio = len(company_matches) / len(company_terms) if company_terms else 0.0
            contact_ratio = len(contact_matches) / len(contact_terms) if contact_terms else 0.0
            subject = "person" if kind == "professional_contact" else "company"
            identity_score = (0.55 * company_ratio + 0.45 * contact_ratio) if subject == "person" else (1.0 if direct_domain else company_ratio)
            identity_score = round(min(1.0, identity_score), 2)
            match_strength = "strong" if (subject == "person" and contact_ratio >= 0.67 and company_ratio >= 0.5) or (subject == "company" and (direct_domain or company_ratio >= 0.75)) else "moderate"
            freshness = _publication_date(item["title"], item["snippet"], item.get("publication_date_hint", ""))
            found.append({"id": f"P{len(found)+1:02d}", "type": kind, "identity_subject": subject,
                          "identity_match": "person_and_company_terms" if subject == "person" else "company_domain" if direct_domain else "company_name_terms",
                          "identity_strength": match_strength, "identity_score": identity_score,
                          "confidence_kind": "heuristic identity match score, not a probability",
                          "source_host": host, "social_platform_result": any(host == d or host.endswith("." + d) for d in SOCIAL_DOMAINS),
                          **freshness, "title": item["title"], "snippet": item["snippet"],
                          "url": url, "query": query, "provider": "DuckDuckGo public web results", "retrieved_at": checked_at,
                          "matched_company_terms": sorted(company_matches), "matched_contact_terms": sorted(contact_matches)})
        time.sleep(1.0)
    return found[:max_signals], errors


def build_herald_field_results(row: dict, signals: list[dict], search_provider: str) -> str:
    """Map research and reviewed-draft outputs to the shared field-result contract."""
    results = []
    now = row.get("herald_checked_at", "")
    provider_fee = 0.0 if search_provider == "duckduckgo" else None
    for subject in ("company", "person"):
        matching = [s for s in signals if s.get("identity_subject") == subject]
        field = f"{subject}_signal_evidence"
        if not matching:
            results.append(fr.make_result(field=field, status="not_found", observed_at=now,
                                          identity_subject=subject, miss_reason=f"No identity-matched {subject} search result was retained."))
        for signal in matching:
            results.append(fr.make_result(
                field=field, value={"title": signal.get("title", ""), "snippet": signal.get("snippet", ""), "type": signal.get("type", "")},
                status="candidate", source_type="public_web_search", source_name=signal.get("provider", search_provider),
                source_url=signal.get("url", ""), source_record_id=signal.get("id", ""), observed_at=signal.get("retrieved_at", now),
                publication_date=signal.get("publication_date", ""), freshness_status=signal.get("freshness_status", "undated"), age_days=signal.get("age_days"),
                identity_subject=subject, identity_match=signal.get("identity_match", ""), identity_strength=signal.get("identity_strength", "unknown"),
                identity_score=signal.get("identity_score"), identity_score_kind="heuristic identity score, not a probability",
                verification_status="unverified_search_snippet", verification_method="Open the source URL and review the full page.",
                cost_amount=provider_fee, cost_currency="USD" if provider_fee is not None else None,
                cost_units="search_provider_fee" if provider_fee is not None else "provider_query_cost_unknown",
                cost_quantity=0 if provider_fee is not None else None, cost_estimated=False if provider_fee is not None else None,
                miss_reason="Search result is a research candidate, not a verified event."))
    try:
        events_doc = json.loads(row.get("herald_signal_events") or "{}")
    except (ValueError, TypeError):
        events_doc = {}
    events = events_doc.get("events", []) if isinstance(events_doc, dict) else []
    for event in events if isinstance(events, list) else []:
        source = next((s for s in signals if s.get("id") == event.get("source_id")), {})
        subject = event.get("subject", "unknown")
        results.append(fr.make_result(
            field="lead_signal_event", value={"category": event.get("category", ""), "label": event.get("label", ""), "path_fit": event.get("path_fit", "general")},
            status="candidate", source_type=event.get("source_type", "signal_taxonomy"), source_name=source.get("provider", "lead CSV or public search"),
            source_url=event.get("url", ""), source_record_id=event.get("source_id", ""), observed_at=source.get("retrieved_at", now),
            publication_date=event.get("publication_date", ""), freshness_status=event.get("freshness_status", "undated"), age_days=source.get("age_days"),
            identity_subject=subject, identity_match=source.get("identity_match", "supplied lead context"),
            identity_strength=source.get("identity_strength", "unknown"), identity_score=source.get("identity_score"),
            identity_score_kind="heuristic identity score, not a probability" if source else "",
            verification_status="unverified_phrase_match", verification_method="matched a signal taxonomy cue; review source",
            cost_amount=provider_fee, cost_currency="USD" if provider_fee is not None else None,
            cost_units="search_provider_fee" if provider_fee is not None else "provider_query_cost_unknown",
            cost_quantity=0 if provider_fee is not None else None, cost_estimated=False if provider_fee is not None else None,
            miss_reason="Phrase match is a research cue, not a verified event."))
    for field in ("outreach_subject", "outreach_body"):
        value = row.get(field, "")
        evidence_ids = [x.strip() for x in (row.get("outreach_evidence") or "").split(",") if x.strip()]
        evidence = [s for s in signals if s.get("id") in evidence_ids]
        results.append(fr.make_result(
            field=field, value=value or None, status="candidate" if value and evidence else "not_found",
            source_type="local_ai" if value else "", source_name=row.get("outreach_model", "") if value else "",
            observed_at=row.get("herald_ai_reviewed_at", now) if value else "",
            verification_status="human_review_required" if value else "not_generated",
            verification_method="AI draft cites the following public research evidence; review before use." if value else "",
            cost_units="local_model_inference" if value else "", cost_estimated=False if value else None,
            candidates=[fr.source_ref(source_type="public_web_search", source_name=s.get("provider", ""), source_url=s.get("url", ""),
                                     source_record_id=s.get("id", ""), value={"title": s.get("title", ""), "snippet": s.get("snippet", "")}) for s in evidence],
            miss_reason="No cited AI draft value was produced." if not value else "AI output is a draft; human review is required."))
    for result in results:
        result.setdefault("metadata", {})["lane"] = "herald_research"
    return fr.dump_results(results)


def build_presence_field_results(signals: list[dict], checked_at: str) -> str:
    """Map public social search snippets to contract records without calling them verified reputation."""
    results = []
    if not signals:
        missing = fr.make_result(field="presence_social_signal", status="not_found", observed_at=checked_at,
                                 identity_subject="company", miss_reason="No identity-matched public social result was retained.",
                                 verification_status="not_found", metadata={"lane": "presence_research"})
        return fr.dump_results([missing])
    for signal in signals:
        subject = signal.get("identity_subject", "company")
        results.append(fr.make_result(
            field="presence_person_signal" if subject == "person" else "presence_company_signal",
            value={"title": signal.get("title", ""), "snippet": signal.get("snippet", ""), "type": signal.get("type", "")},
            status="candidate", source_type="public_web_search", source_name=signal.get("provider", "DuckDuckGo public web results"),
            source_url=signal.get("url", ""), source_record_id=signal.get("id", ""), observed_at=signal.get("retrieved_at", checked_at),
            publication_date=signal.get("publication_date", ""), freshness_status=signal.get("freshness_status", "undated"), age_days=signal.get("age_days"),
            identity_subject=subject, identity_match=signal.get("identity_match", ""), identity_strength=signal.get("identity_strength", "unknown"),
            identity_score=signal.get("identity_score"), identity_score_kind=signal.get("confidence_kind", "heuristic, not a probability"),
            verification_status="unverified_search_snippet", verification_method="Open the source URL and review the full page.",
            cost_amount=0.0, cost_currency="USD", cost_units="search_provider_fee", cost_quantity=0, cost_estimated=False,
            miss_reason="Search result is a candidate public profile/post, not verified identity or reputation."))
    for result in results:
        result.setdefault("metadata", {})["lane"] = "presence_research"
    return fr.dump_results(results)


def _presence_history_key(row: dict) -> str:
    """Hash stable lead identity so locally retained comparison history stores no clear lead identifiers."""
    parts = (
        (row.get("website") or row.get("domain") or "").strip().casefold(),
        (row.get("business") or row.get("company") or row.get("Company") or row.get("name") or "").strip().casefold(),
        (row.get("contact_name") or row.get("decision_maker") or row.get("person") or "").strip().casefold(),
        (row.get("email") or row.get("Email") or "").strip().casefold(),
    )
    if not any(parts):
        return ""
    identity = "|".join(parts)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _load_presence_history() -> dict:
    try:
        data = json.loads(PRESENCE_HISTORY.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("leads"), dict) else {"schema": "dbi.presence-history.v1", "leads": {}}
    except (OSError, ValueError, TypeError):
        return {"schema": "dbi.presence-history.v1", "leads": {}}


def _presence_comparison(previous: dict | None, signals: list[dict], checked_at: str, search_errors: list[str]) -> dict:
    current = {s.get("url", ""): s for s in signals if s.get("url")}
    old_sources = {s.get("url", ""): s for s in (previous or {}).get("sources", []) if s.get("url")}
    new_urls = sorted(set(current) - set(old_sources)) if previous else []
    not_returned = sorted(set(old_sources) - set(current)) if previous else []
    changed_urls = sorted(url for url in set(current) & set(old_sources) if (
        current[url].get("title", "") != old_sources[url].get("title", "") or
        hashlib.sha256(current[url].get("snippet", "").encode("utf-8")).hexdigest() != old_sources[url].get("snippet_hash", "") or
        current[url].get("publication_date", "") != old_sources[url].get("publication_date", ""))) if previous else []
    if search_errors:
        status = "partial_check" if previous else "partial_first_check"
    elif not previous:
        status = "first_check"
    else:
        status = "compared"
    summary = "First check; no earlier snapshot" if status == "first_check" else (
        f"{len(new_urls)} newly returned; {len(changed_urls)} snippet/title changed; {len(not_returned)} previously seen not returned" if status == "compared" else
        f"Partial search; {len(new_urls)} newly returned; absence is inconclusive" if previous else
        "Partial first check; establish a complete baseline before comparing")
    return {"presence_comparison_status": status, "presence_change_summary": summary,
            "presence_new_source_urls": "\n".join(new_urls),
            "presence_changed_source_urls": "\n".join(changed_urls) if status == "compared" else "",
            "presence_not_returned_urls": "\n".join(not_returned) if status == "compared" else "",
            "presence_previous_checked_at": (previous or {}).get("checked_at", ""),
            "_snapshot": {"checked_at": checked_at, "sources": [
                {"url": s.get("url", ""), "subject": s.get("identity_subject", "company"), "title": s.get("title", "")[:240],
                 "snippet_hash": hashlib.sha256(s.get("snippet", "").encode("utf-8")).hexdigest(),
                 "publication_date": s.get("publication_date", ""), "freshness_status": s.get("freshness_status", "undated")}
                for s in signals if s.get("url")][:8]}}


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
    evidence = [{"id": s["id"], "subject": s.get("identity_subject", "unknown"),
                 "evidence_type": s.get("type", "business"), "identity_match": s.get("identity_match", ""),
                 "identity_strength": s.get("identity_strength", "unknown"), "identity_score": s.get("identity_score", 0),
                 "publication_date": s.get("publication_date", ""), "freshness_status": s.get("freshness_status", "undated"),
                 "matched_company_terms": s.get("matched_company_terms", []), "matched_person_terms": s.get("matched_person_terms", []),
                 "source_host": s.get("source_host", ""), "title": s["title"], "snippet": s["snippet"], "url": s["url"]} for s in signals[:6]]
    company = business_profiles.row_value(row, "business", "company", "Company", "name")
    person_context = {
        "first_name": business_profiles.row_value(row, "decision_maker_first_name", "contact_first_name", "first_name", "contact_first"),
        "last_name": business_profiles.row_value(row, "decision_maker_last_name", "contact_last_name", "last_name", "contact_last"),
        "current_position": business_profiles.row_value(row, "current_position", "contact_title", "decision_maker_title"),
        "previous_position": business_profiles.row_value(row, "last_position", "previous_position", "decision_maker_last_position"),
        "current_company": business_profiles.row_value(row, "decision_maker_current_company", "current_company") or company,
        "previous_company": business_profiles.row_value(row, "decision_maker_last_company", "last_company", "previous_company"),
        "lead_signal": business_profiles.row_value(row, "decision_maker_last_signal", "person_last_signal", "contact_recent_signal", "person_last_lead_signal"),
    }
    company_context = {
        "name": company,
        "lead_signal": business_profiles.row_value(row, "company_last_signal", "company_signal", "last_lead_signal", "last_signal"),
    }
    path_context = path_signals.profile(row.get("enrichment_target_path", "any"))
    try:
        candidate_context = json.loads(row.get("herald_people_candidates") or "[]")[:5]
    except (ValueError, TypeError):
        candidate_context = []
    user = {"company": company, "person_context": person_context, "company_context": company_context,
            "city": business_profiles.row_value(row, "city"), "offer": business_profiles.row_value(row, "offer", "gap_line", "lead_why"),
            "target_business_profile": row.get("enrichment_target_profile", "any"), "target_decision_maker": row.get("enrichment_target_decision_maker", "any"),
            "target_role": row.get("enrichment_target_role", "signal_based"), "signal_based_role_candidates": row.get("herald_role_candidates", "[]"),
            "target_path": row.get("enrichment_target_path", "any"), "path_guidance": path_context,
            "legal_form_search_hint": row.get("enrichment_target_legal_form", "any"),
            "ranked_people_candidates": candidate_context,
            "role_evidence_assessment": row.get("herald_role_assessment", "{}"), "evidence": evidence,
            "allowed_role_labels": [item.get("label", "") for item in json.loads(row.get("herald_role_candidates") or "[]") if isinstance(item, dict)]}
    payload = json.dumps({"model": model, "stream": False, "keep_alive": "30m", "format": "json",
        "options": {"num_ctx": 8192, "num_predict": 450, "temperature": 0.2},
        "messages": [{"role": "system", "content": (
            "Review the evidence and draft one honest, concise first-contact business email based ONLY on the supplied evidence and offer. "
            "Keep company evidence, named-person evidence, personal lead signals, and company lead signals distinct. "
            "A signal supplied as search context is not proof: mention it only if an identity-matched source snippet independently supports it. "
            "Do not describe aging or stale evidence as recent; when a source date is absent, do not imply recency. "
            "Prefer a supported current position over a previous position; never present a previous role as current. "
            "Use a candidate's name or role only when person evidence is explicitly matched; company role-discovery results alone do not verify an individual's identity. "
            "Search snippets can be wrong: do not state a claim as fact unless its source ID is returned. Target profiles and heuristic assessments are review aids, not verified company facts; "
            "never claim a business is a franchise, SaaS company, enterprise or C-Corp/S-Corp without clear supplied evidence. Keep company facts and named-person facts distinct. "
            "Only describe a current or former position/company when the cited evidence explicitly supports it. Never claim prior contact, "
            "personal familiarity, urgency, private knowledge, or guaranteed results. If evidence is weak, return empty subject/body. "
            "Also return a source-grounded review: company_summary and company_evidence_ids; person_summary and person_evidence_ids; "
            "role_observations as objects with role (choose only an exact allowed_role_labels value) and evidence_ids; and open_questions as short strings. "
            "Summaries must be empty when there is no matching subject evidence. Use only supplied source IDs, and never use a person source to support a company summary or vice versa. "
            "Do not include citations in email text. Return JSON only with subject, body, evidence_ids, company_summary, company_evidence_ids, "
            "person_summary, person_evidence_ids, role_observations, and open_questions. The body should be under 90 words, plain and low-pressure, "
            "with one clear question and an easy opt-out."
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
    company_ids = {s["id"] for s in signals if s.get("identity_subject") == "company"}
    person_ids = {s["id"] for s in signals if s.get("identity_subject") == "person"}
    used = [x for x in result.get("evidence_ids", []) if isinstance(x, str) and x in ids]
    subject = re.sub(r"\s+", " ", str(result.get("subject", ""))).strip()[:120]
    body = str(result.get("body", "")).strip()[:1200]
    cited = [s for s in signals if s.get("id") in used]
    evidence_detail = [{"id": s["id"], "subject": s.get("identity_subject", "unknown"),
                        "evidence_type": s.get("type", ""), "identity_match": s.get("identity_match", ""),
                        "identity_strength": s.get("identity_strength", "unknown"), "identity_score": s.get("identity_score", 0),
                        "source_host": s.get("source_host", ""),
                        "title": s.get("title", ""), "url": s.get("url", ""),
                        "publication_date": s.get("publication_date", ""), "freshness_status": s.get("freshness_status", "undated"),
                        "retrieved_at": s.get("retrieved_at", "")} for s in cited]
    basis = "; ".join(f"{s['id']} ({s.get('identity_subject', 'unknown')}: {s.get('identity_strength', 'unknown')} {s.get('identity_match', 'match')})" for s in cited)
    def valid_ids(value, allowed):
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(item for item in value if isinstance(item, str) and item in allowed))
    company_review_ids = valid_ids(result.get("company_evidence_ids"), company_ids)
    person_review_ids = valid_ids(result.get("person_evidence_ids"), person_ids)
    company_summary = str(result.get("company_summary", "")).strip()[:500] if company_review_ids else ""
    person_summary = str(result.get("person_summary", "")).strip()[:500] if person_review_ids else ""
    role_review = []
    try:
        role_assessment = json.loads(row.get("herald_role_assessment") or "{}")
    except (ValueError, TypeError):
        role_assessment = {}
    allowed_roles = {str(item.get("label", "")): set(item.get("evidence_ids", []))
                     for item in role_assessment.get("roles", []) if isinstance(item, dict)}
    for item in result.get("role_observations", []) if isinstance(result.get("role_observations", []), list) else []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        role_ids = valid_ids(item.get("evidence_ids"), ids)
        validated_role_ids = [source_id for source_id in role_ids if source_id in allowed_roles.get(role, set())]
        if validated_role_ids:
            role_review.append({"role": role, "evidence_ids": validated_role_ids})
    open_questions = [re.sub(r"\s+", " ", str(question)).strip()[:240]
                      for question in result.get("open_questions", []) if isinstance(question, str)][:5] if isinstance(result.get("open_questions", []), list) else []
    has_review = bool(company_summary or person_summary or role_review or open_questions)
    output = {}
    if has_review:
        ai_review = {"company_summary": company_summary, "company_evidence_ids": company_review_ids,
                     "person_summary": person_summary, "person_evidence_ids": person_review_ids,
                     "role_observations": role_review, "open_questions": open_questions,
                     "basis": "Local-model synthesis constrained to returned public snippets; verify all cited sources."}
        output.update({"herald_ai_review": json.dumps(ai_review, ensure_ascii=False, separators=(",", ":")),
                       "herald_ai_reviewed_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                       "herald_ai_review_model": model})
    if subject and body and used:
        output.update({"outreach_subject": subject, "outreach_body": body, "outreach_evidence": ", ".join(used),
                       "outreach_evidence_detail": json.dumps(evidence_detail, ensure_ascii=False, separators=(",", ":")),
                       "outreach_personalization_basis": basis, "outreach_model": model})
    return output


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def enrich_file(source: str, engine: str = "", max_rows: int = 100, use_ai: bool = True,
                business_profile: str = "any", decision_maker: str = "any", legal_form: str = "any", decision_role: str = "signal_based", custom_role: str = "", search_provider: str = "duckduckgo", path_key: str = "any") -> str:
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
    try:
        bp, dm, lf = business_profiles.normalize_profiles(business_profile, decision_maker, legal_form)
    except ValueError as e:
        raise ValueError(str(e)) from None
    if decision_role not in business_profiles.DECISION_ROLES:
        raise ValueError("Choose a decision-maker role from the listed options.")
    if search_provider not in ("duckduckgo", "brave"):
        raise ValueError("Choose DuckDuckGo or Brave Search as the public search provider.")
    selected_path = path_signals.known_path(path_key)
    if engine:
        from . import engines
        config = engines.load(engine)
        engine_path = path_signals.known_path(config.get("path", ""))
        if engine_path and selected_path and engine_path != selected_path:
            raise ValueError(f"The selected Engine follows the {path_signals.profile(engine_path)['label']} path. Choose that path or leave the path selector on General.")
        selected_path = engine_path or selected_path
    path = path_signals.profile(selected_path)
    custom_role = re.sub(r"[^A-Za-z0-9 /&'-]", "", custom_role).strip()[:80]
    strategy = business_profiles.strategy_text(business_profile, decision_maker, legal_form, decision_role) + (f" Engine path focus: {path['label']}: {path['method']}" if selected_path else "") + (f" Custom role target: {custom_role}." if custom_role else "")
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
        row["enrichment_target_profile"] = business_profile
        row["enrichment_target_decision_maker"] = decision_maker
        row["enrichment_target_role"] = custom_role or decision_role
        row["enrichment_target_path"] = selected_path or "any"
        person_signal = business_profiles.row_value(row, "decision_maker_last_signal", "person_last_signal", "contact_recent_signal", "person_last_lead_signal")
        company_signal = business_profiles.row_value(row, "company_last_signal", "company_signal", "last_lead_signal", "last_signal")
        role_origins = {}
        if decision_role != "signal_based":
            role_origins[decision_role] = ["user_selected"]
        else:
            for role in path["roles"] if selected_path else ():
                role_origins.setdefault(role, []).append("engine_path")
            if person_signal:
                for role in business_profiles.infer_decision_roles(person_signal):
                    role_origins.setdefault(role, []).append("person_signal")
            if company_signal:
                for role in business_profiles.infer_decision_roles(company_signal):
                    role_origins.setdefault(role, []).append("company_signal")
        roles = list(role_origins)
        if not roles:
            roles = business_profiles.infer_decision_roles("", decision_role)
            role_origins = {r: ["default_fallback"] for r in roles}
        role_items = [{"role": r, "label": business_profiles.DECISION_ROLES[r]["label"],
                       "terms": business_profiles.DECISION_ROLES[r]["terms"], "derived_from": role_origins.get(r, [])} for r in roles]
        if custom_role:
            role_items.insert(0, {"role": "custom", "label": custom_role, "terms": custom_role, "derived_from": ["custom_role"]})
        row["herald_role_candidates"] = json.dumps(role_items, ensure_ascii=False, separators=(",", ":"))
        row["herald_people_candidates"] = ""
        row["enrichment_target_legal_form"] = legal_form
        row["enrichment_search_strategy"] = strategy
        signals, row_errors = gather(row, business_profile=business_profile, decision_maker=decision_maker, legal_form=legal_form, decision_role=decision_role, custom_role=custom_role, search_provider=search_provider, path_key=selected_path or "any")
        errors.extend(row_errors)
        identity_summary = {}
        for subject in ("company", "person"):
            subject_signals = [s for s in signals if s.get("identity_subject") == subject]
            counts = {strength: sum(s.get("identity_strength") == strength for s in subject_signals)
                      for strength in ("strong", "moderate", "insufficient")}
            hosts = sorted({s.get("source_host", "") for s in subject_signals if s.get("source_host")})
            identity_summary[subject] = {
                "matched_sources": len(subject_signals), "strength_counts": counts,
                "distinct_source_hosts": len(hosts), "source_hosts": hosts,
                "best_match_score": max((s.get("identity_score", 0) for s in subject_signals), default=0),
                "match_types": list(dict.fromkeys(s.get("identity_match", "") for s in subject_signals)),
            }
        row["herald_identity_summary"] = json.dumps(identity_summary, ensure_ascii=False, separators=(",", ":"))
        company_signals = [s for s in signals if s.get("identity_subject") == "company"]
        person_signals = [s for s in signals if s.get("identity_subject") == "person"]
        row["herald_findings"] = row["research_findings"] = "\n".join(f"[{s['id']}] {s['title']} | {s['snippet']}" for s in signals)
        sources_json = json.dumps(signals, ensure_ascii=False, separators=(",", ":"))
        row["herald_sources"] = row["research_sources"] = sources_json
        row["herald_company_findings"] = "\n".join(f"[{s['id']}] {s['title']} | {s['snippet']}" for s in company_signals)
        row["herald_company_sources"] = json.dumps(company_signals, ensure_ascii=False, separators=(",", ":"))
        row["herald_person_findings"] = "\n".join(f"[{s['id']}] {s['title']} | {s['snippet']}" for s in person_signals)
        row["herald_person_sources"] = json.dumps(person_signals, ensure_ascii=False, separators=(",", ":"))
        checked_at = signals[0]["retrieved_at"] if signals else dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        assessment = classification.assess(signals, roles, custom_role, legal_form, checked_at, context=row)
        row["herald_people_candidates"] = json.dumps(assessment["people_candidates"], ensure_ascii=False, separators=(",", ":"))
        row["herald_business_assessment"] = json.dumps(assessment["business_profiles"], ensure_ascii=False, separators=(",", ":"))
        row["herald_role_assessment"] = json.dumps({"roles": assessment["decision_maker_roles"], "people": assessment["people_candidates"]}, ensure_ascii=False, separators=(",", ":"))
        annotated_events = []
        for event in assessment["signal_events"]:
            event = dict(event)
            category = event.get("category", "")
            event["path_fit"] = "priority" if category in path["priority"] else "supporting" if category in path["supporting"] else "general"
            event["path_label"] = path["label"]
            annotated_events.append(event)
        row["herald_signal_events"] = json.dumps({"basis": assessment["signal_events_basis"], "path_focus": {"key": selected_path or "any", "label": path["label"], "method": path["method"], "pain": path["pain"], "buyer": path["buyer"], "revenue_model": path["revenue_model"], "proof_metrics": path["proof_metrics"], "priority_categories": path["priority"], "supporting_categories": path["supporting"]}, "events": annotated_events}, ensure_ascii=False, separators=(",", ":"))
        row["herald_legal_form_assessment"] = json.dumps(assessment["legal_form_mentions"], ensure_ascii=False, separators=(",", ":"))
        row["herald_assessed_at"] = checked_at
        row["herald_assessment_note"] = assessment["basis"]
        row["herald_checked_at"] = row["research_searched_at"] = checked_at
        row["herald_status"] = row["research_status"] = "business evidence found" if signals else "no matching business results"
        row.update({k: "" for k in ("herald_ai_review", "herald_ai_reviewed_at", "herald_ai_review_model", "outreach_subject", "outreach_body", "outreach_evidence", "outreach_evidence_detail", "outreach_personalization_basis", "outreach_model")})
        if model and signals:
            try:
                generated = draft(row, signals, model)
                if generated:
                    row.update(generated)
                    if generated.get("outreach_body"):
                        row["herald_status"] = row["research_status"] = "draft ready for human review"
                        drafted += 1
                    elif generated.get("herald_ai_review"):
                        row["herald_status"] = row["research_status"] = "local AI evidence review ready"
            except Exception as e:
                errors.append(type(e).__name__)
        row["field_results"] = fr.merge_results(row.get("field_results"), build_herald_field_results(row, signals, search_provider))
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
    processed = out[:min(len(rows), max_rows)]
    collected_sources = [source for row in processed for source in json.loads(row.get("herald_sources") or "[]")]
    dated_sources = sum(bool(source.get("publication_date")) for source in collected_sources)
    stale_sources = sum(source.get("freshness_status") == "stale" for source in collected_sources)
    report = [f"# Lead signals: {p.name}", "", f"- Searched: {min(len(rows), max_rows)} of {len(rows)} rows",
              f"- Public search provider: {search_provider}",
              f"- Engine path focus: {path['label']}", f"- Path method: {path['method']}", f"- Likely buyer to research: {path['buyer']}", f"- Commercial model to verify: {path['revenue_model']}",
              f"- Brave API queries used: {BRAVE_SEARCH_REQUESTS}" if search_provider == "brave" else "- Brave API queries used: 0",
              f"- Business profile target: {bp['label']}", f"- Decision-maker path: {dm['label']}", f"- Decision-maker role target: {custom_role or business_profiles.DECISION_ROLES[decision_role]['label']}", f"- Legal-form search: {lf['label']}",
              "- Target selections guide search queries only; they are not business classifications or legal verification.",
              f"- Leads with public results: {sum(bool(r['research_sources']) for r in out[:min(len(rows), max_rows)])}",
              f"- Leads with at least one strong identity match: {sum(bool(r.get('herald_identity_summary') and any(json.loads(r['herald_identity_summary'])[subject]['strength_counts']['strong'] for subject in ('company', 'person'))) for r in out[:min(len(rows), max_rows)])}",
              f"- Sources with an explicit or relative publication date: {dated_sources} of {len(collected_sources)}",
              f"- Sources marked stale by the date heuristic: {stale_sources}",
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
    history = _load_presence_history()
    previous_history = dict(history["leads"])
    next_history = dict(previous_history)
    for i, original in enumerate(rows[:max_rows], 1):
        row = dict(original)
        normalized = normalized_rows[i - 1] if i <= len(normalized_rows) else {}
        for key in ("business", "website", "city", "contact_name"):
            if normalized.get(key) and not row.get(key):
                row[key] = normalized[key]
        print(f"[{i}/{min(len(rows), max_rows)}] checking public social presence for {row.get('business') or row.get('website') or 'lead'}", file=sys.stderr, flush=True)
        signals, row_errors = gather_presence(row)
        errors.extend(row_errors)
        checked_at = signals[0]["retrieved_at"] if signals else dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        history_key = _presence_history_key(row)
        comparison = _presence_comparison(previous_history.get(history_key) if history_key else None, signals, checked_at, row_errors)
        snapshot = comparison.pop("_snapshot")
        if history_key and not row_errors:
            next_history[history_key] = snapshot
        row["presence_signals"] = json.dumps(signals, ensure_ascii=False, separators=(",", ":"))
        row["presence_sources"] = "\n".join(f"[{s['id']}] {s['title']} | {s['url']}" for s in signals)
        row["presence_checked_at"] = checked_at
        row["presence_status"] = "public professional/social results found" if signals else "no matching public social results"
        row.update(comparison)
        row["field_results"] = fr.merge_results(row.get("field_results"), build_presence_field_results(signals, checked_at))
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
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=PRESENCE_HISTORY_DAYS)
    kept_history = {}
    for key, snapshot in next_history.items():
        try:
            snapshot_date = dt.datetime.fromisoformat(str(snapshot.get("checked_at", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if snapshot_date >= cutoff:
            kept_history[key] = snapshot
    try:
        PRESENCE_HISTORY.parent.mkdir(parents=True, exist_ok=True)
        temporary_history = PRESENCE_HISTORY.with_suffix(".tmp")
        temporary_history.write_text(json.dumps({"schema": "dbi.presence-history.v1", "retention_days": PRESENCE_HISTORY_DAYS,
                                                  "leads": kept_history}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary_history.replace(PRESENCE_HISTORY)
    except OSError as error:
        errors.append(f"local history could not be saved ({type(error).__name__})")
    collected = [signal for row in out[:min(len(rows), max_rows)] for signal in json.loads(row.get("presence_signals") or "[]")]
    report = [f"# Presence public social signals: {p.name}", "", f"- Checked: {min(len(rows), max_rows)} of {len(rows)} rows",
              f"- Rows with public social results: {sum(bool(r['presence_signals']) for r in out[:min(len(rows), max_rows)])}",
              f"- Results with publication date evidence: {sum(bool(s.get('publication_date')) for s in collected)} of {len(collected)}",
              f"- Results marked stale by the date heuristic: {sum(s.get('freshness_status') == 'stale' for s in collected)}",
              f"- Newly returned source links: {sum(len((r.get('presence_new_source_urls') or '').splitlines()) for r in out[:min(len(rows), max_rows)])}",
              f"- Previously seen links with changed snippets or titles: {sum(len((r.get('presence_changed_source_urls') or '').splitlines()) for r in out[:min(len(rows), max_rows)])}",
              f"- Previously seen links not returned in a complete check: {sum(len((r.get('presence_not_returned_urls') or '').splitlines()) for r in out[:min(len(rows), max_rows)])}",
              "- No outreach copy was drafted or sent.", "", "## Review before use", "",
              "Results are search snippets, not verified identity or reputation. Review each source directly. Only public professional and business-related results are included; do not infer sensitive or personal traits.", ""]
    if errors:
        report += ["Search errors: " + ", ".join(errors[:12]), ""]
    dest.with_suffix(".md").write_text("\n".join(report), encoding="utf-8")
    shelf = {"kind": "presence-signals", "v": 2, "business": f"{p.stem} ({min(len(rows), max_rows)} leads)"[:120],
             "made": dt.date.today().isoformat(), "source": "Public professional/business social search",
             "engine": engine or "", "leads": []}
    for i, row in enumerate(out[:min(len(rows), max_rows)]):
        signals = json.loads(row.get("presence_signals") or "[]")
        if not signals or len(shelf["leads"]) >= 60:
            continue
        normalized = normalized_rows[i] if i < len(normalized_rows) else {}
        shelf["leads"].append({
            "ref": f"{stem}-{i+1}",
            "business": str(normalized.get("business") or row.get("business") or row.get("company") or "")[:160],
            "website": str(normalized.get("website") or row.get("website") or "")[:500],
            "city": str(normalized.get("city") or row.get("city") or "")[:120],
            "contact_name": str(normalized.get("contact_name") or row.get("contact_name") or "")[:160],
            "contact_title": str(normalized.get("contact_title") or row.get("contact_title") or "")[:160],
            "email": str(normalized.get("email") or row.get("email") or "")[:254],
            "status": row.get("presence_status", ""),
            "comparison": {key: row.get(key, "") for key in ("presence_comparison_status", "presence_change_summary", "presence_previous_checked_at", "presence_new_source_urls", "presence_changed_source_urls", "presence_not_returned_urls")},
            "signals": signals[:8],
        })
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
