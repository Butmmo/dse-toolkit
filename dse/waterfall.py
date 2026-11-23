"""Configurable, measurable ordered provider rungs shared by enrichment fields."""
from __future__ import annotations

import json
import hashlib
import csv
import math
from pathlib import Path
import re
from copy import deepcopy
from typing import Callable

from . import enrich_providers as ep
from .common import ROOT

SCHEMA = "dbi.waterfall-config.v1"
STOP_RULES = {"personal_email_and_named_person", "personal_email", "any_email"}
DEFAULT = {"schema": SCHEMA, "field": "email", "providers": [], "minimum_confidence": 0.0,
           "stop_when": "personal_email_and_named_person", "max_provider_calls": ep.DEFAULT_BUDGET,
           "field_waterfalls": {}}
FIELD_TYPES = {"phone", "person_identity", "firmographics"}


def build_local_config(name: str, email: str = "", phone: str = "", person_identity: str = "", firmographics: str = "",
                       email_calls: int = 25, phone_calls: int = 25, person_identity_calls: int = 25, firmographics_calls: int = 25,
                       stop_when: str = "personal_email_and_named_person", email_confidence: float = 0,
                       phone_confidence: float = 0, person_identity_confidence: float = 0,
                       firmographics_confidence: float = 0, person_identity_score: float = 0) -> str:
    """Validate selected local adapters and create a never-overwrite waterfall JSON file."""
    slug = re.sub(r"[^a-z0-9_-]+", "-", (name or "").strip().lower()).strip("-_")[:48]
    if not slug:
        raise ValueError("Give this waterfall a name using letters or numbers.")
    if stop_when not in STOP_RULES:
        raise ValueError("Choose a supported email stopping rule.")
    try:
        call_caps = {"email": int(email_calls), "phone": int(phone_calls), "person_identity": int(person_identity_calls), "firmographics": int(firmographics_calls)}
        thresholds = {"email": float(email_confidence), "phone": float(phone_confidence), "person_identity": float(person_identity_confidence), "firmographics": float(firmographics_confidence), "person_identity_score": float(person_identity_score)}
    except (TypeError, ValueError):
        raise ValueError("Call caps and confidence thresholds must be valid numbers.") from None
    if any(not 0 <= cap <= 5000 for cap in call_caps.values()):
        raise ValueError("Every provider call cap must be between 0 and 5000.")
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in thresholds.values()):
        raise ValueError("Confidence and person identity thresholds must be finite numbers between 0 and 1.")

    def ordered(value: str, label: str) -> list[str]:
        names = [part.strip().lower() for part in (value or "").split(",") if part.strip()]
        if len(names) > 12 or len(set(names)) != len(names) or any(not ep.NAME.fullmatch(provider) for provider in names):
            raise ValueError(f"{label} must be up to 12 unique local provider names, comma separated, in priority order.")
        return names

    orders = {"email": ordered(email, "Email providers"), "phone": ordered(phone, "Phone providers"),
              "person_identity": ordered(person_identity, "Person identity providers"),
              "firmographics": ordered(firmographics, "Firmographic providers")}
    if not any(orders.values()):
        raise ValueError("Choose at least one configured provider for an enrichment field.")
    adapters = {}
    for field_name, names in orders.items():
        for provider_name in names:
            if provider_name not in adapters:
                try:
                    adapters[provider_name] = ep.load(provider_name, require_key=False)
                except ep.ProviderError as error:
                    raise ValueError(str(error)) from None
            adapter = adapters[provider_name]
            if field_name == "email" and not adapter.get("response", {}).get("email"):
                raise ValueError(f"Provider '{provider_name}' has no email response mapping and cannot be used for email enrichment.")
            if field_name != "email" and field_name not in adapter.get("response_fields", {}):
                raise ValueError(f"Provider '{provider_name}' has no configured response mapping for {field_name}.")

    config = {"schema": SCHEMA, "field": "email", "providers": orders["email"],
              "minimum_confidence": thresholds["email"], "stop_when": stop_when,
              "max_provider_calls": call_caps["email"], "field_waterfalls": {}}
    for field_name in ("phone", "person_identity", "firmographics"):
        confidence_key = "person_identity" if field_name == "person_identity" else field_name
        config["field_waterfalls"][field_name] = {"providers": orders[field_name],
            "max_provider_calls": call_caps[field_name], "minimum_confidence": thresholds[confidence_key],
            "minimum_identity_score": thresholds["person_identity_score"] if field_name == "person_identity" else 0.0}
    path = ROOT / "enrich-waterfalls" / f"{slug}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
            file.write("\n")
    except FileExistsError:
        raise ValueError(f"{path.name} already exists. Choose a different name; existing configs are never overwritten.") from None
    currencies = sorted({str(adapters[provider_name].get("cost_currency", "")).upper()
                         for names in orders.values() for provider_name in names
                         if adapters[provider_name].get("cost_per_call") is not None})
    unknown = sorted({provider_name for names in orders.values() for provider_name in names
                      if adapters[provider_name].get("cost_per_call") is None})
    return (f"Saved validated local waterfall: {path.relative_to(ROOT).as_posix()}\n"
            f"Provider order by field: " + "; ".join(f"{field}={', '.join(names) or '(none)'}" for field, names in orders.items()) + "\n"
            f"Declared price currencies: {', '.join(currencies) or '(none)'}; unknown-price providers: {', '.join(unknown) or '(none)'}.\n"
            f"Use the config with --waterfall-config {path.relative_to(ROOT).as_posix()} and preview it before a live run.")


def build_order_experiment_configs(source_path: str, field_name: str, provider_a: str,
                                   provider_b: str) -> str:
    """Create two never-overwrite config copies that differ only by swapping two provider positions."""
    if field_name not in {"email", *FIELD_TYPES}:
        raise ValueError("Experiment field must be email, phone, person_identity, or firmographics.")
    provider_a, provider_b = provider_a.strip().lower(), provider_b.strip().lower()
    if not provider_a or not provider_b or provider_a == provider_b:
        raise ValueError("Choose two different provider names.")
    config = load_config(source_path)
    email_adapters = provider_configs(config, dry_run=True) if config["providers"] else []
    field_configs = load_field_waterfalls(source_path, dry_run=True)
    if field_name == "email":
        providers = config["providers"]
    else:
        field_config = field_configs.get(field_name)
        if not field_config:
            raise ValueError(f"The source config has no {field_name} waterfall.")
        providers = field_config["providers"]
    if provider_a not in providers or provider_b not in providers:
        raise ValueError(f"Both providers must already be configured in the source {field_name} waterfall.")
    source = Path(source_path)
    if not source.is_absolute():
        source = ROOT / source
    try:
        original = json.loads(source.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Could not read source waterfall {source_path}: {type(error).__name__}.") from None
    except ValueError:
        raise ValueError(f"Source waterfall {source_path} is not valid JSON.") from None
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    experiment_id = "wfexp-" + hashlib.sha256(
        f"{source_digest}|{field_name}|{provider_a}|{provider_b}".encode("utf-8")
    ).hexdigest()[:12]
    provider_key = "providers" if field_name == "email" else "field_waterfalls"
    target = original[provider_key] if field_name == "email" else original[provider_key][field_name]
    order = list(target if field_name == "email" else target["providers"])
    index_a, index_b = order.index(provider_a), order.index(provider_b)
    variants = []
    for label, first, second in (("a", index_a, index_b), ("b", index_b, index_a)):
        variant = deepcopy(original)
        variant_order = list(order)
        variant_order[first], variant_order[second] = variant_order[second], variant_order[first]
        if field_name == "email":
            variant["providers"] = variant_order
        else:
            variant["field_waterfalls"][field_name]["providers"] = variant_order
        variant["waterfall_experiment"] = {
            "id": experiment_id,
            "variant": label.upper(),
            "field": field_name,
            "providers": [provider_a, provider_b],
            "source_config_sha256": source_digest,
        }
        variants.append((label, variant, variant_order))
    output_dir = ROOT / "enrich-waterfalls"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^a-z0-9_-]+", "-", source.stem.lower()).strip("-_")[:36] or "waterfall"
    safe_a = re.sub(r"[^a-z0-9_-]+", "-", provider_a)[:20]
    safe_b = re.sub(r"[^a-z0-9_-]+", "-", provider_b)[:20]
    paths = [output_dir / f"{safe_stem}-experiment-{field_name}-{safe_a}-vs-{safe_b}-{label}.json"
             for label, _, _ in variants]
    existing = [path.name for path in paths if path.exists()]
    if existing:
        raise ValueError("Experiment config already exists; existing files are never overwritten: " + ", ".join(existing))
    created_paths = []
    try:
        for path, (_, variant, _) in zip(paths, variants):
            with path.open("x", encoding="utf-8") as file:
                created_paths.append(path)
                json.dump(variant, file, ensure_ascii=False, indent=2)
                file.write("\n")
    except FileExistsError:
        for created_path in created_paths:
            created_path.unlink(missing_ok=True)
        raise ValueError("An experiment config appeared during creation; existing files are never overwritten. Remove or rename the conflicting draft and retry.") from None
    except OSError:
        for created_path in created_paths:
            created_path.unlink(missing_ok=True)
        raise
    return (f"Created two reviewed-draft configs for {field_name}:\n"
            f"A ({' > '.join(variants[0][2])}): {paths[0].relative_to(ROOT).as_posix()}\n"
            f"B ({' > '.join(variants[1][2])}): {paths[1].relative_to(ROOT).as_posix()}\n"
            "Only the selected provider positions differ. Review both files, preview spend, and approve the same bounded lead sample before running either variant. No provider calls were made.")


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


def spend_projection(email_providers: list[dict], email_calls: int, field_waterfalls: dict, leads: int) -> dict:
    """Conservative configured-provider maximum; assumes each eligible attempt uses the priciest rung."""
    chains = []
    if email_providers:
        chains.append(("email", email_providers, max(0, int(email_calls))))
    for field_name, config in field_waterfalls.items():
        providers = config.get("provider_configs", [])
        if providers:
            chains.append((field_name, providers, max(0, int(config.get("max_provider_calls", 0)))))
    currencies, unknown, estimate, attempts = set(), [], 0.0, 0
    for field_name, providers, call_cap in chains:
        possible = min(call_cap, max(0, leads) * len(providers))
        if not possible:
            continue
        attempts += possible
        priced = []
        for provider in providers:
            raw = provider.get("cost_per_call")
            if raw is None:
                unknown.append(provider["name"])
                continue
            try:
                price = float(raw)
            except (TypeError, ValueError):
                raise ValueError(f"{provider['name']}: cost_per_call must be a finite non-negative number.") from None
            currency = str(provider.get("cost_currency", "")).upper()
            if not math.isfinite(price) or price < 0 or not re.fullmatch(r"[A-Z]{3}", currency):
                raise ValueError(f"{provider['name']}: a declared provider price needs a finite non-negative amount and three-letter currency.")
            currencies.add(currency)
            priced.append(price)
        if priced:
            estimate += possible * max(priced)
    if len(currencies) > 1:
        raise ValueError("Configured providers use multiple currencies; split the waterfalls so each run has one approved currency.")
    return {"estimate": estimate, "currency": next(iter(currencies), ""), "unknown_providers": sorted(set(unknown)),
            "possible_calls": attempts, "has_unknown_cost": bool(unknown)}


def review_local_config(path: str, lead_count: int = 100, budget_override: int | None = None) -> str:
    """Audit a local waterfall's adapter mapping, key presence and spend readiness without network access."""
    if not path:
        raise ValueError("Choose a local waterfall JSON to review.")
    if not 1 <= lead_count <= 2000:
        raise ValueError("Review between 1 and 2000 leads.")
    if budget_override is not None and not 0 <= budget_override <= 5000:
        raise ValueError("Provider-call override must be between 0 and 5000.")
    config = load_config(path, budget_override=budget_override)
    email_providers = provider_configs(config, dry_run=True) if config["providers"] else []
    fields = load_field_waterfalls(path, budget_override, dry_run=True)
    projection = spend_projection(email_providers, config["max_provider_calls"], fields, lead_count)
    chains = {"email": email_providers}
    chains.update({name: item.get("provider_configs", []) for name, item in fields.items()})
    records, missing_keys, unknown_prices = {}, [], []
    for field_name, providers in chains.items():
        records[field_name] = []
        for provider in providers:
            price = provider.get("cost_per_call")
            record = {"provider": provider["name"], "key_configured": bool(provider.get("_key")),
                      "price_per_call": float(price) if price is not None else None,
                      "currency": str(provider.get("cost_currency", "")).upper() if price is not None else None,
                      "field_mapping_valid": True}
            records[field_name].append(record)
            if not record["key_configured"]:
                missing_keys.append(provider["name"])
            if price is None:
                unknown_prices.append(provider["name"])
    caps = {"email": config["max_provider_calls"]}
    caps.update({field_name: item["max_provider_calls"] for field_name, item in fields.items()})
    output = {"type": "provider_waterfall_readiness", "config": path, "lead_count": lead_count,
        "call_caps": caps, "providers_by_field": records, "all_adapter_mappings_valid": True,
        "missing_api_keys": sorted(set(missing_keys)), "unknown_price_providers": sorted(set(unknown_prices)),
        "live_keys_ready": not missing_keys, "maximum_possible_provider_calls": projection["possible_calls"],
        "maximum_estimated_spend": round(projection["estimate"], 8), "currency": projection["currency"] or None,
        "numeric_spend_approval_required": bool(projection["possible_calls"]),
        "unknown_price_acknowledgment_required": projection["has_unknown_cost"],
        "email_acceptance": {"minimum_confidence": config["minimum_confidence"], "stop_when": config["stop_when"]},
        "network_requests": 0, "lead_data_read": False, "api_key_values_returned": False}
    return json.dumps(output, ensure_ascii=False, separators=(",", ":"))


def review_experiment_pair(source_path: str, config_a_path: str, config_b_path: str,
                           lead_count: int, approved_combined_max: float, allow_unknown: bool = False) -> str:
    """Read-only preflight for a paired A/B run; reads only stable lead IDs from the CSV."""
    if not 1 <= lead_count <= 2000:
        raise ValueError("Experiment cohort must be between 1 and 2000 leads.")
    if not math.isfinite(approved_combined_max) or approved_combined_max < 0:
        raise ValueError("Combined approved spend ceiling must be a finite non-negative number.")

    def local_path(value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else ROOT / path

    source = local_path(source_path)
    paths = [local_path(config_a_path), local_path(config_b_path)]
    if not source.is_file() or source.suffix.lower() != ".csv":
        raise ValueError("Choose an existing local source CSV.")
    configs = []
    for path in paths:
        if not path.is_file():
            raise ValueError("Both local A and B waterfall config files must exist.")
        raw = json.loads(path.read_text(encoding="utf-8"))
        experiment = raw.get("waterfall_experiment") if isinstance(raw, dict) else None
        if not isinstance(experiment, dict):
            raise ValueError("Both configs must be drafts created by the waterfall experiment builder.")
        configs.append((raw, experiment, path))
    (a, ea, pa), (b, eb, pb) = configs
    if (str(ea.get("id")) != str(eb.get("id")) or ea.get("variant") != "A" or eb.get("variant") != "B"
            or ea.get("field") != eb.get("field") or ea.get("providers") != eb.get("providers")
            or ea.get("source_config_sha256") != eb.get("source_config_sha256")):
        raise ValueError("A and B must be the matching experiment pair with the same field, providers, and source config fingerprint.")
    field_name = ea["field"]
    key = "providers" if field_name == "email" else "field_waterfalls"
    order_a = list(a.get(key, []) if field_name == "email" else a.get(key, {}).get(field_name, {}).get("providers", []))
    order_b = list(b.get(key, []) if field_name == "email" else b.get(key, {}).get(field_name, {}).get("providers", []))
    first, second = ea["providers"]
    if (len(order_a) != len(order_b) or first not in order_a or second not in order_a
            or order_b != [second if name == first else first if name == second else name for name in order_a]):
        raise ValueError("A and B do not contain the expected provider-order swap.")
    baseline_a, baseline_b = dict(a), dict(b)
    baseline_a.pop("waterfall_experiment", None); baseline_b.pop("waterfall_experiment", None)
    if field_name == "email":
        baseline_b["providers"] = baseline_a["providers"]
    else:
        baseline_b["field_waterfalls"] = dict(baseline_b.get("field_waterfalls", {}))
        baseline_b["field_waterfalls"][field_name] = dict(baseline_b["field_waterfalls"].get(field_name, {}))
        baseline_b["field_waterfalls"][field_name]["providers"] = baseline_a.get("field_waterfalls", {}).get(field_name, {}).get("providers", [])
    if baseline_a != baseline_b:
        raise ValueError("A and B change settings beyond the selected provider order; rebuild the experiment pair.")
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Source CSV needs a header row.")
        sampled = []
        for row_number, row in enumerate(reader, 2):
            if len(sampled) >= lead_count:
                break
            lead_id = str(row.get("waterfall_experiment_lead_id") or row.get("source_row")
                          or row.get("lead_id") or row.get("id") or f"input-row:{row_number}").strip()
            if not lead_id:
                raise ValueError("Source CSV contains an empty stable lead ID.")
            sampled.append(lead_id)
    if not sampled:
        raise ValueError("Source CSV has no lead rows.")
    if len(set(sampled)) != len(sampled):
        raise ValueError("The selected bounded cohort has duplicate stable lead IDs.")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    cohort_hash = hashlib.sha256(json.dumps(sampled, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    reviews = [json.loads(review_local_config(str(path), len(sampled))) for path in paths]
    currencies = {r["currency"] for r in reviews if r.get("currency")}
    if len(currencies) > 1:
        raise ValueError("The two configs use different currencies; combined spend cannot be approved safely.")
    currency = next(iter(currencies), None)
    estimate = sum(float(r["maximum_estimated_spend"]) for r in reviews)
    unknown = sorted({name for r in reviews for name in r["unknown_price_providers"]})
    report = {"type": "waterfall_experiment_preflight", "experiment_id": ea["id"],
              "field": ea["field"], "providers": ea["providers"], "source_csv": source.name,
              "source_sha256": source_hash, "cohort_sha256": cohort_hash,
              "lead_count": len(sampled), "requested_lead_cap": lead_count,
              "variant_configs": {"A": {"path": str(pa), "config_sha256": hashlib.sha256(pa.read_bytes()).hexdigest(), "estimated_maximum": reviews[0]["maximum_estimated_spend"]},
                                  "B": {"path": str(pb), "config_sha256": hashlib.sha256(pb.read_bytes()).hexdigest(), "estimated_maximum": reviews[1]["maximum_estimated_spend"]}},
              "combined_known_price_estimate": round(estimate, 8), "currency": currency,
              "approved_combined_maximum": approved_combined_max,
              "within_approved_ceiling": estimate <= approved_combined_max + 1e-9,
              "unknown_price_providers": unknown, "unknown_price_acknowledged": bool(allow_unknown),
              "ready_to_run": estimate <= approved_combined_max + 1e-9 and (not unknown or allow_unknown)
                  and all(r["live_keys_ready"] and r["all_adapter_mappings_valid"] for r in reviews),
              "missing_api_keys": sorted({name for r in reviews for name in r["missing_api_keys"]}),
              "network_requests": 0, "paid_provider_calls": 0, "files_written": 0,
              "lead_row_values_returned": False, "api_key_values_returned": False}
    return json.dumps(report, ensure_ascii=False, separators=(",", ":"))


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
            record["api_calls"] = int(getattr(e, "waterfall_api_calls", 0) or 0)
            record["cache_hits"] = int(getattr(e, "waterfall_cache_hits", 0) or 0)
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
