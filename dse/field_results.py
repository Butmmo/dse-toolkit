"""Shared, provider-neutral schema for enriched field values and their evidence."""
from __future__ import annotations

import json
from typing import Any

SCHEMA = "dbi.field-result.v1"
STATUSES = {"accepted", "candidate", "not_found", "rejected", "error"}


def make_result(*, field: str, value: Any = None, status: str = "not_found", source_type: str = "",
                source_name: str = "", source_url: str = "", source_record_id: str = "",
                observed_at: str = "", publication_date: str = "", freshness_status: str = "unknown",
                age_days: int | None = None, identity_subject: str = "unknown", identity_match: str = "",
                identity_strength: str = "unknown", identity_score: float | None = None,
                identity_score_kind: str = "", verification_status: str = "unknown",
                verification_method: str = "", verification_checked_at: str = "",
                cost_amount: float | None = None, cost_currency: str | None = None,
                cost_units: str = "", cost_quantity: float | None = None,
                cost_estimated: bool | None = None, miss_reason: str = "",
                candidates: list[dict] | None = None, metadata: dict | None = None) -> dict:
    """Create one stable result envelope; consumers can ignore fields they do not yet use."""
    if status not in STATUSES:
        raise ValueError(f"Unsupported field-result status: {status}")
    return {
        "schema": SCHEMA,
        "field": str(field),
        "value": value,
        "status": status,
        "source": {"type": str(source_type), "name": str(source_name), "url": str(source_url), "record_id": str(source_record_id)},
        "observed_at": str(observed_at),
        "freshness": {"publication_date": str(publication_date), "status": str(freshness_status), "age_days": age_days},
        "identity": {"subject": str(identity_subject), "match": str(identity_match), "strength": str(identity_strength),
                     "score": identity_score, "score_kind": str(identity_score_kind)},
        "verification": {"status": str(verification_status), "method": str(verification_method), "checked_at": str(verification_checked_at)},
        "cost": {"amount": cost_amount, "currency": cost_currency, "units": str(cost_units),
                 "quantity": cost_quantity, "estimated": cost_estimated},
        "miss_reason": str(miss_reason),
        "candidates": candidates or [],
        "metadata": metadata or {},
    }


def dump_results(results: list[dict]) -> str:
    """Serialize a list of contract records for CSV/JSON transport."""
    return json.dumps(results, ensure_ascii=False, separators=(",", ":"))


def merge_results(existing: str | list[dict] | None, current: str | list[dict] | None, limit: int = 200) -> str:
    """Combine lanes, refreshing each lane's prior snapshot and deduplicating its field/source records."""
    def unpack(value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                return []
        return value if isinstance(value, list) else []
    old_items, new_items = unpack(existing), unpack(current)
    active_lanes = {item.get("metadata", {}).get("lane") for item in new_items
                    if isinstance(item, dict) and isinstance(item.get("metadata"), dict) and item.get("metadata", {}).get("lane")}
    old_items = [item for item in old_items if not (isinstance(item, dict) and isinstance(item.get("metadata"), dict)
                                                    and item.get("metadata", {}).get("lane") in active_lanes)]
    merged: dict[tuple[str, str, str, str], dict] = {}
    for item in old_items + new_items:
        if not isinstance(item, dict) or item.get("schema") != SCHEMA or not item.get("field"):
            continue
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        key = (str(item.get("field", "")), str(source.get("type", "")),
               str(source.get("url", "")), str(source.get("record_id", "") or source.get("name", "")))
        merged[key] = item
    return dump_results(list(merged.values())[-max(1, limit):])


def source_ref(*, source_type: str, source_name: str = "", source_url: str = "", source_record_id: str = "",
               status: str = "candidate", value: Any = None) -> dict:
    """Small typed evidence reference for a result's candidate list."""
    if status not in STATUSES:
        status = "candidate"
    return {"status": status, "value": value,
            "source": {"type": source_type, "name": source_name, "url": source_url, "record_id": source_record_id}}
