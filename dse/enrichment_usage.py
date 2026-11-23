"""Local cost-estimate journal for optional enrichment-provider API calls.

Only provider and call metadata are stored. Lead identifiers and API credentials
are deliberately excluded. This is a usage estimate, not vendor invoice data.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import uuid
from pathlib import Path

from .common import DATA

LEDGER = DATA / "enrichment-provider-usage.jsonl"


def record_call(config: dict, field: str, outcome: str, status_code: int | None = None) -> str:
    """Append one attempted provider request; return an error string if it could not be saved."""
    price = config.get("cost_per_call")
    currency = config.get("cost_currency") if price is not None else None
    try:
        amount = float(price) if price is not None else None
        if amount is not None and (not math.isfinite(amount) or amount < 0):
            amount, currency = None, None
    except (TypeError, ValueError):
        amount, currency = None, None
    event = {
        "schema": "dbi.enrichment-usage.v1",
        "event_id": str(uuid.uuid4()),
        "occurred_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "provider": str(config.get("name", "unknown")),
        "field": str(field or "unknown"),
        "outcome": str(outcome),
        "http_status": status_code,
        "request_count": 1,
        "cost": {
            "amount": amount,
            "currency": currency,
            "basis": str(config.get("cost_basis") or ("configured_cost_per_call" if amount is not None else "unknown")),
            "estimated": amount is not None,
            "actual_invoice_amount": None,
        },
    }
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError as error:
        return f"Could not save provider usage record ({type(error).__name__}); this call is not in the local usage summary."
    return ""


def report(days: int = 30) -> str:
    """Summarize recent local provider requests, keeping unknown costs visible."""
    if not 1 <= int(days) <= 3650:
        raise ValueError("Usage history days must be between 1 and 3650.")
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(days))
    totals: dict[str, dict] = {}
    malformed = 0
    try:
        stream = LEDGER.open("r", encoding="utf-8")
    except FileNotFoundError:
        return f"No paid enrichment-provider calls have been recorded on this PC in the last {days} days.\nUsage records are local to this PC; they are estimates, not vendor invoices."
    except OSError as error:
        return f"Could not read local provider usage history ({type(error).__name__})."
    with stream:
        for line in stream:
            try:
                item = json.loads(line)
                when = dt.datetime.fromisoformat(str(item["occurred_at"]).replace("Z", "+00:00"))
                if when < cutoff or item.get("schema") != "dbi.enrichment-usage.v1":
                    continue
                name = str(item.get("provider", "unknown"))
                bucket = totals.setdefault(name, {"calls": 0, "unknown": 0, "outcomes": {}, "estimates": {}, "by_field": {}})
                count = int(item.get("request_count", 1))
                bucket["calls"] += count
                field_name = str(item.get("field", "unknown"))
                field_bucket = bucket["by_field"].setdefault(field_name, {"calls": 0, "unknown": 0, "estimates": {}})
                field_bucket["calls"] += count
                outcome = str(item.get("outcome", "unknown"))
                bucket["outcomes"][outcome] = bucket["outcomes"].get(outcome, 0) + count
                cost = item.get("cost") if isinstance(item.get("cost"), dict) else {}
                amount, currency = cost.get("amount"), cost.get("currency")
                if isinstance(amount, (int, float)) and currency:
                    bucket["estimates"][currency] = bucket["estimates"].get(currency, 0.0) + float(amount)
                    field_bucket["estimates"][currency] = field_bucket["estimates"].get(currency, 0.0) + float(amount)
                else:
                    bucket["unknown"] += count
                    field_bucket["unknown"] += count
            except (ValueError, TypeError, KeyError):
                malformed += 1
    if not totals:
        return f"No paid enrichment-provider calls have been recorded on this PC in the last {days} days.\nUsage records are local to this PC; they are estimates, not vendor invoices."
    lines = [f"Optional enrichment-provider usage on this PC (last {days} days):"]
    for name, bucket in sorted(totals.items()):
        estimates = ", ".join(f"{amount:.4f} {currency} estimated" for currency, amount in sorted(bucket["estimates"].items())) or "no configured monetary estimate"
        outcomes = ", ".join(f"{key}: {value}" for key, value in sorted(bucket["outcomes"].items()))
        lines.append(f"  {name}: {bucket['calls']} requests; {estimates}; {bucket['unknown']} request(s) with unknown cost; outcomes: {outcomes or 'none'}")
        for field_name, field_bucket in sorted(bucket["by_field"].items()):
            field_estimates = ", ".join(f"{amount:.4f} {currency} estimated" for currency, amount in sorted(field_bucket["estimates"].items())) or "cost unknown"
            lines.append(f"    {field_name}: {field_bucket['calls']} requests; {field_estimates}; {field_bucket['unknown']} unknown")
    lines.append("These records do not confirm vendor billing. Check each provider's dashboard/invoice; call-based estimates may not match credits or outcome-based charges.")
    if malformed:
        lines.append(f"Skipped {malformed} malformed usage record(s).")
    return "\n".join(lines)
