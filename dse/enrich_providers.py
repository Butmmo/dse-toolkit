"""Bring-your-own-key enrichment sources. The tool is free without them; this is for someone who already has a paid (or free-plan) API of their own.

    python dse.py enrich --providers                       which providers are set up here, and whether their key is present (the key is never shown)
    python dse.py enrich --add-provider hunter             copy the Hunter example into enrich-providers/ (see dse/provider_examples/)
    python dse.py enrich leads.csv --provider hunter --budget 25

How it stays safe and cheap:
  * nothing paid ever runs unless you name a provider on that run
  * the KEY lives only in a Windows user variable on this PC (setx HUNTER_API_KEY "..."), named in the provider file. It is never in a file here, never in Git, never typed
    into Citadel, never printed or logged (it is scrubbed from every message)
  * a call budget (default 25 lookups a run) stops a long list from using up your credits; when it is spent, the rest of the list gets the free steps only
  * results are saved in data/enrich-cache/ for 30 days, so the same domain is never paid for twice
  * a provider is a small JSON file (dse/provider_examples/TEMPLATE.json): its URL, how the key is sent, and where the emails sit in the answer. Any API that answers
    "which emails does this domain have" can be added without changing code. Only https addresses are allowed.
  * the paid step runs only for a lead the free steps could not finish (no personal email or no named owner), so you spend credits where they are needed
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import time
import urllib.parse
from pathlib import Path

import requests

from .common import DATA, ROOT
from . import enrichment_usage as eu

PROVIDERS = ROOT / "enrich-providers"
EXAMPLES = Path(__file__).with_name("provider_examples")
CACHE = DATA / "enrich-cache"
CACHE_DAYS = 30
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")
DEFAULT_BUDGET = 25


class ProviderError(Exception):
    """A problem the person can fix; the message says how."""


def shown(p: Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def scrub(text: str, key: str = "") -> str:
    t = text or ""
    if key and len(key) >= 6:
        t = t.replace(key, "[key hidden]")
    return re.sub(r"(?i)(api[_-]?key|token|authorization)[=:]\s*[A-Za-z0-9._~+/=-]{8,}", r"\1=[hidden]", t)


def list_providers() -> list[dict]:
    out = []
    if PROVIDERS.is_dir():
        for p in sorted(PROVIDERS.glob("*.json")):
            try:
                cfg = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if NAME.match(str(cfg.get("name", ""))):
                out.append({"name": cfg["name"], "label": cfg.get("label", cfg["name"]), "key_env": cfg.get("key_env", ""), "key_set": bool(os.environ.get(cfg.get("key_env", ""), "").strip())})
    return out


def describe() -> str:
    have = list_providers()
    ex = sorted(p.stem for p in EXAMPLES.glob("*.json") if p.stem != "TEMPLATE") if EXAMPLES.is_dir() else []
    lines = ["Enrichment is free by default. A provider is optional and uses YOUR own account and key.", ""]
    if have:
        lines.append("Set up on this PC:")
        for h in have:
            lines.append(f"  {h['name']:<14} {h['label']}   key {h['key_env']}: {'present' if h['key_set'] else 'NOT SET'}")
    else:
        lines.append("No provider set up yet.")
    lines += ["", "Ready-made examples you can add: " + (", ".join(ex) or "none") + "   (python dse.py enrich --add-provider NAME)",
              "Any other API: copy dse/provider_examples/TEMPLATE.json to enrich-providers/NAME.json and fill it in from the provider's documentation.",
              "Your key goes in a Windows user variable, never in a file: setx NAME_OF_THE_VARIABLE \"your key\"  (then restart the runner or open a new terminal)."]
    return "\n".join(lines)


def describe_catalog() -> str:
    """Show provider access and integration status without implying a provider is enabled."""
    path = Path(__file__).with_name("enrichment_provider_catalog.json")
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "Provider catalog is unavailable or invalid."
    lines = [f"Paid enrichment provider catalog (reviewed {catalog.get('reviewed_on', 'date unknown')}):",
             "Catalog entries do not enable a provider or make a paid request."]
    for item in catalog.get("providers", []):
        if not isinstance(item, dict):
            continue
        lines.append(f"- {item.get('name', item.get('id', 'Provider'))} [{item.get('integration', 'status unknown')}] — {item.get('category', 'category unknown')}; access: {item.get('access', 'check provider')}.")
        if item.get("notes"):
            lines.append(f"  {item['notes']}")
        if item.get("pricing_url"):
            lines.append(f"  Pricing/terms: {item['pricing_url']}")
    return "\n".join(lines)


def add_provider(name: str) -> str:
    if not NAME.match(name or ""):
        raise ValueError("A provider name is lower-case letters, digits, dash or underscore.")
    src = EXAMPLES / f"{name}.json"
    if not src.is_file() or name == "TEMPLATE":
        ex = ", ".join(sorted(p.stem for p in EXAMPLES.glob("*.json") if p.stem != "TEMPLATE"))
        raise ValueError(f"There is no ready-made example called '{name}'. Available: {ex}. For another API, copy TEMPLATE.json.")
    PROVIDERS.mkdir(exist_ok=True)
    dest = PROVIDERS / f"{name}.json"
    if dest.exists():
        return f"{shown(dest)} already exists; left as it is."
    shutil.copyfile(src, dest)
    cfg = json.loads(dest.read_text(encoding="utf-8"))
    return (f"Added {shown(dest)}. Now put your own key in a Windows user variable (it never goes in a file):\n"
            f"  setx {cfg['key_env']} \"your key\"\nThen open a new terminal (and restart the runner), and use: python dse.py enrich leads.csv --provider {name} --budget 25")


def load(name: str, require_key: bool = True) -> dict:
    if not NAME.match(name or ""):
        raise ProviderError("A provider name is lower-case letters, digits, dash or underscore.")
    p = PROVIDERS / f"{name}.json"
    if not p.is_file():
        raise ProviderError(f"No provider '{name}' is set up on this PC. Add one: python dse.py enrich --add-provider {name}  (or see dse/provider_examples/TEMPLATE.json)")
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ProviderError(f"{p.name} is not valid JSON: {e}") from None
    req, res = cfg.get("request") or {}, cfg.get("response") or {}
    if not str(req.get("url", "")).startswith("https://"):
        raise ProviderError(f"{p.name}: the url must start with https://")
    if req.get("method", "GET").upper() not in ("GET", "POST"):
        raise ProviderError(f"{p.name}: method is GET or POST")
    if not res.get("list") or not (res.get("email") or isinstance(cfg.get("response_fields"), dict)):
        raise ProviderError(f"{p.name}: response needs 'list' and either the email mapping or response_fields mappings.")
    key_env = cfg.get("key_env", "")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,60}", key_env):
        raise ProviderError(f"{p.name}: key_env is the NAME of a variable, like HUNTER_API_KEY (never the key itself)")
    cfg["_key"] = os.environ.get(key_env, "").strip()
    if not cfg["_key"] and require_key:
        raise ProviderError(f"The key for '{name}' is not set. Put your own key in a Windows user variable, then open a new terminal and restart the runner:\n  setx {key_env} \"your key\"")
    if cfg.get("cost_per_call") is not None:
        try:
            price = float(cfg["cost_per_call"])
        except (TypeError, ValueError):
            raise ProviderError(f"{p.name}: cost_per_call must be a non-negative number.") from None
        if not math.isfinite(price) or price < 0 or not re.fullmatch(r"[A-Z]{3}", str(cfg.get("cost_currency", ""))):
            raise ProviderError(f"{p.name}: a price needs non-negative cost_per_call and a three-letter cost_currency.")
    return cfg


def dig(obj, path: str):
    for part in (path or "").split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list) and part.isdigit() and int(part) < len(obj):
            obj = obj[int(part)]
        else:
            return None
    return obj


class SpendApproval:
    """Run-wide estimate guard. Reserves configured estimates before each paid request."""

    def __init__(self, maximum: float | None, currency: str, allow_unknown: bool = False):
        self.maximum, self.currency, self.allow_unknown = maximum, currency, allow_unknown
        self.reserved = 0.0

    def reserve(self, cfg: dict) -> None:
        raw = cfg.get("cost_per_call")
        if raw is None:
            if not self.allow_unknown:
                raise ProviderError(f"{cfg.get('name', 'Provider')}: price is unknown; explicitly approve unknown provider cost before running.")
            return
        amount = float(raw)
        currency = str(cfg.get("cost_currency", "")).upper()
        if not math.isfinite(amount) or amount < 0 or currency != self.currency:
            raise ProviderError(f"{cfg.get('name', 'Provider')}: provider price does not match the approved run currency.")
        if self.maximum is not None and self.reserved + amount > self.maximum + 1e-9:
            raise ProviderError(f"Provider spend ceiling reached before contacting {cfg.get('name', 'provider')}; no further paid request was made.")
        self.reserved += amount


class Budget:
    """Counts paid lookups for one run. Cached answers are free and do not count."""

    def __init__(self, limit: int = DEFAULT_BUDGET, spend_approval: SpendApproval | None = None):
        self.limit, self.used, self.cached, self.projected, self.stopped = max(0, limit), 0, 0, 0, ""
        self.spend_approval = spend_approval

    def left(self) -> int:
        return 0 if self.stopped else max(0, self.limit - self.used)


def cache_file(provider: str, domain: str) -> Path:
    return CACHE / provider / (re.sub(r"[^a-z0-9.-]", "_", domain.lower()) + ".json")


def cached(cfg: dict, domain: str, today: dt.date | None = None) -> tuple[bool, list[dict]]:
    """Read a fresh provider cache entry without making a network request."""
    today = today or dt.date.today()
    cf = cache_file(cfg["name"], domain)
    if not cf.is_file():
        return False, []
    try:
        item = json.loads(cf.read_text(encoding="utf-8"))
        if (today - dt.date.fromisoformat(item["date"])).days <= CACHE_DAYS and isinstance(item.get("results"), list):
            return True, item["results"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return False, []


def parse(cfg: dict, data) -> list[dict]:
    res = cfg["response"]
    items = dig(data, res["list"]) or []
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        email = str(dig(it, res["email"]) or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}", email):
            continue
        first, last = str(dig(it, res.get("first", "")) or "").strip(), str(dig(it, res.get("last", "")) or "").strip()
        kind = str(dig(it, res.get("kind", "")) or "").lower()
        out.append({"email": email, "kind": "personal" if kind == "personal" else "generic" if kind == "generic" else "personal" if first or last else "generic",
                    "name": f"{first} {last}".strip(), "title": str(dig(it, res.get("title", "")) or "").strip(), "confidence": dig(it, res.get("confidence", ""))})
    return out


def parse_field(cfg: dict, data, field: str) -> list[dict]:
    """Parse a configured non-email field mapping into canonical candidates."""
    mapping = (cfg.get("response_fields") or {}).get(field)
    if not isinstance(mapping, dict) or not mapping.get("list"):
        raise ProviderError(f"{cfg.get('name', 'Provider')} has no response_fields mapping for {field}.")
    items = dig(data, mapping["list"])
    if isinstance(items, dict):
        items = [items]
    if isinstance(items, dict):
        items = [items]
    candidates = []
    value_path = mapping.get("value", "")
    fields_map = mapping.get("fields", {})
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) and not (field == "phone" and isinstance(item, (str, int))):
            continue
        if field == "firmographics":
            value = {key: dig(item, path) for key, path in fields_map.items() if isinstance(path, str) and path}
            value = {key: val for key, val in value.items() if val not in (None, "", [], {})}
        elif field == "person_identity":
            value = {key: dig(item, path) for key, path in fields_map.items() if isinstance(path, str) and path}
            value = {key: val for key, val in value.items() if val not in (None, "", [], {})}
        else:
            value = dig(item, value_path) if isinstance(item, dict) and value_path else item
        if value in (None, "", [], {}):
            continue
        candidates.append({"value": value, "confidence": dig(item, mapping.get("confidence", "")) if isinstance(item, dict) and mapping.get("confidence") else None,
                           "identity_score": dig(item, mapping.get("identity_score", "")) if isinstance(item, dict) and mapping.get("identity_score") else None,
                           "identity_domain": dig(item, mapping.get("identity_domain", "")) if isinstance(item, dict) and mapping.get("identity_domain") else "",
                           "identity_company": dig(item, mapping.get("identity_company", "")) if isinstance(item, dict) and mapping.get("identity_company") else "",
                           "source_url": dig(item, mapping.get("source_url", "")) if isinstance(item, dict) and mapping.get("source_url") else ""})
    return candidates


def lookup(cfg: dict, domain: str, company: str, budget: Budget, today: dt.date | None = None) -> list[dict]:
    """Emails the provider knows for a domain. Cached for 30 days; a paid call only when the budget allows. Raises ProviderError for a problem worth telling the person."""
    today = today or dt.date.today()
    name = cfg["name"]
    cf = cache_file(name, domain)
    is_cached, cache_results = cached(cfg, domain, today)
    if is_cached:
        budget.cached += 1
        return cache_results
    if budget.left() <= 0:
        return []
    if budget.spend_approval:
        budget.spend_approval.reserve(cfg)
    req = cfg["request"]
    fill = lambda s: str(s).replace("{domain}", domain).replace("{company}", company or domain)  # noqa: E731
    query = {k: fill(v) for k, v in (req.get("query") or {}).items()}
    headers = {"Accept": "application/json", "User-Agent": "DSEToolkit/1.0"}
    auth = req.get("auth") or {"in": "header", "name": "Authorization", "prefix": "Bearer "}
    key = cfg["_key"]
    if auth.get("in") == "query":
        query[auth.get("name", "api_key")] = key
    else:
        headers[auth.get("name", "Authorization")] = f"{auth.get('prefix', '')}{key}"
    budget.used += 1
    try:
        if req.get("method", "GET").upper() == "POST":
            r = requests.post(req["url"], params=query if auth.get("in") == "query" else None, json={k: fill(v) for k, v in (req.get("body") or {}).items()} or None, headers=headers, timeout=20)
        else:
            r = requests.get(req["url"], params=query, headers=headers, timeout=20)
    except requests.RequestException as e:
        _record_usage(cfg, "email", "request_error", budget)
        raise ProviderError(scrub(f"{name}: could not reach the provider ({type(e).__name__}). The free steps continue.", key)) from None
    if r.status_code in (401, 403):
        _record_usage(cfg, "email", "authentication_error", budget, r.status_code)
        budget.stopped = "key rejected"
        raise ProviderError(f"{name}: the provider rejected your key (HTTP {r.status_code}). Check the variable {cfg['key_env']}. The rest of the list uses the free steps only.")
    if r.status_code in (402, 429):
        _record_usage(cfg, "email", "credits_or_rate_limit", budget, r.status_code)
        budget.stopped = "limit or credits reached"
        raise ProviderError(f"{name}: the provider says you are out of credits or sending too fast (HTTP {r.status_code}). The rest of the list uses the free steps only.")
    if r.status_code >= 400:
        _record_usage(cfg, "email", "http_error", budget, r.status_code)
        return []
    try:
        payload = r.json()
        results = parse(cfg, payload)
    except ValueError:
        _record_usage(cfg, "email", "invalid_response", budget, r.status_code)
        return []
    _record_usage(cfg, "email", "success", budget, r.status_code)
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps({"date": today.isoformat(), "domain": domain, "results": results}), encoding="utf-8")
    time.sleep(0.2)
    return results


def field_cache_file(provider: str, domain: str, field: str, contact_name: str = "") -> Path:
    suffix = "." + hashlib.sha256(contact_name.casefold().strip().encode("utf-8")).hexdigest()[:12] if field == "person_identity" and contact_name else ""
    return CACHE / provider / (re.sub(r"[^a-z0-9.-]", "_", domain.lower()) + f".{field}{suffix}.json")


def cached_field(cfg: dict, domain: str, field: str, today: dt.date | None = None, contact_name: str = "") -> tuple[bool, list[dict]]:
    today = today or dt.date.today()
    cf = field_cache_file(cfg["name"], domain, field, contact_name)
    try:
        item = json.loads(cf.read_text(encoding="utf-8"))
        if (today - dt.date.fromisoformat(item["date"])).days <= CACHE_DAYS and isinstance(item.get("results"), list):
            return True, item["results"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return False, []


def lookup_field(cfg: dict, field: str, identity: dict, budget: Budget, today: dt.date | None = None) -> list[dict]:
    """Call a configured adapter for phone, person_identity or firmographics."""
    today = today or dt.date.today()
    name = cfg["name"]
    is_cached, cached_results = cached_field(cfg, identity.get("domain", ""), field, today, identity.get("contact_name", ""))
    if is_cached:
        budget.cached += 1
        return cached_results
    if budget.left() <= 0:
        return []
    if budget.spend_approval:
        budget.spend_approval.reserve(cfg)
    req = cfg["request"]
    values = {**identity, "domain": identity.get("domain", ""), "company": identity.get("company", "") or identity.get("domain", "")}
    fill = lambda value: re.sub(r"\{([a-z_]+)\}", lambda match: str(values.get(match.group(1), "")), str(value))
    query = {key: fill(value) for key, value in (req.get("query") or {}).items()}
    body = {key: fill(value) for key, value in (req.get("body") or {}).items()}
    headers = {"Accept": "application/json", "User-Agent": "DSEToolkit/1.0"}
    auth = req.get("auth") or {"in": "header", "name": "Authorization", "prefix": "Bearer "}
    key = cfg["_key"]
    if auth.get("in") == "query":
        query[auth.get("name", "api_key")] = key
    else:
        headers[auth.get("name", "Authorization")] = f"{auth.get('prefix', '')}{key}"
    budget.used += 1
    try:
        if req.get("method", "GET").upper() == "POST":
            response = requests.post(req["url"], params=query if auth.get("in") == "query" else None, json=body or None, headers=headers, timeout=20)
        else:
            response = requests.get(req["url"], params=query, headers=headers, timeout=20)
    except requests.RequestException as error:
        _record_usage(cfg, field, "request_error", budget)
        raise ProviderError(scrub(f"{name}: could not reach the provider ({type(error).__name__}).", key)) from None
    if response.status_code in (401, 403):
        _record_usage(cfg, field, "authentication_error", budget, response.status_code)
        budget.stopped = "key rejected"
        raise ProviderError(f"{name}: the provider rejected its key (HTTP {response.status_code}); check {cfg['key_env']}.")
    if response.status_code in (402, 429):
        _record_usage(cfg, field, "credits_or_rate_limit", budget, response.status_code)
        budget.stopped = "limit or credits reached"
        raise ProviderError(f"{name}: provider credits or rate limit reached (HTTP {response.status_code}).")
    if response.status_code >= 400:
        _record_usage(cfg, field, "http_error", budget, response.status_code)
        return []
    try:
        payload = response.json()
        candidates = parse_field(cfg, payload, field)
    except (ValueError, TypeError):
        _record_usage(cfg, field, "invalid_response", budget, response.status_code)
        return []
    _record_usage(cfg, field, "success", budget, response.status_code)
    cf = field_cache_file(name, identity.get("domain", ""), field, identity.get("contact_name", ""))
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps({"date": today.isoformat(), "domain": identity.get("domain", ""), "field": field, "results": candidates}), encoding="utf-8")
    time.sleep(0.2)
    return candidates


def _record_usage(cfg: dict, field: str, outcome: str, budget: Budget, status_code: int | None = None) -> None:
    warning = eu.record_call(cfg, field, outcome, status_code)
    if warning:
        if not hasattr(budget, "accounting_warnings"):
            budget.accounting_warnings = []
        budget.accounting_warnings.append(warning)
