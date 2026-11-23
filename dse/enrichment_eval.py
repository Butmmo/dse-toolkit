"""Prepare and score small, human-reviewed enrichment benchmark sheets."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


REVIEW_FIELDS = ["value_correct", "identity_correct", "evidence_adequate", "freshness_acceptable", "review_note"]
YES = {"y", "yes", "true", "1"}
NO = {"n", "no", "false", "0"}
FIT_JUDGMENTS = {"good_fit", "not_a_fit", "uncertain"}
TARGET_CONTEXT_FIELDS = {
    "requested_business_profile": "business_profile",
    "requested_decision_maker": "decision_maker",
    "requested_role": "role",
    "requested_legal_form": "legal_form",
    "requested_path": "path",
    "requested_search_strategy": "search_strategy",
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
    source_fields = [h for h in ("engine_path", "path", "company", "business", "website", "domain", "contact_name", "decision_maker") if h in headers]
    columns = ["evaluation_id", "source_row", "field", "value", "status", "source_type", "source_name", "source_url",
               "observed_at", "publication_date", "freshness_status", "age_days", "identity_subject", "identity_match",
               "identity_strength", "identity_score", "verification_status", "cost_amount", "cost_currency", "cost_units",
               "cost_quantity", "cost_estimated", *source_fields, *REVIEW_FIELDS]
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
                output_row = {"evaluation_id": _stable_id(row, row_number), "source_row": row_number,
                              "field": result.get("field", ""), "value": json.dumps(result.get("value"), ensure_ascii=False) if isinstance(result.get("value"), (dict, list)) else result.get("value", ""),
                              "status": result.get("status", ""), "source_type": source_info.get("type", ""),
                              "source_name": source_info.get("name", ""), "source_url": source_info.get("url", ""),
                              "observed_at": result.get("observed_at", ""), "publication_date": freshness.get("publication_date", ""),
                              "freshness_status": freshness.get("status", ""), "age_days": freshness.get("age_days", ""),
                              "identity_subject": identity.get("subject", ""), "identity_match": identity.get("match", ""),
                              "identity_strength": identity.get("strength", ""), "identity_score": identity.get("score", ""),
                              "verification_status": verification.get("status", ""), "cost_amount": cost.get("amount", ""),
                              "cost_currency": cost.get("currency", ""), "cost_units": cost.get("units", ""),
                              "cost_quantity": cost.get("quantity", ""), "cost_estimated": cost.get("estimated", "")}
                output_row.update({name: row.get(name, "") for name in source_fields})
                output_row.update({name: "" for name in REVIEW_FIELDS})
                writer.writerow(output_row)
                count += 1
    if not count:
        raise ValueError("No dbi.field-result.v1 records were found in the input CSV.")
    print(f"Prepared {count} field reviews in {output}")
    print("Label the four review columns with yes/no; leave a label blank when it cannot be judged.")
    return output


def _ratio(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def score(source: str, out: str = "") -> tuple[dict, Path]:
    """Summarize reviewed quality, coverage, freshness and declared provider cost."""
    headers, rows = _read(source)
    required = {"field", "status", *REVIEW_FIELDS[:4]}
    missing = sorted(required - set(headers))
    if missing:
        raise ValueError("Review CSV is missing columns: " + ", ".join(missing))
    by_field: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_field[(row.get("field") or "(blank field)").strip()].append(row)

    def metrics(items: list[dict[str, str]]) -> dict:
        labeled = {field: [r for r in items if (r.get(field) or "").strip().casefold() in YES | NO] for field in REVIEW_FIELDS[:4]}
        correct_values = sum((r.get("value_correct") or "").strip().casefold() in YES for r in labeled["value_correct"])
        costs: dict[str, float] = defaultdict(float)
        for row in items:
            try:
                amount = float(row.get("cost_amount") or "")
            except (TypeError, ValueError):
                continue
            currency = (row.get("cost_currency") or "unknown").strip() or "unknown"
            costs[currency] += amount
        accepted = sum((r.get("status") or "").strip().casefold() == "accepted" for r in items)
        fresh_known = [r for r in items if (r.get("freshness_status") or "").strip() and (r.get("freshness_status") or "").casefold() != "unknown"]
        return {"fields": len(items), "accepted": accepted, "coverage": _ratio(accepted, len(items)),
                "status_counts": {status: sum((r.get("status") or "").strip().casefold() == status for r in items)
                                  for status in ("accepted", "candidate", "not_found", "rejected", "error")},
                "review_labels": {k: {"labeled": len(v), "yes": sum((r.get(k) or "").strip().casefold() in YES for r in v),
                                      "rate": _ratio(sum((r.get(k) or "").strip().casefold() in YES for r in v), len(v))}
                                  for k, v in labeled.items()},
                "freshness_documented": len(fresh_known), "freshness_documented_rate": _ratio(len(fresh_known), len(items)),
                "declared_cost_by_currency": dict(costs),
                "declared_cost_per_accepted_field_by_currency": {currency: _ratio(amount, accepted) for currency, amount in costs.items()}}

    report = {"schema": "dbi.enrichment-evaluation.v1", "source_file": str(Path(source).resolve()),
              "review_rows": len(rows), "fields": {name: metrics(items) for name, items in sorted(by_field.items())},
              "overall": metrics(rows),
              "interpretation": "Coverage is the accepted-result share. Human label rates apply only to explicitly labeled rows; they are not population-wide accuracy estimates. Declared costs may be estimates, not provider invoices."}
    output = Path(out) if out else Path(source).with_name(Path(source).stem + "-evaluation.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Scored {len(rows)} reviewed field rows across {len(by_field)} fields: {output}")
    for field, values in report["fields"].items():
        m = values["review_labels"]
        fmt = lambda key: "n/a" if m[key]["rate"] is None else f"{m[key]['rate']:.1%} ({m[key]['labeled']} labeled)"
        print(f"  {field}: coverage {values['coverage']:.1%}; value correctness {fmt('value_correct')}; identity correctness {fmt('identity_correct')}; evidence adequacy {fmt('evidence_adequate')}; freshness accepted {fmt('freshness_acceptable')}")
    print("Costs are summed only when a result declares a numeric amount and currency; unknown costs are omitted.")
    return report, output


def score_ledger(source: str, out: str = "", min_decided: int = 10) -> tuple[dict, Path]:
    """Measure Ledger fit judgements and associate them with same-lane field results."""
    if min_decided < 1:
        raise ValueError("--min-decided must be at least 1.")
    headers, rows = _read(source)
    column = next((name for name in headers if name.strip().casefold() == "enrichment_review"), "")
    if not column:
        raise ValueError("Ledger CSV needs the enrichment_review column. Make it visible before exporting the grid.")

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
            latest[(row_number, lane)] = {"judgment": item["judgment"], "lane": lane, "profile_key": profile,
                                          "reviewed_at": str(item.get("reviewed_at") or ""),
                                          "research_checked_at": str(item.get("research_checked_at") or ""),
                                          "target_context": target_context,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dse.py eval-enrichment", description="Prepare and score a reviewed enrichment benchmark.")
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("prepare", help="flatten field_results into a human-review CSV")
    p.add_argument("source", help="enriched CSV containing a field_results JSON column")
    p.add_argument("--out", default="", help="review CSV output path")
    s = sub.add_parser("score", help="score a completed human-review CSV")
    s.add_argument("source", help="review CSV with yes/no labels")
    s.add_argument("--out", default="", help="JSON report output path")
    l = sub.add_parser("score-ledger", help="score fit reviews exported from a Ledger grid")
    l.add_argument("source", help="Ledger grid CSV with an enrichment_review column")
    l.add_argument("--out", default="", help="JSON report output path")
    l.add_argument("--min-decided", type=int, default=10, help="minimum good-fit plus not-a-fit reviews before a profile is marked descriptive only (default: 10)")
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            prepare(args.source, args.out)
        elif args.action == "score":
            score(args.source, args.out)
        else:
            score_ledger(args.source, args.out, args.min_decided)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
