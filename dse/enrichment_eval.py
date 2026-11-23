"""Prepare and score small, human-reviewed enrichment benchmark sheets."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REVIEW_FIELDS = ["value_correct", "identity_correct", "evidence_adequate", "freshness_acceptable", "review_note"]
YES = {"y", "yes", "true", "1"}
NO = {"n", "no", "false", "0"}
UNKNOWN = {"unknown", "uncertain", "cannot_judge", "can't_judge", "not_enough_evidence"}
FIT_JUDGMENTS = {"good_fit", "not_a_fit", "uncertain"}
TARGET_CONTEXT_FIELDS = {
    "requested_business_profile": "business_profile",
    "requested_decision_maker": "decision_maker",
    "requested_role": "role",
    "requested_legal_form": "legal_form",
    "requested_path": "path",
    "requested_search_strategy": "search_strategy",
}
OBSERVED_CONTEXT_FIELDS = {
    "business_profiles": ("business_profile", "key"),
    "roles": ("role_evidence", "label"),
    "legal_forms": ("legal_form_mention", "key"),
    "person_role_candidates": ("person_role_candidate", "title"),
    "presence_signal_categories": ("presence_signal_category", ""),
}


def _json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return []
    try:
        return json.loads(str(value))
    except (ValueError, TypeError):
        return []


def _read(path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"File not found: {p}")
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {p}")
        return list(reader.fieldnames), list(reader)


def _stable_id(row: dict[str, str], row_number: int) -> str:
    supplied = (row.get("evaluation_id") or row.get("lead_id") or row.get("id") or "").strip()
    if supplied:
        return supplied
    identity = "|".join((row.get(k) or "").strip().casefold() for k in
                        ("company", "business", "website", "domain", "contact_name", "decision_maker"))
    seed = identity or f"row-{row_number}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def prepare(source: str, out: str = "") -> Path:
    """Flatten field_results into a review sheet with human-label columns."""
    headers, rows = _read(source)
    result_col = "field_results" if "field_results" in headers else "field_result"
    if result_col not in headers:
        raise ValueError("Input CSV needs a field_results JSON column (dbi.field-result.v1 records).")
    output = Path(out) if out else Path(source).with_name(Path(source).stem + "-enrichment-review.csv")
    source_fields = [h for h in ("engine_path", "path", "company", "business", "website", "domain", "contact_name", "decision_maker",
                                 "waterfall_experiment_id", "waterfall_experiment_variant", "waterfall_experiment_field",
                                 "waterfall_experiment_providers", "waterfall_experiment_lead_id",
                                 "waterfall_config_sha256") if h in headers]
    columns = ["evaluation_id", "source_row", "engine_path", "enrichment_profile", "research_lane", "field", "value", "status", "source_type", "source_name", "source_url",
               "observed_at", "publication_date", "freshness_status", "age_days", "identity_subject", "identity_match",
               "identity_strength", "identity_score", "verification_status", "cost_amount", "cost_currency", "cost_units",
               "cost_quantity", "cost_estimated", "provider_waterfall_cost", "provider_cost_shared_from_duplicate_domain", *source_fields, *REVIEW_FIELDS]
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(dict.fromkeys(columns)), extrasaction="ignore")
        writer.writeheader()
        for row_number, row in enumerate(rows, 2):
            payload = _json(row.get(result_col))
            if not isinstance(payload, list):
                continue
            for result in payload:
                if not isinstance(result, dict) or result.get("schema") != "dbi.field-result.v1":
                    continue
                source_info = result.get("source") if isinstance(result.get("source"), dict) else {}
                freshness = result.get("freshness") if isinstance(result.get("freshness"), dict) else {}
                identity = result.get("identity") if isinstance(result.get("identity"), dict) else {}
                verification = result.get("verification") if isinstance(result.get("verification"), dict) else {}
                cost = result.get("cost") if isinstance(result.get("cost"), dict) else {}
                metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
                profile_payload = _json(row.get("enrichment_profile"))
                profile_key = profile_payload.get("profile_key", "") if isinstance(profile_payload, dict) else ""
                engine_path = row.get("engine_path") or row.get("path") or ""
                output_row = {"evaluation_id": _stable_id(row, row_number), "source_row": row_number,
                              "engine_path": engine_path, "enrichment_profile": profile_key or "unknown",
                              "research_lane": str(metadata.get("lane") or "unknown"),
                              "field": result.get("field", ""), "value": json.dumps(result.get("value"), ensure_ascii=False) if isinstance(result.get("value"), (dict, list)) else result.get("value", ""),
                              "status": result.get("status", ""), "source_type": source_info.get("type", ""),
                              "source_name": source_info.get("name", ""), "source_url": source_info.get("url", ""),
                              "observed_at": result.get("observed_at", ""), "publication_date": freshness.get("publication_date", ""),
                              "freshness_status": freshness.get("status", ""), "age_days": freshness.get("age_days", ""),
                              "identity_subject": identity.get("subject", ""), "identity_match": identity.get("match", ""),
                              "identity_strength": identity.get("strength", ""), "identity_score": identity.get("score", ""),
                              "verification_status": verification.get("status", ""), "cost_amount": cost.get("amount", ""),
                              "cost_currency": cost.get("currency", ""), "cost_units": cost.get("units", ""),
                              "cost_quantity": cost.get("quantity", ""), "cost_estimated": cost.get("estimated", ""),
                              "provider_waterfall_cost": json.dumps(metadata.get("provider_waterfall_cost"), ensure_ascii=False, separators=(",", ":"))
                                  if isinstance(metadata.get("provider_waterfall_cost"), dict) else "",
                              "provider_cost_shared_from_duplicate_domain": bool(metadata.get("provider_cost_shared_from_duplicate_domain", False))}
                output_row.update({name: row.get(name, "") for name in source_fields})
                output_row.update({name: "" for name in REVIEW_FIELDS})
                writer.writerow(output_row)
                count += 1
    if not count:
        raise ValueError("No dbi.field-result.v1 records were found in the input CSV.")
    print(f"Prepared {count} field reviews in {output}")
    print("Label review columns yes/no/unknown; use unknown when evidence is insufficient and blank only when not reviewed.")
    return output


def sample_ledger(source: str, leads: int = 40, seed: int = 42, stratify: str = "engine_path,enrichment_profile", out: str = "") -> Path:
    """Select whole lead rows from a prepared worksheet, stratified by cohort."""
    if leads < 1:
        raise ValueError("--leads must be at least 1.")
    headers, rows = _read(source)
    required = {"source_row", "field", "value_correct", "identity_correct", "evidence_adequate", "freshness_acceptable"}
    missing = sorted(required - set(headers))
    if missing:
        raise ValueError("Prepared review sheet is missing columns: " + ", ".join(missing) + ". Run `prepare` first.")
    strata_fields = [field.strip() for field in stratify.split(",") if field.strip()]
    missing_strata = [field for field in strata_fields if field not in headers]
    if missing_strata:
        raise ValueError("Cannot stratify by missing columns: " + ", ".join(missing_strata))

    clusters: dict[str, list[dict[str, str]]] = defaultdict(list)
    cluster_strata: dict[str, tuple[str, ...]] = {}
    for row in rows:
        lead_id = (row.get("source_row") or "").strip()
        if not lead_id:
            continue
        clusters[lead_id].append(row)
        cluster_strata[lead_id] = tuple((row.get(field) or "unknown").strip() or "unknown" for field in strata_fields)
    if not clusters:
        raise ValueError("No lead rows with field results are available to sample.")

    rng = random.Random(seed)
    grouped: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for lead_id, key in cluster_strata.items():
        grouped[key].append(lead_id)
    if len(grouped) > leads:
        raise ValueError(f"The requested sample of {leads} leads is smaller than the {len(grouped)} strata. Increase --leads or choose fewer --stratify fields.")

    allocation = {key: 1 for key in grouped}
    remaining = min(leads, len(clusters)) - len(allocation)
    while remaining > 0:
        available = [key for key, members in grouped.items() if allocation[key] < len(members)]
        if not available:
            break
        # Give the next lead to the most under-sampled proportional stratum.
        key = max(available, key=lambda k: (len(grouped[k]) / (allocation[k] + 1), tuple(reversed(k))))
        allocation[key] += 1
        remaining -= 1

    selected: list[tuple[str, ...]] = []
    for key in sorted(grouped):
        members = sorted(grouped[key])
        rng.shuffle(members)
        selected.extend((lead_id, key) for lead_id in members[:allocation[key]])
    rng.shuffle(selected)
    selected_ids = {lead_id for lead_id, _ in selected}
    stratum_labels = {lead_id: "|".join(key) if key else "all" for lead_id, key in selected}
    output = Path(out) if out else Path(source).with_name(Path(source).stem + "-benchmark-sample.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[*headers, "benchmark_stratum", "benchmark_seed"], extrasaction="ignore")
        writer.writeheader()
        for lead_id, _ in selected:
            for row in clusters[lead_id]:
                output_row = dict(row)
                output_row.update({field: "" for field in REVIEW_FIELDS})
                output_row["benchmark_stratum"] = stratum_labels[lead_id]
                output_row["benchmark_seed"] = str(seed)
                writer.writerow(output_row)
    print(f"Selected {len(selected_ids)} leads ({sum(len(clusters[lead_id]) for lead_id in selected_ids)} field reviews) across {len(grouped)} strata: {output}")
    print("The sample is deterministic for this seed and remains a manual audit, not a representative population estimate.")
    return output


def plan_waterfall_experiment(source: str, field: str, provider_a: str, provider_b: str,
                              engine_path: str, enrichment_profile: str, research_lane: str,
                              leads: int = 50, seed: int = 42, out: str = "") -> Path:
    """Write a deterministic paired lead manifest for a manual provider-order experiment."""
    if leads < 1:
        raise ValueError("--leads must be at least 1.")
    if not field.strip() or not provider_a.strip() or not provider_b.strip() or provider_a == provider_b:
        raise ValueError("Choose a field and two different provider names.")
    headers, rows = _read(source)
    required = {"source_row", "field", "engine_path", "enrichment_profile", "research_lane", "source_type", "source_name"}
    missing = sorted(required - set(headers))
    if missing:
        raise ValueError("Review CSV is missing columns needed for cohort matching: " + ", ".join(missing))
    label_column = "adjudicated_value_correct" if "adjudicated_value_correct" in headers else "value_correct"
    if label_column not in headers:
        raise ValueError("Review CSV needs value_correct or adjudicated_value_correct labels.")
    identity_columns = [column for column in ("company", "business", "website", "domain", "city", "state") if column in headers]
    cohort = (engine_path.strip(), enrichment_profile.strip(), research_lane.strip())
    grouped: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    lead_rows: dict[str, dict[str, str]] = {}
    for row in rows:
        row_cohort = tuple((row.get(key) or "unknown").strip() or "unknown"
                           for key in ("engine_path", "enrichment_profile", "research_lane"))
        source_row = (row.get("source_row") or "").strip()
        if (row_cohort != cohort or (row.get("field") or "").strip() != field.strip()
                or (row.get("source_type") or "").strip() != "configured_provider"
                or not source_row):
            continue
        source_name = (row.get("source_name") or "").strip()
        if source_name not in {provider_a.strip(), provider_b.strip()}:
            continue
        label = _review_category(row.get(label_column, ""))
        if label not in {"yes", "no"}:
            continue
        grouped[source_row][source_name].append(row)
        lead_rows.setdefault(source_row, row)
    eligible = [lead_id for lead_id, by_provider in grouped.items()
                if len(by_provider.get(provider_a.strip(), [])) == 1
                and len(by_provider.get(provider_b.strip(), [])) == 1]
    if not eligible:
        raise ValueError("No leads have exactly one explicitly reviewed result from each provider in the selected field and cohort.")
    rng = random.Random(seed)
    eligible.sort()
    rng.shuffle(eligible)
    selected = eligible[:min(leads, len(eligible))]
    source_digest = hashlib.sha256(Path(source).read_bytes()).hexdigest()
    plan_id = hashlib.sha256(
        f"{source_digest}|{field}|{provider_a}|{provider_b}|{cohort}|{seed}|{','.join(selected)}".encode("utf-8")
    ).hexdigest()[:16]
    output = Path(out) if out else Path(source).with_name(Path(source).stem + "-waterfall-experiment-manifest.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = ["plan_id", "source_sha256", "seed", "source_row", *identity_columns,
               "field", "engine_path", "enrichment_profile", "research_lane",
               "variant_a_provider_order", "variant_b_provider_order", "paired_reviewed_value_correct"]
    with output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for lead_id in selected:
            provider_rows = grouped[lead_id]
            row = dict(lead_rows[lead_id])
            row.update({"plan_id": plan_id, "source_sha256": source_digest, "seed": seed,
                        "source_row": lead_id, "field": field.strip(), "engine_path": cohort[0],
                        "enrichment_profile": cohort[1], "research_lane": cohort[2],
                        "variant_a_provider_order": f"{provider_a.strip()} > {provider_b.strip()}",
                        "variant_b_provider_order": f"{provider_b.strip()} > {provider_a.strip()}",
                        "paired_reviewed_value_correct": f"{provider_a.strip()}={_review_category(provider_rows[provider_a.strip()][0].get(label_column, ''))};{provider_b.strip()}={_review_category(provider_rows[provider_b.strip()][0].get(label_column, ''))}"})
            writer.writerow(row)
    print(f"Created paired waterfall experiment manifest for {len(selected)} of {len(eligible)} eligible leads: {output}")
    print("Each lead is listed once with both order variants. This does not run providers or outreach; maintain isolated outputs and an approved spend cap when executing manually.")
    return output


def pair_experiment_variants(variant_a_path: str, variant_b_path: str) -> tuple[Path, dict]:
    """Combine verified A/B enrichment outputs only when their recorded source cohort matches exactly."""
    root = Path(__file__).resolve().parents[1]
    required = {"waterfall_experiment_id", "waterfall_experiment_variant", "waterfall_experiment_field",
                "waterfall_experiment_providers", "waterfall_experiment_lead_id", "waterfall_config_sha256"}

    def load_variant(path_value: str, expected_variant: str):
        path = Path(path_value)
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        try:
            relative = path.relative_to(root.resolve()).as_posix()
        except ValueError:
            raise ValueError("Choose both variant CSVs from this toolkit's local my-lists folder.") from None
        headers, rows = _read(path)
        missing = sorted(required - set(headers))
        if missing:
            raise ValueError(f"Variant {expected_variant} is missing experiment metadata columns: " + ", ".join(missing))
        if len(headers) != len(set(headers)):
            raise ValueError(f"Variant {expected_variant} has duplicate CSV headers; preserve the source and correct the duplicate columns before pairing.")
        if not rows:
            raise ValueError(f"Variant {expected_variant} has no lead rows.")
        ids = []
        experiment_ids = set()
        fields = set()
        provider_pairs = set()
        config_hashes = set()
        variants = set()
        for row_number, row in enumerate(rows, 2):
            lead_id = (row.get("waterfall_experiment_lead_id") or "").strip()
            variant = (row.get("waterfall_experiment_variant") or "").strip().upper()
            experiment_id = (row.get("waterfall_experiment_id") or "").strip()
            field = (row.get("waterfall_experiment_field") or "").strip()
            try:
                providers = json.loads(row.get("waterfall_experiment_providers") or "")
            except (TypeError, ValueError):
                providers = None
            if not lead_id or not experiment_id or variant != expected_variant or not field:
                raise ValueError(f"Variant {expected_variant} has incomplete or conflicting experiment metadata at row {row_number}.")
            if not isinstance(providers, list) or len(providers) != 2 or any(not isinstance(name, str) for name in providers):
                raise ValueError(f"Variant {expected_variant} has invalid provider metadata at row {row_number}.")
            ids.append(lead_id)
            experiment_ids.add(experiment_id)
            fields.add(field)
            provider_pairs.add(tuple(providers))
            config_hashes.add((row.get("waterfall_config_sha256") or "").strip().lower())
            variants.add(variant)
        if len(ids) != len(set(ids)):
            raise ValueError(f"Variant {expected_variant} contains duplicate lead IDs; no paired file was written.")
        if len(experiment_ids) != 1 or len(fields) != 1 or len(provider_pairs) != 1 or len(config_hashes) != 1 or "" in config_hashes:
            raise ValueError(f"Variant {expected_variant} mixes experiment IDs, fields, provider pairs, or config fingerprints.")
        return path, relative, headers, rows, ids, next(iter(experiment_ids)), next(iter(fields)), next(iter(provider_pairs)), next(iter(config_hashes))

    path_a, rel_a, headers_a, rows_a, ids_a, experiment_id, field, providers_a, config_hash_a = load_variant(variant_a_path, "A")
    path_b, rel_b, headers_b, rows_b, ids_b, experiment_b, field_b, providers_b, config_hash_b = load_variant(variant_b_path, "B")
    if experiment_b != experiment_id or field_b != field or providers_b != providers_a:
        raise ValueError("The selected files are not the A and B variants of the same experiment field and provider pair.")
    if ids_a != ids_b:
        raise ValueError("The selected variants do not contain the same leads in the same order; no paired CSV was written.")
    manifest_path = root / "my-lists" / f"waterfall-experiment-{experiment_id}-cohort.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("The local experiment cohort record is missing or unreadable. Preserve both CSVs and inspect the matching waterfall-experiment cohort file.") from None
    expected_cohort = hashlib.sha256(json.dumps(ids_a, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    if (manifest.get("schema") != "dbi.waterfall-experiment-cohort.v1"
            or manifest.get("id") != experiment_id
            or manifest.get("field") != field
            or manifest.get("providers") != list(providers_a)
            or manifest.get("sample_rows") != len(ids_a)
            or manifest.get("cohort_sha256") != expected_cohort):
        raise ValueError("The selected CSV rows do not match the experiment's recorded cohort; no paired file was written.")
    records = manifest.get("variants")
    record_a = records.get("A") if isinstance(records, dict) else None
    record_b = records.get("B") if isinstance(records, dict) else None
    if not isinstance(record_a, dict) or not isinstance(record_b, dict):
        raise ValueError("Both variants must complete and be recorded before they can be paired.")
    if (record_a.get("result_csv") != rel_a or record_b.get("result_csv") != rel_b
            or record_a.get("config_sha256") != config_hash_a or record_b.get("config_sha256") != config_hash_b
            or record_a.get("result_sha256") != hashlib.sha256(path_a.read_bytes()).hexdigest()
            or record_b.get("result_sha256") != hashlib.sha256(path_b.read_bytes()).hexdigest()):
        raise ValueError("One selected result no longer matches the locally recorded experiment output. Preserve it and rerun only through the original workflow.")
    headers = list(dict.fromkeys([*headers_a, *headers_b]))
    output = root / "my-lists" / f"waterfall-experiment-{experiment_id}-paired.csv"
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    writer.writerows([*rows_a, *rows_b])
    output_bytes = ("\ufeff" + buffer.getvalue()).encode("utf-8")
    if output.exists():
        if output.read_bytes() != output_bytes:
            raise ValueError(f"A different paired output already exists; it was left untouched: {output.relative_to(root).as_posix()}")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with output.open("xb") as file:
                file.write(output_bytes)
        except FileExistsError:
            if output.read_bytes() != output_bytes:
                raise ValueError(f"A different paired output appeared during creation and was left untouched: {output.relative_to(root).as_posix()}") from None
    manifest["paired_csv"] = {"path": output.relative_to(root).as_posix(),
                              "sha256": hashlib.sha256(output_bytes).hexdigest(), "rows": len(rows_a) + len(rows_b)}
    temp_path = manifest_path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(manifest_path)
    result = {"experiment_id": experiment_id, "field": field, "lead_count": len(ids_a),
              "rows": len(rows_a) + len(rows_b), "variants": {"A": len(rows_a), "B": len(rows_b)},
              "output": output.relative_to(root).as_posix(), "outreach_assigned": False}
    print(f"Paired {len(ids_a)} leads across A and B ({len(rows_a) + len(rows_b)} rows): {result['output']}")
    print("The verified paired file is ready for the assign-outreach step; no variant was selected and no Engine was changed.")
    return output, result


def assign_outreach_variant(source: str, experiment_id: str, seed: str = "42", out: str = "", engine: str = "") -> tuple[Path, dict]:
    """Select exactly one A/B enriched row per lead using a stable hash assignment."""
    root = Path(__file__).resolve().parents[1]
    source_path = Path(source)
    if not source_path.is_absolute():
        source_path = root / source_path
    source_path = source_path.resolve()
    try:
        source_relative = source_path.relative_to(root.resolve()).as_posix()
    except ValueError:
        raise ValueError("Choose a paired experiment CSV from this toolkit's local my-lists folder.") from None
    headers, rows = _read(source_path)
    required = {"waterfall_experiment_id", "waterfall_experiment_variant", "waterfall_experiment_field",
                "waterfall_experiment_providers", "waterfall_experiment_lead_id", "waterfall_config_sha256"}
    missing = sorted(required - set(headers))
    if missing:
        raise ValueError("Input CSV is missing required experiment columns: " + ", ".join(missing))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", experiment_id or ""):
        raise ValueError("Experiment ID must be 1-80 letters, numbers, dots, underscores, or hyphens, starting with a letter or number.")
    source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    cohort_manifest_path = root / "my-lists" / f"waterfall-experiment-{experiment_id}-cohort.json"
    try:
        cohort_manifest = json.loads(cohort_manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("The verified local cohort record is missing or unreadable. Pair the A and B results again before assignment.") from None
    paired_record = cohort_manifest.get("paired_csv")
    if (cohort_manifest.get("schema") != "dbi.waterfall-experiment-cohort.v1"
            or cohort_manifest.get("id") != experiment_id
            or not isinstance(paired_record, dict)
            or paired_record.get("path") != source_relative
            or paired_record.get("sha256") != source_digest
            or paired_record.get("rows") != len(rows)):
        raise ValueError("This CSV does not match the locally verified paired output for that experiment. Pair the original A and B files again; no assignment was made.")
    selected = [row for row in rows if (row.get("waterfall_experiment_id") or "").strip() == experiment_id]
    if not selected:
        raise ValueError(f"No rows for experiment {experiment_id!r} were found in {source}.")
    if len(selected) != len(rows):
        raise ValueError("The paired CSV contains rows from more than one experiment; no assignment was made.")
    fields = {(row.get("waterfall_experiment_field") or "").strip() for row in selected}
    if len(fields) != 1 or not next(iter(fields)):
        raise ValueError("Select rows from exactly one nonblank experiment field per outreach assignment.")
    if fields != {cohort_manifest.get("field")}:
        raise ValueError("The paired CSV field does not match its local cohort record; no assignment was made.")
    provider_pairs = set()
    variant_ids: dict[str, list[str]] = {"A": [], "B": []}
    variant_configs: dict[str, set[str]] = {"A": set(), "B": set()}

    by_lead: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row_number, row in enumerate(selected, 2):
        lead_id = (row.get("waterfall_experiment_lead_id") or "").strip()
        variant = (row.get("waterfall_experiment_variant") or "").strip().upper()
        if not lead_id:
            raise ValueError(f"Experiment row {row_number} has no stable lead ID.")
        if variant not in {"A", "B"}:
            raise ValueError(f"Experiment row {row_number} has invalid variant {variant!r}; expected A or B.")
        if variant in by_lead[lead_id]:
            raise ValueError(f"Lead {lead_id!r} has more than one {variant} row; resolve duplicates before assignment.")
        try:
            providers = json.loads(row.get("waterfall_experiment_providers") or "")
        except (TypeError, ValueError):
            providers = None
        if not isinstance(providers, list) or providers != cohort_manifest.get("providers"):
            raise ValueError(f"Experiment row {row_number} has provider metadata that does not match its cohort record.")
        provider_pairs.add(tuple(providers))
        variant_ids[variant].append(lead_id)
        variant_configs[variant].add((row.get("waterfall_config_sha256") or "").strip().lower())
        by_lead[lead_id][variant] = row
    if len(provider_pairs) != 1:
        raise ValueError("The paired CSV mixes configured provider pairs; no assignment was made.")
    unpaired = [lead for lead, variants in by_lead.items() if set(variants) != {"A", "B"}]
    if unpaired:
        sample = ", ".join(repr(x) for x in unpaired[:5])
        raise ValueError(f"{len(unpaired)} lead(s) do not have exactly one A and one B enrichment row (for example {sample}); no assignment file was written.")
    expected_cohort = hashlib.sha256(json.dumps(variant_ids["A"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    variant_records = cohort_manifest.get("variants") if isinstance(cohort_manifest.get("variants"), dict) else {}
    if (variant_ids["A"] != variant_ids["B"]
            or len(variant_ids["A"]) != cohort_manifest.get("sample_rows")
            or cohort_manifest.get("cohort_sha256") != expected_cohort
            or any(len(variant_configs[v]) != 1 or next(iter(variant_configs[v])) != (variant_records.get(v) or {}).get("config_sha256") for v in ("A", "B"))):
        raise ValueError("The paired lead cohort or variant config fingerprints do not match the local record; no assignment was made.")

    extra = ["waterfall_outreach_assignment_experiment_id", "waterfall_outreach_assignment_variant", "waterfall_outreach_assignment_seed"]
    assigned_rows = []
    counts = {"A": 0, "B": 0}
    for lead_id in sorted(by_lead):
        digest = hashlib.sha256(f"{experiment_id}\0{seed}\0{lead_id}".encode("utf-8")).digest()
        variant = "A" if digest[0] % 2 == 0 else "B"
        row = dict(by_lead[lead_id][variant])
        row["waterfall_experiment_variant"] = variant
        row["waterfall_outreach_assignment_experiment_id"] = experiment_id
        row["waterfall_outreach_assignment_variant"] = variant
        row["waterfall_outreach_assignment_seed"] = str(seed)
        assigned_rows.append(row)
        counts[variant] += 1
    if engine:
        if out:
            raise ValueError("Choose an Engine destination or an explicit output path, not both.")
        from .engines import engine_dir, load, validate_waterfall_outreach_rows
        cfg = load(engine)
        validate_waterfall_outreach_rows(engine, assigned_rows)
        output = engine_dir(engine) / "imports" / (source_path.stem + f"-{experiment_id}-outreach-assigned.csv")
        engine_slug = cfg.get("slug")
    else:
        output = Path(out) if out else source_path.with_name(source_path.stem + f"-{experiment_id}-outreach-assigned.csv")
        engine_slug = None
    try:
        assignment_output_path = output.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        assignment_output_path = str(output.resolve())
    previous_assignment = cohort_manifest.get("assignment")
    if isinstance(previous_assignment, dict) and (previous_assignment.get("seed") != str(seed)
            or previous_assignment.get("engine") != engine_slug
            or previous_assignment.get("assigned_csv") != assignment_output_path):
        raise ValueError("This experiment already has an outreach assignment with a different seed, Engine, or output name. Keep the original cohort assignment consistent.")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(dict.fromkeys([*headers, *extra])), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(assigned_rows)
    output_bytes = ("\ufeff" + buffer.getvalue()).encode("utf-8")
    if output.exists() and output.read_bytes() != output_bytes:
        raise ValueError(f"Assignment output already exists with different contents; it was left untouched: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = output.with_name(output.stem + "-assignment.json")
    manifest = {"schema": "dbi.waterfall-outreach-assignment.v1", "experiment_id": experiment_id,
                "experiment_field": next(iter(fields)), "seed": str(seed),
                "assignment_algorithm": "sha256_parity_experiment_id_seed_stable_lead_id",
                "lead_count": len(by_lead), "source_rows": len(selected), "variant_counts": counts,
        "one_variant_per_lead": True, "source_file_name": source_path.name,
                "source_path": source_relative, "source_sha256": source_digest,
                "cohort_sha256": cohort_manifest.get("cohort_sha256"),
                "assigned_csv_name": output.name, "assigned_csv_sha256": hashlib.sha256(output_bytes).hexdigest(),
                "engine": engine_slug}
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if manifest_path.exists() and manifest_path.read_bytes() != manifest_bytes:
        raise ValueError(f"Assignment audit already exists with different contents; it was left untouched: {manifest_path}")
    if not output.exists():
        output.write_bytes(output_bytes)
    if not manifest_path.exists():
        manifest_path.write_bytes(manifest_bytes)
    cohort_manifest["assignment"] = {"seed": str(seed), "engine": engine_slug,
                                      "assigned_csv": assignment_output_path,
                                      "assigned_csv_sha256": hashlib.sha256(output_bytes).hexdigest(),
                                      "assignment_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                                      "paired_source_sha256": source_digest}
    cohort_temp = cohort_manifest_path.with_suffix(".json.tmp")
    cohort_temp.write_text(json.dumps(cohort_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cohort_temp.replace(cohort_manifest_path)
    result = {"experiment_id": experiment_id, "experiment_field": next(iter(fields)), "seed": str(seed),
              "lead_count": len(by_lead), "variant_counts": counts, "assignment": "stable SHA-256 parity of experiment ID, seed, and lead ID",
              "one_variant_per_lead": True, "source_rows": len(selected), "engine": cfg.get("slug") if engine else None,
              "output": str(output.resolve()), "assignment_manifest": str(manifest_path.resolve()),
              "source_sha256": manifest["source_sha256"], "assigned_csv_sha256": manifest["assigned_csv_sha256"]}
    print(f"Assigned {len(by_lead)} paired leads to one outreach variant each (A {counts['A']}, B {counts['B']}): {output}")
    print(f"Wrote data-minimized assignment audit: {manifest_path}")
    print("The same experiment ID, seed, and lead ID always produce the same assignment. Store this output as the only outreach input for these leads.")
    return output, result


def pair_reviewers(source: str, out: str = "") -> Path:
    """Create independent reviewer and adjudication columns for a prepared sample."""
    headers, rows = _read(source)
    required = set(REVIEW_FIELDS)
    missing = sorted(required - set(headers))
    if missing:
        raise ValueError("Prepared review sheet is missing columns: " + ", ".join(missing) + ". Run `prepare` first.")
    review_dimensions = REVIEW_FIELDS[:4]
    added = [f"reviewer_{reviewer}_{field}" for reviewer in ("a", "b") for field in review_dimensions]
    added += ["reviewer_a_note", "reviewer_b_note"]
    added += [f"adjudicated_{field}" for field in review_dimensions] + ["adjudication_note"]
    output = Path(out) if out else Path(source).with_name(Path(source).stem + "-paired-review.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(dict.fromkeys([*headers, *added]))
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            paired = dict(row)
            paired.update({field: "" for field in REVIEW_FIELDS})
            paired.update({field: "" for field in added})
            writer.writerow(paired)
    print(f"Prepared {len(rows)} paired review rows: {output}")
    print("Review independently in reviewer_a_* and reviewer_b_*; record the resolved label in adjudicated_*.")
    return output


def _ratio(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> dict | None:
    """Return a Wilson score interval for a binary proportion (95% by default)."""
    if total <= 0:
        return None
    rate = successes / total
    z2 = z * z
    denominator = 1 + z2 / total
    center = (rate + z2 / (2 * total)) / denominator
    margin = z * ((rate * (1 - rate) / total + z2 / (4 * total * total)) ** 0.5) / denominator
    return {"lower": max(0.0, center - margin), "upper": min(1.0, center + margin)}


def _review_category(value: str) -> str | None:
    normalized = (value or "").strip().casefold()
    if normalized in YES:
        return "yes"
    if normalized in NO:
        return "no"
    if normalized in UNKNOWN:
        return "unknown"
    return None


def _agreement(items: list[dict[str, str]], field: str) -> dict:
    a_key, b_key = f"reviewer_a_{field}", f"reviewer_b_{field}"
    categories = ("yes", "no", "unknown")
    confusion = {a: {b: 0 for b in categories} for a in categories}
    excluded = 0
    for row in items:
        a, b = _review_category(row.get(a_key, "")), _review_category(row.get(b_key, ""))
        if a is None or b is None:
            excluded += 1
            continue
        confusion[a][b] += 1
    comparable = sum(sum(row.values()) for row in confusion.values())
    observed = _ratio(sum(confusion[label][label] for label in categories), comparable)
    expected = None
    kappa = None
    if comparable:
        a_totals = {label: sum(confusion[label].values()) for label in categories}
        b_totals = {label: sum(confusion[a][label] for a in categories) for label in categories}
        expected = sum(a_totals[label] * b_totals[label] for label in categories) / (comparable * comparable)
        if expected < 1:
            kappa = (observed - expected) / (1 - expected)
    return {"comparable": comparable, "excluded_missing_or_invalid": excluded,
            "observed_agreement": observed, "expected_agreement": expected,
            "cohen_kappa": kappa, "confusion_matrix": confusion}


def _paired_source_comparisons(rows: list[dict[str, str]], headers: list[str], min_labeled: int,
                              bootstrap_reps: int = 500, bootstrap_seed: int = 42) -> list[dict]:
    if "source_row" not in headers:
        return []
    label_columns = {field: f"adjudicated_{field}" if f"adjudicated_{field}" in headers else field
                     for field in REVIEW_FIELDS[:4]}
    cases: dict[tuple[str, tuple[str, str, str], str], dict[tuple[str, str], list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    leads_by_cohort: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    by_field_cohort_sources: dict[tuple[str, tuple[str, str, str]], set[tuple[str, str]]] = defaultdict(set)
    for row in rows:
        lead_id = (row.get("source_row") or "").strip()
        field = (row.get("field") or "").strip()
        if not lead_id:
            continue
        cohort = tuple((row.get(name) or "unknown").strip() or "unknown"
                       for name in ("engine_path", "enrichment_profile", "research_lane"))
        leads_by_cohort[cohort].add(lead_id)
        if not field:
            continue
        source = ((row.get("source_type") or "unattributed").strip() or "unattributed",
                  (row.get("source_name") or "unattributed").strip() or "unattributed")
        by_field_cohort_sources[(field, cohort)].add(source)
        cases[(field, cohort, lead_id)][source].append(row)

    comparisons = []

    def priced_attempt_cost(row: dict[str, str]) -> tuple[dict[str, float], int, int]:
        payload = _json(row.get("provider_waterfall_cost"))
        providers = payload.get("providers") if isinstance(payload, dict) else None
        totals: dict[str, float] = defaultdict(float)
        unknown_price_calls = 0
        invalid_price_calls = 0
        if not isinstance(providers, dict):
            return {}, 0, 0
        for attempt in providers.values():
            if not isinstance(attempt, dict):
                continue
            try:
                calls = max(0, int(attempt.get("calls", 0) or 0))
            except (TypeError, ValueError):
                continue
            if not calls:
                continue
            currency, amount = attempt.get("currency"), attempt.get("estimated_cost")
            if not currency or amount is None:
                unknown_price_calls += calls
                continue
            try:
                amount_value = float(amount)
            except (TypeError, ValueError):
                invalid_price_calls += calls
                continue
            if not math.isfinite(amount_value) or amount_value < 0:
                invalid_price_calls += calls
                continue
            totals[str(currency)] += amount_value
        return dict(totals), unknown_price_calls, invalid_price_calls

    for (field, cohort), sources in sorted(by_field_cohort_sources.items()):
        for source_a, source_b in itertools.combinations(sorted(sources), 2):
            a_present = {lead for (case_field, case_cohort, lead), result_map in cases.items()
                         if case_field == field and case_cohort == cohort and source_a in result_map}
            b_present = {lead for (case_field, case_cohort, lead), result_map in cases.items()
                         if case_field == field and case_cohort == cohort and source_b in result_map}
            shared = a_present & b_present
            counts = {dimension: {"source_a_wins": 0, "source_b_wins": 0, "ties": 0,
                                  "source_a_yes": 0, "source_b_yes": 0,
                                  "excluded_unknown_or_unlabeled": 0, "excluded_duplicate_result_sets": 0}
                      for dimension in REVIEW_FIELDS[:4]}
            paired_costs: dict[str, dict[str, Any]] = defaultdict(
                lambda: {"source_a_total": 0.0, "source_b_total": 0.0, "matched_leads": 0,
                         "source_a_correct": 0, "source_b_correct": 0, "lead_cost_differences": [],
                         "source_a_unknown_price_calls": 0, "source_b_unknown_price_calls": 0,
                         "source_a_invalid_price_calls": 0, "source_b_invalid_price_calls": 0}
            )
            paired_cost_input_quality = {"source_a_unknown_price_calls": 0, "source_b_unknown_price_calls": 0,
                                         "source_a_invalid_price_calls": 0, "source_b_invalid_price_calls": 0}
            paired_labels: dict[str, list[tuple[int, int]]] = defaultdict(list)
            for lead in shared:
                a_rows = cases[(field, cohort, lead)][source_a]
                b_rows = cases[(field, cohort, lead)][source_b]
                if len(a_rows) != 1 or len(b_rows) != 1:
                    for dimension_counts in counts.values():
                        dimension_counts["excluded_duplicate_result_sets"] += 1
                    continue
                a_value_label = _review_category(a_rows[0].get(label_columns["value_correct"], ""))
                b_value_label = _review_category(b_rows[0].get(label_columns["value_correct"], ""))
                if a_value_label in {"yes", "no"} and b_value_label in {"yes", "no"}:
                    a_costs, a_unknown, a_invalid = priced_attempt_cost(a_rows[0])
                    b_costs, b_unknown, b_invalid = priced_attempt_cost(b_rows[0])
                    paired_cost_input_quality["source_a_unknown_price_calls"] += a_unknown
                    paired_cost_input_quality["source_b_unknown_price_calls"] += b_unknown
                    paired_cost_input_quality["source_a_invalid_price_calls"] += a_invalid
                    paired_cost_input_quality["source_b_invalid_price_calls"] += b_invalid
                    for currency in a_costs.keys() & b_costs.keys():
                        cost_pair = paired_costs[currency]
                        cost_pair["source_a_total"] += a_costs[currency]
                        cost_pair["source_b_total"] += b_costs[currency]
                        cost_pair["matched_leads"] += 1
                        cost_pair["source_a_correct"] += a_value_label == "yes"
                        cost_pair["source_b_correct"] += b_value_label == "yes"
                        cost_pair["lead_cost_differences"].append(a_costs[currency] - b_costs[currency])
                for dimension, dimension_counts in counts.items():
                    a_label = _review_category(a_rows[0].get(label_columns[dimension], ""))
                    b_label = _review_category(b_rows[0].get(label_columns[dimension], ""))
                    if a_label not in {"yes", "no"} or b_label not in {"yes", "no"}:
                        dimension_counts["excluded_unknown_or_unlabeled"] += 1
                        continue
                    dimension_counts["source_a_yes"] += a_label == "yes"
                    dimension_counts["source_b_yes"] += b_label == "yes"
                    paired_labels[dimension].append((int(a_label == "yes"), int(b_label == "yes")))
                    if a_label == b_label:
                        dimension_counts["ties"] += 1
                    elif a_label == "yes":
                        dimension_counts["source_a_wins"] += 1
                    else:
                        dimension_counts["source_b_wins"] += 1
            dimensions = {}
            for dimension, dimension_counts in counts.items():
                matched = (dimension_counts["source_a_wins"] + dimension_counts["source_b_wins"] + dimension_counts["ties"])
                label_pairs = paired_labels[dimension]
                bootstrap_differences = []
                if bootstrap_reps and label_pairs:
                    rng = random.Random(
                        f"{bootstrap_seed}:{field}:{cohort}:{source_a}:{source_b}:{dimension}"
                    )
                    for _ in range(bootstrap_reps):
                        sample = [label_pairs[rng.randrange(len(label_pairs))] for _ in label_pairs]
                        bootstrap_differences.append(
                            sum(a_yes - b_yes for a_yes, b_yes in sample) / len(sample)
                        )
                    bootstrap_differences.sort()
                dimensions[dimension] = {
                    "matched_adjudicated_leads": matched,
                    "source_a_wins": dimension_counts["source_a_wins"],
                    "source_b_wins": dimension_counts["source_b_wins"],
                    "ties": dimension_counts["ties"],
                    "reviewed_agreement_rate": _ratio(dimension_counts["ties"], matched),
                    "reviewed_disagreement_rate": _ratio(
                        dimension_counts["source_a_wins"] + dimension_counts["source_b_wins"], matched),
                    "source_a_yes_rate": _ratio(dimension_counts["source_a_yes"], matched),
                    "source_b_yes_rate": _ratio(dimension_counts["source_b_yes"], matched),
                    "paired_rate_difference_a_minus_b": _ratio(dimension_counts["source_a_yes"] - dimension_counts["source_b_yes"], matched),
                    "paired_rate_difference_cluster_bootstrap_95": {
                        "method": "percentile bootstrap; sample matched lead pairs with replacement",
                        "seed": bootstrap_seed,
                        "requested_replicates": bootstrap_reps,
                        "valid_replicates": len(bootstrap_differences),
                        "lower": bootstrap_differences[max(0, math.ceil(0.025 * len(bootstrap_differences)) - 1)] if bootstrap_differences else None,
                        "upper": bootstrap_differences[max(0, math.ceil(0.975 * len(bootstrap_differences)) - 1)] if bootstrap_differences else None,
                    },
                    "excluded_unknown_or_unlabeled": dimension_counts["excluded_unknown_or_unlabeled"],
                    "excluded_duplicate_result_sets": dimension_counts["excluded_duplicate_result_sets"],
                    "minimum_labeled_count": min_labeled,
                    "minimum_labeled_met": matched >= min_labeled,
                }
            value_result = dimensions["value_correct"]
            cohort_leads = leads_by_cohort[cohort]
            only_a = a_present - b_present
            only_b = b_present - a_present
            neither = cohort_leads - (a_present | b_present)
            paired_cost_comparison = {}
            for currency, cost_pair in paired_costs.items():
                matched_cost_leads = int(cost_pair["matched_leads"])
                a_mean = _ratio(float(cost_pair["source_a_total"]), matched_cost_leads)
                b_mean = _ratio(float(cost_pair["source_b_total"]), matched_cost_leads)
                cost_differences = cost_pair["lead_cost_differences"]
                cost_bootstrap = []
                if bootstrap_reps and cost_differences:
                    rng = random.Random(
                        f"{bootstrap_seed}:{field}:{cohort}:{source_a}:{source_b}:{currency}:cost"
                    )
                    for _ in range(bootstrap_reps):
                        sample = [cost_differences[rng.randrange(len(cost_differences))]
                                  for _ in cost_differences]
                        cost_bootstrap.append(sum(sample) / len(sample))
                    cost_bootstrap.sort()
                paired_cost_comparison[currency] = {
                    "matched_leads_with_priced_attempts_from_both_sources": matched_cost_leads,
                    "source_a_mean_estimated_cost_per_matched_lead": a_mean,
                    "source_b_mean_estimated_cost_per_matched_lead": b_mean,
                    "mean_cost_difference_a_minus_b": (a_mean - b_mean) if a_mean is not None and b_mean is not None else None,
                    "excluded_unknown_or_invalid_price_calls": {
                        "source_a_unknown_price_calls": paired_cost_input_quality["source_a_unknown_price_calls"],
                        "source_b_unknown_price_calls": paired_cost_input_quality["source_b_unknown_price_calls"],
                        "source_a_invalid_price_calls": paired_cost_input_quality["source_a_invalid_price_calls"],
                        "source_b_invalid_price_calls": paired_cost_input_quality["source_b_invalid_price_calls"],
                    },
                    "mean_cost_difference_cluster_bootstrap_95": {
                        "method": "percentile bootstrap; sample matched lead cost pairs with replacement",
                        "seed": bootstrap_seed,
                        "requested_replicates": bootstrap_reps,
                        "valid_replicates": len(cost_bootstrap),
                        "lower": cost_bootstrap[max(0, math.ceil(0.025 * len(cost_bootstrap)) - 1)] if cost_bootstrap else None,
                        "upper": cost_bootstrap[max(0, math.ceil(0.975 * len(cost_bootstrap)) - 1)] if cost_bootstrap else None,
                    },
                    "source_a_value_correct_rate_on_priced_subset": _ratio(int(cost_pair["source_a_correct"]), matched_cost_leads),
                    "source_b_value_correct_rate_on_priced_subset": _ratio(int(cost_pair["source_b_correct"]), matched_cost_leads),
                    "priced_subset_value_correct_rate_difference_a_minus_b": _ratio(
                        int(cost_pair["source_a_correct"]) - int(cost_pair["source_b_correct"]), matched_cost_leads),
                    "costs_include_failed_attempts_when_recorded": True,
                }
                cost_difference = paired_cost_comparison[currency]["mean_cost_difference_a_minus_b"]
                quality_difference = paired_cost_comparison[currency]["priced_subset_value_correct_rate_difference_a_minus_b"]
                if cost_difference is not None and quality_difference is not None and cost_difference != 0:
                    cheaper_source = "source_a" if cost_difference < 0 else "source_b"
                    cheaper_quality = quality_difference if cheaper_source == "source_a" else -quality_difference
                    paired_cost_comparison[currency]["descriptive_cost_quality_readout"] = (
                        f"{cheaper_source} had lower estimated cost and no lower reviewed correctness on this priced matched subset."
                        if cheaper_quality >= 0 else
                        f"{cheaper_source} had lower estimated cost, alongside lower reviewed correctness on this priced matched subset."
                    )
                else:
                    paired_cost_comparison[currency]["descriptive_cost_quality_readout"] = "No clear cost direction in the priced matched subset."
            value_interval = value_result["paired_rate_difference_cluster_bootstrap_95"]
            if value_result["matched_adjudicated_leads"] < min_labeled:
                evidence_status = "below_minimum_labeled_caution_threshold"
                quality_direction = "insufficient_reviewed_leads"
            elif value_interval["lower"] is not None and value_interval["lower"] > 0:
                evidence_status, quality_direction = "interval_directional", "source_a_higher_reviewed_correctness"
            elif value_interval["upper"] is not None and value_interval["upper"] < 0:
                evidence_status, quality_direction = "interval_directional", "source_b_higher_reviewed_correctness"
            else:
                evidence_status, quality_direction = "no_clear_interval_direction", "unclear"
            value_sign = value_result["paired_rate_difference_a_minus_b"]
            tradeoffs = [name for name, values in dimensions.items()
                         if name != "value_correct" and values["paired_rate_difference_a_minus_b"] is not None
                         and value_sign is not None
                         and values["paired_rate_difference_a_minus_b"] * value_sign < 0]
            comparisons.append({
                "field": field,
                "engine_path": cohort[0],
                "enrichment_profile": cohort[1],
                "research_lane": cohort[2],
                "source_a": {"type": source_a[0], "name": source_a[1]},
                "source_b": {"type": source_b[0], "name": source_b[1]},
                "sample_leads": len(leads_by_cohort[cohort]),
                "source_a_leads_with_result": len(a_present),
                "source_a_result_coverage": _ratio(len(a_present), len(leads_by_cohort[cohort])),
                "source_b_leads_with_result": len(b_present),
                "source_b_result_coverage": _ratio(len(b_present), len(leads_by_cohort[cohort])),
                "shared_leads_with_result": len(shared),
                "lead_result_availability": {
                    "cohort_leads": len(cohort_leads),
                    "both_sources_returned_result": len(shared),
                    "only_source_a_returned_result": len(only_a),
                    "only_source_b_returned_result": len(only_b),
                    "neither_source_returned_result": len(neither),
                    "both_sources_rate": _ratio(len(shared), len(cohort_leads)),
                    "only_source_a_rate": _ratio(len(only_a), len(cohort_leads)),
                    "only_source_b_rate": _ratio(len(only_b), len(cohort_leads)),
                    "neither_rate": _ratio(len(neither), len(cohort_leads)),
                },
                "paired_provider_attempt_cost_by_currency": paired_cost_comparison,
                "paired_cost_input_quality": {
                    **paired_cost_input_quality,
                    "scope": "matched leads with explicit yes/no value-correctness reviews from both sources",
                    "rule": "only positive-call-count attempts with a finite, nonnegative estimate and a currency enter paired cost totals; missing prices are unknown, invalid amounts are excluded",
                },
                "decision_readout": {
                    "evidence_status": evidence_status,
                    "value_correctness_direction": quality_direction,
                    "dimensions_with_opposing_point_estimate_direction": tradeoffs,
                    "automatic_provider_selection": False,
                    "note": "Descriptive comparison of this matched reviewed cohort; use business importance, evidence strength, coverage, and cost together.",
                },
                "dimensions": dimensions,
                "matched_adjudicated_leads": value_result["matched_adjudicated_leads"],
                "source_a_wins": value_result["source_a_wins"],
                "source_b_wins": value_result["source_b_wins"],
                "ties": value_result["ties"],
                "source_a_value_correct_rate": value_result["source_a_yes_rate"],
                "source_b_value_correct_rate": value_result["source_b_yes_rate"],
                "paired_rate_difference_a_minus_b": value_result["paired_rate_difference_a_minus_b"],
                "excluded_unknown_or_unlabeled": value_result["excluded_unknown_or_unlabeled"],
                "excluded_duplicate_result_sets": value_result["excluded_duplicate_result_sets"],
                "minimum_labeled_count": min_labeled,
                "minimum_labeled_met": value_result["minimum_labeled_met"],
            })
    return comparisons


def _decision_brief(report: dict) -> str:
    provenance = report.get("scoring_provenance", {})
    lines = ["# Enrichment benchmark decision brief", "",
             f"Reviewed field rows: {report.get('review_rows', 0)}", "",
             f"Scored at (UTC): {provenance.get('scored_at_utc', 'unknown')}",
             f"Source SHA-256: `{provenance.get('source_sha256', 'unknown')}`", "",
             "> This is a descriptive summary of reviewed benchmark evidence. It does not automatically select a provider. Cost figures are configured estimates, not invoices.", ""]
    comparisons = report.get("paired_source_comparisons") or []
    if not comparisons:
        lines.extend(["No paired source comparisons were available for this review file.", ""])
        return "\n".join(lines)
    lines.extend(["## Paired source comparisons", ""])
    for item in comparisons:
        source_a = item.get("source_a", {})
        source_b = item.get("source_b", {})
        label_a = f"{source_a.get('name', 'Source A')} ({source_a.get('type', 'unknown')})"
        label_b = f"{source_b.get('name', 'Source B')} ({source_b.get('type', 'unknown')})"
        readout = item.get("decision_readout", {})
        coverage = item.get("lead_result_availability", {})
        value = (item.get("dimensions") or {}).get("value_correct", {})
        interval = value.get("paired_rate_difference_cluster_bootstrap_95", {})
        low, high = interval.get("lower"), interval.get("upper")
        interval_text = f"{low:+.1%} to {high:+.1%}" if isinstance(low, (int, float)) and isinstance(high, (int, float)) else "unavailable"
        lines.extend([
            f"### {item.get('field', '(unknown field)')}: {label_a} vs {label_b}", "",
            f"- Evidence: `{readout.get('evidence_status', 'unavailable')}`; matched reviewed leads: {value.get('matched_adjudicated_leads', 0)}.",
            f"- Value-correctness difference (A minus B): {_display_rate(value.get('paired_rate_difference_a_minus_b'))}; 95% lead-pair interval: {interval_text}.",
            f"- Result availability: both {coverage.get('both_sources_returned_result', 0)}, only A {coverage.get('only_source_a_returned_result', 0)}, only B {coverage.get('only_source_b_returned_result', 0)}, neither {coverage.get('neither_source_returned_result', 0)} of {coverage.get('cohort_leads', 0)} cohort leads.",
        ])
        tradeoffs = readout.get("dimensions_with_opposing_point_estimate_direction") or []
        if tradeoffs:
            lines.append(f"- Other dimensions with opposing point-estimate direction: {', '.join(tradeoffs)}.")
        for currency, costs in (item.get("paired_provider_attempt_cost_by_currency") or {}).items():
            a_cost = costs.get("source_a_mean_estimated_cost_per_matched_lead")
            b_cost = costs.get("source_b_mean_estimated_cost_per_matched_lead")
            cost_interval = costs.get("mean_cost_difference_cluster_bootstrap_95", {})
            cost_low, cost_high = cost_interval.get("lower"), cost_interval.get("upper")
            cost_interval_text = (f"{cost_low:+.4g} to {cost_high:+.4g} {currency}"
                                  if isinstance(cost_low, (int, float)) and isinstance(cost_high, (int, float))
                                  else "unavailable")
            lines.append(
                f"- {currency} estimated cost per priced matched lead: A {_display_amount(a_cost)}; B {_display_amount(b_cost)}; A-minus-B cost interval {cost_interval_text}; {costs.get('descriptive_cost_quality_readout', 'No cost-quality readout.') }"
            )
        cost_quality = item.get("paired_cost_input_quality", {})
        if cost_quality:
            unknown = int(cost_quality.get("source_a_unknown_price_calls", 0)) + int(cost_quality.get("source_b_unknown_price_calls", 0))
            invalid = int(cost_quality.get("source_a_invalid_price_calls", 0)) + int(cost_quality.get("source_b_invalid_price_calls", 0))
            lines.append(f"- Paired cost metadata excluded {unknown} unknown-price calls and {invalid} invalid-price calls across both sources.")
        lines.append("")
    advisories = report.get("waterfall_evidence_advisories") or []
    plans = report.get("waterfall_experiment_plans") or []
    lines.extend(["## Waterfall experiments to consider", ""])
    if plans:
        for item in plans:
            variant_a, variant_b = item["variants"]
            lines.append(
                f"- For `{item.get('field')}` in `{item.get('engine_path')} / {item.get('enrichment_profile')} / {item.get('research_lane')}`, compare A `{ ' > '.join(variant_a['provider_order']) }` with B `{ ' > '.join(variant_b['provider_order']) }`. Hold the lead sample, thresholds, stop rules, budget and currency constant. Review coverage, correctness dimensions, freshness, cost, failures and unknown prices. No run or config change was made."
            )
    else:
        lines.append("No configured-provider pair currently has a directional interval and enough reviewed labels to produce an experiment plan.")
    lines.append("The reviewed-pair minimum is a caution threshold, not a sample-size or power guarantee. Run only on an approved small sample and keep outreach disabled during the comparison.")
    lines.append("")
    lines.extend(["## How to read this", "",
                  "A positive A-minus-B value-correctness difference favors A in this reviewed cohort; a negative difference favors B. An interval spanning zero does not show a clear direction. Coverage and the matched review count matter: comparisons can be biased if the reviewed leads are not representative. Cost comparisons use only the priced matched subset and should be considered alongside the quality interval and business context.", ""])
    experiment_comparisons = report.get("waterfall_experiment_comparisons") or []
    lines.extend(["## Completed waterfall experiment comparisons", ""])
    if experiment_comparisons:
        for item in experiment_comparisons:
            value = (item.get("dimensions") or {}).get("value_correct", {})
            interval = value.get("lead_pair_bootstrap_95", {})
            low, high = interval.get("lower"), interval.get("upper")
            interval_text = f"{low:+.1%} to {high:+.1%}" if isinstance(low, (int, float)) and isinstance(high, (int, float)) else "unavailable"
            availability = item.get("lead_availability", {})
            lines.append(
                f"- `{item.get('experiment_id')}` / `{item.get('field')}` ({item.get('engine_path')} / {item.get('enrichment_profile')} / {item.get('research_lane')}): A-minus-B reviewed correctness {_display_rate(value.get('rate_difference_a_minus_b'))}; interval {interval_text}; matched leads {value.get('matched_reviewed_leads', 0)}; outputs A {availability.get('variant_a', 0)}, B {availability.get('variant_b', 0)}. Status: `{item.get('decision_status')}`."
            )
            experiment_readout = item.get("experiment_readout", {})
            lines.append(
                f"  - Combined readout: `{experiment_readout.get('status', 'unavailable')}`; quality {experiment_readout.get('reviewed_correctness_direction', 'unknown')}; coverage {experiment_readout.get('accepted_coverage_direction', 'unknown')}; lower-cost variant by currency {experiment_readout.get('lower_estimated_cost_variant_by_currency', {})}."
            )
            for tradeoff in experiment_readout.get("tradeoffs", []):
                lines.append(f"  - Trade-off: {tradeoff}.")
            operational = item.get("paired_operational_outcomes", {})
            accepted_interval = operational.get("accepted_coverage_lead_pair_bootstrap_95", {})
            accepted_low, accepted_high = accepted_interval.get("lower"), accepted_interval.get("upper")
            accepted_interval_text = (f"{accepted_low:+.1%} to {accepted_high:+.1%}"
                                      if isinstance(accepted_low, (int, float)) and isinstance(accepted_high, (int, float))
                                      else "unavailable")
            lines.append(
                f"  - Accepted-result coverage on {operational.get('paired_unique_leads', 0)} paired leads: A {_display_rate(operational.get('variant_a_accepted_coverage'))}, B {_display_rate(operational.get('variant_b_accepted_coverage'))}; A-minus-B interval {accepted_interval_text}."
            )
            for currency, costs in (item.get("paired_provider_attempt_cost_by_currency") or {}).items():
                cost_interval = costs.get("mean_cost_difference_lead_pair_bootstrap_95", {})
                cost_low, cost_high = cost_interval.get("lower"), cost_interval.get("upper")
                cost_interval_text = (f"{cost_low:+.4g} to {cost_high:+.4g} {currency}"
                                      if isinstance(cost_low, (int, float)) and isinstance(cost_high, (int, float))
                                      else "unavailable")
                efficiency = costs.get("cost_per_reviewed_correct_result", {})
                lines.append(
                    f"  - {currency} paired estimated spend per lead A {_display_amount(costs.get('variant_a_mean_estimated_cost_per_lead'))}, B {_display_amount(costs.get('variant_b_mean_estimated_cost_per_lead') )}; A-minus-B interval {cost_interval_text}; cost per reviewed-correct result A {_display_amount(efficiency.get('variant_a'))}, B {_display_amount(efficiency.get('variant_b'))}."
                )
            price_quality = item.get("paired_cost_input_quality", {})
            excluded_unknown = int(price_quality.get("variant_a_unknown_price_calls", 0)) + int(price_quality.get("variant_b_unknown_price_calls", 0))
            excluded_invalid = int(price_quality.get("variant_a_invalid_price_calls", 0)) + int(price_quality.get("variant_b_invalid_price_calls", 0))
            if excluded_unknown or excluded_invalid:
                lines.append(f"  - Cost exclusions across variants: {excluded_unknown} unknown-price calls and {excluded_invalid} invalid-price calls.")
    else:
        lines.append("No completed A/B waterfall runs with preserved experiment lead IDs were found in this review file.")
    lines.append("")
    lines.extend(["## How to read this", "",
                  "A positive A-minus-B value-correctness difference favors A in this reviewed cohort; a negative difference favors B. An interval spanning zero does not show a clear direction. Coverage and the matched review count matter: comparisons can be biased if the reviewed leads are not representative. Cost comparisons use only the priced matched subset and should be considered alongside the quality interval and business context.", ""])
    return "\n".join(lines)


def _display_rate(value: Any) -> str:
    return f"{value:.1%}" if isinstance(value, (int, float)) else "n/a"


def _display_amount(value: Any) -> str:
    return f"{value:.4g}" if isinstance(value, (int, float)) else "n/a"


def _waterfall_evidence_advisories(comparisons: list[dict]) -> list[dict]:
    """Surface sufficiently reviewed provider-pair signals without editing waterfall configs."""
    advisories = []
    for item in comparisons:
        source_a, source_b = item.get("source_a", {}), item.get("source_b", {})
        readout = item.get("decision_readout", {})
        if source_a.get("type") != "configured_provider" or source_b.get("type") != "configured_provider":
            continue
        if readout.get("evidence_status") != "interval_directional":
            continue
        direction = readout.get("value_correctness_direction")
        if direction not in {"source_a_higher_reviewed_correctness", "source_b_higher_reviewed_correctness"}:
            continue
        favored = source_a if direction.startswith("source_a") else source_b
        other = source_b if direction.startswith("source_a") else source_a
        value = (item.get("dimensions") or {}).get("value_correct", {})
        interval = value.get("paired_rate_difference_cluster_bootstrap_95", {})
        advisories.append({
            "field": item.get("field", ""),
            "engine_path": item.get("engine_path", "unknown"),
            "enrichment_profile": item.get("enrichment_profile", "unknown"),
            "research_lane": item.get("research_lane", "unknown"),
            "candidate_to_test_earlier": favored.get("name", ""),
            "compared_with": other.get("name", ""),
            "matched_reviewed_leads": value.get("matched_adjudicated_leads", 0),
            "paired_correctness_difference_a_minus_b": value.get("paired_rate_difference_a_minus_b"),
            "paired_correctness_interval_95": {"lower": interval.get("lower"), "upper": interval.get("upper")},
            "other_dimensions_with_opposing_point_estimate_direction": readout.get("dimensions_with_opposing_point_estimate_direction", []),
            "action": "consider_in_a_controlled_waterfall_order_experiment",
            "automatic_config_change": False,
        })
    return advisories


def _waterfall_experiment_plans(advisories: list[dict], min_labeled: int) -> list[dict]:
    plans = []
    for advisory in advisories:
        provider_a = advisory["candidate_to_test_earlier"]
        provider_b = advisory["compared_with"]
        plans.append({
            "field": advisory["field"],
            "engine_path": advisory["engine_path"],
            "enrichment_profile": advisory["enrichment_profile"],
            "research_lane": advisory["research_lane"],
            "providers": [provider_a, provider_b],
            "variants": [
                {"variant": "A", "provider_order": [provider_a, provider_b]},
                {"variant": "B", "provider_order": [provider_b, provider_a]},
            ],
            "hold_constant": ["same lead sample", "same field acceptance thresholds", "same stop rules", "same provider-call budget", "same currency and pricing configuration"],
            "measure": ["accepted coverage", "reviewed value correctness", "identity correctness", "evidence adequacy", "freshness", "provider-attempt cost", "failure and unknown-price rates"],
            "reviewed_pairs_caution_threshold": min_labeled,
            "guardrails": ["run on a small approved sample", "do not send outreach from the experiment", "review evidence and cost before wider rollout", "this threshold is a caution flag, not a power guarantee"],
            "automatic_execution": False,
            "automatic_config_change": False,
        })
    return plans


def _known_attempt_costs(row: dict[str, str]) -> tuple[dict[str, float], int, int]:
    payload = _json(row.get("provider_waterfall_cost"))
    providers = payload.get("providers") if isinstance(payload, dict) else None
    totals: dict[str, float] = defaultdict(float)
    unknown_calls = invalid_calls = 0
    if not isinstance(providers, dict):
        return {}, 0, 0
    for attempt in providers.values():
        if not isinstance(attempt, dict):
            continue
        try:
            calls = max(0, int(attempt.get("calls", 0) or 0))
        except (TypeError, ValueError):
            continue
        if not calls:
            continue
        currency, amount = attempt.get("currency"), attempt.get("estimated_cost")
        if not currency or amount is None:
            unknown_calls += calls
            continue
        try:
            amount_value = float(amount)
        except (TypeError, ValueError):
            invalid_calls += calls
            continue
        if not math.isfinite(amount_value) or amount_value < 0:
            invalid_calls += calls
            continue
        totals[str(currency)] += amount_value
    return dict(totals), unknown_calls, invalid_calls


def _waterfall_experiment_comparisons(rows: list[dict[str, str]], headers: list[str], min_labeled: int,
                                     bootstrap_reps: int, bootstrap_seed: int) -> list[dict]:
    required = {"waterfall_experiment_id", "waterfall_experiment_variant", "waterfall_experiment_lead_id"}
    if not required.issubset(headers):
        return []
    label_columns = {field: f"adjudicated_{field}" if f"adjudicated_{field}" in headers else field
                     for field in REVIEW_FIELDS[:4]}
    groups: dict[tuple[str, str, str, str, str], dict[str, dict[str, list[dict[str, str]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list)))
    for row in rows:
        experiment_id = (row.get("waterfall_experiment_id") or "").strip()
        variant = (row.get("waterfall_experiment_variant") or "").strip().upper()
        lead_id = (row.get("waterfall_experiment_lead_id") or "").strip()
        field = (row.get("field") or "").strip()
        if not experiment_id or variant not in {"A", "B"} or not lead_id or not field:
            continue
        cohort = tuple((row.get(key) or "unknown").strip() or "unknown"
                       for key in ("engine_path", "enrichment_profile", "research_lane"))
        groups[(experiment_id, field, *cohort)][lead_id][variant].append(row)
    comparisons = []
    for (experiment_id, field, engine_path, profile, lane), leads in sorted(groups.items()):
        a_ids = {lead for lead, variants in leads.items() if variants.get("A")}
        b_ids = {lead for lead, variants in leads.items() if variants.get("B")}
        paired_labels: dict[str, list[tuple[int, int]]] = defaultdict(list)
        paired_accepted: list[tuple[int, int]] = []
        status_counts = {"A": defaultdict(int), "B": defaultdict(int)}
        excluded_duplicate = 0
        excluded_unlabeled = defaultdict(int)
        paired_costs: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"a_total": 0.0, "b_total": 0.0, "a_correct": 0, "b_correct": 0,
                     "differences": [], "matched_leads": 0}
        )
        cost_input_quality = {"variant_a_unknown_price_calls": 0, "variant_b_unknown_price_calls": 0,
                              "variant_a_invalid_price_calls": 0, "variant_b_invalid_price_calls": 0}
        a_hashes, b_hashes = set(), set()
        for lead in a_ids | b_ids:
            variants = leads[lead]
            for variant, hashes in (("A", a_hashes), ("B", b_hashes)):
                for row in variants.get(variant, []):
                    digest = (row.get("waterfall_config_sha256") or "").strip()
                    if digest:
                        hashes.add(digest)
            if len(variants.get("A", [])) != 1 or len(variants.get("B", [])) != 1:
                if variants.get("A") and variants.get("B"):
                    excluded_duplicate += 1
                continue
            a_value = _review_category(variants["A"][0].get(label_columns["value_correct"], ""))
            b_value = _review_category(variants["B"][0].get(label_columns["value_correct"], ""))
            a_status = (variants["A"][0].get("status") or "blank").strip().casefold() or "blank"
            b_status = (variants["B"][0].get("status") or "blank").strip().casefold() or "blank"
            status_counts["A"][a_status] += 1
            status_counts["B"][b_status] += 1
            paired_accepted.append((int(a_status == "accepted"), int(b_status == "accepted")))
            if a_value in {"yes", "no"} and b_value in {"yes", "no"}:
                a_costs, a_unknown, a_invalid = _known_attempt_costs(variants["A"][0])
                b_costs, b_unknown, b_invalid = _known_attempt_costs(variants["B"][0])
                cost_input_quality["variant_a_unknown_price_calls"] += a_unknown
                cost_input_quality["variant_b_unknown_price_calls"] += b_unknown
                cost_input_quality["variant_a_invalid_price_calls"] += a_invalid
                cost_input_quality["variant_b_invalid_price_calls"] += b_invalid
                for currency in a_costs.keys() & b_costs.keys():
                    costs = paired_costs[currency]
                    costs["a_total"] += a_costs[currency]
                    costs["b_total"] += b_costs[currency]
                    costs["a_correct"] += a_value == "yes"
                    costs["b_correct"] += b_value == "yes"
                    costs["differences"].append(a_costs[currency] - b_costs[currency])
                    costs["matched_leads"] += 1
            for dimension, column in label_columns.items():
                a_label = _review_category(variants["A"][0].get(column, ""))
                b_label = _review_category(variants["B"][0].get(column, ""))
                if a_label not in {"yes", "no"} or b_label not in {"yes", "no"}:
                    excluded_unlabeled[dimension] += 1
                    continue
                paired_labels[dimension].append((int(a_label == "yes"), int(b_label == "yes")))
        dimensions = {}
        for dimension in label_columns:
            pairs = paired_labels[dimension]
            a_yes = sum(pair[0] for pair in pairs)
            b_yes = sum(pair[1] for pair in pairs)
            differences = []
            if bootstrap_reps and pairs:
                rng = random.Random(f"{bootstrap_seed}:{experiment_id}:{field}:{engine_path}:{profile}:{lane}:{dimension}")
                for _ in range(bootstrap_reps):
                    sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
                    differences.append(sum(a - b for a, b in sample) / len(sample))
                differences.sort()
            dimensions[dimension] = {
                "matched_reviewed_leads": len(pairs),
                "variant_a_yes": a_yes,
                "variant_b_yes": b_yes,
                "variant_a_wins": sum(a == 1 and b == 0 for a, b in pairs),
                "variant_b_wins": sum(a == 0 and b == 1 for a, b in pairs),
                "ties": sum(a == b for a, b in pairs),
                "variant_a_yes_rate": _ratio(a_yes, len(pairs)),
                "variant_b_yes_rate": _ratio(b_yes, len(pairs)),
                "rate_difference_a_minus_b": _ratio(a_yes - b_yes, len(pairs)),
                "lead_pair_bootstrap_95": {
                    "method": "percentile bootstrap; resample matched leads with replacement",
                    "seed": bootstrap_seed,
                    "requested_replicates": bootstrap_reps,
                    "valid_replicates": len(differences),
                    "lower": differences[max(0, math.ceil(0.025 * len(differences)) - 1)] if differences else None,
                    "upper": differences[max(0, math.ceil(0.975 * len(differences)) - 1)] if differences else None,
                },
                "excluded_unlabeled_or_unknown_pairs": excluded_unlabeled[dimension],
                "minimum_labeled_count": min_labeled,
                "minimum_labeled_met": len(pairs) >= min_labeled,
            }
        value = dimensions.get("value_correct", {})
        accepted_a = sum(pair[0] for pair in paired_accepted)
        accepted_b = sum(pair[1] for pair in paired_accepted)
        acceptance_differences = []
        if bootstrap_reps and paired_accepted:
            rng = random.Random(f"{bootstrap_seed}:{experiment_id}:{field}:{engine_path}:{profile}:{lane}:acceptance")
            for _ in range(bootstrap_reps):
                sample = [paired_accepted[rng.randrange(len(paired_accepted))] for _ in paired_accepted]
                acceptance_differences.append(sum(a - b for a, b in sample) / len(sample))
            acceptance_differences.sort()
        operational_outcomes = {
            "paired_unique_leads": len(paired_accepted),
            "variant_a_status_counts": dict(sorted(status_counts["A"].items())),
            "variant_b_status_counts": dict(sorted(status_counts["B"].items())),
            "variant_a_accepted_coverage": _ratio(accepted_a, len(paired_accepted)),
            "variant_b_accepted_coverage": _ratio(accepted_b, len(paired_accepted)),
            "accepted_coverage_difference_a_minus_b": _ratio(accepted_a - accepted_b, len(paired_accepted)),
            "variant_a_acceptance_wins": sum(a == 1 and b == 0 for a, b in paired_accepted),
            "variant_b_acceptance_wins": sum(a == 0 and b == 1 for a, b in paired_accepted),
            "ties": sum(a == b for a, b in paired_accepted),
            "accepted_coverage_lead_pair_bootstrap_95": {
                "method": "percentile bootstrap; resample matched leads with replacement",
                "seed": bootstrap_seed,
                "requested_replicates": bootstrap_reps,
                "valid_replicates": len(acceptance_differences),
                "lower": acceptance_differences[max(0, math.ceil(0.025 * len(acceptance_differences)) - 1)] if acceptance_differences else None,
                "upper": acceptance_differences[max(0, math.ceil(0.975 * len(acceptance_differences)) - 1)] if acceptance_differences else None,
            },
        }
        cost_comparisons = {}
        for currency, costs in paired_costs.items():
            count = int(costs["matched_leads"])
            a_mean, b_mean = _ratio(costs["a_total"], count), _ratio(costs["b_total"], count)
            cost_differences = []
            if bootstrap_reps and costs["differences"]:
                rng = random.Random(f"{bootstrap_seed}:{experiment_id}:{field}:{engine_path}:{profile}:{lane}:{currency}:cost")
                for _ in range(bootstrap_reps):
                    sample = [costs["differences"][rng.randrange(len(costs["differences"]))]
                              for _ in costs["differences"]]
                    cost_differences.append(sum(sample) / len(sample))
                cost_differences.sort()
            cost_comparisons[currency] = {
                "matched_reviewed_leads_with_known_prices_in_both_variants": count,
                "variant_a_mean_estimated_cost_per_lead": a_mean,
                "variant_b_mean_estimated_cost_per_lead": b_mean,
                "mean_cost_difference_a_minus_b": a_mean - b_mean if a_mean is not None and b_mean is not None else None,
                "cost_per_reviewed_correct_result": {
                    "variant_a": _ratio(costs["a_total"], int(costs["a_correct"])),
                    "variant_b": _ratio(costs["b_total"], int(costs["b_correct"])),
                    "variant_a_reviewed_correct_denominator": int(costs["a_correct"]),
                    "variant_b_reviewed_correct_denominator": int(costs["b_correct"]),
                },
                "mean_cost_difference_lead_pair_bootstrap_95": {
                    "method": "percentile bootstrap; resample matched lead cost pairs with replacement",
                    "seed": bootstrap_seed,
                    "requested_replicates": bootstrap_reps,
                    "valid_replicates": len(cost_differences),
                    "lower": cost_differences[max(0, math.ceil(0.025 * len(cost_differences)) - 1)] if cost_differences else None,
                    "upper": cost_differences[max(0, math.ceil(0.975 * len(cost_differences)) - 1)] if cost_differences else None,
                },
            }
        quality_interval = value.get("lead_pair_bootstrap_95", {})
        if value.get("matched_reviewed_leads", 0) < min_labeled:
            quality_direction = "insufficient_reviewed_evidence"
        elif quality_interval.get("lower") is not None and quality_interval["lower"] > 0:
            quality_direction = "variant_a_higher_reviewed_correctness"
        elif quality_interval.get("upper") is not None and quality_interval["upper"] < 0:
            quality_direction = "variant_b_higher_reviewed_correctness"
        else:
            quality_direction = "no_clear_interval_direction"
        acceptance_interval = operational_outcomes["accepted_coverage_lead_pair_bootstrap_95"]
        if acceptance_interval.get("lower") is not None and acceptance_interval["lower"] > 0:
            coverage_direction = "variant_a_higher_accepted_coverage"
        elif acceptance_interval.get("upper") is not None and acceptance_interval["upper"] < 0:
            coverage_direction = "variant_b_higher_accepted_coverage"
        else:
            coverage_direction = "no_clear_interval_direction"
        tradeoffs = []
        if quality_direction.startswith("variant_a") and coverage_direction.startswith("variant_b"):
            tradeoffs.append("reviewed correctness favors A while accepted coverage favors B")
        elif quality_direction.startswith("variant_b") and coverage_direction.startswith("variant_a"):
            tradeoffs.append("reviewed correctness favors B while accepted coverage favors A")
        cost_directions = {}
        for currency, costs in cost_comparisons.items():
            interval = costs["mean_cost_difference_lead_pair_bootstrap_95"]
            if interval.get("lower") is not None and interval["lower"] > 0:
                lower_cost = "variant_b"
            elif interval.get("upper") is not None and interval["upper"] < 0:
                lower_cost = "variant_a"
            else:
                lower_cost = "no_clear_interval_direction"
            cost_directions[currency] = lower_cost
            if quality_direction.startswith("variant_a") and lower_cost == "variant_b":
                tradeoffs.append(f"reviewed correctness favors A while {currency} cost favors B")
            elif quality_direction.startswith("variant_b") and lower_cost == "variant_a":
                tradeoffs.append(f"reviewed correctness favors B while {currency} cost favors A")
        if value.get("matched_reviewed_leads", 0) < min_labeled:
            readout_status = "below_minimum_labeled_caution_threshold"
        elif tradeoffs:
            readout_status = "evidence_tradeoffs_need_business_judgment"
        elif quality_direction == "no_clear_interval_direction":
            readout_status = "no_clear_reviewed_quality_direction"
        else:
            readout_status = "directional_quality_signal_for_this_cohort"
        experiment_readout = {
            "status": readout_status,
            "reviewed_correctness_direction": quality_direction,
            "accepted_coverage_direction": coverage_direction,
            "lower_estimated_cost_variant_by_currency": cost_directions,
            "tradeoffs": tradeoffs,
            "automatic_variant_selection": False,
            "note": "Interpret quality, coverage, and cost separately; results describe this reviewed cohort and do not prove general performance.",
        }
        comparisons.append({
            "experiment_id": experiment_id,
            "field": field,
            "engine_path": engine_path,
            "enrichment_profile": profile,
            "research_lane": lane,
            "variant_a_config_sha256": sorted(a_hashes),
            "variant_b_config_sha256": sorted(b_hashes),
            "lead_availability": {"variant_a": len(a_ids), "variant_b": len(b_ids),
                                  "both_variants": len(a_ids & b_ids),
                                  "only_a": len(a_ids - b_ids), "only_b": len(b_ids - a_ids),
                                  "unpaired_leads_excluded_from_quality_comparison": len(a_ids - b_ids) + len(b_ids - a_ids)},
            "duplicate_result_leads_excluded": excluded_duplicate,
            "paired_operational_outcomes": operational_outcomes,
            "paired_provider_attempt_cost_by_currency": cost_comparisons,
            "paired_cost_input_quality": {**cost_input_quality,
                                           "scope": "paired leads with explicit yes/no value-correctness reviews",
                                           "unknown_or_invalid_prices_excluded_not_treated_as_zero": True},
            "experiment_readout": experiment_readout,
            "dimensions": dimensions,
            "decision_status": "below_minimum_labeled_caution_threshold" if value.get("matched_reviewed_leads", 0) < min_labeled else "descriptive_only",
            "automatic_provider_selection": False,
        })
    return comparisons


def score(source: str, out: str = "", min_labeled: int = 20,
          cost_bootstrap_reps: int = 500, cost_bootstrap_seed: int = 42,
          paired_bootstrap_reps: int = 500, paired_bootstrap_seed: int = 42,
          markdown_out: str = "") -> tuple[dict, Path]:
    """Summarize reviewed quality, coverage, freshness and declared provider cost."""
    if min_labeled < 1:
        raise ValueError("--min-labeled must be at least 1.")
    if cost_bootstrap_reps < 0 or cost_bootstrap_reps > 5000:
        raise ValueError("--cost-bootstrap-reps must be between 0 and 5000.")
    if paired_bootstrap_reps < 0 or paired_bootstrap_reps > 5000:
        raise ValueError("--paired-bootstrap-reps must be between 0 and 5000.")
    headers, rows = _read(source)
    required = {"field", "status", *REVIEW_FIELDS[:4]}
    missing = sorted(required - set(headers))
    if missing:
        raise ValueError("Review CSV is missing columns: " + ", ".join(missing))
    by_field: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_path_profile_lane: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    by_field_source: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        field = (row.get("field") or "(blank field)").strip()
        source_type = (row.get("source_type") or "unattributed").strip() or "unattributed"
        source_name = (row.get("source_name") or "unattributed").strip() or "unattributed"
        by_field[field].append(row)
        by_field_source[(field, source_type, source_name)].append(row)
        cohort = tuple((row.get(key) or "unknown").strip() or "unknown" for key in ("engine_path", "enrichment_profile", "research_lane"))
        by_path_profile_lane[cohort].append(row)

    def metrics(items: list[dict[str, str]]) -> dict:
        label_columns = {field: f"adjudicated_{field}" if f"adjudicated_{field}" in headers else field
                         for field in REVIEW_FIELDS[:4]}
        labeled = {field: [r for r in items if (r.get(label_columns[field]) or "").strip().casefold() in YES | NO]
                   for field in REVIEW_FIELDS[:4]}
        responses = {}
        for field in REVIEW_FIELDS[:4]:
            counts = {"yes": 0, "no": 0, "unknown": 0, "blank": 0, "invalid": 0}
            for row in items:
                value = (row.get(label_columns[field]) or "").strip().casefold()
                if value in YES:
                    counts["yes"] += 1
                elif value in NO:
                    counts["no"] += 1
                elif value in UNKNOWN:
                    counts["unknown"] += 1
                elif not value:
                    counts["blank"] += 1
                else:
                    counts["invalid"] += 1
            responses[field] = counts
        correct_values = sum((r.get(label_columns["value_correct"]) or "").strip().casefold() in YES for r in labeled["value_correct"])
        costs: dict[str, float] = defaultdict(float)
        provider_attempt_costs: dict[str, float] = defaultdict(float)
        provider_cost_review_denominator: dict[str, int] = defaultdict(int)
        reviewed_provider_costs: dict[str, float] = defaultdict(float)
        reviewed_cost_clusters: dict[str, dict[str, dict[str, float | int]]] = defaultdict(
            lambda: defaultdict(lambda: {"cost": 0.0, "correct": 0})
        )
        human_correct_with_provider_attempts = 0
        provider_cost_details: dict[str, dict] = defaultdict(lambda: {"calls": 0, "estimated_cost_by_currency": {}, "unknown_price_calls": 0})
        unknown_provider_attempts = 0
        for row in items:
            try:
                amount = float(row.get("cost_amount") or "")
            except (TypeError, ValueError):
                continue
            currency = (row.get("cost_currency") or "unknown").strip() or "unknown"
            costs[currency] += amount
        for row_index, row in enumerate(items):
            waterfall_cost = _json(row.get("provider_waterfall_cost"))
            if not isinstance(waterfall_cost, dict):
                continue
            provider_map = waterfall_cost.get("providers") if isinstance(waterfall_cost.get("providers"), dict) else {}
            row_currencies = set()
            row_has_attempts = False
            for provider_name, attempt in provider_map.items():
                if not isinstance(attempt, dict):
                    continue
                try:
                    attempt_count = max(0, int(attempt.get("calls", 0) or 0))
                except (TypeError, ValueError):
                    continue
                attempt_amount, attempt_currency = attempt.get("estimated_cost"), attempt.get("currency")
                detail = provider_cost_details[str(provider_name)]
                detail["calls"] += attempt_count
                row_has_attempts |= attempt_count > 0
                if isinstance(attempt_amount, (int, float)) and math.isfinite(float(attempt_amount)) and attempt_currency:
                    provider_attempt_costs[str(attempt_currency)] += float(attempt_amount)
                    row_currencies.add(str(attempt_currency))
                    currency_totals = detail["estimated_cost_by_currency"]
                    currency_totals[str(attempt_currency)] = currency_totals.get(str(attempt_currency), 0.0) + float(attempt_amount)
                elif attempt_count:
                    unknown_provider_attempts += attempt_count
                    detail["unknown_price_calls"] += attempt_count
            label_column = label_columns["value_correct"]
            label = (row.get(label_column) or "").strip().casefold()
            is_reviewed = label in YES | NO
            is_human_correct = label in YES
            cluster_id = (row.get("source_row") or row.get("evaluation_id") or f"row:{row_index}").strip()
            if row_has_attempts and is_reviewed:
                for currency in row_currencies:
                    reviewed_cost_clusters[currency][cluster_id]["cost"] += sum(
                        float(attempt.get("estimated_cost"))
                        for attempt in provider_map.values()
                        if isinstance(attempt, dict)
                        and attempt.get("currency") == currency
                        and isinstance(attempt.get("estimated_cost"), (int, float))
                        and math.isfinite(float(attempt.get("estimated_cost")))
                    )
                for currency in row_currencies:
                    row_cost = sum(
                        float(attempt.get("estimated_cost"))
                        for attempt in provider_map.values()
                        if isinstance(attempt, dict)
                        and attempt.get("currency") == currency
                        and isinstance(attempt.get("estimated_cost"), (int, float))
                        and math.isfinite(float(attempt.get("estimated_cost")))
                    )
                    reviewed_provider_costs[currency] += row_cost
                    if is_human_correct:
                        reviewed_cost_clusters[currency][cluster_id]["correct"] += 1
            if row_has_attempts and is_human_correct:
                human_correct_with_provider_attempts += 1
                for currency in row_currencies:
                    provider_cost_review_denominator[currency] += 1
        accepted = sum((r.get("status") or "").strip().casefold() == "accepted" for r in items)
        fresh_known = [r for r in items if (r.get("freshness_status") or "").strip() and (r.get("freshness_status") or "").casefold() != "unknown"]
        cost_uncertainty = {}
        for currency, clusters in reviewed_cost_clusters.items():
            cluster_values = list(clusters.values())
            point_denominator = sum(int(value["correct"]) for value in cluster_values)
            ratios = []
            if cost_bootstrap_reps and cluster_values:
                rng = random.Random(f"{cost_bootstrap_seed}:{currency}:{'|'.join(sorted(clusters))}")
                for _ in range(cost_bootstrap_reps):
                    sampled = [cluster_values[rng.randrange(len(cluster_values))] for _ in cluster_values]
                    denominator = sum(int(value["correct"]) for value in sampled)
                    if denominator:
                        numerator = sum(float(value["cost"]) for value in sampled)
                        ratios.append(numerator / denominator)
            ratios.sort()
            cost_uncertainty[currency] = {
                "reviewed_cost_estimate": reviewed_provider_costs[currency],
                "human_reviewed_correct_denominator": point_denominator,
                "point_estimate_per_human_reviewed_correct_result": _ratio(reviewed_provider_costs[currency], point_denominator),
                "unique_leads_with_reviewed_provider_attempts": len(cluster_values),
                "cluster_bootstrap_95": {
                    "method": "percentile bootstrap; sample lead clusters with replacement",
                    "seed": cost_bootstrap_seed,
                    "requested_replicates": cost_bootstrap_reps,
                    "valid_replicates": len(ratios),
                    "replicates_without_correct_result": cost_bootstrap_reps - len(ratios),
                    "lower": ratios[max(0, math.ceil(0.025 * len(ratios)) - 1)] if ratios else None,
                    "upper": ratios[max(0, math.ceil(0.975 * len(ratios)) - 1)] if ratios else None,
                },
            }
        return {"fields": len(items), "accepted": accepted, "coverage": _ratio(accepted, len(items)),
                "status_counts": {status: sum((r.get("status") or "").strip().casefold() == status for r in items)
                                  for status in ("accepted", "candidate", "not_found", "rejected", "error")},
                "review_labels": {k: {
                    "label_column": label_columns[k],
                    "labeled": len(v),
                    "yes": sum((r.get(label_columns[k]) or "").strip().casefold() in YES for r in v),
                    "rate": _ratio(sum((r.get(label_columns[k]) or "").strip().casefold() in YES for r in v), len(v)),
                    "wilson_95": _wilson(sum((r.get(label_columns[k]) or "").strip().casefold() in YES for r in v), len(v)),
                    "minimum_labeled_count": min_labeled,
                    "minimum_labeled_met": len(v) >= min_labeled,
                } for k, v in labeled.items()},
                "review_responses": responses,
                "reviewer_agreement": {field: _agreement(items, field) for field in REVIEW_FIELDS[:4]
                                        if f"reviewer_a_{field}" in headers and f"reviewer_b_{field}" in headers},
                "freshness_documented": len(fresh_known), "freshness_documented_rate": _ratio(len(fresh_known), len(items)),
                "declared_cost_by_currency": dict(costs),
                "declared_cost_per_accepted_field_by_currency": {currency: _ratio(amount, accepted) for currency, amount in costs.items()},
                "provider_attempt_cost_estimate_by_currency": dict(provider_attempt_costs),
                "provider_attempt_cost_estimate_by_provider": dict(provider_cost_details),
                "provider_attempt_estimate_per_accepted_result_by_currency": {currency: _ratio(amount, accepted) for currency, amount in provider_attempt_costs.items()},
                "human_reviewed_correct_results_with_provider_attempts": human_correct_with_provider_attempts,
                "provider_attempt_estimate_per_human_reviewed_correct_result_by_currency": {
                    currency: _ratio(reviewed_provider_costs[currency], provider_cost_review_denominator[currency]) for currency in reviewed_provider_costs},
                "provider_attempt_cost_human_correct_denominator_by_currency": dict(provider_cost_review_denominator),
                "provider_cost_per_reviewed_correct_uncertainty_by_currency": cost_uncertainty,
                "provider_attempts_with_unknown_price": unknown_provider_attempts,
                "provider_attempt_cost_note": "Attempt totals include failed/rejected lookups when recorded. Cost per human-reviewed correct result uses priced provider costs only from rows explicitly labeled yes or no for value_correct, divided by explicitly yes-labeled rows with priced provider attempts. Unknown-price attempts remain separately counted. The lead-cluster percentile bootstrap is descriptive sampling uncertainty; it cannot correct sampling bias or establish population performance. Estimates use configured call prices, not invoices."}

    source_sha256 = hashlib.sha256(Path(source).read_bytes()).hexdigest()
    paired_comparisons = _paired_source_comparisons(
        rows, headers, min_labeled, paired_bootstrap_reps, paired_bootstrap_seed)
    waterfall_advisories = _waterfall_evidence_advisories(paired_comparisons)
    experiment_comparisons = _waterfall_experiment_comparisons(
        rows, headers, min_labeled, paired_bootstrap_reps, paired_bootstrap_seed)
    report = {"schema": "dbi.enrichment-evaluation.v1", "source_file": str(Path(source).resolve()),
              "scoring_provenance": {
                  "scored_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "source_sha256": source_sha256,
                  "settings": {
                      "minimum_labeled_caution_threshold": min_labeled,
                      "cost_bootstrap_replicates": cost_bootstrap_reps,
                      "cost_bootstrap_seed": cost_bootstrap_seed,
                      "paired_bootstrap_replicates": paired_bootstrap_reps,
                      "paired_bootstrap_seed": paired_bootstrap_seed,
                  },
              },
              "review_rows": len(rows), "fields": {name: metrics(items) for name, items in sorted(by_field.items())},
              "by_field_and_source": [{"field": field, "source_type": source_type, "source_name": source_name,
                                       **metrics(items)}
                                      for (field, source_type, source_name), items in sorted(by_field_source.items())],
              "paired_source_comparisons": paired_comparisons,
              "waterfall_evidence_advisories": waterfall_advisories,
              "waterfall_experiment_plans": _waterfall_experiment_plans(waterfall_advisories, min_labeled),
              "waterfall_experiment_comparisons": experiment_comparisons,
              "by_path_profile_and_lane": {"|".join(key): metrics(items) for key, items in sorted(by_path_profile_lane.items())},
              "overall": metrics(rows),
              "minimum_labeled_for_caution_flag": min_labeled,
              "interpretation": "Coverage is the accepted-result share. Human label rates apply only to explicitly labeled rows; they are not population-wide accuracy estimates. Wilson intervals describe sampling uncertainty under a simple binomial model, not bias or representativeness. Paired source wins compare adjudicated value correctness for the same lead and field; they are descriptive and do not prove general provider superiority. Cost bootstrap intervals resample lead clusters from explicitly reviewed rows and do not correct sampling bias. The minimum labeled count is a caution flag, not proof of statistical power or significance. Source names may identify a provider or an evidence source depending on the producer. Declared costs may be estimates, not provider invoices. Compare cohorts only when field and lead mix are sufficiently similar."}
    output = Path(out) if out else Path(source).with_name(Path(source).stem + "-evaluation.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if markdown_out:
        brief_path = Path(markdown_out)
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(_decision_brief(report), encoding="utf-8")
        print(f"Wrote decision brief: {brief_path}")
    print(f"Scored {len(rows)} reviewed field rows across {len(by_field)} fields: {output}")
    for field, values in report["fields"].items():
        m = values["review_labels"]
        fmt = lambda key: "n/a" if m[key]["rate"] is None else f"{m[key]['rate']:.1%} ({m[key]['labeled']} labeled)"
        print(f"  {field}: coverage {values['coverage']:.1%}; value correctness {fmt('value_correct')}; identity correctness {fmt('identity_correct')}; evidence adequacy {fmt('evidence_adequate')}; freshness accepted {fmt('freshness_acceptable')}")
    print("Costs are summed only when a result declares a numeric amount and currency; unknown costs are omitted.")
    print("Provider waterfall cost-per-human-reviewed-correct metrics use only explicitly yes-labeled value_correct rows; estimates are not invoices.")
    return report, output


def score_ledger(source: str, out: str = "", min_decided: int = 10) -> tuple[dict, Path]:
    """Measure Ledger fit judgements and associate them with same-lane field results."""
    if min_decided < 1:
        raise ValueError("--min-decided must be at least 1.")
    headers, rows = _read(source)
    column = next((name for name in headers if name.strip().casefold() == "enrichment_review"), "")
    if not column:
        raise ValueError("Ledger CSV needs the enrichment_review column. Make it visible before exporting the grid.")
    desk_status_column = next((name for name in headers
                               if name.strip().casefold().replace(" ", "_") in {"desk_status", "c_desk_status"}), "")
    desk_last_column = next((name for name in headers
                             if name.strip().casefold().replace(" ", "_") in {"desk_last_update", "desk_last", "c_desk_last"}), "")

    latest: dict[tuple[int, str], dict[str, Any]] = {}
    row_results: dict[int, list[dict[str, Any]]] = {}
    malformed = 0
    valid_history_entries = 0
    for row_number, row in enumerate(rows, 2):
        payload = _json(row.get(column))
        if not isinstance(payload, dict) or payload.get("schema") != "dbi.enrichment-human-review.v1":
            if row.get(column, "").strip():
                malformed += 1
            continue
        history = payload.get("history")
        if not isinstance(history, list):
            malformed += 1
            continue
        for item in history:
            if not isinstance(item, dict) or item.get("judgment") not in FIT_JUDGMENTS:
                malformed += 1
                continue
            lane = str(item.get("lane") or "unknown").strip().casefold()
            if lane not in {"herald", "website", "presence"}:
                lane = "unknown"
            profile = str(item.get("profile_key") or "unknown").strip() or "unknown"
            raw_context = item.get("target_context") if isinstance(item.get("target_context"), dict) else {}
            target_context = {}
            for field in TARGET_CONTEXT_FIELDS:
                value = raw_context.get(field)
                if isinstance(value, (str, int, float)) and str(value).strip():
                    target_context[field] = str(value).strip()[:160]
            raw_observed = item.get("observed_context") if isinstance(item.get("observed_context"), dict) else {}
            observed_context: dict[str, list[str]] = {}
            for field, (_, item_key) in OBSERVED_CONTEXT_FIELDS.items():
                raw_values = raw_observed.get(field)
                if not isinstance(raw_values, list):
                    continue
                observed_values = []
                for raw_value in raw_values[:12]:
                    value = raw_value if not item_key and isinstance(raw_value, str) else raw_value.get(item_key) if item_key and isinstance(raw_value, dict) else ""
                    if isinstance(value, str) and value.strip():
                        observed_values.append(value.strip()[:120])
                if observed_values:
                    observed_context[field] = list(dict.fromkeys(observed_values))
            raw_desk_status = str(row.get(desk_status_column) or "").strip().casefold().replace("_", " ") if desk_status_column else "not_available"
            if raw_desk_status in {"call booked", "booked call"}:
                raw_desk_status = "booked"
            if raw_desk_status == "to do":
                raw_desk_status = "not_recorded"
            elif not raw_desk_status:
                raw_desk_status = "not_recorded"
            elif raw_desk_status not in {"sent", "skipped", "replied", "booked", "won", "lost", "not_available"}:
                raw_desk_status = "other"
            desk_date = str(row.get(desk_last_column) or "").strip()[:10] if desk_last_column else ""
            review_date = str(item.get("reviewed_at") or "")[:10]
            try:
                desk_day = date.fromisoformat(desk_date)
                review_day = date.fromisoformat(review_date)
            except ValueError:
                desk_timing = "unknown"
            else:
                if desk_day > review_day:
                    desk_timing = "after_review"
                elif desk_day == review_day:
                    desk_timing = "same_day_order_unknown"
                else:
                    desk_timing = "before_review"
            latest[(row_number, lane)] = {"judgment": item["judgment"], "lane": lane, "profile_key": profile,
                                          "reviewed_at": str(item.get("reviewed_at") or ""),
                                          "research_checked_at": str(item.get("research_checked_at") or ""),
                                          "target_context": target_context,
                                          "observed_context": observed_context,
                                          "desk_status": raw_desk_status,
                                          "desk_timing": desk_timing,
                                          "row_number": row_number}
            valid_history_entries += 1

        result_column = next((name for name in headers if name.strip().casefold() == "field_results"), "")
        if result_column:
            result_payload = _json(row.get(result_column))
            if isinstance(result_payload, list):
                row_results[row_number] = [item for item in result_payload
                                           if isinstance(item, dict) and item.get("schema") == "dbi.field-result.v1"]

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        counts = {label: sum(item["judgment"] == label for item in items) for label in ("good_fit", "not_a_fit", "uncertain")}
        decided = counts["good_fit"] + counts["not_a_fit"]
        return {"latest_row_lane_reviews": len(items), "judgment_counts": counts,
                "good_fit_rate_among_decided": _ratio(counts["good_fit"], decided),
                "uncertain_rate": _ratio(counts["uncertain"], len(items)),
                "review_time_documented": sum(bool(item["reviewed_at"]) for item in items),
                "research_check_time_documented": sum(bool(item["research_checked_at"]) for item in items)}

    latest_items = list(latest.values())
    by_lane_profile: dict[str, dict[str, Any]] = {}
    keys = sorted({(item["lane"], item["profile_key"]) for item in latest_items})
    for lane, profile in keys:
        group = [item for item in latest_items if item["lane"] == lane and item["profile_key"] == profile]
        by_lane_profile[f"{lane}|{profile}"] = summarize(group)

    profile_comparison: dict[str, dict[str, Any]] = {}
    for lane, profile in keys:
        group = [item for item in latest_items if item["lane"] == lane and item["profile_key"] == profile]
        alternatives = [item for item in latest_items if item["lane"] == lane and item["profile_key"] != profile]
        profile_metrics = summarize(group)
        alternative_metrics = summarize(alternatives)
        group_rate = profile_metrics["good_fit_rate_among_decided"]
        alternatives_rate = alternative_metrics["good_fit_rate_among_decided"]
        decided = profile_metrics["judgment_counts"]["good_fit"] + profile_metrics["judgment_counts"]["not_a_fit"]
        alternatives_decided = alternative_metrics["judgment_counts"]["good_fit"] + alternative_metrics["judgment_counts"]["not_a_fit"]
        delta = round((group_rate - alternatives_rate) * 100, 1) if group_rate is not None and alternatives_rate is not None else None
        profile_comparison[f"{lane}|{profile}"] = {
            "profile_decided_reviews": decided,
            "profile_good_fit_rate_among_decided": group_rate,
            "other_profiles_decided_reviews": alternatives_decided,
            "other_profiles_good_fit_rate_among_decided": alternatives_rate,
            "good_fit_rate_delta_percentage_points": delta,
            "sample_status": "too_few_profile_reviews" if decided < min_decided else
                             "too_few_other_profile_reviews" if alternatives_decided < min_decided else "descriptive_only",
            "comparison_note": "Other-profile baseline includes only different profile keys in the same lane; it is descriptive and non-causal."}

    target_segment_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    target_segment_labels: dict[tuple[str, str, str], str] = {}
    target_context_coverage = {dimension: 0 for dimension in TARGET_CONTEXT_FIELDS.values()}
    for review in latest_items:
        context = review["target_context"]
        for field, dimension in TARGET_CONTEXT_FIELDS.items():
            value = context.get(field)
            if not value:
                continue
            target_context_coverage[dimension] += 1
            key = (review["lane"], dimension, value.casefold())
            target_segment_groups[key].append(review)
            target_segment_labels.setdefault(key, value)
    target_segments: dict[str, dict[str, Any]] = {}
    for key, group in sorted(target_segment_groups.items()):
        lane, dimension, _ = key
        metrics = summarize(group)
        decided = metrics["judgment_counts"]["good_fit"] + metrics["judgment_counts"]["not_a_fit"]
        target_segments[f"{lane}|{dimension}|{target_segment_labels[key]}"] = {
            **metrics, "decided_reviews": decided,
            "sample_status": "too_few_decided_reviews" if decided < min_decided else "descriptive_only"}

    observed_segment_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    observed_segment_labels: dict[tuple[str, str, str], str] = {}
    observed_context_coverage = {dimension: 0 for dimension, _ in OBSERVED_CONTEXT_FIELDS.values()}
    for review in latest_items:
        context = review["observed_context"]
        for field, (dimension, _) in OBSERVED_CONTEXT_FIELDS.items():
            values = context.get(field, [])
            if not values:
                continue
            observed_context_coverage[dimension] += 1
            for value in values:
                key = (review["lane"], dimension, value.casefold())
                observed_segment_groups[key].append(review)
                observed_segment_labels.setdefault(key, value)
    observed_segments: dict[str, dict[str, Any]] = {}
    for key, group in sorted(observed_segment_groups.items()):
        lane, dimension, _ = key
        metrics = summarize(group)
        decided = metrics["judgment_counts"]["good_fit"] + metrics["judgment_counts"]["not_a_fit"]
        observed_segments[f"{lane}|{dimension}|{observed_segment_labels[key]}"] = {
            **metrics, "decided_reviews": decided,
            "sample_status": "too_few_decided_reviews" if decided < min_decided else "descriptive_only"}

    def outcome_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
        counts: dict[str, int] = defaultdict(int)
        timing: dict[str, int] = defaultdict(int)
        for item in items:
            counts[item["desk_status"]] += 1
            timing[item["desk_timing"]] += 1
        return {"fit_reviews": len(items), "desk_status_column_found": bool(desk_status_column),
                "desk_last_update_column_found": bool(desk_last_column),
                "desk_status_counts": dict(sorted(counts.items())),
                "desk_timing_relative_to_review_counts": dict(sorted(timing.items()))}

    outcomes_by_judgment_lane_profile: dict[str, dict[str, Any]] = {}
    outcome_keys = sorted({(item["judgment"], item["lane"], item["profile_key"]) for item in latest_items})
    for judgment, lane, profile in outcome_keys:
        group = [item for item in latest_items if (item["judgment"], item["lane"], item["profile_key"]) == (judgment, lane, profile)]
        outcomes_by_judgment_lane_profile[f"{judgment}|{lane}|{profile}"] = outcome_summary(group)

    def outcome_segments(context_name: str, dimensions: dict[str, str], observed: bool = False) -> dict[str, dict[str, Any]]:
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        labels: dict[tuple[str, str, str], str] = {}
        for review in latest_items:
            context = review[context_name]
            for field, dimension in dimensions.items():
                raw = context.get(field, []) if observed else context.get(field)
                values = raw if isinstance(raw, list) else [raw]
                for value in dict.fromkeys(v for v in values if isinstance(v, str) and v.strip()):
                    key = (review["lane"], dimension, value.casefold())
                    groups[key].append(review)
                    labels.setdefault(key, value)
        out: dict[str, dict[str, Any]] = {}
        for key, group in sorted(groups.items()):
            lane, dimension, _ = key
            out[f"{lane}|{dimension}|{labels[key]}"] = outcome_summary(group)
        return out

    target_outcomes = outcome_segments("target_context", TARGET_CONTEXT_FIELDS)
    observed_outcomes = outcome_segments("observed_context", {field: config[0] for field, config in OBSERVED_CONTEXT_FIELDS.items()}, observed=True)

    lane_aliases = {"website_enrichment": "website", "herald_research": "herald", "presence_research": "presence"}
    joined: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    matched_reviews = 0
    unmatched_reviews = 0
    for review in latest_items:
        matching = []
        for result in row_results.get(int(review["row_number"]), []):
            metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
            result_lane = lane_aliases.get(str(metadata.get("lane") or ""), "")
            if result_lane != review["lane"]:
                continue
            matching.append(result)
        if not matching:
            unmatched_reviews += 1
            continue
        matched_reviews += 1
        for result in matching:
            source_info = result.get("source") if isinstance(result.get("source"), dict) else {}
            freshness = result.get("freshness") if isinstance(result.get("freshness"), dict) else {}
            verification = result.get("verification") if isinstance(result.get("verification"), dict) else {}
            joined[(review["judgment"], review["lane"], review["profile_key"])].append({
                "field": str(result.get("field") or "(blank field)"),
                "status": str(result.get("status") or "unknown"),
                "source_type": str(source_info.get("type") or "unknown"),
                "source_name": str(source_info.get("name") or "unknown"),
                "freshness_status": str(freshness.get("status") or "unknown"),
                "verification_status": str(verification.get("status") or "unknown"),
            })

    def field_summary(items: list[dict[str, str]]) -> dict[str, Any]:
        def counts(records: list[dict[str, str]], key: str) -> dict[str, int]:
            values: dict[str, int] = defaultdict(int)
            for record in records:
                values[record[key]] += 1
            return dict(sorted(values.items()))

        fields: dict[str, list[dict[str, str]]] = defaultdict(list)
        for item in items:
            fields[item["field"]].append(item)
        return {"field_result_records": len(items), "fields": {
            field: {"records": len(records),
                    "status_counts": counts(records, "status"),
                    "accepted_rate": _ratio(sum(r["status"] == "accepted" for r in records), len(records)),
                    "source_type_counts": counts(records, "source_type"),
                    "source_name_counts": counts(records, "source_name"),
                    "freshness_status_counts": counts(records, "freshness_status"),
                    "verification_status_counts": counts(records, "verification_status")}
            for field, records in sorted(fields.items())}}

    field_join = {f"{judgment}|{lane}|{profile}": field_summary(items)
                  for (judgment, lane, profile), items in sorted(joined.items())}

    report = {"schema": "dbi.ledger-fit-evaluation.v1", "source_file": str(Path(source).resolve()),
              "source_rows": len(rows), "valid_history_entries": valid_history_entries,
              "latest_by_row_and_lane": summarize(latest_items), "by_lane_and_profile": by_lane_profile,
              "profile_comparison": {"minimum_decided_reviews": min_decided,
                                     "by_lane_and_profile": profile_comparison},
              "target_context_segments": {"minimum_decided_reviews": min_decided,
                                          "review_coverage_by_dimension": target_context_coverage,
                                          "by_lane_dimension_and_value": target_segments},
              "observed_context_segments": {"minimum_decided_reviews": min_decided,
                                             "review_coverage_by_dimension": observed_context_coverage,
                                             "by_lane_dimension_and_value": observed_segments},
              "send_desk_outcomes": {"desk_status_column_found": bool(desk_status_column),
                                     "desk_last_update_column_found": bool(desk_last_column),
                                     "by_judgment_lane_and_profile": outcomes_by_judgment_lane_profile,
                                     "by_requested_target_segments": target_outcomes,
                                     "by_observed_research_cue_segments": observed_outcomes},
              "field_results_join": {"reviewed_rows_with_matching_lane_results": matched_reviews,
                                     "reviewed_rows_without_matching_lane_results": unmatched_reviews,
                                     "by_judgment_lane_and_profile": field_join},
              "malformed_or_unsupported_entries": malformed,
              "interpretation": "Fit rates summarize human decisions, not factual accuracy, conversion, ability to pay, or population-wide lead quality. Field-result status, provider and freshness counts are descriptive associations among same-row results in the reviewed lane; fit judgements do not verify those fields. Each grid row contributes its latest review per lane; repeated reviews are retained in the source history but do not get extra weight here. Profile groups with small samples should be treated as descriptive only."}
    output = Path(out) if out else Path(source).with_name(Path(source).stem + "-ledger-fit-evaluation.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Scored {len(latest_items)} latest Ledger fit reviews across {len(by_lane_profile)} lane/profile groups: {output}")
    print("Fit rates are descriptive human decisions, not verified accuracy or business outcomes.")
    return report, output


def _send_outcome_brief(report: dict) -> str:
    def pct(value: float | None) -> str:
        return "not available" if value is None else f"{value:.1%}"

    lines = ["# Waterfall experiment: Send Desk outcomes", "", f"- Engine: `{report['engine']}`",
             f"- Experiment filter: `{report.get('experiment_filter') or 'all tagged experiments'}`",
             f"- Scored at (UTC): {report['scored_at_utc']}", "",
             "These are descriptive observations from explicitly logged Send Desk actions. They do not prove that a variant caused an outcome or that one provider is better.", ""]
    for cohort in report["cohorts"]:
        lines.extend([f"## Experiment `{cohort['experiment_id']}` · field `{cohort['field'] or 'unspecified'}`", "",
                      "| Variant | Assigned | Sent | Send coverage | Skipped | Unmarked | Replies | Reply rate (95% interval) | Calls booked | Booked rate (95% interval) | Wins | Win rate (95% interval) | Sample note |",
                      "|---|---:|---:|---:|---:|---:|---:|---|---:|---|---:|---|---|"])
        seeds = ", ".join(cohort["outreach_assignment_seeds"]) or "not recorded (legacy rows)"
        lines.append(f"Outreach assignment mode: `{cohort['outreach_assignment_mode']}`; seed(s): {seeds}; metadata-eligible for comparison: {cohort['comparison_eligible']}.\n")
        for variant in ("A", "B"):
            m = cohort["variants"].get(variant)
            if not m:
                continue
            orders = "; ".join(json.dumps(order, ensure_ascii=False) if isinstance(order, (list, dict)) else str(order)
                                for order in m["provider_orders"]) or "not recorded"
            lines.append(f"{variant} recorded provider order(s): `{orders}`. Config fingerprint(s): {', '.join(value[:12] for value in m['config_sha256s']) or 'not recorded'}. Metadata complete: {m['configuration_metadata_complete']}; consistent: {m['configuration_metadata_consistent']}.\n")
            intervals = m["outcome_rate_95_percent_wilson_intervals"]
            def interval(key: str) -> str:
                ci = intervals[key]
                return "not available" if ci is None else f"{ci['lower']:.1%}–{ci['upper']:.1%}"
            note = "Low sample (<30 sent)" if m["low_sample_caution"] else "30+ sent; still descriptive"
            lines.append(f"| {variant} | {m['assigned_unique_leads']} | {m['sent_unique_leads']} | {pct(m['send_coverage_rate'])} | {m['skipped_unique_leads']} | {m['unmarked_unique_leads']} | {m['replied_unique_leads']} | {pct(m['reply_rate_per_sent_lead'])} ({interval('replied')}) | {m['booked_unique_leads']} | {pct(m['booked_rate_per_sent_lead'])} ({interval('booked')}) | {m['won_unique_leads']} | {pct(m['won_rate_per_sent_lead'])} ({interval('won')}) | {note} |")
            mature = m["mature_window"]
            lines.append(f"\n{variant} fixed-window outcomes ({mature['window_days']} days): {mature['mature_sent_leads']} mature sent leads; {mature['awaiting_window_leads']} still awaiting the full window; replies {pct(mature['reply_rate'])}, booked {pct(mature['booked_rate'])}, wins {pct(mature['won_rate'])}.\n")
            if m["reply_categories_unique_leads"]:
                cats = ", ".join(f"{str(label).replace('|', '/')} ({count})" for label, count in sorted(m["reply_categories_unique_leads"].items()))
                lines.append(f"All-time logged reply categories, unique leads per category (categories can overlap): {cats}.\n")
            mature_cats = mature.get("reply_categories_unique_leads", {})
            if mature_cats:
                cats = ", ".join(f"{str(label).replace('|', '/')} ({count})" for label, count in sorted(mature_cats.items()))
                lines.append(f"Reply categories inside the fixed window, mature leads only (categories can overlap): {cats}.\n")
        lines.append(f"\nLeads present in both variants: **{cohort['same_leads_in_both_variants']}**. Shared leads may have received both variants, so interpret comparisons cautiously.\n")
        if cohort.get("comparison_suppressed_reason"):
            lines.append(f"A/B comparison suppressed: {cohort['comparison_suppressed_reason']}.\n")
        comparison = next((item for item in report["comparisons"]
                           if item["experiment_id"] == cohort["experiment_id"] and item["field"] == cohort["field"]), None)
        if comparison and comparison.get("mature_window_days"):
            def pp(value: float | None) -> str:
                return "not available" if value is None else f"{value * 100:+.1f} percentage points"
            lines.append(f"Fixed {comparison['mature_window_days']}-day A-minus-B differences (descriptive): replies {pp(comparison['mature_reply_rate_a_minus_b'])}, booked {pp(comparison['mature_booked_rate_a_minus_b'])}, wins {pp(comparison['mature_won_rate_a_minus_b'])}. Mature leads sent in both variants: {comparison['mature_same_leads_sent_in_both_variants']}.\n")
    lines.extend(["## Interpretation", "", report["interpretation"], "",
                  "No variant is automatically selected. Review lead assignment, comparable lead mix, send status, and cross-variant exposure before using these numbers to change a waterfall.", ""])
    audits = report.get("assignment_audit_checks", [])
    if audits:
        lines.extend(["## Assignment audit", "", "| Experiment | Field | Audit status | Assigned CSV hash | Cohort record | Exact lead roster | Expected leads | In Send Desk lists | A expected/seen | B expected/seen | Seed matches | Integrity detail |",
                      "|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|"])
        for audit in audits:
            expected, seen = audit["expected_variant_counts"], audit["send_list_variant_counts"]
            hash_status = "matches" if audit["assigned_csv_hash_matches"] else "missing or mismatch"
            cohort_status = "matches" if audit.get("cohort_record_matches") else "missing or mismatch"
            roster_status = "matches" if audit.get("send_list_exact_lead_roster_matches") else "missing or differs"
            seed_status = "yes" if audit["assignment_seed_matches"] is True else "pending" if audit["assignment_seed_matches"] is None else "no"
            diffs = audit.get("send_list_roster_differences", {})
            roster_detail = "; ".join(f"{variant}: {diffs.get(variant, {}).get('missing', 0)} missing, {diffs.get(variant, {}).get('unexpected', 0)} unexpected" for variant in ("A", "B"))
            integrity_detail = str(audit.get("cohort_record_error") or "").strip()
            detail = "; ".join(x for x in (integrity_detail, roster_detail) if x) or "—"
            detail = detail.replace("|", "/").replace("\r", " ").replace("\n", " ")
            lines.append(f"| {audit['experiment_id']} | {audit['experiment_field']} | {audit['status']} | {hash_status} | {cohort_status} | {roster_status} | {audit['expected_lead_count']} | {audit['send_list_lead_count']} | {expected['A']}/{seen['A']} | {expected['B']}/{seen['B']} | {seed_status} | {detail} |")
        lines.append("")
    return "\n".join(lines)


def score_send_outcomes(engine: str, experiment_id: str = "", out: str = "", markdown_out: str = "", maturity_days: int = 14) -> tuple[dict, Path]:
    """Join experiment-tagged Send Desk rows to explicit taps and summarize unique-lead outcomes."""
    from . import desklog, outcomes
    from .engines import engine_dir, load

    if not 1 <= maturity_days <= 365:
        raise ValueError("Maturity window must be between 1 and 365 days.")
    if experiment_id and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", experiment_id):
        raise ValueError("Experiment ID may contain only letters, numbers, dots, underscores, and hyphens (up to 80 characters).")
    load(engine)
    as_of = date.today()
    hist = desklog.history(engine)
    cohorts: dict[tuple[str, str, str], dict[str, dict[str, bool]]] = defaultdict(dict)
    provider_orders: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    config_hashes: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    assignment_modes: dict[tuple[str, str], set[str]] = defaultdict(set)
    assignment_seeds: dict[tuple[str, str], set[str]] = defaultdict(set)
    assignment_leads: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    assignment_variant_leads: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    missing_assignment_seed: set[tuple[str, str]] = set()
    provider_metadata_missing: set[tuple[str, str, str]] = set()
    config_metadata_missing: set[tuple[str, str, str]] = set()
    missing_ids = 0
    for row in desklog.load_lists(engine):
        eid = (row.get("waterfall_experiment_id") or "").strip()
        variant = (row.get("waterfall_experiment_variant") or "").strip().upper()
        lead_id = (row.get("waterfall_experiment_lead_id") or "").strip()
        if not eid or variant not in {"A", "B"}:
            continue
        if experiment_id and eid != experiment_id:
            continue
        if not lead_id:
            missing_ids += 1
            continue
        field = (row.get("waterfall_experiment_field") or "").strip()
        assignment_experiment = (row.get("waterfall_outreach_assignment_experiment_id") or "").strip()
        assignment_variant = (row.get("waterfall_outreach_assignment_variant") or "").strip().upper()
        assignment_seed = (row.get("waterfall_outreach_assignment_seed") or "").strip()
        assignment_key = (eid, field)
        if assignment_experiment:
            if assignment_experiment != eid:
                raise ValueError(f"Lead {lead_id!r} has an outreach assignment for experiment {assignment_experiment!r}, but its row is tagged {eid!r}.")
            if assignment_variant not in {"A", "B"} or assignment_variant != variant:
                raise ValueError(f"Lead {lead_id!r} has an invalid or conflicting outreach assignment variant.")
            mode = "single_variant_assigned"
            assignment_variant_leads[(eid, field, variant)].add(lead_id)
            if assignment_seed:
                assignment_seeds[assignment_key].add(assignment_seed)
            else:
                missing_assignment_seed.add(assignment_key)
        else:
            if assignment_variant or assignment_seed:
                raise ValueError(f"Lead {lead_id!r} has incomplete outreach assignment metadata.")
            mode = "legacy_variant_tag_unassigned"
        assignment_modes[assignment_key].add(mode)
        assignment_leads[(eid, field, mode)].add(lead_id)
        cohort_key = (eid, field, variant)
        provider_raw = (row.get("waterfall_experiment_providers") or "").strip()
        if provider_raw:
            try:
                parsed_providers = json.loads(provider_raw)
                provider_orders[cohort_key].add(json.dumps(parsed_providers, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            except ValueError:
                provider_orders[cohort_key].add(provider_raw)
        else:
            provider_metadata_missing.add(cohort_key)
        config_hash = (row.get("waterfall_config_sha256") or "").strip().lower()
        if config_hash:
            config_hashes[cohort_key].add(config_hash)
        else:
            config_metadata_missing.add(cohort_key)
        events = hist.get((row["_source"], row["_row_id"]), [])
        flags = outcomes._flags(events)
        lead = cohorts[cohort_key].setdefault(lead_id,
                  {**{k: False for k in ("sent", "replied", "booked", "won", "lost", "skipped")},
                   "_sent_dates": [], "_outcome_dates": {k: [] for k in ("replied", "booked", "won")},
                   "_reply_categories": set(), "_reply_category_dates": defaultdict(list)})
        for key in ("sent", "replied", "booked", "won", "lost", "skipped"):
            lead[key] = lead[key] or bool(flags.get(key))
        for event in events:
            stamp = (event.get("logged_at") or "")[:10]
            try:
                day = date.fromisoformat(stamp)
            except ValueError:
                continue
            if event.get("status") in outcomes.SENT_STATES or desklog.is_out_of_office(event):
                lead["_sent_dates"].append(day)
            if event.get("status") in ("replied", "booked", "won") and not desklog.is_out_of_office(event):
                lead["_outcome_dates"][event["status"]].append(day)
            if event.get("status") == "replied" and not desklog.is_out_of_office(event):
                category = (event.get("category") or "uncategorized").strip().casefold()
                lead["_reply_categories"].add(category)
                lead["_reply_category_dates"][category].append(day)

    if not cohorts:
        raise ValueError("No tagged experiment rows with stable lead IDs were found for this engine" +
                         (f" and experiment {experiment_id!r}." if experiment_id else "."))

    groups: dict[tuple[str, str], dict] = {}
    mature_id_sets: dict[tuple[str, str, str], set[str]] = {}
    minimum_sent_caution = 30
    for (eid, field, variant), leads in sorted(cohorts.items()):
        sent = sum(bool(x["sent"]) for x in leads.values())
        skipped = sum(bool(x["skipped"]) and not bool(x["sent"]) for x in leads.values())
        unmarked = max(0, len(leads) - sent - skipped)
        groups[(eid, field)] = groups.get((eid, field), {"experiment_id": eid, "field": field, "variants": {}})
        counts = {key: sum(bool(x[key]) for x in leads.values()) for key in ("replied", "booked", "won", "lost")}
        reply_categories = defaultdict(int)
        for lead in leads.values():
            for category in lead["_reply_categories"]:
                reply_categories[category] += 1
        mature_leads = {}
        missing_sent_date = 0
        for lead_id, lead in leads.items():
            if not lead["sent"]:
                continue
            first_sent = min(lead["_sent_dates"]) if lead["_sent_dates"] else None
            if first_sent is None:
                missing_sent_date += 1
                continue
            window_end = first_sent + timedelta(days=maturity_days)
            if window_end > as_of:
                continue
            mature_leads[lead_id] = {key: any(first_sent <= day <= window_end for day in lead["_outcome_dates"][key])
                                     for key in ("replied", "booked", "won")}
            mature_leads[lead_id]["_reply_categories"] = {
                category for category, days in lead["_reply_category_dates"].items()
                if any(first_sent <= day <= window_end for day in days)}
        mature_counts = {key: sum(bool(x[key]) for x in mature_leads.values()) for key in ("replied", "booked", "won")}
        mature_reply_categories = defaultdict(int)
        for lead in mature_leads.values():
            for category in lead["_reply_categories"]:
                mature_reply_categories[category] += 1
        mature_id_sets[(eid, field, variant)] = set(mature_leads)
        decoded_orders = []
        for order in sorted(provider_orders[(eid, field, variant)]):
            try:
                decoded_orders.append(json.loads(order))
            except ValueError:
                decoded_orders.append(order)
        metric = {"assigned_unique_leads": len(leads), "sent_unique_leads": sent,
                  "provider_orders": decoded_orders,
                  "config_sha256s": sorted(config_hashes[(eid, field, variant)]),
                  "configuration_metadata_complete": cohort_key not in provider_metadata_missing and cohort_key not in config_metadata_missing,
                  "configuration_metadata_consistent": cohort_key not in provider_metadata_missing and cohort_key not in config_metadata_missing and len(provider_orders[(eid, field, variant)]) <= 1 and len(config_hashes[(eid, field, variant)]) <= 1,
                  "skipped_unique_leads": skipped, "unmarked_unique_leads": unmarked,
                  "send_coverage_rate": _ratio(sent, len(leads)),
                  "skip_rate_per_assigned_lead": _ratio(skipped, len(leads)),
                  "unmarked_rate_per_assigned_lead": _ratio(unmarked, len(leads)),
                  "reply_categories_unique_leads": dict(sorted(reply_categories.items())),
                  "replied_unique_leads": counts["replied"], "booked_unique_leads": counts["booked"],
                  "won_unique_leads": counts["won"], "lost_unique_leads": counts["lost"],
                  "low_sample_caution": sent < minimum_sent_caution,
                  "sample_caution_threshold_sent_leads": minimum_sent_caution,
                  "outcome_rate_95_percent_wilson_intervals": {},
                  "mature_window": {"window_days": maturity_days, "mature_sent_leads": len(mature_leads),
                                    "awaiting_window_leads": max(0, sent - len(mature_leads) - missing_sent_date),
                                    "sent_leads_missing_date": missing_sent_date,
                                    "reply_categories_unique_leads": dict(sorted(mature_reply_categories.items())),
                                    "reply_count": mature_counts["replied"], "booked_count": mature_counts["booked"],
                                    "won_count": mature_counts["won"],
                                    "reply_rate": _ratio(mature_counts["replied"], len(mature_leads)),
                                    "booked_rate": _ratio(mature_counts["booked"], len(mature_leads)),
                                    "won_rate": _ratio(mature_counts["won"], len(mature_leads))}}
        for key in ("replied", "booked", "won"):
            rate = _ratio(counts[key], sent)
            metric[f"{key}_rate_per_sent_lead"] = rate
            metric["outcome_rate_95_percent_wilson_intervals"][key] = _wilson(counts[key], sent)
        groups[(eid, field)]["variants"][variant] = metric
    comparisons = []
    for item in groups.values():
        assignment_key = (item["experiment_id"], item["field"])
        modes = assignment_modes[assignment_key]
        item["outreach_assignment_mode"] = next(iter(modes)) if len(modes) == 1 else "mixed_assigned_and_legacy"
        item["outreach_assignment_leads"] = {mode: len(assignment_leads[(item["experiment_id"], item["field"], mode)]) for mode in sorted(modes)}
        item["outreach_assignment_seeds"] = sorted(assignment_seeds[assignment_key])
        item["assignment_seed_missing"] = assignment_key in missing_assignment_seed
        item["comparison_eligible"] = len(modes) == 1 and not item["assignment_seed_missing"] and (item["outreach_assignment_mode"] != "single_variant_assigned" or len(item["outreach_assignment_seeds"]) == 1)
        if len(modes) > 1:
            item["comparison_suppressed_reason"] = "assigned and legacy unassigned rows are mixed"
        elif item["assignment_seed_missing"]:
            item["comparison_suppressed_reason"] = "explicitly assigned rows are missing the assignment seed"
        elif item["outreach_assignment_mode"] == "single_variant_assigned" and len(item["outreach_assignment_seeds"]) != 1:
            item["comparison_suppressed_reason"] = "multiple assignment seeds are mixed"
        else:
            item["comparison_suppressed_reason"] = ""
        variants = item["variants"]
        ids_by_variant = {v: set(cohorts[(item["experiment_id"], item["field"], v)]) for v in ("A", "B")}
        overlap = ids_by_variant["A"] & ids_by_variant["B"]
        item["same_leads_in_both_variants"] = len(overlap)
        item["interpretation"] = "descriptive only; no causal winner is declared"
        if "A" in variants and "B" in variants and item["comparison_eligible"]:
            mature_overlap = mature_id_sets[(item["experiment_id"], item["field"], "A")] & mature_id_sets[(item["experiment_id"], item["field"], "B")]
            mature_a = variants["A"]["mature_window"]
            mature_b = variants["B"]["mature_window"]
            comparisons.append({"experiment_id": item["experiment_id"], "field": item["field"],
                               "reply_rate_a_minus_b": (variants["A"]["reply_rate_per_sent_lead"] - variants["B"]["reply_rate_per_sent_lead"])
                                   if variants["A"]["reply_rate_per_sent_lead"] is not None and variants["B"]["reply_rate_per_sent_lead"] is not None else None,
                               "booked_rate_a_minus_b": (variants["A"]["booked_rate_per_sent_lead"] - variants["B"]["booked_rate_per_sent_lead"])
                                   if variants["A"]["booked_rate_per_sent_lead"] is not None and variants["B"]["booked_rate_per_sent_lead"] is not None else None,
                               "won_rate_a_minus_b": (variants["A"]["won_rate_per_sent_lead"] - variants["B"]["won_rate_per_sent_lead"])
                                   if variants["A"]["won_rate_per_sent_lead"] is not None and variants["B"]["won_rate_per_sent_lead"] is not None else None,
                               "same_leads_in_both_variants": len(overlap),
                               "overlap_caution": "overlapping leads may have received both variants; compare as descriptive only" if overlap else "",
                               "mature_window_days": maturity_days,
                               "mature_sent_leads_a": mature_a["mature_sent_leads"],
                               "mature_sent_leads_b": mature_b["mature_sent_leads"],
                               "mature_same_leads_sent_in_both_variants": len(mature_overlap),
                               "mature_reply_rate_a_minus_b": _ratio(mature_a["reply_count"], mature_a["mature_sent_leads"]) - _ratio(mature_b["reply_count"], mature_b["mature_sent_leads"])
                                   if mature_a["reply_rate"] is not None and mature_b["reply_rate"] is not None else None,
                               "mature_booked_rate_a_minus_b": _ratio(mature_a["booked_count"], mature_a["mature_sent_leads"]) - _ratio(mature_b["booked_count"], mature_b["mature_sent_leads"])
                                   if mature_a["booked_rate"] is not None and mature_b["booked_rate"] is not None else None,
                               "mature_won_rate_a_minus_b": _ratio(mature_a["won_count"], mature_a["mature_sent_leads"]) - _ratio(mature_b["won_count"], mature_b["mature_sent_leads"])
                                   if mature_a["won_rate"] is not None and mature_b["won_rate"] is not None else None})
    imports_dir = engine_dir(engine) / "imports"
    from . import importer
    audit_candidates = sorted(imports_dir.glob(f"*-{experiment_id}-outreach-assigned-assignment.json")) if experiment_id else sorted(imports_dir.glob("*-outreach-assigned-assignment.json"))
    assignment_audit_checks = []
    for audit_path in audit_candidates:
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if audit.get("schema") != "dbi.waterfall-outreach-assignment.v1":
            continue
        eid = str(audit.get("experiment_id") or "")
        field = str(audit.get("experiment_field") or "")
        assigned_name = str(audit.get("assigned_csv_name") or "")
        csv_path = (audit_path.parent / assigned_name).resolve() if assigned_name and Path(assigned_name).name == assigned_name else None
        csv_exists = bool(csv_path and csv_path.is_file() and imports_dir.resolve() in csv_path.parents)
        csv_hash_matches = bool(csv_exists and hashlib.sha256(csv_path.read_bytes()).hexdigest() == audit.get("assigned_csv_sha256"))
        cohort_record_matches = False
        cohort_record_error = ""
        if csv_hash_matches and csv_path is not None:
            try:
                importer._verify_waterfall_assignment_file(engine, csv_path)
                cohort_record_matches = True
            except (OSError, ValueError) as error:
                cohort_record_error = str(error)[:300]
        expected_ids_by_variant: dict[str, set[str]] = {"A": set(), "B": set()}
        if csv_hash_matches and cohort_record_matches and csv_path is not None:
            try:
                _assigned_headers, assigned_rows = importer.read_rows(csv_path)
                for row in assigned_rows:
                    variant = (row.get("waterfall_experiment_variant") or "").strip().upper()
                    lead_id = (row.get("waterfall_experiment_lead_id") or "").strip()
                    if variant in expected_ids_by_variant and lead_id:
                        expected_ids_by_variant[variant].add(lead_id)
            except (OSError, ValueError) as error:
                cohort_record_matches = False
                cohort_record_error = (str(error) or "Could not read assigned lead roster.")[:300]
        observed_ids_by_variant = {variant: set(assignment_variant_leads[(eid, field, variant)])
                                   for variant in ("A", "B")}
        roster_diffs = {
            variant: {"missing": len(expected_ids_by_variant[variant] - observed_ids_by_variant[variant]),
                      "unexpected": len(observed_ids_by_variant[variant] - expected_ids_by_variant[variant])}
            for variant in ("A", "B")
        }
        exact_roster_matches = bool(cohort_record_matches and all(
            expected_ids_by_variant[variant] == observed_ids_by_variant[variant] for variant in ("A", "B")))
        observed = {variant: len(assignment_variant_leads[(eid, field, variant)]) for variant in ("A", "B")}
        expected_raw = audit.get("variant_counts") if isinstance(audit.get("variant_counts"), dict) else {}
        expected = {variant: int(expected_raw.get(variant, 0) or 0) for variant in ("A", "B")}
        observed_total = sum(observed.values())
        expected_total = int(audit.get("lead_count", 0) or 0)
        seeds = assignment_seeds[(eid, field)]
        seed_matches = seeds == {str(audit.get("seed") or "")} if observed_total else None
        if not csv_exists:
            status = "assigned_csv_missing"
        elif not csv_hash_matches:
            status = "assigned_csv_hash_mismatch"
        elif not cohort_record_matches:
            status = "cohort_record_mismatch"
        elif observed_total < expected_total and not any(item["unexpected"] for item in roster_diffs.values()):
            status = "send_lists_incomplete"
        elif (not exact_roster_matches or observed_total > expected_total or observed != expected
              or seed_matches is False):
            status = "send_list_assignment_mismatch"
        else:
            status = "verified_in_send_lists"
        assignment_audit_checks.append({"experiment_id": eid, "experiment_field": field,
             "audit_file": audit_path.name, "assigned_csv": assigned_name,
             "source_sha256": audit.get("source_sha256"), "assigned_csv_sha256": audit.get("assigned_csv_sha256"),
             "assigned_csv_exists": csv_exists, "assigned_csv_hash_matches": csv_hash_matches,
             "cohort_record_matches": cohort_record_matches, "cohort_record_error": cohort_record_error or None,
             "send_list_exact_lead_roster_matches": exact_roster_matches,
             "send_list_roster_differences": roster_diffs,
             "expected_lead_count": expected_total, "expected_variant_counts": expected,
             "send_list_lead_count": observed_total, "send_list_variant_counts": observed,
             "assignment_seed_matches": seed_matches, "status": status})
    blocked_audit_keys = {(check["experiment_id"], check["experiment_field"]): check["status"]
                          for check in assignment_audit_checks if check["status"] != "verified_in_send_lists"}
    if blocked_audit_keys:
        comparisons = [comparison for comparison in comparisons
                       if (comparison["experiment_id"], comparison["field"]) not in blocked_audit_keys]
        for key, status in blocked_audit_keys.items():
            cohort = groups.get(key)
            if cohort:
                cohort["comparison_eligible"] = False
                cohort["comparison_suppressed_reason"] = f"assignment audit status is {status}"
                cohort["interpretation"] = "A/B comparison withheld until the staged assignment is reconciled with Send Desk lists"
    report = {"schema": "dbi.waterfall-send-outcomes.v1", "engine": engine, "experiment_filter": experiment_id or None,
              "scored_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "source": "tagged send-list rows joined to explicit Send Desk log taps by list and row ID",
              "missing_stable_lead_id_rows": missing_ids, "cohorts": list(groups.values()), "comparisons": comparisons,
              "assignment_audit_checks": assignment_audit_checks,
              "sample_caution_threshold_sent_leads": minimum_sent_caution,
              "maturity_window_days": maturity_days, "maturity_as_of_date": as_of.isoformat(),
              "interpretation": "Counts deduplicate by stable experiment lead ID and include only explicit logged outcomes. When explicit outreach assignment metadata exists, its variant is validated against the experiment variant tag and its seed is reported. A/B comparisons are suppressed for cohorts mixing assigned and legacy unassigned rows or multiple/missing assignment seeds; when an assignment audit exists, comparisons are also withheld until the assigned CSV hash, local cohort record, source evidence, expected counts, seed, and complete Send Desk-list coverage reconcile. Per-variant counts remain visible with the reason. Overall rates and 95% Wilson intervals are descriptive; intervals reflect binomial sampling uncertainty only. Fixed-window rates count outcomes logged from first confirmed send through the configured maturity window, only for leads whose full window has elapsed. Missing send dates are excluded from fixed-window denominators. Neither view accounts for assignment, delivery, lead mix, or other bias. The low-sample threshold is a caution flag, not a power guarantee. Overlap indicates leads appearing in both variants and can contaminate a comparison."}
    output = Path(out) if out else engine_dir(engine) / "data" / (f"waterfall-send-outcomes-{experiment_id}.json" if experiment_id else "waterfall-send-outcomes.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Scored {sum(v['assigned_unique_leads'] for g in groups.values() for v in g['variants'].values())} tagged lead-variant records across {len(groups)} experiment-field cohorts: {output}")
    brief_path = Path(markdown_out) if markdown_out else output.with_suffix(".md")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(_send_outcome_brief(report), encoding="utf-8")
    print(f"Wrote human-readable outcome brief: {brief_path}")
    print("Rates are descriptive only; overlapping leads across A/B are flagged in the report.")
    return report, output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dse.py eval-enrichment", description="Prepare and score a reviewed enrichment benchmark.")
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("prepare", help="flatten field_results into a human-review CSV")
    p.add_argument("source", help="enriched CSV containing a field_results JSON column")
    p.add_argument("--out", default="", help="review CSV output path")
    s = sub.add_parser("score", help="score a completed human-review CSV")
    s.add_argument("source", help="review CSV with yes/no labels")
    s.add_argument("--out", default="", help="JSON report output path")
    s.add_argument("--min-labeled", type=int, default=20, help="minimum yes/no labels before a cohort is flagged as reaching the caution threshold (default: 20)")
    s.add_argument("--cost-bootstrap-reps", type=int, default=500, help="lead-cluster bootstrap replicates for reviewed cost intervals (0 disables; default: 500)")
    s.add_argument("--cost-bootstrap-seed", type=int, default=42, help="seed for reproducible reviewed cost intervals (default: 42)")
    s.add_argument("--paired-bootstrap-reps", type=int, default=500, help="lead-pair bootstrap replicates for paired source quality and cost differences (0 disables; default: 500)")
    s.add_argument("--paired-bootstrap-seed", type=int, default=42, help="seed for reproducible paired source quality and cost intervals (default: 42)")
    s.add_argument("--markdown-out", default="", help="optional Markdown decision brief output path")
    sm = sub.add_parser("sample-ledger", help="select a reproducible, stratified lead-level benchmark sample")
    sm.add_argument("source", help="prepared human-review CSV from `prepare`")
    sm.add_argument("--leads", type=int, default=40, help="maximum leads to sample (default: 40)")
    sm.add_argument("--seed", type=int, default=42, help="random seed for reproducible sampling (default: 42)")
    sm.add_argument("--stratify", default="engine_path,enrichment_profile", help="comma-separated prepared CSV columns (default: engine_path,enrichment_profile)")
    sm.add_argument("--out", default="", help="sample CSV output path")
    wx = sub.add_parser("plan-waterfall-experiment", help="create a reproducible paired manifest for manually testing two provider orders")
    wx.add_argument("source", help="prepared or adjudicated enrichment review CSV")
    wx.add_argument("--field", required=True)
    wx.add_argument("--provider-a", required=True)
    wx.add_argument("--provider-b", required=True)
    wx.add_argument("--engine-path", required=True)
    wx.add_argument("--enrichment-profile", required=True)
    wx.add_argument("--research-lane", required=True)
    wx.add_argument("--leads", type=int, default=50)
    wx.add_argument("--seed", type=int, default=42)
    wx.add_argument("--out", default="", help="manifest CSV output path")
    pv = sub.add_parser("pair-variants", help="verify and combine the recorded A/B waterfall result files")
    pv.add_argument("variant_a", help="completed A result CSV from my-lists")
    pv.add_argument("variant_b", help="completed B result CSV from my-lists")
    ao = sub.add_parser("assign-outreach", help="assign each paired experiment lead to exactly one outreach variant")
    ao.add_argument("source", help="verified paired A/B enrichment CSV with stable experiment lead IDs")
    ao.add_argument("--experiment-id", required=True)
    ao.add_argument("--seed", default="42", help="sticky assignment seed (same seed preserves assignments)")
    ao.add_argument("--engine", default="", help="optional Engine: validate existing exposures and save directly to its imports folder")
    ao.add_argument("--out", default="", help="assigned CSV output path")
    so = sub.add_parser("score-send-outcomes", help="join experiment variants to explicit Send Desk outcomes for one engine")
    so.add_argument("engine", help="engine slug")
    so.add_argument("--experiment-id", default="", help="limit the report to one experiment ID")
    so.add_argument("--out", default="", help="JSON report output path")
    so.add_argument("--markdown-out", default="", help="Markdown brief path (default: same path as JSON with .md extension)")
    so.add_argument("--maturity-days", type=int, default=14, help="fixed outcome observation window after first confirmed send (default: 14 days)")
    pr = sub.add_parser("pair-reviewers", help="create independent reviewer and adjudication columns")
    pr.add_argument("source", help="prepared sample review CSV")
    pr.add_argument("--out", default="", help="paired review CSV output path")
    l = sub.add_parser("score-ledger", help="score fit reviews exported from a Ledger grid")
    l.add_argument("source", help="Ledger grid CSV with an enrichment_review column")
    l.add_argument("--out", default="", help="JSON report output path")
    l.add_argument("--min-decided", type=int, default=10, help="minimum good-fit plus not-a-fit reviews before a profile is marked descriptive only (default: 10)")
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            prepare(args.source, args.out)
        elif args.action == "score":
            score(args.source, args.out, args.min_labeled, args.cost_bootstrap_reps, args.cost_bootstrap_seed,
                  args.paired_bootstrap_reps, args.paired_bootstrap_seed, args.markdown_out)
        elif args.action == "sample-ledger":
            sample_ledger(args.source, args.leads, args.seed, args.stratify, args.out)
        elif args.action == "plan-waterfall-experiment":
            plan_waterfall_experiment(args.source, args.field, args.provider_a, args.provider_b,
                                      args.engine_path, args.enrichment_profile, args.research_lane,
                                      args.leads, args.seed, args.out)
        elif args.action == "pair-variants":
            pair_experiment_variants(args.variant_a, args.variant_b)
        elif args.action == "assign-outreach":
            assign_outreach_variant(args.source, args.experiment_id, args.seed, args.out, args.engine)
        elif args.action == "pair-reviewers":
            pair_reviewers(args.source, args.out)
        elif args.action == "score-send-outcomes":
            score_send_outcomes(args.engine, args.experiment_id, args.out, args.markdown_out, args.maturity_days)
        else:
            score_ledger(args.source, args.out, args.min_decided)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
