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
from . import enrichment_profiles
from . import field_results as fr
from . import enrichment_usage as eu
from .common import LISTS, ROOT

USER_AGENT = "DFamociousHQ/1.0 (local user-requested business research)"
OUT_FIELDS = ["herald_findings", "herald_sources", "herald_checked_at", "herald_status",
              "research_findings", "research_sources", "research_searched_at", "research_status",
              "herald_company_findings", "herald_company_sources", "herald_person_findings", "herald_person_sources",
              "herald_business_assessment", "herald_role_assessment", "herald_legal_form_assessment", "herald_assessed_at", "herald_assessment_note",
              "herald_identity_summary",
              "herald_ai_review", "herald_ai_reviewed_at", "herald_ai_review_model",
              "outreach_subject", "outreach_body", "outreach_evidence", "outreach_evidence_detail", "outreach_personalization_basis", "outreach_model",
              "herald_role_candidates", "herald_people_candidates", "herald_signal_events", "dse_path_outcome", "dse_path_ai_advice", "dse_path_ai_advice_status", "enrichment_target_profile", "enrichment_target_decision_maker", "enrichment_target_role", "enrichment_target_legal_form", "enrichment_target_path", "enrichment_search_strategy", "enrichment_profile", "field_results"]
OUT_FIELDS.insert(-1, "herald_search_waterfall")
HERALD_MONITOR_FIELDS = ["herald_comparison_status", "herald_change_summary", "herald_new_source_urls", "herald_changed_source_urls", "herald_not_returned_urls", "herald_previous_checked_at", "herald_change_action", "herald_change_categories", "herald_change_sources", "herald_change_evidence"]
OUT_FIELDS[-1:-1] = HERALD_MONITOR_FIELDS
PRESENCE_FIELDS = ["presence_signals", "presence_sources", "presence_checked_at", "presence_status", "enrichment_profile",
                   "presence_comparison_status", "presence_change_summary", "presence_new_source_urls", "presence_changed_source_urls", "presence_not_returned_urls", "presence_previous_checked_at", "presence_change_action", "presence_change_categories", "presence_change_sources", "presence_change_evidence", "field_results"]
PRESENCE_FIELDS.insert(-1, "presence_search_waterfall")
PRESENCE_HISTORY = ROOT / "data" / "presence-history.json"
HERALD_HISTORY = ROOT / "data" / "herald-signal-history.json"
PRESENCE_HISTORY_DAYS = 180
SOCIAL_DOMAINS = ("linkedin.com", "instagram.com", "facebook.com", "x.com", "twitter.com", "youtube.com", "tiktok.com")
STOP = {"the", "and", "for", "with", "company", "business", "services", "service", "inc", "llc", "ltd", "co"}
BRAVE_SEARCH_REQUESTS = 0
BRAVE_USAGE_WARNINGS: list[str] = []


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


def _record_brave_usage(lane: str, outcome: str, cost_per_1000: float | None,
                        status_code: int | None = None) -> None:
    cfg = {"name": "brave_search"}
    if cost_per_1000 is not None:
        cfg.update({"cost_per_call": cost_per_1000 / 1000, "cost_currency": "USD",
                    "cost_basis": "user_declared_price_per_1000_requests"})
    warning = eu.record_call(cfg, lane, outcome, status_code)
    if warning and warning not in BRAVE_USAGE_WARNINGS:
        BRAVE_USAGE_WARNINGS.append(warning)


def _brave_request_cap() -> int:
    try:
        cap = int(os.environ.get("DSE_BRAVE_SEARCH_QUERY_LIMIT", "150"))
    except ValueError:
        cap = 150
    return max(0, min(1000, cap))


def search(query: str, limit: int = 2, provider: str = "duckduckgo", lane: str = "herald_signals",
           brave_cost_per_1000: float | None = None) -> list[dict]:
    """Fetch search snippets only; the selected provider is explicit and recorded."""
    global BRAVE_SEARCH_REQUESTS
    provider = (provider or "duckduckgo").strip().casefold()
    if provider not in ("duckduckgo", "brave"):
        raise SearchProviderError("Choose DuckDuckGo or Brave Search as the public search provider.")
    if provider == "brave":
        api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
        if not api_key:
            raise SearchProviderError("Brave Search was selected, but BRAVE_SEARCH_API_KEY is not set on this PC.")
        request_limit = _brave_request_cap()
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
                status_code = getattr(response, "status", None)
                data = json.loads(response.read(1_500_000))
        except urllib.error.HTTPError as error:
            _record_brave_usage(lane, "http_error", brave_cost_per_1000, error.code)
            raise SearchProviderError(f"Brave Search API returned HTTP {error.code}.") from None
        except (urllib.error.URLError, TimeoutError):
            _record_brave_usage(lane, "request_error", brave_cost_per_1000)
            raise SearchProviderError("Brave Search API could not be reached from this PC.") from None
        except (ValueError, TypeError):
            _record_brave_usage(lane, "invalid_response", brave_cost_per_1000, locals().get("status_code"))
            raise SearchProviderError("Brave Search API returned an unreadable response.") from None
        except Exception as error:
            _record_brave_usage(lane, "request_error", brave_cost_per_1000)
            raise SearchProviderError(f"Brave Search API request failed ({type(error).__name__}).") from None
        web_payload = data.get("web") if isinstance(data, dict) else None
        if not isinstance(data, dict) or (web_payload is not None and not isinstance(web_payload, dict)) or (isinstance(web_payload, dict) and not isinstance(web_payload.get("results", []), list)):
            _record_brave_usage(lane, "invalid_response", brave_cost_per_1000, status_code)
            raise SearchProviderError("Brave Search API returned an unreadable response.")
        _record_brave_usage(lane, "success", brave_cost_per_1000, status_code)
        out, seen = [], set()
        for item in (data.get("web") or {}).get("results", []):
            if not isinstance(item, dict):
                continue
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


def _query_fingerprints(source: dict) -> list[dict]:
    """Keep search-rung coverage auditable without retaining the searched text in the snapshot."""
    matches = source.get("query_matches") if isinstance(source.get("query_matches"), list) else []
    if not matches and source.get("type") and source.get("query"):
        matches = [{"type": source.get("type"), "query": source.get("query")}]
    seen, out = set(), []
    for match in matches:
        if not isinstance(match, dict) or not match.get("type") or not match.get("query"):
            continue
        rung = str(match["type"])[:48]
        normalized = " ".join(str(match["query"]).split()).casefold()
        fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        key = (rung, fingerprint)
        if key not in seen:
            seen.add(key)
            out.append({"rung": rung, "fingerprint": fingerprint})
    return out[:8]


_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid", "vero_id"}


def _canonical_monitor_url(url: str) -> str:
    """Normalize tracking-only URL differences for monitoring identity, not for display/open links."""
    raw = str(url or "").strip()
    try:
        parsed = urllib.parse.urlsplit(raw)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return raw
        scheme = parsed.scheme.lower()
        host = parsed.hostname.lower()
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = parsed.port
        netloc = host
        if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
            netloc = f"{netloc}:{port}"
        query = [(key, value) for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
                 if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_QUERY_KEYS]
        query.sort(key=lambda item: (item[0].casefold(), item[0], item[1]))
        return urllib.parse.urlunsplit((scheme, netloc, parsed.path or "/", urllib.parse.urlencode(query, doseq=True), ""))
    except (ValueError, UnicodeError):
        return raw


def _url_fingerprint(source: dict) -> str:
    """Compare URLs after removing fragments and common tracking parameters."""
    supplied = str(source.get("url_fingerprint") or "").strip()
    if supplied.startswith("u2:"):
        return supplied
    url = str(source.get("url") or "").strip()
    if not url and supplied:
        return supplied
    canonical = _canonical_monitor_url(url)
    return "u2:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16] if canonical else ""


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


def gather(row: dict, max_signals: int = 6, business_profile: str = "any", decision_maker: str = "any", legal_form: str = "any", decision_role: str = "signal_based", custom_role: str = "", search_provider: str = "duckduckgo", path_key: str = "any", search_budget: int = 12, minimum_identity_score: float = 0.0, metrics_out: list[dict] | None = None, brave_cost_per_1000: float | None = None) -> tuple[list[dict], list[str]]:
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
    for query_index, (kind, query) in enumerate(queries):
        metric = {"rung": kind, "query_fingerprint": hashlib.sha256(" ".join(query.split()).casefold().encode("utf-8")).hexdigest()[:16],
                  "attempted": 0, "search_calls": 0, "results_returned": 0, "retained": 0,
                  "duplicates": 0, "identity_rejected": 0, "role_rejected": 0, "score_rejected": 0, "errors": 0,
                  "status": "not_run"}
        if metrics_out is not None:
            metrics_out.append(metric)
        if query_index >= search_budget:
            metric["status"] = "skipped_budget"
            continue
        metric["attempted"], metric["status"] = 1, "running"
        calls_before = BRAVE_SEARCH_REQUESTS
        try:
            results = search(query, provider=search_provider, lane="herald_signals", brave_cost_per_1000=brave_cost_per_1000)
            metric["search_calls"] = (BRAVE_SEARCH_REQUESTS - calls_before) if search_provider == "brave" else 1
            metric["results_returned"] = len(results)
            metric["observed_url_fingerprints"] = list(dict.fromkeys(
                _url_fingerprint(item)
                for item in results if isinstance(item, dict) and item.get("url")))[:30]
        except SearchProviderError as e:
            metric["search_calls"] = BRAVE_SEARCH_REQUESTS - calls_before if search_provider == "brave" else 0
            metric["errors"], metric["status"] = 1, "error"
            if str(e) not in errors:
                errors.append(str(e))
            continue
        except Exception as e:
            metric["search_calls"] = BRAVE_SEARCH_REQUESTS - calls_before if search_provider == "brave" else 0
            metric["errors"], metric["status"] = 1, "error"
            errors.append(type(e).__name__)
            continue
        for item in results:
            key = item["url"]
            if key in seen:
                metric["duplicates"] += 1
                seen[key].setdefault("query_matches", []).append({"type": kind, "query": query})
                continue
            text = f"{item['title']} {item['snippet']} {key}".lower()
            identity = _source_identity(row, kind, key, text)
            if identity["identity_strength"] == "insufficient":
                metric["identity_rejected"] += 1
                continue
            if kind.startswith("decision_maker_role_discovery") and not (role_match_terms & _tokens(text)):
                metric["role_rejected"] += 1
                continue
            if float(identity.get("identity_score", 0) or 0) < minimum_identity_score:
                metric["score_rejected"] += 1
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
            metric["retained"] += 1
            seen[key] = source
        if metric["status"] == "running":
            metric["status"] = "hit" if metric["retained"] else "miss"
        time.sleep(1.0)
    company_found = [s for s in found if not s["type"].startswith("decision_maker")]
    person_found = [s for s in found if s["type"].startswith("decision_maker")]
    if person_found and max_signals > 1:
        selected = company_found[:max_signals - min(2, len(person_found))] + person_found[:2]
        return selected[:max_signals], errors
    return company_found[:max_signals], errors


def presence_queries_for(row: dict, path_key: str = "any") -> list[tuple[str, str]]:
    """Search only for public professional/business social presence, not personal-life content."""
    company = (row.get("business") or row.get("company") or row.get("Company") or row.get("name") or "").strip()
    contact = (row.get("contact_name") or row.get("decision_maker") or row.get("person") or "").strip()
    city = (row.get("city") or row.get("City") or "").strip()
    if not company:
        company = (row.get("website") or row.get("domain") or "").strip()
    suffix = f" {city}" if city else ""
    queries = [("business_profile", f'"{company}"{suffix} site:linkedin.com/company OR site:instagram.com OR site:facebook.com OR site:x.com OR site:youtube.com OR site:tiktok.com'[:300]),
               ("business_posts", f'"{company}"{suffix} site:linkedin.com/posts OR site:instagram.com/p OR site:facebook.com/posts OR site:x.com'[:300])]
    if path_signals.known_path(path_key):
        terms = path_signals.profile(path_key).get("query_terms", "")
        if terms:
            queries[1] = ("path_business_signal", f'"{company}"{suffix} {terms} site:linkedin.com OR site:instagram.com OR site:x.com OR site:youtube.com'[:300])
    if contact and company:
        queries.append(("professional_contact", f'"{contact}" "{company}" site:linkedin.com/in OR site:linkedin.com/posts'[:260]))
    return [(kind, query) for kind, query in queries if company]


def gather_presence(row: dict, max_signals: int = 8, search_budget: int = 3, minimum_identity_score: float = 0.0,
                    path_key: str = "any",
                    metrics_out: list[dict] | None = None) -> tuple[list[dict], list[str]]:
    company = (row.get("business") or row.get("company") or row.get("Company") or row.get("name") or "").strip()
    contact = (row.get("contact_name") or row.get("decision_maker") or row.get("person") or "").strip()
    company_terms, contact_terms = _tokens(company), _tokens(contact)
    checked_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    found, seen, errors = [], set(), []
    for query_index, (kind, query) in enumerate(presence_queries_for(row, path_key)):
        metric = {"rung": kind, "query_fingerprint": hashlib.sha256(" ".join(query.split()).casefold().encode("utf-8")).hexdigest()[:16],
                  "attempted": 0, "search_calls": 0, "results_returned": 0, "retained": 0,
                  "duplicates": 0, "identity_rejected": 0, "score_rejected": 0, "errors": 0, "status": "not_run"}
        if metrics_out is not None:
            metrics_out.append(metric)
        if query_index >= search_budget:
            metric["status"] = "skipped_budget"
            continue
        metric["attempted"], metric["status"] = 1, "running"
        try:
            results = search(query)
            metric["search_calls"], metric["results_returned"] = 1, len(results)
            metric["observed_url_fingerprints"] = list(dict.fromkeys(
                _url_fingerprint(item)
                for item in results if isinstance(item, dict) and item.get("url")))[:30]
        except Exception as e:
            metric["errors"], metric["status"] = 1, "error"
            errors.append(type(e).__name__)
            continue
        for item in results:
            url = item["url"]
            if url in seen:
                metric["duplicates"] += 1
                continue
            text = f"{item['title']} {item['snippet']} {url}".lower()
            terms = _tokens(text)
            company_matches = company_terms & terms
            contact_matches = contact_terms & terms
            # When a named contact was supplied, require both the business and person to match.
            if not company_matches or (kind == "professional_contact" and contact_terms and not contact_matches):
                metric["identity_rejected"] += 1
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
            if identity_score < minimum_identity_score:
                metric["score_rejected"] += 1
                continue
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
            metric["retained"] += 1
        if metric["status"] == "running":
            metric["status"] = "hit" if metric["retained"] else "miss"
        time.sleep(1.0)
    return found[:max_signals], errors


def _waterfall_metrics(metrics: list[dict], budget: int, minimum_identity_score: float, provider: str,
                       brave_cost_per_1000: float | None = None) -> dict:
    calls = sum(int(x.get("search_calls", 0)) for x in metrics)
    amount = (float(brave_cost_per_1000) * calls / 1000) if provider == "brave" and brave_cost_per_1000 is not None else 0.0 if provider == "duckduckgo" else None
    return {"schema": "dbi.search-waterfall.v1", "budget": budget, "minimum_identity_score": minimum_identity_score,
            "provider": provider, "total_search_calls": sum(int(x.get("search_calls", 0)) for x in metrics),
            "cost_estimate": {"amount": amount, "currency": "USD" if amount is not None else None,
                              "basis": "user-declared price per 1,000 requests" if provider == "brave" and amount is not None else "no paid search provider" if provider == "duckduckgo" else "unknown",
                              "estimated": provider == "brave" and amount is not None},
            "total_results_returned": sum(int(x.get("results_returned", 0)) for x in metrics),
            "total_retained": sum(int(x.get("retained", 0)) for x in metrics),
            "total_rejected": sum(int(x.get("identity_rejected", 0)) + int(x.get("role_rejected", 0)) + int(x.get("score_rejected", 0)) for x in metrics),
            "rungs": metrics}


def _profile_run_record(profile_key: str, path_key: str, lane: str, query_budget: int,
                       freshness_days: int) -> dict:
    if not profile_key:
        return {}
    return {"schema": enrichment_profiles.SCHEMA, "profile_version": enrichment_profiles.PROFILE_VERSION,
            "profile_key": profile_key, "path_key": path_key or "any", "lane": lane,
            "query_budget_per_lead": query_budget, "freshness_target_days": freshness_days,
            "provider_calls_per_run": 0, "profile_status": "applied"}


def _mark_profile_freshness(signals: list[dict], freshness_days: int) -> None:
    """Add a path-specific freshness label without discarding the source result."""
    for item in signals:
        age = item.get("age_days")
        if isinstance(age, (int, float)):
            item["profile_freshness_status"] = "within_target_window" if age <= freshness_days else "outside_target_window"
        else:
            item["profile_freshness_status"] = "undated"


def _attach_profile_results(encoded: str, profile_record: dict, signals: list[dict]) -> str:
    try:
        results = json.loads(encoded)
    except (TypeError, ValueError):
        return encoded
    if not profile_record or not isinstance(results, list):
        return encoded
    by_url = {str(item.get("url", "")): item for item in signals if item.get("url")}
    for result in results:
        if not isinstance(result, dict):
            continue
        metadata = result.setdefault("metadata", {})
        metadata["enrichment_profile"] = profile_record
        url = str((result.get("source") or {}).get("url", ""))
        if url in by_url:
            metadata["profile_freshness_status"] = by_url[url].get("profile_freshness_status", "undated")
    return json.dumps(results, ensure_ascii=False, separators=(",", ":"))


def _monitor_review_payload(action: object, evidence: object, categories: object, sources: object,
                            source_ids: dict[str, str] | None = None) -> dict:
    """Return a stable, structured review cue shared by Herald and Presence."""
    def as_list(value: object) -> list:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                return []
        return [item for item in value if isinstance(item, (dict, str))] if isinstance(value, list) else []

    source_ids = source_ids or {}
    normalized_sources = []
    for item in as_list(sources):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        normalized_sources.append({
            "category": str(item.get("category") or ""),
            "url": url,
            "url_fingerprint": str(item.get("url_fingerprint") or ""),
            "record_id": source_ids.get(url, ""),
        })
    return {
        "action": str(action or ""),
        "evidence": str(evidence or ""),
        "categories": as_list(categories),
        "sources": normalized_sources,
    }


def build_herald_field_results(row: dict, signals: list[dict], search_provider: str, search_metrics: list[dict] | None = None,
                               search_budget: int = 12, minimum_identity_score: float = 0.0,
                               brave_cost_per_1000: float | None = None) -> str:
    """Map research and reviewed-draft outputs to the shared field-result contract."""
    results = []
    now = row.get("herald_checked_at", "")
    provider_fee = 0.0 if search_provider == "duckduckgo" else None
    search_metrics = search_metrics or []
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
        relevant_rungs = [m for m in search_metrics if (str(m.get("rung", "")).startswith("decision_maker") == (subject == "person"))]
        metrics = _waterfall_metrics(relevant_rungs, search_budget, minimum_identity_score, search_provider, brave_cost_per_1000)
        for result in results:
            if result.get("field") == field:
                result.setdefault("metadata", {})["search_waterfall"] = metrics
    monitor_status = row.get("herald_comparison_status", "")
    monitor_urls = set((row.get("herald_new_source_urls", "") + "\n" + row.get("herald_changed_source_urls", "")).splitlines())
    monitor_sources = [s for s in signals if s.get("url") in monitor_urls]
    try:
        monitor_refs = json.loads(row.get("herald_change_sources") or "[]")
    except (ValueError, TypeError):
        monitor_refs = []
    signal_by_url = {str(signal.get("url") or ""): signal for signal in signals if isinstance(signal, dict) and signal.get("url")}
    monitor_candidates = [fr.source_ref(
        source_type="public_web_search", source_name=f"Monitoring cue: {ref.get('category') or 'source change'}",
        source_url=str(ref.get("url") or ""),
        source_record_id=str(signal_by_url.get(str(ref.get("url") or ""), {}).get("id") or ""),
        value={"change_category": ref.get("category", ""), "url_fingerprint": ref.get("url_fingerprint", "")})
        for ref in monitor_refs if isinstance(ref, dict) and ref.get("url")]
    seen_monitor_urls = {str(ref.get("url") or "") for ref in monitor_refs if isinstance(ref, dict)}
    monitor_candidates.extend(fr.source_ref(source_type="public_web_search", source_name=s.get("provider", search_provider),
                                  source_url=s.get("url", ""), source_record_id=s.get("id", ""),
                                  value={"title": s.get("title", ""), "snippet": s.get("snippet", "")})
                              for s in monitor_sources if s.get("url") not in seen_monitor_urls)
    results.append(fr.make_result(
        field="signal_source_monitoring",
        value={"status": monitor_status, "action": row.get("herald_change_action", ""),
               "evidence": row.get("herald_change_evidence", ""),
               "review": _monitor_review_payload(row.get("herald_change_action"), row.get("herald_change_evidence"),
                                                  row.get("herald_change_categories"), row.get("herald_change_sources"),
                                                  {url: str(signal.get("id") or "") for url, signal in signal_by_url.items()}),
               "summary": row.get("herald_change_summary", ""),
               "new_source_urls": row.get("herald_new_source_urls", ""),
               "changed_source_urls": row.get("herald_changed_source_urls", ""),
               "not_returned_urls": row.get("herald_not_returned_urls", ""),
               "change_categories": row.get("herald_change_categories", "[]"),
               "change_sources": row.get("herald_change_sources", "[]"),
               "previous_checked_at": row.get("herald_previous_checked_at", "")},
        status="candidate" if monitor_status in ("compared", "first_check") or monitor_candidates else "not_found",
        observed_at=now, source_type="public_web_search", source_name=search_provider,
        verification_status="source_snapshot_comparison",
        verification_method="Compares source URL, title, snippet and publication date. Missing-source checks also compare recorded query-rung fingerprints; partial or changed-query coverage is inconclusive.",
        candidates=monitor_candidates))
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
    try:
        outcome = json.loads(row.get("dse_path_outcome") or "{}")
    except (ValueError, TypeError):
        outcome = {}
    if isinstance(outcome, dict) and outcome:
        outcome_refs = outcome.get("evidence", []) if isinstance(outcome.get("evidence"), list) else []
        results.append(fr.make_result(
            field="dse_path_outcome", value=outcome,
            status="candidate",
            source_type="path_specific_research_plan", source_name=str(outcome.get("path_label", "General lead research")),
            observed_at=now, verification_status="human_review_required",
            verification_method="Combines path-specific research directions with cited candidate signals. Manually verify need, buyer, budget/commercial capacity, and baseline outcomes before recommending work.",
            miss_reason="No path-priority source signal was retained; this plan is guidance, not proof of fit." if not outcome_refs else "Path signal candidates still require source review and commercial qualification.",
            candidates=[fr.source_ref(source_type="public_web_search", source_name="Path-fit candidate", source_url=item.get("url", ""),
                                      source_record_id=item.get("id", ""), value={"fit": item.get("fit"), "title": item.get("title", ""), "category": item.get("category", "")})
                        for item in outcome_refs[:8] if item.get("id")],
            metadata={"lane": "herald_research", "path_key": outcome.get("path_key", "any"), "decision_status": outcome.get("decision_status", "")}
        ))
    advice_status = str(row.get("dse_path_ai_advice_status", "not_run"))
    try:
        path_advice = json.loads(row.get("dse_path_ai_advice") or "{}")
    except (ValueError, TypeError):
        path_advice = {}
    if isinstance(path_advice, dict) and path_advice:
        refs = {str(item.get("id")): item for item in signals if isinstance(item, dict) and item.get("id")}
        advice_ids = [item for item in path_advice.get("evidence_ids", []) if isinstance(item, str) and item in refs]
        results.append(fr.make_result(
            field="dse_path_ai_advice", value=path_advice, status="candidate",
            source_type="local_model_advice", source_name=str(path_advice.get("model", "local Ollama model")), observed_at=path_advice.get("generated_at", now),
            verification_status="human_review_required", verification_method="Advice cites only retained path-fit source IDs; use it to plan a manual check, never as a qualification or action decision.",
            candidates=[fr.source_ref(source_type="public_web_search", source_name=refs[source_id].get("provider", search_provider),
                                      source_url=refs[source_id].get("url", ""), source_record_id=source_id,
                                      value={"title": refs[source_id].get("title", ""), "identity_subject": refs[source_id].get("identity_subject", "unknown")}) for source_id in advice_ids],
            metadata={"lane": "herald_research", "advisory_only": True, "changes_findings": False, "takes_actions": False}
        ))
    if not isinstance(path_advice, dict) or not path_advice:
        results.append(fr.make_result(field="dse_path_ai_advice", status="not_found", observed_at=now,
            source_type="local_model_advice", verification_status=advice_status,
            verification_method="A local advice record was not generated for this run. Existing saved history is retained separately.",
            miss_reason=advice_status.replace("_", " "), metadata={"lane": "herald_research", "advisory_only": True}))
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


def build_presence_field_results(signals: list[dict], checked_at: str, search_metrics: list[dict] | None = None,
                                  search_budget: int = 3, minimum_identity_score: float = 0.0,
                                  monitor_row: dict | None = None) -> str:
    """Map public social search snippets to contract records without calling them verified reputation."""
    results = []
    if not signals:
        missing = fr.make_result(field="presence_social_signal", status="not_found", observed_at=checked_at,
                                 identity_subject="company", miss_reason="No identity-matched public social result was retained.",
                                 verification_status="not_found", metadata={"lane": "presence_research",
                                     "search_waterfall": _waterfall_metrics(search_metrics or [], search_budget, minimum_identity_score, "duckduckgo")})
        results.append(missing)
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
        result.setdefault("metadata", {}).update({"lane": "presence_research", "search_waterfall": _waterfall_metrics(search_metrics or [], search_budget, minimum_identity_score, "duckduckgo")})
    monitor_row = monitor_row or {}
    monitor_status = monitor_row.get("presence_comparison_status", "")
    try:
        monitor_refs = json.loads(monitor_row.get("presence_change_sources") or "[]")
        monitor_categories = json.loads(monitor_row.get("presence_change_categories") or "[]")
    except (ValueError, TypeError):
        monitor_refs, monitor_categories = [], []
    signal_by_url = {str(signal.get("url") or ""): signal for signal in signals if isinstance(signal, dict) and signal.get("url")}
    monitor_candidates = [fr.source_ref(
        source_type="public_web_search", source_name=f"Monitoring cue: {ref.get('category') or 'source change'}",
        source_url=str(ref.get("url") or ""),
        source_record_id=str(signal_by_url.get(str(ref.get("url") or ""), {}).get("id") or ""),
        value={"change_category": ref.get("category", ""), "url_fingerprint": ref.get("url_fingerprint", "")})
        for ref in monitor_refs if isinstance(ref, dict) and ref.get("url")]
    results.append(fr.make_result(
        field="presence_source_monitoring",
        value={"status": monitor_status, "action": monitor_row.get("presence_change_action", ""),
               "evidence": monitor_row.get("presence_change_evidence", ""),
               "review": _monitor_review_payload(monitor_row.get("presence_change_action"), monitor_row.get("presence_change_evidence"),
                                                  monitor_categories, monitor_refs,
                                                  {url: str(signal.get("id") or "") for url, signal in signal_by_url.items()}),
               "summary": monitor_row.get("presence_change_summary", ""), "categories": monitor_categories,
               "sources": monitor_refs, "previous_checked_at": monitor_row.get("presence_previous_checked_at", "")},
        status="candidate" if monitor_status in ("compared", "first_check") or monitor_candidates else "not_found",
        observed_at=checked_at, source_type="public_web_search", source_name="Presence source monitoring",
        verification_status="source_snapshot_comparison",
        verification_method="Links detected monitoring cues to their source URLs. Cue classifications and search comparisons require human review; absence alone is inconclusive.",
        candidates=monitor_candidates,
        miss_reason="No source-monitoring comparison was available for this check." if not monitor_status else "No source change category was recorded." if not monitor_candidates else ""))
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


def _ledger_monitor_snapshot(row: dict, lane: str) -> dict | None:
    """Read the newest complete Ledger-row baseline so any PC can continue its comparison."""
    try:
        history = json.loads(row.get(f"{lane}_monitor_history") or "[]")
    except (ValueError, TypeError):
        return None
    if not isinstance(history, list):
        return None
    for record in reversed(history):
        if not isinstance(record, dict) or record.get("status") not in {"first_check", "compared"}:
            continue
        snapshot = record.get("snapshot")
        if isinstance(snapshot, dict) and isinstance(snapshot.get("sources"), list):
            return snapshot
        # Earlier Ledger monitor history kept display snippets without fingerprints.
        # Reuse its URLs and titles, but let the comparator treat missing hashes as unknown.
        legacy_sources = record.get("sources")
        if isinstance(legacy_sources, list):
            return {"checked_at": record.get("checked_at", ""),
                    "sources": [{key: source.get(key) for key in ("url", "url_fingerprint", "title", "snippet_hash", "publication_date", "freshness_status", "identity_subject", "identity_strength", "type", "category", "query_rungs", "query_fingerprints") if key in source}
                                for source in legacy_sources if isinstance(source, dict) and source.get("url")]}
    return None


def _presence_comparison(previous: dict | None, signals: list[dict], checked_at: str, search_errors: list[str]) -> dict:
    current = {_url_fingerprint(s): s for s in signals if s.get("url")}
    old_sources = {_url_fingerprint(s): s for s in (previous or {}).get("sources", []) if s.get("url")}
    new_keys = set(current) - set(old_sources) if previous else set()
    missing_keys = set(old_sources) - set(current) if previous else set()
    common_keys = set(current) & set(old_sources) if previous else set()
    new_urls = sorted(str(current[key].get("url") or "") for key in new_keys)
    not_returned = sorted(str(old_sources[key].get("url") or "") for key in missing_keys)
    changed_urls = sorted(str(current[key].get("url") or "") for key in common_keys if (
        current[key].get("title", "") != old_sources[key].get("title", "") or
        (old_sources[key].get("snippet_hash") and hashlib.sha256(current[key].get("snippet", "").encode("utf-8")).hexdigest() != old_sources[key].get("snippet_hash")) or
        current[key].get("publication_date", "") != old_sources[key].get("publication_date", "")))
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
                {"url": s.get("url", ""), "url_fingerprint": _url_fingerprint(s),
                 "subject": s.get("identity_subject", "company"),
                 "identity_subject": s.get("identity_subject", "company"), "title": s.get("title", "")[:240],
                 "identity_strength": s.get("identity_strength", "unknown"),
                 "snippet_hash": hashlib.sha256(s.get("snippet", "").encode("utf-8")).hexdigest(),
                 "publication_date": s.get("publication_date", ""), "freshness_status": s.get("freshness_status", "undated"),
                 "type": s.get("type", ""),
                 "query_rungs": list(dict.fromkeys(str(match.get("type") or "")[:48] for match in s.get("query_matches", [])
                                                    if isinstance(match, dict) and match.get("type")))[:6],
                 "query_fingerprints": _query_fingerprints(s)}
                for s in signals if s.get("url")][:8]}}


def _herald_comparison(previous: dict | None, signals: list[dict], checked_at: str, partial: bool) -> dict:
    """Compare source-backed Herald observations; absence is meaningful only after a complete search."""
    current = {_url_fingerprint(s): s for s in signals if s.get("url")}
    old_sources = {_url_fingerprint(s): s for s in (previous or {}).get("sources", []) if s.get("url")}
    new_keys = set(current) - set(old_sources) if previous else set()
    missing_keys = set(old_sources) - set(current) if previous else set()
    common_keys = set(current) & set(old_sources) if previous else set()
    new_urls = sorted(str(current[key].get("url") or "") for key in new_keys)
    missing_urls = sorted(str(old_sources[key].get("url") or "") for key in missing_keys)
    changed_urls = sorted(str(current[key].get("url") or "") for key in common_keys if (
        current[key].get("title", "") != old_sources[key].get("title", "") or
        (old_sources[key].get("snippet_hash") and hashlib.sha256(current[key].get("snippet", "").encode("utf-8")).hexdigest() != old_sources[key].get("snippet_hash")) or
        current[key].get("publication_date", "") != old_sources[key].get("publication_date", "")))
    status = "partial_check" if partial and previous else "partial_first_check" if partial else "first_check" if not previous else "compared"
    summary = "First check; no earlier source snapshot" if status == "first_check" else (
        f"{len(new_urls)} new source links; {len(changed_urls)} source records changed; {len(missing_urls)} previously seen not returned" if status == "compared" else
        f"Partial search; {len(new_urls)} new source links; missing links are inconclusive" if previous else
        "Partial first search; complete searches are needed for a baseline")
    return {"herald_comparison_status": status, "herald_change_summary": summary,
            "herald_new_source_urls": "\n".join(new_urls),
            "herald_changed_source_urls": "\n".join(changed_urls) if status == "compared" else "",
            "herald_not_returned_urls": "\n".join(missing_urls) if status == "compared" else "",
            "herald_previous_checked_at": (previous or {}).get("checked_at", ""),
            "_snapshot": {"checked_at": checked_at, "sources": [
                {"url": s.get("url", ""), "url_fingerprint": _url_fingerprint(s),
                 "subject": s.get("identity_subject", "company"),
                 "identity_subject": s.get("identity_subject", "company"),
                 "identity_strength": s.get("identity_strength", "unknown"),
                 "title": s.get("title", "")[:240],
                 "snippet_hash": hashlib.sha256(s.get("snippet", "").encode("utf-8")).hexdigest(),
                 "publication_date": s.get("publication_date", ""),
                 "freshness_status": s.get("freshness_status", "undated"),
                 "category": s.get("type", ""), "type": s.get("type", ""),
                 "query_rungs": list(dict.fromkeys(str(match.get("type") or "")[:48] for match in s.get("query_matches", [])
                                                    if isinstance(match, dict) and match.get("type")))[:6],
                 "query_fingerprints": _query_fingerprints(s)}
                for s in signals if s.get("url")][:12]}}


def _monitor_action(lane: str, comparison: dict, signals: list[dict], events: list[dict] | None = None,
                    previous: dict | None = None, query_metrics: list[dict] | None = None) -> dict:
    """Turn a source snapshot diff into a cautious, source-linked review cue; never trigger outreach."""
    prefix = "herald" if lane == "herald" else "presence"
    status = str(comparison.get(f"{prefix}_comparison_status", "unknown"))
    new_urls = {u for u in str(comparison.get(f"{prefix}_new_source_urls") or "").splitlines() if u}
    changed_urls = {u for u in str(comparison.get(f"{prefix}_changed_source_urls") or "").splitlines() if u}
    missing_urls = {u for u in str(comparison.get(f"{prefix}_not_returned_urls") or "").splitlines() if u}
    metrics_by_query = {(str(metric.get("rung") or ""), str(metric.get("query_fingerprint") or "")): metric
                        for metric in (query_metrics or []) if isinstance(metric, dict)}
    metrics_by_rung = {str(metric.get("rung") or ""): metric for metric in (query_metrics or []) if isinstance(metric, dict)}
    observed_url_rungs = {}
    for metric in (query_metrics or []):
        if not isinstance(metric, dict):
            continue
        for fingerprint in metric.get("observed_url_fingerprints", []):
            observed_url_rungs.setdefault(str(fingerprint), []).append(str(metric.get("rung") or "unknown"))
    old_sources_by_url = {str(item.get("url") or ""): item for item in (previous or {}).get("sources", [])
                          if isinstance(item, dict) and item.get("url")} if isinstance(previous, dict) else {}
    returned_not_retained = {}
    for url in missing_urls:
        source = old_sources_by_url.get(url, {})
        url_fingerprint = _url_fingerprint(source) if source else _url_fingerprint({"url": url})
        if observed_url_rungs.get(url_fingerprint):
            returned_not_retained[url] = list(dict.fromkeys(observed_url_rungs[url_fingerprint]))
    actual_missing_urls = missing_urls - set(returned_not_retained)
    covered_missing, uncovered_missing = {}, {}
    for url in actual_missing_urls:
        source = old_sources_by_url.get(url, {})
        query_fingerprints = source.get("query_fingerprints") if isinstance(source.get("query_fingerprints"), list) else []
        rungs = source.get("query_rungs") if isinstance(source.get("query_rungs"), list) else []
        if query_fingerprints:
            rung_states = {}
            for item in query_fingerprints:
                if not isinstance(item, dict) or not item.get("rung") or not item.get("fingerprint"):
                    continue
                rung, fingerprint = str(item["rung"]), str(item["fingerprint"])
                metric = metrics_by_query.get((rung, fingerprint), {})
                rung_states[f"{rung}#{fingerprint}"] = str(metric.get("status") or "query changed or not repeated")
        else:
            if not rungs:
                fallback_rung = source.get("type") or source.get("category")
                rungs = [fallback_rung] if fallback_rung else []
            rung_states = {str(rung): str(metrics_by_rung.get(str(rung), {}).get("status") or "not repeated") for rung in rungs}
        # If several prior searches found the same source, repeat each known rung
        # before treating its absence as a meaningful recheck.
        covered = bool(rung_states) and all(state in ("hit", "miss") for state in rung_states.values())
        (covered_missing if covered else uncovered_missing)[url] = rung_states
    freshness_rank = {"recent": 0, "aging": 1, "stale": 2}
    strength_rank = {"insufficient": 0, "weak": 0, "moderate": 1, "strong": 2}
    previous_sources = {_url_fingerprint(item): item for item in (previous or {}).get("sources", [])
                        if isinstance(item, dict) and item.get("url")} if isinstance(previous, dict) else {}
    freshness_downgrades = set()
    identity_changes = {}
    identity_strength_drops = {}
    if status == "compared":
        for signal in signals:
            url = str(signal.get("url") or "")
            prior_source = previous_sources.get(_url_fingerprint(signal), {})
            prior_subject = str(prior_source.get("identity_subject") or prior_source.get("subject") or "")
            current_subject = str(signal.get("identity_subject") or "")
            if url and prior_subject in ("company", "person") and current_subject in ("company", "person") and prior_subject != current_subject:
                identity_changes[url] = (prior_subject, current_subject)
            prior_strength = str(prior_source.get("identity_strength") or "")
            current_strength = str(signal.get("identity_strength") or "")
            if url and strength_rank.get(prior_strength) is not None and strength_rank.get(current_strength) is not None and strength_rank[current_strength] < strength_rank[prior_strength]:
                identity_strength_drops[url] = (prior_strength, current_strength)
            before = freshness_rank.get(str(prior_source.get("freshness_status") or ""))
            after = freshness_rank.get(str(signal.get("freshness_status") or ""))
            if url and before is not None and after is not None and after > before:
                freshness_downgrades.add(url)
    event_deltas = []
    event_no_longer_detected = []
    if lane == "herald" and isinstance(previous, dict) and isinstance(previous.get("signal_events"), list):
        prior_fits = {}
        for old_event in previous["signal_events"]:
            if isinstance(old_event, dict) and old_event.get("url") and old_event.get("category"):
                key = (_url_fingerprint(old_event), old_event.get("category"), old_event.get("subject", ""))
                prior_fits[key] = old_event.get("path_fit", "")
        for event in events or []:
            if not isinstance(event, dict) or not event.get("url") or not event.get("category"):
                continue
            key = (_url_fingerprint(event), event.get("category"), event.get("subject", ""))
            if key not in prior_fits:
                event_deltas.append((event, "new event cue"))
            elif event.get("path_fit") == "priority" and prior_fits[key] != "priority":
                event_deltas.append((event, "now priority for this path"))
        current_event_keys = {(_url_fingerprint(event), event.get("category"), event.get("subject", ""))
                              for event in (events or []) if isinstance(event, dict) and event.get("url") and event.get("category")}
        current_source_urls = {_url_fingerprint(signal) for signal in signals if isinstance(signal, dict) and signal.get("url")}
        event_no_longer_detected = [old_event for old_event in previous["signal_events"]
                                    if isinstance(old_event, dict) and _url_fingerprint(old_event) in current_source_urls
                                    and (_url_fingerprint(old_event), old_event.get("category"), old_event.get("subject", "")) not in current_event_keys]
    change_categories = []
    def add_category(condition: bool, category: str) -> None:
        if condition and category not in change_categories:
            change_categories.append(category)
    add_category(bool(new_urls), "new_source")
    add_category(bool(changed_urls), "changed_source")
    add_category(bool(identity_changes), "identity_subject_changed")
    add_category(bool(identity_strength_drops), "identity_strength_declined")
    add_category(bool(event_deltas), "event_cue_added_or_promoted")
    add_category(bool(event_no_longer_detected), "event_cue_no_longer_detected")
    add_category(bool(returned_not_retained), "prior_source_returned_but_filtered")
    add_category(bool(freshness_downgrades), "source_freshness_declined")
    add_category(bool(covered_missing), "prior_source_not_returned_with_matching_coverage")
    add_category(bool(uncovered_missing), "prior_source_coverage_incomplete")
    add_category(status.startswith("partial"), "search_incomplete")
    add_category(status == "first_check", "baseline_established")
    change_sources = []
    seen_change_sources = set()
    def add_sources(category: str, urls) -> None:
        for url in urls:
            url = str(url or "").strip()
            fingerprint = _url_fingerprint({"url": url}) if url else ""
            key = (category, fingerprint)
            if url and key not in seen_change_sources and len(change_sources) < 12:
                seen_change_sources.add(key)
                change_sources.append({"category": category, "url": url[:220], "url_fingerprint": fingerprint})
    add_sources("new_source", new_urls)
    add_sources("changed_source", changed_urls)
    add_sources("identity_subject_changed", identity_changes)
    add_sources("identity_strength_declined", identity_strength_drops)
    add_sources("event_cue_added_or_promoted", [event.get("url") for event, _reason in event_deltas if isinstance(event, dict)])
    add_sources("event_cue_no_longer_detected", [event.get("url") for event in event_no_longer_detected if isinstance(event, dict)])
    add_sources("prior_source_returned_but_filtered", returned_not_retained)
    add_sources("source_freshness_declined", freshness_downgrades)
    add_sources("prior_source_not_returned_with_matching_coverage", covered_missing)
    add_sources("prior_source_coverage_incomplete", uncovered_missing)
    priority_event_delta = any(event.get("path_fit") == "priority" for event, _reason in event_deltas)
    if status.startswith("partial"):
        action = "CHECK INCOMPLETE — do not treat missing sources as a signal"
    elif status in ("first_check",):
        action = "BASELINE — no earlier complete check to compare"
    elif identity_changes or identity_strength_drops:
        action = "REVIEW SOURCE IDENTITY — confirm whether this result concerns the same subject"
    elif lane == "herald" and (priority_event_delta or any(
            event.get("path_fit") == "priority" and event.get("url") in new_urls | changed_urls
            for event in (events or []) if isinstance(event, dict)
        )):
        action = "REVIEW PRIORITY SIGNAL — confirm it at the source"
    elif returned_not_retained:
        action = "REVIEW SOURCE MATCH — a prior URL appeared in search but was not retained"
    elif new_urls or changed_urls or event_deltas:
        action = "REVIEW SOURCE CHANGE — confirm it at the source"
    elif freshness_downgrades:
        action = "RECHECK — source evidence has aged; verify it is still current"
    elif event_no_longer_detected:
        action = "RECHECK — a prior event cue was not detected in current result text"
    elif uncovered_missing:
        action = "CHECK INCOMPLETE — earlier source searches were not all repeated"
    elif covered_missing:
        action = "RECHECK — previously returned sources were not found"
    elif status == "compared":
        action = "NO NEW SOURCE CHANGE"
    else:
        action = "NO COMPARISON AVAILABLE"
    signal_by_url = {str(item.get("url") or ""): item for item in signals if isinstance(item, dict) and item.get("url")}
    event_by_url = {str(item.get("url") or ""): item for item in (events or []) if isinstance(item, dict) and item.get("url")}
    details = []
    for url in sorted(new_urls | changed_urls)[:5]:
        signal = signal_by_url.get(url, {})
        event = event_by_url.get(url, {})
        label = str(event.get("label") or event.get("category") or signal.get("title") or "Source changed")[:90]
        fit = str(event.get("path_fit") or "public presence")
        details.append(f"{fit}: {label} — {url[:240]}")
    for event, reason in event_deltas[:5]:
        label = str(event.get("label") or event.get("category") or "new event cue")[:90]
        fit = str(event.get("path_fit") or "general")
        detail = f"{fit}: {reason} — {label} — {str(event.get('url') or '')[:240]}"
        if detail not in details:
            details.append(detail)
    for event in event_no_longer_detected[:5]:
        label = str(event.get("label") or event.get("category") or "prior event cue")[:90]
        details.append(f"Prior cue not detected in current result text; verify the source before treating it as changed: {label} — {str(event.get('url') or '')[:240]}")
    for url, rungs in sorted(returned_not_retained.items())[:5]:
        details.append(f"URL appeared in raw search results on {', '.join(rungs)} but was not retained in this run's signal set; review identity/role/score filtering or output caps: {url[:240]}")
    for url in sorted(freshness_downgrades)[:5]:
        signal = signal_by_url.get(url, {})
        date = str(signal.get("publication_date") or "publication date unavailable")[:24]
        freshness = str(signal.get("freshness_status") or "unknown")[:20]
        details.append(f"Source freshness changed to {freshness} ({date}); recheck current evidence — {url[:240]}")
    for url, (before, after) in sorted(identity_changes.items())[:5]:
        details.append(f"Source subject changed from {before} to {after}; verify the company/person match — {url[:240]}")
    for url, (before, after) in sorted(identity_strength_drops.items())[:5]:
        details.append(f"Identity match strength declined from {before} to {after}; verify the source match — {url[:240]}")
    if not status.startswith("partial"):
        details.extend(
            f"Not returned after repeating recorded rung(s) ({', '.join(f'{rung}={state}' for rung, state in covered_missing[url].items())}); existence is unconfirmed: {url[:240]}"
            for url in sorted(covered_missing)[:3])
        details.extend(
            f"Coverage incomplete ({', '.join(f'{rung}={state}' for rung, state in uncovered_missing[url].items()) or 'no prior rung recorded'}); absence is inconclusive: {url[:240]}"
            for url in sorted(uncovered_missing)[:3])
    result = {f"{prefix}_change_action": action,
            f"{prefix}_change_categories": json.dumps(change_categories, ensure_ascii=False, separators=(",", ":")),
            f"{prefix}_change_sources": json.dumps(change_sources, ensure_ascii=False, separators=(",", ":")),
            f"{prefix}_change_evidence": "\n".join(details)[:1800]}
    if status == "compared":
        result[f"{prefix}_not_returned_urls"] = "\n".join(sorted(actual_missing_urls))
        result[f"{prefix}_change_summary"] = (
            f"{len(new_urls)} new source links; {len(changed_urls)} source records changed; "
            f"{len(actual_missing_urls)} previously seen not returned; "
            f"{len(returned_not_retained)} prior URLs returned but not retained")
    return result


def _save_signal_history(path: Path, schema: str, history: dict) -> None:
    """Keep only recent hashed lead keys and source fingerprints; never store lead contact details."""
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=PRESENCE_HISTORY_DAYS)
    kept = {}
    for key, snapshot in history.items():
        try:
            checked = dt.datetime.fromisoformat(str(snapshot.get("checked_at", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if checked >= cutoff:
            kept[key] = snapshot
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"schema": schema, "retention_days": PRESENCE_HISTORY_DAYS,
                                     "leads": kept}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def _load_herald_history() -> dict:
    try:
        data = json.loads(HERALD_HISTORY.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("leads"), dict) else {"leads": {}}
    except (OSError, ValueError, TypeError):
        return {"leads": {}}


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
            "path_outcome_brief": json.loads(row.get("dse_path_outcome") or "{}"),
            "legal_form_search_hint": row.get("enrichment_target_legal_form", "any"),
            "ranked_people_candidates": candidate_context,
            "role_evidence_assessment": row.get("herald_role_assessment", "{}"), "evidence": evidence,
            "allowed_role_labels": [item.get("label", "") for item in json.loads(row.get("herald_role_candidates") or "[]") if isinstance(item, dict)]}
    payload = json.dumps({"model": model, "stream": False, "keep_alive": "30m", "format": "json",
        "options": {"num_ctx": 8192, "num_predict": 700, "temperature": 0.2},
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
            "Also return path_advice: recommend only a human validation step that follows the deterministic path_outcome_brief; identify which supplied path evidence IDs motivate it; and give up to three neutral questions that verify the source or missing commercial facts. "
            "Do not assign a lead score, decide qualification, infer need, budget, or ability to pay, change enrichment findings, propose an unapproved action, or send/claim outreach. If evidence does not support path-specific advice, return an empty path_advice object. "
            "Do not include citations in email text. Return JSON only with subject, body, evidence_ids, company_summary, company_evidence_ids, "
            "person_summary, person_evidence_ids, role_observations, open_questions, and path_advice {recommended_validation, reason, evidence_ids, questions}, "
            "where questions is an array of {question, evidence_ids}. The body should be under 90 words, plain and low-pressure, "
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
    try:
        path_outcome = json.loads(row.get("dse_path_outcome") or "{}")
    except (ValueError, TypeError):
        path_outcome = {}
    allowed_path_ids = {str(item.get("id")) for item in path_outcome.get("evidence", [])
                        if isinstance(item, dict) and item.get("id")} if isinstance(path_outcome, dict) else set()
    raw_path_advice = result.get("path_advice") if isinstance(result.get("path_advice"), dict) else {}
    def path_ids(value):
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(str(item) for item in value if isinstance(item, str) and item in allowed_path_ids))[:4]
    validated_path_ids = path_ids(raw_path_advice.get("evidence_ids"))
    questions = []
    raw_questions = raw_path_advice.get("questions", [])
    for item in raw_questions if isinstance(raw_questions, list) else []:
        if not isinstance(item, dict):
            continue
        qids = path_ids(item.get("evidence_ids"))
        question = re.sub(r"\s+", " ", str(item.get("question", ""))).strip()[:220]
        if question and qids:
            questions.append({"question": question, "evidence_ids": qids})
        if len(questions) == 3:
            break
    validation = re.sub(r"\s+", " ", str(raw_path_advice.get("recommended_validation", ""))).strip()[:300]
    reason = re.sub(r"\s+", " ", str(raw_path_advice.get("reason", ""))).strip()[:300]
    if allowed_path_ids and validated_path_ids and (validation or questions):
        output["dse_path_ai_advice"] = json.dumps({"schema": "dbi.path-ai-advice.v1", "status": "advisory_review_required",
            "model": model, "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "recommended_validation": validation, "reason": reason, "evidence_ids": validated_path_ids,
            "questions": questions, "guardrail": "Local AI advice only. It cannot change findings, determine qualification or commercial viability, or take actions."}, ensure_ascii=False, separators=(",", ":"))
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


def _path_outcome_observations(row: dict, signals: list[dict], path_evidence: list[dict]) -> list[dict]:
    """Summarize evidence already present on the lead; observations are not a prospect qualification score."""
    def normalized(value: object) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")

    values = {normalized(key): value for key, value in row.items()}
    try:
        results = json.loads(row.get("field_results") or "[]")
    except (ValueError, TypeError):
        results = []
    results = results if isinstance(results, list) else []
    indexed = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        key = normalized(result.get("field"))
        if key and result.get("value") not in (None, "", [], {}):
            indexed.setdefault(key, result)
    try:
        website_bundle = json.loads(row.get("website_evidence_decisions") or "{}")
    except (ValueError, TypeError):
        website_bundle = {}
    for result in website_bundle.get("fields", []) if isinstance(website_bundle, dict) else []:
        if isinstance(result, dict) and result.get("field"):
            indexed.setdefault(normalized(result.get("field")), result)

    def get_fact(label: str, aliases: tuple[str, ...]) -> dict | None:
        for alias in aliases:
            key = normalized(alias)
            value = values.get(key)
            result = indexed.get(key)
            if (value is None or value == "") and result:
                value = result.get("value")
            if value is None or value == "" or value == [] or value == {}:
                continue
            source = result.get("source") if result and isinstance(result.get("source"), dict) else {}
            verification = result.get("verification") if result and isinstance(result.get("verification"), dict) else {}
            identity = result.get("identity") if result and isinstance(result.get("identity"), dict) else {}
            return {"label": label, "value": str(value)[:180],
                    "basis": "source-backed enrichment" if source.get("url") else "lead record / enrichment field",
                    "source_name": source.get("name") or source.get("type") or "",
                    "url": source.get("url", ""), "verification": verification.get("status", "not recorded"),
                    "identity": identity.get("match", "")}
        return None

    facts = []
    website = get_fact("Website activity", ("site_active", "website_active", "site_status"))
    if website:
        facts.append(website)
    channel_facts = []
    for label, aliases in (("email", ("best_email", "email", "work_email")),
                           ("phone", ("phone_found", "phone", "phone_number")),
                           ("contact form", ("contact_form_url", "contact_page_url", "contact_form")),
                           ("booking", ("booking_tool", "online_booking", "booking_url"))):
        item = get_fact(label, aliases)
        if item:
            channel_facts.append(item)
    if channel_facts:
        facts.append({"label": "Available contact / booking routes", "value": ", ".join(x["label"] for x in channel_facts),
                      "count": len(channel_facts), "basis": "observed populated fields", "sources": channel_facts})
    scale = []
    for label, aliases in (("Employees", ("employees", "employee_count", "staff_count", "team_size")),
                           ("Locations", ("locations", "location_count", "number_of_locations")),
                           ("Revenue", ("annual_revenue", "revenue", "revenue_range")),
                           ("Store activity", ("ecommerce_active", "store_active", "product_count"))):
        item = get_fact(label, aliases)
        if item:
            scale.append(item)
    firmographics = get_fact("Firmographics", ("firmographics",))
    if firmographics:
        try:
            parsed = json.loads(firmographics["value"])
            if isinstance(parsed, dict):
                for key in ("employees", "employee_count", "locations", "revenue", "revenue_range", "industry", "business_type"):
                    val = parsed.get(key)
                    if val not in (None, "", [], {}):
                        scale.append({"label": key.replace("_", " ").title(), "value": str(val)[:120],
                                      "basis": firmographics["basis"], "source_name": firmographics["source_name"], "url": firmographics["url"],
                                      "verification": firmographics["verification"]})
        except (ValueError, TypeError):
            pass
    if scale:
        facts.append({"label": "Disclosed scale / operating facts", "value": f"{len(scale)} populated scale fields", "basis": "observed fields, not a viability conclusion", "sources": scale[:5]})
    decision = get_fact("Decision-maker details", ("decision_maker", "decision_maker_name", "contact_name", "decision_maker_title", "contact_title", "current_position"))
    if decision:
        facts.append(decision)
    person_candidates = row.get("herald_people_candidates")
    if person_candidates:
        try:
            people = json.loads(person_candidates)
        except (ValueError, TypeError):
            people = []
        if isinstance(people, list) and people:
            facts.append({"label": "Herald person candidates", "value": f"{len(people)} candidate profile(s) returned", "basis": "identity and role review required"})
    presence = row.get("presence_signals")
    if isinstance(presence, str):
        try:
            presence = json.loads(presence)
        except (ValueError, TypeError):
            presence = []
    if isinstance(presence, dict):
        presence = presence.get("signals", [])
    if not isinstance(presence, list) or not presence:
        try:
            presence_bundle = json.loads(row.get("presence_evidence_decisions") or "{}")
        except (ValueError, TypeError):
            presence_bundle = {}
        presence = presence_bundle.get("signals", []) if isinstance(presence_bundle, dict) else []
    if isinstance(presence, list) and presence:
        matched = [item for item in presence if isinstance(item, dict) and item.get("identity_strength") in ("strong", "moderate")]
        fresh = [item for item in matched if item.get("freshness_status") == "fresh"]
        facts.append({"label": "Presence identity / freshness", "value": f"{len(matched)} strong or moderate identity candidate(s); {len(fresh)} marked fresh",
                      "basis": "Presence search heuristics; open sources to confirm", "sources": [
                          {"label": (str(item.get("identity_subject", item.get("subject", "company"))) + " signal"), "value": str(item.get("title", ""))[:120],
                           "basis": "public search candidate", "source_name": item.get("provider", ""), "url": item.get("url", ""),
                           "verification": "unverified search snippet", "identity": item.get("identity_match", ""),
                           "publication_date": item.get("publication_date", ""), "freshness": item.get("freshness_status", "undated")}
                          for item in matched[:4]]})
    if path_evidence:
        latest = next((item.get("publication_date") for item in path_evidence if item.get("publication_date")), "")
        facts.append({"label": "Path-fit signal candidates", "value": f"{sum(x.get('fit') == 'priority' for x in path_evidence)} priority; {sum(x.get('fit') == 'supporting' for x in path_evidence)} supporting",
                      "basis": "unverified signal matches", "latest_publication_date": latest,
                      "source_ids": [item.get("id") for item in path_evidence[:8] if item.get("id")]})
    return facts[:8]


def enrich_file(source: str, engine: str = "", max_rows: int = 100, use_ai: bool = True,
                business_profile: str = "any", decision_maker: str = "any", legal_form: str = "any", decision_role: str = "signal_based", custom_role: str = "", search_provider: str = "duckduckgo", path_key: str = "any",
                search_budget: int = 12, minimum_identity_score: float = 0.0, enrichment_profile: str = "",
                brave_cost_per_1000: float | None = None, brave_max_spend: float | None = None,
                announce_cost_ceiling: bool = True) -> str:
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
    profile_doc = {}
    profile_record = {}
    profile_freshness_days = 180
    if enrichment_profile:
        profile_doc = enrichment_profiles.build_profile(enrichment_profile)
        if path_key not in ("", "any", enrichment_profile):
            raise ValueError("The selected path and enrichment profile do not match. Choose one path for this run.")
        path_key = enrichment_profile
        search_budget = min(search_budget, profile_doc["limits"]["herald_queries_per_lead"])
        profile_freshness_days = profile_doc["limits"]["signal_freshness_days"]
        if business_profile == "any" and profile_doc["intent"]["target_business_segment_keys"]:
            business_profile = profile_doc["intent"]["target_business_segment_keys"][0]
        profile_record = _profile_run_record(enrichment_profile, path_key, "herald", search_budget, profile_freshness_days)
    try:
        bp, dm, lf = business_profiles.normalize_profiles(business_profile, decision_maker, legal_form)
    except ValueError as e:
        raise ValueError(str(e)) from None
    if decision_role not in business_profiles.DECISION_ROLES:
        raise ValueError("Choose a decision-maker role from the listed options.")
    if search_provider not in ("duckduckgo", "brave"):
        raise ValueError("Choose DuckDuckGo or Brave Search as the public search provider.")
    if not 0 <= search_budget <= 30:
        raise ValueError("--search-budget must be between 0 and 30 queries per lead.")
    if not 0 <= minimum_identity_score <= 1:
        raise ValueError("--minimum-identity-score must be between 0 and 1.")
    if brave_cost_per_1000 is not None and (not isinstance(brave_cost_per_1000, (int, float)) or not 0 <= brave_cost_per_1000 <= 100000):
        raise ValueError("--brave-cost-per-1000 must be between 0 and 100000 USD.")
    if brave_max_spend is not None and (not isinstance(brave_max_spend, (int, float)) or not 0 <= brave_max_spend <= 100000):
        raise ValueError("--brave-max-spend must be between 0 and 100000 USD.")
    global BRAVE_SEARCH_REQUESTS
    BRAVE_SEARCH_REQUESTS = 0
    BRAVE_USAGE_WARNINGS.clear()
    run_max_queries = None
    maximum_cost = None
    if search_provider == "brave":
        run_max_queries = min(search_budget * min(len(rows), max_rows), _brave_request_cap())
        maximum_cost = (run_max_queries * brave_cost_per_1000 / 1000) if brave_cost_per_1000 is not None else None
        if run_max_queries and (brave_cost_per_1000 is None or brave_max_spend is None):
            raise ValueError("Brave searches need both your current --brave-cost-per-1000 and --brave-max-spend approval. Use DuckDuckGo if you cannot estimate or approve a spend ceiling.")
        if maximum_cost is not None and brave_max_spend is not None and maximum_cost > brave_max_spend + 1e-9:
            raise ValueError(f"Brave run estimate is {maximum_cost:.4f} USD, above your approved maximum of {brave_max_spend:.4f} USD. Lower the request budget or raise the approved maximum.")
        cost_label = f"up to {maximum_cost:.4f} USD estimated at your declared rate" if maximum_cost is not None else "monetary cost unknown (no per-1,000 request rate supplied)"
        if announce_cost_ceiling and run_max_queries:
            print(f"Brave spend ceiling approved: up to {run_max_queries} requests; {cost_label}; user maximum {brave_max_spend:.4f} USD.", file=sys.stderr, flush=True)
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
    strategy = business_profiles.strategy_text(business_profile, decision_maker, legal_form, decision_role) + (f" Engine path focus: {path['label']}: {path['method']}" if selected_path else "") + (f" Custom role target: {custom_role}." if custom_role else "") + (f" Applied enrichment profile {enrichment_profile} v{enrichment_profiles.PROFILE_VERSION}; freshness target {profile_freshness_days} days." if profile_record else "")
    model = _ollama_model() if use_ai else ""
    normalized_rows, _report = importer.normalize(p)
    out, errors, drafted = [], [], 0
    prior_history = _load_herald_history()
    next_history = dict(prior_history["leads"])
    monitor_errors = []
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
        row["enrichment_profile"] = json.dumps(profile_record, ensure_ascii=False, separators=(",", ":")) if profile_record else ""
        query_metrics = []
        signals, row_errors = gather(row, business_profile=business_profile, decision_maker=decision_maker, legal_form=legal_form, decision_role=decision_role, custom_role=custom_role,
                                     search_provider=search_provider, path_key=selected_path or "any", search_budget=search_budget,
                                     minimum_identity_score=minimum_identity_score, metrics_out=query_metrics,
                                     brave_cost_per_1000=brave_cost_per_1000)
        if profile_record:
            _mark_profile_freshness(signals, profile_freshness_days)
        waterfall = _waterfall_metrics(query_metrics, search_budget, minimum_identity_score, search_provider, brave_cost_per_1000)
        if profile_record:
            waterfall["enrichment_profile"] = profile_record
        row["herald_search_waterfall"] = json.dumps(waterfall, ensure_ascii=False, separators=(",", ":"))
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
        history_key = _presence_history_key(row)
        partial = bool(row_errors) or any(m.get("status") == "skipped_budget" or m.get("errors", 0) for m in query_metrics)
        prior_snapshot = _ledger_monitor_snapshot(row, "herald") or (prior_history["leads"].get(history_key) if history_key else None)
        comparison = _herald_comparison(prior_snapshot,
                                        signals, checked_at, partial)
        snapshot = comparison.pop("_snapshot")
        row.update(comparison)
        if history_key and not partial:
            next_history[history_key] = snapshot
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
        row.update(_monitor_action("herald", comparison, signals, annotated_events, prior_snapshot, query_metrics))
        row["herald_signal_events"] = json.dumps({"basis": assessment["signal_events_basis"], "path_focus": {"key": selected_path or "any", "label": path["label"], "method": path["method"], "pain": path["pain"], "buyer": path["buyer"], "revenue_model": path["revenue_model"], "proof_metrics": path["proof_metrics"], "priority_categories": path["priority"], "supporting_categories": path["supporting"]}, "events": annotated_events}, ensure_ascii=False, separators=(",", ":"))
        outcome_plan = path_signals.outcome_plan(selected_path or "any")
        known_source_ids = {signal.get("id"): signal for signal in signals if signal.get("id")}
        path_evidence = []
        for event in annotated_events:
            source = known_source_ids.get(event.get("source_id"))
            if source and event.get("path_fit") in ("priority", "supporting"):
                path_evidence.append({"id": source["id"], "fit": event["path_fit"], "category": event.get("category", ""),
                                     "subject": source.get("identity_subject", "unknown"), "title": source.get("title", "")[:140],
                                     "url": source.get("url", ""), "publication_date": source.get("publication_date", ""),
                                     "freshness_status": source.get("freshness_status", "undated")})
        has_priority = any(item["fit"] == "priority" for item in path_evidence)
        row["dse_path_outcome"] = json.dumps({"schema": "dbi.path-outcome.v1", "path_key": outcome_plan["key"], "path_label": path["label"],
            "outcome": outcome_plan["outcome"], "customer": path["buyer"], "pain_hypothesis": path["pain"],
            "monetization_model": path["revenue_model"], "proof_metrics": path["proof_metrics"],
            "commercial_viability_checks": [{"check": item, "state": "not_assessed"} for item in outcome_plan["viability_checks"]],
            "decision_status": "priority_signal_needs_human_validation" if has_priority else "insufficient_path_specific_evidence",
            "priority_evidence_count": sum(item["fit"] == "priority" for item in path_evidence),
            "supporting_evidence_count": sum(item["fit"] == "supporting" for item in path_evidence),
            "evidence": path_evidence[:8], "observed_facts": _path_outcome_observations(row, signals, path_evidence), "next_step": outcome_plan["next_step"],
            "limits": ["Signal matches are research cues, not verified pain, buying intent, budget, or ability to pay.", "Complete the listed commercial viability checks with a human before qualifying or pitching."]}, ensure_ascii=False, separators=(",", ":"))
        row["herald_legal_form_assessment"] = json.dumps(assessment["legal_form_mentions"], ensure_ascii=False, separators=(",", ":"))
        row["herald_assessed_at"] = checked_at
        row["herald_assessment_note"] = assessment["basis"]
        row["herald_checked_at"] = row["research_searched_at"] = checked_at
        row["herald_status"] = row["research_status"] = "business evidence found" if signals else "no matching business results"
        if not use_ai:
            row["dse_path_ai_advice_status"] = "disabled"
        elif not model:
            row["dse_path_ai_advice_status"] = "local_model_unavailable"
        elif not signals:
            row["dse_path_ai_advice_status"] = "no_research_sources"
        elif not path_evidence:
            row["dse_path_ai_advice_status"] = "no_path_fit_source_ids"
        else:
            row["dse_path_ai_advice_status"] = "awaiting_local_review"
        row.update({k: "" for k in ("herald_ai_review", "herald_ai_reviewed_at", "herald_ai_review_model", "dse_path_ai_advice", "outreach_subject", "outreach_body", "outreach_evidence", "outreach_evidence_detail", "outreach_personalization_basis", "outreach_model")})
        if model and signals:
            try:
                generated = draft(row, signals, model)
                if generated:
                    row.update(generated)
                    if generated.get("dse_path_ai_advice"):
                        row["dse_path_ai_advice_status"] = "ready"
                    elif row["dse_path_ai_advice_status"] == "awaiting_local_review":
                        row["dse_path_ai_advice_status"] = "no_valid_source_linked_advice"
                    if generated.get("outreach_body"):
                        row["herald_status"] = row["research_status"] = "draft ready for human review"
                        drafted += 1
                    elif generated.get("herald_ai_review"):
                        row["herald_status"] = row["research_status"] = "local AI evidence review ready"
                    elif generated.get("dse_path_ai_advice"):
                        row["herald_status"] = row["research_status"] = "local AI path advice ready for human review"
            except Exception as e:
                if row.get("dse_path_ai_advice_status") == "awaiting_local_review":
                    row["dse_path_ai_advice_status"] = "local_model_error"
                errors.append(type(e).__name__)
        result_contract = build_herald_field_results(row, signals, search_provider, query_metrics, search_budget, minimum_identity_score,
                                                     brave_cost_per_1000)
        result_contract = _attach_profile_results(result_contract, profile_record, signals)
        row["field_results"] = fr.merge_results(row.get("field_results"), result_contract)
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
              f"- Search waterfall: {sum(json.loads(r.get('herald_search_waterfall') or '{}').get('total_search_calls', 0) for r in out[:min(len(rows), max_rows)])} queries used; cap {search_budget} per lead; minimum identity score {minimum_identity_score:.2f}",
              f"- Business profile target: {bp['label']}", f"- Decision-maker path: {dm['label']}", f"- Decision-maker role target: {custom_role or business_profiles.DECISION_ROLES[decision_role]['label']}", f"- Legal-form search: {lf['label']}",
              "- Target selections guide search queries only; they are not business classifications or legal verification.",
              f"- Leads with public results: {sum(bool(r['research_sources']) for r in out[:min(len(rows), max_rows)])}",
              f"- Leads with at least one strong identity match: {sum(bool(r.get('herald_identity_summary') and any(json.loads(r['herald_identity_summary'])[subject]['strength_counts']['strong'] for subject in ('company', 'person'))) for r in out[:min(len(rows), max_rows)])}",
              f"- Sources with an explicit or relative publication date: {dated_sources} of {len(collected_sources)}",
              f"- Sources marked stale by the date heuristic: {stale_sources}",
              f"- Source monitoring comparisons completed: {sum(r.get('herald_comparison_status') == 'compared' for r in processed)}; partial checks: {sum(str(r.get('herald_comparison_status', '')).startswith('partial') for r in processed)}",
              f"- New source links: {sum(len((r.get('herald_new_source_urls') or '').splitlines()) for r in processed)}; changed source records: {sum(len((r.get('herald_changed_source_urls') or '').splitlines()) for r in processed)}; previously seen links not returned in complete checks: {sum(len((r.get('herald_not_returned_urls') or '').splitlines()) for r in processed)}",
              f"- Local AI drafts ready for review: {drafted}", f"- Local model: {model or 'not used / unavailable'}", "",
              "## Review before use", "", "Search snippets are leads for human review, not verified facts. Open the linked source before using a claim in outreach. Nothing was sent.", ""]
    if search_provider == "brave":
        actual_estimate = (BRAVE_SEARCH_REQUESTS * brave_cost_per_1000 / 1000) if brave_cost_per_1000 is not None else None
        report.insert(4, f"- Brave request cost estimate: {actual_estimate:.4f} USD at your declared per-1,000 rate" if actual_estimate is not None else "- Brave request cost estimate: unknown; no per-1,000 request rate was supplied")
        ceiling = f"up to {maximum_cost:.4f} USD estimated" if maximum_cost is not None else "monetary ceiling unknown"
        report.insert(5, f"- Brave run request ceiling: {run_max_queries} queries; {ceiling} (provider-side account limits may be lower)")
        if brave_max_spend is not None:
            report.insert(6, f"- User-approved Brave maximum: {brave_max_spend:.4f} USD (approval compares declared-rate estimate, not invoice billing)")
        for warning in BRAVE_USAGE_WARNINGS:
            report.append(f"Usage-record warning: {warning}")
    if errors:
        report += ["Search/model errors: " + ", ".join(errors[:12]), ""]
    try:
        _save_signal_history(HERALD_HISTORY, "dbi.herald-signal-history.v1", next_history)
    except OSError as error:
        report += ["Monitoring history could not be saved: " + type(error).__name__, ""]
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


def enrich_presence_file(source: str, engine: str = "", max_rows: int = 100, search_budget: int = 3,
                         minimum_identity_score: float = 0.0, enrichment_profile: str = "") -> str:
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
    profile_doc = {}
    profile_record = {}
    path_key = "any"
    profile_freshness_days = 180
    if enrichment_profile:
        profile_doc = enrichment_profiles.build_profile(enrichment_profile)
        path_key = enrichment_profile
        search_budget = min(search_budget, profile_doc["limits"]["presence_queries_per_lead"])
        profile_freshness_days = profile_doc["limits"]["signal_freshness_days"]
        profile_record = _profile_run_record(enrichment_profile, path_key, "presence", search_budget, profile_freshness_days)
        if engine:
            from . import engines
            engine_path = path_signals.known_path(engines.load(engine).get("path", ""))
            if engine_path and engine_path != path_key:
                raise ValueError(f"The selected Engine follows the {path_signals.profile(engine_path)['label']} path. Choose its profile instead.")
    if not 0 <= search_budget <= 10:
        raise ValueError("--search-budget must be between 0 and 10 queries per lead.")
    if not 0 <= minimum_identity_score <= 1:
        raise ValueError("--minimum-identity-score must be between 0 and 1.")
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
        query_metrics = []
        signals, row_errors = gather_presence(row, search_budget=search_budget, minimum_identity_score=minimum_identity_score,
                                              path_key=path_key, metrics_out=query_metrics)
        if profile_record:
            _mark_profile_freshness(signals, profile_freshness_days)
        errors.extend(row_errors)
        checked_at = signals[0]["retrieved_at"] if signals else dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        history_key = _presence_history_key(row)
        comparison_errors = list(row_errors)
        if any(m.get("status") == "skipped_budget" for m in query_metrics):
            comparison_errors.append("search budget limited this check")
        prior_snapshot = _ledger_monitor_snapshot(row, "presence") or (previous_history.get(history_key) if history_key else None)
        comparison = _presence_comparison(prior_snapshot, signals, checked_at, comparison_errors)
        snapshot = comparison.pop("_snapshot")
        if history_key and not comparison_errors:
            next_history[history_key] = snapshot
        row["presence_signals"] = json.dumps(signals, ensure_ascii=False, separators=(",", ":"))
        row["presence_sources"] = "\n".join(f"[{s['id']}] {s['title']} | {s['url']}" for s in signals)
        row["presence_checked_at"] = checked_at
        row["presence_status"] = "public professional/social results found" if signals else "no matching public social results"
        waterfall = _waterfall_metrics(query_metrics, search_budget, minimum_identity_score, "duckduckgo")
        if profile_record:
            waterfall["enrichment_profile"] = profile_record
        row["presence_search_waterfall"] = json.dumps(waterfall, ensure_ascii=False, separators=(",", ":"))
        row["enrichment_profile"] = json.dumps(profile_record, ensure_ascii=False, separators=(",", ":")) if profile_record else ""
        row.update(comparison)
        row.update(_monitor_action("presence", comparison, signals, previous=prior_snapshot, query_metrics=query_metrics))
        result_contract = build_presence_field_results(signals, checked_at, query_metrics, search_budget, minimum_identity_score, monitor_row=row)
        result_contract = _attach_profile_results(result_contract, profile_record, signals)
        row["field_results"] = fr.merge_results(row.get("field_results"), result_contract)
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
              f"- Search waterfall: {sum(json.loads(r.get('presence_search_waterfall') or '{}').get('total_search_calls', 0) for r in out[:min(len(rows), max_rows)])} queries used; cap {search_budget} per lead; minimum identity score {minimum_identity_score:.2f}",
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
