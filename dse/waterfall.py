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
           "stop_when": "personal_email_and_named_person", "max_provider_calls": ep.DEFAULT_BUDGET}


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
