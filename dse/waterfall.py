"""Configurable, measurable ordered provider rungs shared by enrichment fields."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from . import enrich_providers as ep
from .common import ROOT

SCHEMA = "dbi.waterfall-config.v1"
STOP_RULES = {"personal_email_and_named_person", "personal_email", "any_email"}
DEFAULT = {"schema": SCHEMA, "field": "email", "providers": [], "minimum_confidence": 0.0,
           "stop_when": "personal_email_and_named_person", "max_provider_calls": ep.DEFAULT_BUDGET,
           "field_waterfalls": {}}
FIELD_TYPES = {"phone", "person_identity", "firmographics"}


def load_config(path: str = "", provider: str = "", budget_override: int | None = None) -> dict:
    """Load a local JSON provider order or build the backward-compatible one-provider config."""
    if path and provider:
        raise ValueError("Use either --provider or --waterfall-config; the config already defines provider order.")
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = ROOT / p
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except OSError as e:
            raise ValueError(f"Could not read waterfall config {path}: {type(e).__name__}.") from None
        except ValueError:
            raise ValueError(f"Waterfall config {path} is not valid JSON.") from None
    else:
        cfg = dict(DEFAULT)
        cfg["providers"] = [provider] if provider else []
    if not isinstance(cfg, dict) or cfg.get("schema") != SCHEMA or cfg.get("field") != "email":
        raise ValueError(f"Waterfall config must use schema {SCHEMA} and field 'email'.")
    providers = cfg.get("providers")
    if not isinstance(providers, list) or len(providers) > 12 or any(not isinstance(n, str) or not ep.NAME.fullmatch(n) for n in providers):
        raise ValueError("Waterfall providers must be an ordered list of up to 12 provider names.")
    if len(set(providers)) != len(providers):
        raise ValueError("A provider can only appear once in the waterfall order.")
    try:
        minimum = float(cfg.get("minimum_confidence", 0.0))
        max_calls = int(cfg.get("max_provider_calls", ep.DEFAULT_BUDGET))
    except (TypeError, ValueError):
        raise ValueError("Waterfall minimum_confidence and max_provider_calls must be numbers.") from None
    if not 0 <= minimum <= 1 or not 0 <= max_calls <= 5000:
        raise ValueError("Set minimum_confidence between 0 and 1 and max_provider_calls between 0 and 5000.")
    stop_when = cfg.get("stop_when", "personal_email_and_named_person")
    if stop_when not in STOP_RULES:
        raise ValueError("stop_when must be personal_email_and_named_person, personal_email, or any_email.")
    return {**DEFAULT, **cfg, "providers": list(providers), "minimum_confidence": minimum,
            "max_provider_calls": min(max_calls, budget_override) if budget_override is not None else max_calls,
            "stop_when": stop_when}


def provider_configs(config: dict, dry_run: bool = False) -> list[dict]:
    """Validate each named adapter; dry-run does not require API keys."""
    result = []
    for name in config["providers"]:
        try:
            result.append(ep.load(name, require_key=not dry_run))
        except ep.ProviderError as e:
            raise ValueError(str(e)) from None
    return result


def load_field_waterfalls(path: str = "", budget_override: int | None = None, dry_run: bool = False) -> dict:
    """Read per-field provider orders from the same waterfall JSON; all are opt-in."""
    if not path:
        return {}
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    try:
        root = json.loads(p.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Could not read waterfall config {path}: {type(error).__name__}.") from None
    except ValueError:
        raise ValueError(f"Waterfall config {path} is not valid JSON.") from None
    if not isinstance(root, dict) or root.get("schema") != SCHEMA:
        raise ValueError(f"Field waterfall config must use schema {SCHEMA}.")
    raw = root.get("field_waterfalls", {})
    if not isinstance(raw, dict) or set(raw) - FIELD_TYPES:
        raise ValueError("field_waterfalls may configure only phone, person_identity and firmographics.")
    configured = {}
    for field_name, item in raw.items():
        if not isinstance(item, dict):
            raise ValueError(f"Waterfall settings for {field_name} must be an object.")
        providers = item.get("providers", [])
        if not isinstance(providers, list) or len(providers) > 12 or any(not isinstance(n, str) or not ep.NAME.fullmatch(n) for n in providers) or len(set(providers)) != len(providers):
            raise ValueError(f"{field_name} providers must be an ordered list of up to 12 unique provider names.")
        try:
            calls = int(item.get("max_provider_calls", ep.DEFAULT_BUDGET))
            confidence = float(item.get("minimum_confidence", 0.0))
            identity_score = float(item.get("minimum_identity_score", 0.0))
        except (TypeError, ValueError):
            raise ValueError(f"{field_name} confidence, identity threshold and call cap must be numbers.") from None
        if not 0 <= calls <= 5000 or not 0 <= confidence <= 1 or not 0 <= identity_score <= 1:
            raise ValueError(f"{field_name} call cap must be 0–5000 and score thresholds 0–1.")
        cfg = {"providers": providers, "max_provider_calls": min(calls, budget_override) if budget_override is not None else calls,
               "minimum_confidence": confidence, "minimum_identity_score": identity_score}
        configs = []
        for name in providers:
            try:
                provider = ep.load(name, require_key=not dry_run)
            except ep.ProviderError as error:
                raise ValueError(str(error)) from None
            if field_name not in provider.get("response_fields", {}):
                raise ValueError(f"Provider '{name}' has no response_fields mapping for {field_name}.")
            configs.append(provider)
        cfg["provider_configs"] = configs
        configured[field_name] = cfg
    return configured


def confidence_value(raw) -> float | None:
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return None
    if score > 1:
        score /= 100
    return min(1.0, max(0.0, score))


def accept_email(candidate: dict, domain: str, minimum_confidence: float) -> tuple[bool, str]:
    email = str(candidate.get("email", "")).strip().lower()
    email_domain = email.rpartition("@")[2]
    if not email_domain or email_domain != domain.lower().removeprefix("www."):
        return False, "email_domain_mismatch"
    score = confidence_value(candidate.get("confidence"))
    if minimum_confidence > 0 and (score is None or score < minimum_confidence):
        return False, "provider_confidence_below_threshold_or_missing"
    return True, "accepted_by_configured_email_policy"


def accept_field_candidate(field: str, candidate: dict, domain: str, company: str, contact_name: str,
                           minimum_confidence: float = 0.0, minimum_identity_score: float = 0.0) -> tuple[bool, str]:
    """Field-specific checks: valid phone shape, anchored person, or domain/company-bound firmographics."""
    value = candidate.get("value")
    score = confidence_value(candidate.get("confidence"))
    if minimum_confidence > 0 and (score is None or score < minimum_confidence):
        return False, "provider_confidence_below_threshold_or_missing"
    if field == "phone":
        phone = str(value or "")
        digits = "".join(ch for ch in phone if ch.isdigit())
        if not 7 <= len(digits) <= 15:
            return False, "phone_length_invalid"
        phone_domain = str(candidate.get("identity_domain", "")).lower().strip().removeprefix("www.")
        phone_company = str(candidate.get("identity_company", "")).casefold().strip()
        target_company = company.casefold().strip()
        if not ((phone_domain == domain.lower().removeprefix("www.") or phone_domain.endswith("." + domain.lower().removeprefix("www.")))
                or (phone_company and target_company and (phone_company == target_company or phone_company in target_company or target_company in phone_company))):
            return False, "phone_business_identity_not_matched"
        identity_score = confidence_value(candidate.get("identity_score"))
        if minimum_identity_score > 0 and (identity_score is None or identity_score < minimum_identity_score):
            return False, "identity_score_below_threshold_or_missing"
        return True, "valid_phone_shape"
    if not isinstance(value, dict):
        return False, "provider_value_not_object"
    normalized_domain = domain.lower().removeprefix("www.")
    returned_domain = str(value.get("domain", value.get("website", ""))).lower().strip().removeprefix("www.")
    returned_company = str(value.get("company", value.get("company_name", ""))).casefold().strip()
    company_match = bool(company and returned_company and (
        returned_company == company.casefold().strip() or returned_company in company.casefold() or company.casefold() in returned_company))
    domain_match = bool(returned_domain and (returned_domain == normalized_domain or returned_domain.endswith("." + normalized_domain)))
    if field == "person_identity":
        name = str(value.get("name", value.get("full_name", ""))).strip()
        title = str(value.get("title", value.get("current_position", ""))).strip()
        if len(name.split()) < 2 or not (title or value.get("profile_url")):
            return False, "person_name_and_role_or_profile_required"
        wanted = {t.casefold() for t in contact_name.split() if len(t) > 1}
        got = {t.casefold() for t in name.split() if len(t) > 1}
        contact_match = not wanted or len(wanted & got) / len(wanted) >= 0.5
        identity_score = confidence_value(candidate.get("identity_score"))
        identity_score = identity_score if identity_score is not None else (1.0 if domain_match else 0.75 if company_match else 0.0)
        if not contact_match or not (domain_match or company_match) or identity_score < minimum_identity_score:
            return False, "person_identity_not_anchored_to_lead"
        return True, "named_person_and_company_identity_matched"
    if field == "firmographics":
        allowed = {"company", "company_name", "domain", "website", "industry", "business_type", "employee_count", "employee_range",
                   "annual_revenue", "revenue_range", "headquarters", "city", "state", "country", "description", "legal_form", "founded_year"}
        if not value or not (domain_match or company_match):
            return False, "firmographic_company_identity_not_matched"
        if not any(key in allowed and item not in (None, "", [], {}) for key, item in value.items()):
            return False, "no_supported_firmographic_values"
        identity_score = confidence_value(candidate.get("identity_score"))
        identity_score = identity_score if identity_score is not None else (1.0 if domain_match else 0.75 if company_match else 0.0)
        if identity_score < minimum_identity_score:
            return False, "identity_score_below_threshold"
        return True, "company_identity_matched"
    return False, "unsupported_field"


def execute_chain(rungs: list[dict], accept: Callable[[dict, str], tuple[bool, str]],
                  stop_after: Callable[[list[dict]], bool]) -> dict:
    """Run ordered lookup callables, isolate rung errors, track every outcome and stop on policy."""
    accepted, candidates, metrics = [], [], []
    stop_reason = "all_rungs_exhausted"
    for rung in rungs:
        name = str(rung.get("name", "provider"))
        record = {"rung": name, "attempted": 0, "api_calls": 0, "cache_hits": 0,
                  "returned": 0, "accepted": 0, "rejected": 0, "failures": 0, "projected": 0, "status": "not_run"}
        metrics.append(record)
        if rung.get("skip_reason"):
            record["status"], record["skip_reason"] = "skipped", str(rung["skip_reason"])
            continue
        record["attempted"], record["status"] = 1, "running"
        try:
            result = rung["run"]()
            record["api_calls"] = int(result.get("api_calls", 0))
            record["cache_hits"] = int(result.get("cache_hits", 0))
            record["projected"] = int(result.get("projected", 0))
            returned = result.get("candidates", [])
            record["returned"] = len(returned)
            for item in returned:
                ok, reason = accept(item, name)
                candidate = {**item, "waterfall_provider": name,
                             "waterfall_status": "accepted" if ok else "rejected",
                             "waterfall_reason": reason}
                candidates.append(candidate)
                if ok:
                    record["accepted"] += 1
                    accepted.append(candidate)
                else:
                    record["rejected"] += 1
            record["status"] = "hit" if record["accepted"] else "miss"
        except Exception as e:
            record["status"], record["failures"], record["error"] = "error", 1, str(e)
        if stop_after(accepted):
            stop_reason = "acceptance_rule_met"
            break
    return {"accepted": accepted, "candidates": candidates, "rungs": metrics, "stop_reason": stop_reason}


def cost_estimate(config: dict, providers: list[dict], eligible_leads: int, cached_by_provider: dict | None = None) -> dict:
    """Compute a maximum-call projection. Monetary values remain unknown unless config declares price/currency."""
    remaining = max(0, int(config["max_provider_calls"]))
    provider_rows = []
    for provider in providers:
        name = provider["name"]
        cached = min(eligible_leads, int((cached_by_provider or {}).get(name, 0)))
        projected_calls = min(max(0, eligible_leads - cached), remaining)
        remaining -= projected_calls
        price = provider.get("cost_per_call")
        currency = provider.get("cost_currency")
        try:
            amount = float(price) * projected_calls if price is not None and currency else None
        except (TypeError, ValueError):
            amount = None
        provider_rows.append({"provider": name, "eligible_leads": eligible_leads, "cache_hits_possible": cached,
                              "maximum_projected_calls": projected_calls, "currency_cost_max": amount,
                              "currency": currency if amount is not None else None,
                              "cost_basis": "provider config cost_per_call" if amount is not None else "unknown"})
    return {"eligible_leads": eligible_leads, "global_call_cap": config["max_provider_calls"],
            "maximum_projected_calls": sum(x["maximum_projected_calls"] for x in provider_rows),
            "providers": provider_rows, "estimate_kind": "maximum; later rungs run only when earlier rungs miss acceptance"}
