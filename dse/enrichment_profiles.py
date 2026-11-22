"""Versioned path-specific enrichment profiles and transparent previews."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import business_profiles, path_signals

SCHEMA = "dbi.enrichment-profile.v1"
PROFILE_VERSION = "1.0.0"

# Role and signal guidance comes from the maintained path methodology catalog.
# Field priorities and default budgets are explicit recommendations, not evidence
# of prospect quality, provider availability, or expected coverage.
PATH_FIELDS = {
    "any": ["company", "website", "contact_name", "company_last_signal", "decision_maker_title", "email"],
    "smb": ["business_type", "locations", "website", "review_volume", "review_response", "contact_or_booking_route", "owner_or_operator", "email"],
    "search": ["service_area", "website", "search_visibility_evidence", "listing_consistency", "review_signal", "marketing_owner", "email"],
    "voiceai": ["public_phone", "call_route", "business_hours", "booking_route", "location_count", "owner_or_operations_buyer", "email"],
    "automation": ["repeatable_process_signal", "team_scale", "existing_tools", "process_owner", "hiring_signal", "email"],
    "revenue": ["store_url", "product_category", "lifecycle_flow_evidence", "traffic_or_scale_context", "ecommerce_buyer", "email"],
    "gtm": ["company_domain", "crm_or_sales_stack", "team_scale", "hiring_or_funding_signal", "revops_or_sales_buyer", "email"],
    "authority": ["expert_offer", "public_positioning", "content_cadence", "audience_evidence", "inquiry_path", "offer_owner", "email"],
    "broadcast": ["show_url", "publishing_cadence", "episode_topics", "audience_capture", "sponsor_readiness", "show_owner", "email"],
    "ascent": ["offer_url", "offer_price_evidence", "closer_demand", "lead_flow_evidence", "written_terms_human_check", "offer_owner", "email"],
}
PATH_SEGMENTS = {
    "any": ["franchise_group", "local_smb", "saas", "online_store", "enterprise"],
    "smb": ["local_smb", "franchise_group"], "search": ["local_smb", "franchise_group"],
    "voiceai": ["local_smb", "franchise_group"], "automation": ["local_smb", "saas", "enterprise", "franchise_group"],
    "revenue": ["online_store"], "gtm": ["saas", "enterprise"], "authority": ["local_smb"],
    "broadcast": ["local_smb"], "ascent": ["local_smb", "saas", "enterprise"],
}

COMMON_ACCEPTANCE = {
    "person_identity": "Require a named person and a role or profile URL tied to the target company; keep weak matches as candidates.",
    "company_identity": "Require a matching domain or a reviewed company-name match before accepting provider fields.",
    "signal": "Keep a source URL and subject match; label search snippets as candidates until a human checks the source.",
    "email": "Require a valid address and company-domain match; deliverability remains unverified unless a distinct check says otherwise.",
    "legal_form": "Treat public-search mentions as hints; accept a legal classification only from an authoritative, relevant registry record.",
}


def available_paths() -> list[str]:
    return list(path_signals.PATH_SIGNAL_PROFILES)


def build_profile(path_key: str, *, max_provider_calls: int = 0, herald_queries: int = 12,
                  presence_queries: int = 3, signal_freshness_days: int = 180, max_spend: float = 0.0) -> dict[str, Any]:
    key = (path_key or "any").strip().lower()
    if key not in path_signals.PATH_SIGNAL_PROFILES:
        raise ValueError("Unknown path. Choose one of: " + ", ".join(available_paths()))
    for name, value, ceiling in (("provider calls", max_provider_calls, 5000), ("Herald queries", herald_queries, 30),
                                 ("Presence queries", presence_queries, 10), ("signal freshness days", signal_freshness_days, 3650)):
        if not isinstance(value, int) or value < 0 or value > ceiling:
            raise ValueError(f"{name} must be between 0 and {ceiling}.")
    if not isinstance(max_spend, (float, int)) or not 0 <= max_spend <= 100000:
        raise ValueError("max spend must be between 0 and 100000 USD.")
    path = path_signals.profile(key)
    roles = list(path.get("roles") or [])
    role_labels = [business_profiles.DECISION_ROLES[r]["label"] for r in roles if r in business_profiles.DECISION_ROLES]
    business_types = [business_profiles.BUSINESS_PROFILES[k]["label"] for k in PATH_SEGMENTS[key]]
    return {
        "schema": SCHEMA, "profile_version": PROFILE_VERSION, "path_key": key, "path_label": path["label"],
        "intent": {"method": path["method"], "pain_hypothesis": path["pain"], "likely_buyer": path["buyer"],
                   "target_business_segments_to_select": business_types, "buyer_role_families": role_labels},
        "priorities": {"lead_fields": PATH_FIELDS[key], "priority_signal_categories": list(path.get("priority") or []),
                       "supporting_signal_categories": list(path.get("supporting") or []), "search_terms": path.get("query_terms", "")},
        "recommended_lanes": ["website", "herald"] + (["presence"] if key != "any" else []),
        "source_order": ["user-supplied and existing Ledger evidence", "first-party company website", "budgeted public search",
                         "configured provider only when the field remains unresolved", "local DBI-AI advice after source-backed evidence"],
        "limits": {"herald_queries_per_lead": herald_queries, "presence_queries_per_lead": presence_queries,
                   "provider_calls_per_run": max_provider_calls, "provider_spend_ceiling": {"amount": float(max_spend), "currency": "USD",
                                                                                              "note": "A profile recommendation; no paid call runs unless the execution config is integrated and explicitly enabled."},
                   "signal_freshness_days": signal_freshness_days, "expected_coverage": "not measured yet"},
        "acceptance_rules": dict(COMMON_ACCEPTANCE),
        "commercial_checks": list(path_signals.outcome_plan(key).get("viability_checks") or []),
        "recommended_next_human_step": path_signals.outcome_plan(key).get("next_step", ""),
        "guardrails": ["Path and segment choices are targeting preferences, not verified classifications.",
                       "A signal is not proof of pain, intent, budget, or ability to pay.",
                       "Keep ambiguous identity and source conflicts reviewable; do not silently promote them to facts.",
                       "DBI-AI advice remains separate and cannot qualify or act on a lead."],
        "execution_status": "preview_only; this profile does not yet configure an enrichment run",
    }


def _print_profile(profile: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(profile, ensure_ascii=False, indent=2))
        return
    print(f"{profile['path_label']} — profile {profile['profile_version']} ({profile['path_key']})")
    print(f"Intent: {profile['intent']['pain_hypothesis']}")
    print(f"Likely buyer: {profile['intent']['likely_buyer']}")
    print("Role families: " + (", ".join(profile["intent"]["buyer_role_families"]) or "none configured"))
    print("Priority fields: " + ", ".join(profile["priorities"]["lead_fields"]))
    print("Priority signals: " + (", ".join(profile["priorities"]["priority_signal_categories"]) or "general"))
    print("Lanes: " + ", ".join(profile["recommended_lanes"]))
    limits = profile["limits"]
    print(f"Preview budget: {limits['herald_queries_per_lead']} Herald queries/lead; {limits['presence_queries_per_lead']} Presence queries/lead; {limits['provider_calls_per_run']} provider calls/run; ${limits['provider_spend_ceiling']['amount']:.2f} USD cap.")
    print(f"Signal freshness target: {limits['signal_freshness_days']} days; expected coverage: {limits['expected_coverage']}.")
    print("Sources: " + " → ".join(profile["source_order"]))
    print("Next human step: " + profile["recommended_next_human_step"])
    print("Preview only: selecting a profile does not change an enrichment run yet.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dse.py enrichment-profile", description="Inspect or export versioned path enrichment profiles.")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="list available Engine paths")
    for action in ("show", "preview", "export"):
        p = sub.add_parser(action, help={"show": "show profile defaults", "preview": "preview adjusted budgets", "export": "write a JSON copy for review"}[action])
        p.add_argument("path", choices=available_paths())
        p.add_argument("--provider-calls", type=int, default=0, help="planned max provider calls per run")
        p.add_argument("--herald-queries", type=int, default=12)
        p.add_argument("--presence-queries", type=int, default=3)
        p.add_argument("--freshness-days", type=int, default=180)
        p.add_argument("--max-spend", type=float, default=0.0, help="planned USD provider spend cap (0 means no paid budget)")
        p.add_argument("--json", action="store_true", help="print full profile JSON (show/preview)")
        if action == "export":
            p.add_argument("--out", default="", help="output JSON path; defaults to enrichment-profiles/<path>.v1.json")
    args = parser.parse_args(argv)
    try:
        if args.action == "list":
            for key in available_paths():
                print(f"{key:<12} {path_signals.profile(key)['label']}")
            return 0
        profile = build_profile(args.path, max_provider_calls=args.provider_calls, herald_queries=args.herald_queries,
                                presence_queries=args.presence_queries, signal_freshness_days=args.freshness_days, max_spend=args.max_spend)
        if args.action == "export":
            target = Path(args.out) if args.out else Path("enrichment-profiles") / f"{args.path}.v1.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"Wrote profile preview to {target}")
        else:
            _print_profile(profile, args.json)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
