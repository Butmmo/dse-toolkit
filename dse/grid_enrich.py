"""Run the existing enrichment lanes against live Ledger rows and write their fields back to the grid."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import tempfile
from pathlib import Path

from . import gridpush, gridrun
from .common import LISTS, ROOT

LANES = {"website", "herald", "presence"}
OUTPUTS = {
    "website": ["best_email", "best_email_source", "email_kind", "decision_maker", "decision_maker_title", "decision_maker_source", "phone_found", "contact_form_url", "booking_tool", "linkedin_found", "instagram_found", "facebook_found", "x_found", "youtube_found", "tech_stack", "site_description", "site_active", "mx_ok", "icp_hits", "lead_score", "lead_why", "enriched_on", "waterfall_metrics", "firmographics", "field_waterfall_metrics"],
    "herald": ["herald_company_findings", "herald_person_findings", "herald_signal_events", "herald_identity_summary", "herald_business_assessment", "herald_role_assessment", "herald_legal_form_assessment", "herald_checked_at", "herald_status", "herald_comparison_status", "herald_change_summary", "herald_new_source_urls", "herald_changed_source_urls", "herald_not_returned_urls", "herald_previous_checked_at", "herald_monitor_history", "herald_evidence_decisions", "dse_path_outcome", "dse_path_ai_advice", "dse_path_ai_advice_status", "dse_path_ai_advice_history", "herald_ai_review", "outreach_subject", "outreach_body", "outreach_evidence_detail"],
    "presence": ["presence_sources", "presence_checked_at", "presence_status", "presence_comparison_status", "presence_change_summary", "presence_new_source_urls", "presence_changed_source_urls", "presence_not_returned_urls", "presence_monitor_history"],
}
FULL_OUTPUTS = {
    "website": ["found_email", "email_source", "other_emails", "email_guesses", "email_check", "contact_page_url", "field_results", "enrichment_audit"],
    "herald": ["herald_findings", "herald_sources", "herald_company_sources", "herald_person_sources", "herald_role_candidates", "herald_people_candidates", "research_findings", "research_sources", "research_searched_at", "research_status", "enrichment_search_strategy", "field_results"],
    "presence": ["presence_signals", "field_results", "presence_search_waterfall"],
}


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _read_result(path: Path) -> tuple[list[str], list[dict]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader.fieldnames or []), list(reader)


def _run_lane(source: Path, lane: str, engine: str, limit: int, output_detail: str,
              icp: str = "", waterfall_config: str = "", dry_run: bool = False,
              path: str = "any", profile: str = "any", decision_maker: str = "any", legal_form: str = "any",
              decision_role: str = "signal_based", custom_role: str = "", search_provider: str = "duckduckgo",
              search_budget: int = 12, minimum_identity_score: float = 0.0, use_ai: bool = True):
    if lane == "website":
        from . import enrich
        report = enrich.enrich_file(str(source), icp=icp, engine=engine, max_rows=limit, render=False,
                                    waterfall_config_path=waterfall_config, dry_run=dry_run)
        m = re.search(r"Saved: (\S+\.csv)", report)
    elif lane == "herald":
        from . import signal_enrichment
        report = signal_enrichment.enrich_file(str(source), engine=engine, max_rows=limit, use_ai=use_ai,
            business_profile=profile, decision_maker=decision_maker, legal_form=legal_form, decision_role=decision_role,
            custom_role=custom_role, search_provider=search_provider, path_key=path, search_budget=search_budget,
            minimum_identity_score=minimum_identity_score)
        m = re.search(r"Saved: (\S+\.csv)", report)
    else:
        from . import signal_enrichment
        report = signal_enrichment.enrich_presence_file(str(source), engine=engine, max_rows=limit,
            search_budget=min(search_budget, 10), minimum_identity_score=minimum_identity_score)
        m = re.search(r"Saved: (\S+\.csv)", report)
    if not m:
        raise RuntimeError("The enrichment finished but did not report its result CSV path.")
    result_path = ROOT / m.group(1)
    if not result_path.is_file():
        raise RuntimeError("The enrichment result CSV is missing from this PC.")
    headers, rows = _read_result(result_path)
    selected = list(OUTPUTS[lane])
    if output_detail == "full":
        selected.extend(FULL_OUTPUTS[lane])
    history_column = f"{lane}_monitor_history"
    if lane in ("herald", "presence") and history_column not in selected:
        selected.append(history_column)
    advice_history_column = "dse_path_ai_advice_history"
    if lane == "herald" and advice_history_column not in selected:
        selected.append(advice_history_column)
    evidence_header = f"{lane}_evidence_decisions"
    if lane in ("website", "herald", "presence") and evidence_header not in selected:
        selected.append(evidence_header)
    selected = [h for h in selected if h in headers or h in {history_column, evidence_header, "dse_path_ai_advice_status", advice_history_column}]
    return result_path, selected, rows


def _decode_json(value, fallback):
    try:
        result = json.loads(value) if isinstance(value, str) else value
        return result if isinstance(result, type(fallback)) else fallback
    except (ValueError, TypeError):
        return fallback


def _evidence_decisions(row: dict, lane: str = "herald") -> str:
    """Compact each lane's selected fields, evidence, alternatives, and decision metadata for Ledger review."""
    if lane == "website":
        field_results = _decode_json(row.get("field_results"), [])
        selected_fields = {"best_email", "phone", "decision_maker", "decision_maker_title", "firmographics", "contact_form", "booking", "linkedin_profile", "instagram_profile", "facebook_profile", "x_profile", "youtube_profile", "technology", "site_description", "site_active", "icp_term_hits"}
        fields, evidence, n = [], [], 0
        for item in field_results:
            if not isinstance(item, dict) or item.get("field") not in selected_fields or item.get("metadata", {}).get("lane") != "website_enrichment":
                continue
            source = item.get("source") if isinstance(item.get("source"), dict) else {}
            value = item.get("value")
            fields.append({"field": item.get("field"), "value": value, "status": item.get("status"),
                           "source": source, "identity": item.get("identity", {}), "verification": item.get("verification", {}),
                           "cost": item.get("cost", {}), "miss_reason": item.get("miss_reason", ""),
                           "metadata": item.get("metadata", {}), "candidate_ids": []})
            field = fields[-1]
            if source.get("url") or source.get("name"):
                n += 1
                evidence_id = f"W{n:02d}"
                field["selected_evidence_id"] = evidence_id
                evidence.append({"id": evidence_id, "field": item.get("field"), "status": item.get("status"),
                                 "source_type": source.get("type", ""), "source_name": source.get("name", ""),
                                 "title": str(item.get("field", "")), "snippet": str(value if isinstance(value, (str, int, float, bool)) else json.dumps(value, ensure_ascii=False))[:130],
                                 "url": source.get("url", ""), "value": value})
            for candidate in (item.get("candidates") or [])[:6]:
                csource = candidate.get("source") if isinstance(candidate.get("source"), dict) else {}
                n += 1
                evidence_id = f"W{n:02d}"
                field["candidate_ids"].append(evidence_id)
                cvalue = candidate.get("value")
                evidence.append({"id": evidence_id, "field": item.get("field"), "status": candidate.get("status", "candidate"),
                                 "source_type": csource.get("type", ""), "source_name": csource.get("name", ""),
                                 "title": str(item.get("field", "")) + " candidate", "snippet": str(cvalue if isinstance(cvalue, (str, int, float, bool)) else json.dumps(cvalue, ensure_ascii=False))[:130],
                                 "url": csource.get("url", ""), "value": cvalue})
        payload = {"schema": "dbi.website-evidence-decisions.v1", "lane": lane,
                   "checked_at": row.get("enriched_on", ""), "status": row.get("enrich_status", ""),
                   "lead_score": row.get("lead_score", ""), "lead_why": str(row.get("lead_why", ""))[:400],
                   "fields": fields[:18], "sources": evidence[:48]}
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > 4800:
            for source in payload["sources"]:
                source["snippet"] = source["snippet"][:55]
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        while len(encoded) > 4800 and payload["sources"]:
            payload["sources"].pop()
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > 4800:
            payload["fields"] = [{k: (str(v)[:180] if isinstance(v, str) else v) for k, v in f.items() if k in ("field", "value", "status", "source", "identity", "verification", "selected_evidence_id")} for f in payload["fields"][:6]]
            payload["sources"] = payload["sources"][:6]
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > 4800:
            payload = {"schema": payload["schema"], "lane": lane, "checked_at": payload.get("checked_at", ""),
                       "status": payload.get("status", ""), "lead_score": payload.get("lead_score", ""),
                       "fields": [{"field": f.get("field"), "value": str(f.get("value", ""))[:120], "status": f.get("status"),
                                   "selected_evidence_id": f.get("selected_evidence_id")} for f in payload["fields"][:4]],
                       "sources": [{k: str(v or "")[:180] for k, v in source.items() if k in ("id", "field", "source_name", "status", "url")} for source in payload["sources"][:4]]}
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return encoded[:4800]
    if lane == "presence":
        signals = _decode_json(row.get("presence_signals"), [])
        waterfall = _decode_json(row.get("presence_search_waterfall"), {})
        compact = [{"id": str(s.get("id", ""))[:12], "subject": str(s.get("identity_subject", "company"))[:12],
                    "title": str(s.get("title", ""))[:130], "snippet": str(s.get("snippet", ""))[:180], "url": str(s.get("url", ""))[:300],
                    "identity_match": str(s.get("identity_match", ""))[:60], "identity_strength": str(s.get("identity_strength", "unknown"))[:16],
                    "identity_score": s.get("identity_score"), "confidence_kind": str(s.get("confidence_kind", "heuristic, not a probability"))[:48],
                    "matched_company_terms": s.get("matched_company_terms", [])[:6], "matched_person_terms": s.get("matched_person_terms", [])[:6],
                    "publication_date": str(s.get("publication_date", ""))[:24], "freshness_status": str(s.get("freshness_status", "undated"))[:20],
                    "query_matches": s.get("query_matches", [])[:3]}
                   for s in signals[:10] if isinstance(s, dict)]
        payload = {"schema": "dbi.presence-evidence-decisions.v1", "lane": lane,
                   "checked_at": row.get("presence_checked_at", ""), "status": row.get("presence_status", ""),
                   "comparison_status": row.get("presence_comparison_status", ""), "change_summary": str(row.get("presence_change_summary", ""))[:240],
                   "minimum_identity_score": waterfall.get("minimum_identity_score"), "search_waterfall": waterfall,
                   "signals": compact, "sources": [{"id": s["id"], "subject": s["subject"], "title": s["title"], "snippet": s["snippet"], "url": s["url"],
                                                        "identity_strength": s["identity_strength"], "identity_match": s["identity_match"],
                                                        "publication_date": s["publication_date"], "freshness_status": s["freshness_status"]} for s in compact]}
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > 4800:
            for item in payload["signals"]:
                item["snippet"] = item["snippet"][:60]
            payload["sources"] = [{**s, "snippet": s["snippet"][:60]} for s in payload["sources"]]
            payload["search_waterfall"] = {k: v for k, v in waterfall.items() if k in ("schema", "budget", "minimum_identity_score", "provider", "total_search_calls", "total_results_returned", "total_retained", "total_errors", "rungs")}
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        while len(encoded) > 4800 and payload["signals"]:
            payload["signals"].pop()
            payload["sources"].pop()
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > 4800:
            payload = {"schema": payload["schema"], "lane": lane, "checked_at": payload.get("checked_at", ""),
                       "status": payload.get("status", ""), "comparison_status": payload.get("comparison_status", ""),
                       "minimum_identity_score": payload.get("minimum_identity_score"), "search_waterfall": {},
                       "signals": [], "sources": []}
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return encoded

    business = _decode_json(row.get("herald_business_assessment"), {})
    roles_doc = _decode_json(row.get("herald_role_assessment"), {})
    people = _decode_json(row.get("herald_people_candidates"), [])
    legal_doc = _decode_json(row.get("herald_legal_form_assessment"), {})
    events_doc = _decode_json(row.get("herald_signal_events"), {})
    sources = _decode_json(row.get("herald_sources") or row.get("research_sources"), [])
    ai_review = _decode_json(row.get("herald_ai_review"), {})
    outreach_ids = [x.strip() for x in str(row.get("outreach_evidence") or "").split(",") if x.strip()]
    compact_sources = [{"id": str(s.get("id", ""))[:12], "subject": str(s.get("identity_subject", "unknown"))[:12],
                        "title": str(s.get("title", ""))[:110], "snippet": str(s.get("snippet", ""))[:135],
                        "url": str(s.get("url", ""))[:280], "identity_strength": str(s.get("identity_strength", "unknown"))[:16],
                        "identity_match": str(s.get("identity_match", ""))[:40], "publication_date": str(s.get("publication_date", ""))[:24],
                        "freshness_status": str(s.get("freshness_status", "undated"))[:20]}
                       for s in sources[:10] if isinstance(s, dict) and s.get("id")]
    profiles = [{"key": key, "label": str(value.get("label", key))[:60], "assessment": value.get("assessment", "unclear"),
                 "confidence": value.get("confidence", 0), "confidence_kind": value.get("confidence_kind", "heuristic evidence score"),
                 "evidence_ids": value.get("evidence_ids", [])[:8], "matched_cues": value.get("matched_cues", [])[:8]}
                for key, value in business.items() if isinstance(value, dict)]
    role_items = roles_doc.get("roles", []) if isinstance(roles_doc, dict) else []
    roles = [{"label": str(item.get("label", item.get("role", "")))[:80], "assessment": item.get("assessment", "unclear"),
              "candidate_status": item.get("candidate_status", ""), "confidence": item.get("confidence", 0),
              "confidence_kind": item.get("confidence_kind", "heuristic evidence score"),
              "evidence_ids": item.get("evidence_ids", [])[:8], "matched_cues": item.get("matched_cues", [])[:8]}
             for item in role_items[:12] if isinstance(item, dict)]
    forms = legal_doc.get("forms", {}) if isinstance(legal_doc, dict) else {}
    legal = [{"key": key, "status": value.get("status", ""), "evidence_ids": value.get("evidence_ids", [])[:8],
              "matched_cues": value.get("matched_cues", [])[:8]}
             for key, value in forms.items() if isinstance(value, dict)]
    event_items = events_doc.get("events", []) if isinstance(events_doc, dict) else []
    events = [{k: item.get(k) for k in ("category", "label", "subject", "source_id", "url", "matched_cues", "path_fit", "path_label") if k in item}
              for item in event_items[:12] if isinstance(item, dict)]
    person_items = [{"source_id": item.get("source_id", ""), "title": str(item.get("title", ""))[:100],
                     "url": str(item.get("url", ""))[:280], "candidate_score": item.get("candidate_score", 0),
                     "candidate_score_kind": item.get("candidate_score_kind", "heuristic review ordering, not a probability"),
                     "identity_strength": item.get("identity_strength", "unknown"), "status": item.get("status", ""),
                     "review_reasons": item.get("review_reasons", [])[:4], "evidence_relevance": item.get("evidence_relevance", {})}
                    for item in people[:5] if isinstance(item, dict)]
    ai = {k: ai_review.get(k) for k in ("company_summary", "company_evidence_ids", "person_summary", "person_evidence_ids", "role_observations", "open_questions", "basis") if k in ai_review} if isinstance(ai_review, dict) else {}
    payload = {"schema": "dbi.herald-evidence-decisions.v1", "checked_at": row.get("herald_checked_at", ""),
               "status": row.get("herald_status", ""), "comparison_status": row.get("herald_comparison_status", ""),
               "business_profiles": profiles, "roles": roles, "legal_form_mentions": legal, "signal_events": events,
               "people_candidates": person_items, "ai_review": ai,
               "path_outcome": {**_decode_json(row.get("dse_path_outcome"), {}),
                                "ai_advice": (_decode_json(row.get("dse_path_ai_advice"), {}) or None),
                                "ai_advice_status": row.get("dse_path_ai_advice_status", ""),
                                "ai_advice_history": _decode_json(row.get("dse_path_ai_advice_history"), [])[-3:]},
               "outreach": {"subject": str(row.get("outreach_subject", ""))[:120], "body": str(row.get("outreach_body", ""))[:900],
                            "evidence_ids": outreach_ids[:8], "personalization_basis": str(row.get("outreach_personalization_basis", ""))[:300]},
               "sources": compact_sources}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > 4800:
        for source in payload["sources"]:
            source["snippet"] = source["snippet"][:60]
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > 4800:
        payload["people_candidates"] = payload["people_candidates"][:2]
        payload["signal_events"] = payload["signal_events"][:6]
        payload["roles"] = payload["roles"][:8]
        payload["ai_review"] = {k: (v[:180] if isinstance(v, str) else v[:4] if isinstance(v, list) else v)
                                for k, v in payload["ai_review"].items()}
        payload["outreach"]["body"] = payload["outreach"]["body"][:360]
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > 4800 and isinstance(payload.get("path_outcome"), dict):
        outcome = payload["path_outcome"]
        outcome["evidence"] = outcome.get("evidence", [])[:4]
        outcome["commercial_viability_checks"] = outcome.get("commercial_viability_checks", [])[:3]
        outcome["observed_facts"] = outcome.get("observed_facts", [])[:5]
        outcome["ai_advice_history"] = outcome.get("ai_advice_history", [])[-2:]
        for history_item in outcome["ai_advice_history"]:
            if isinstance(history_item, dict) and isinstance(history_item.get("advice"), dict):
                history_advice = history_item["advice"]
                history_advice["sources"] = history_advice.get("sources", [])[:2]
                history_advice["questions"] = history_advice.get("questions", [])[:2]
                for key in ("recommended_validation", "reason"):
                    if isinstance(history_advice.get(key), str):
                        history_advice[key] = history_advice[key][:180]
        advice = outcome.get("ai_advice", {})
        if isinstance(advice, dict):
            advice["questions"] = advice.get("questions", [])[:2]
            for key in ("recommended_validation", "reason", "guardrail"):
                if isinstance(advice.get(key), str):
                    advice[key] = advice[key][:220]
        for fact in outcome["observed_facts"]:
            if isinstance(fact, dict):
                fact["sources"] = fact.get("sources", [])[:2]
                fact["value"] = str(fact.get("value", ""))[:120]
                for source in fact["sources"]:
                    if isinstance(source, dict):
                        source["value"] = str(source.get("value", ""))[:100]
                        source["url"] = str(source.get("url", ""))[:180]
        for key in ("outcome", "customer", "pain_hypothesis", "monetization_model", "next_step"):
            if isinstance(outcome.get(key), str):
                outcome[key] = outcome[key][:220]
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > 4800:
        payload = {"schema": payload["schema"], "checked_at": payload["checked_at"], "status": payload["status"],
                   "business_profiles": [{k: item.get(k) for k in ("key", "label", "assessment", "evidence_ids")} for item in payload["business_profiles"][:3]],
                   "roles": [{k: item.get(k) for k in ("label", "assessment", "evidence_ids")} for item in payload["roles"][:3]],
                   "signal_events": payload["signal_events"][:3],
                   "path_outcome": {k: payload["path_outcome"].get(k) for k in ("path_label", "outcome", "customer", "pain_hypothesis", "monetization_model", "proof_metrics", "commercial_viability_checks", "decision_status", "priority_evidence_count", "supporting_evidence_count", "evidence", "observed_facts", "next_step", "limits", "ai_advice", "ai_advice_status", "ai_advice_history")} if isinstance(payload.get("path_outcome"), dict) else {},
                   "sources": [{k: (str(item.get(k) or "")[:180] if k == "url" else item.get(k)) for k in ("id", "subject", "title", "url")} for item in payload["sources"][:5]]}
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > 4800:
        outcome = payload.get("path_outcome", {})
        advice = outcome.get("ai_advice", {}) if isinstance(outcome, dict) else {}
        history = outcome.get("ai_advice_history", []) if isinstance(outcome, dict) else []
        compact_history = []
        for item in history[-2:] if isinstance(history, list) else []:
            if not isinstance(item, dict):
                continue
            old_advice = item.get("advice", {}) if isinstance(item.get("advice"), dict) else {}
            compact_history.append({"checked_at": item.get("checked_at", ""), "path_key": item.get("path_key", "any"),
                                   "status": item.get("status", "unknown"), "change": item.get("change", ""),
                                   "advice": {"recommended_validation": str(old_advice.get("recommended_validation", ""))[:160],
                                              "model": old_advice.get("model", ""), "sources": old_advice.get("sources", [])[:1]}})
        payload = {"schema": payload.get("schema"), "checked_at": payload.get("checked_at", ""), "status": payload.get("status", ""),
                   "path_outcome": {"path_label": outcome.get("path_label", "") if isinstance(outcome, dict) else "",
                                    "decision_status": outcome.get("decision_status", "") if isinstance(outcome, dict) else "",
                                    "ai_advice_status": outcome.get("ai_advice_status", "") if isinstance(outcome, dict) else "",
                                    "ai_advice": ({"status": advice.get("status", ""), "model": advice.get("model", ""),
                                                    "recommended_validation": str(advice.get("recommended_validation", ""))[:180],
                                                    "evidence_ids": advice.get("evidence_ids", [])[:3], "guardrail": advice.get("guardrail", "")} if advice else None),
                                    "ai_advice_history": compact_history},
                   "sources": [{k: item.get(k) for k in ("id", "subject", "title", "url")} for item in payload.get("sources", [])[:3]]}
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return encoded


def _monitor_history(lane: str, result_row: dict, previous: object) -> str:
    """Append a compact source snapshot to the shared Ledger row history."""
    if lane == "herald":
        prefix, sources_field = "herald", "herald_sources"
    else:
        prefix, sources_field = "presence", "presence_signals"
    def urls(field: str) -> list[str]:
        return [x for x in str(result_row.get(f"{prefix}_{field}") or "").splitlines() if x][:8]
    try:
        old = json.loads(str(previous)) if previous else []
    except (ValueError, TypeError):
        old = []
    if not isinstance(old, list):
        old = []
    try:
        raw_sources = json.loads(result_row.get(sources_field) or "[]")
    except (ValueError, TypeError):
        raw_sources = []
    if not isinstance(raw_sources, list):
        raw_sources = []
    sources = [{k: str(source.get(k) or "")[:limit] for k, limit in (("url", 220), ("title", 100), ("snippet", 80), ("identity_subject", 12), ("publication_date", 24), ("freshness_status", 20), ("type", 48))}
               for source in raw_sources[:3] if isinstance(source, dict) and source.get("url")]
    record = {"checked_at": result_row.get(f"{prefix}_checked_at") or result_row.get("research_searched_at") or "",
              "status": result_row.get(f"{prefix}_comparison_status") or "unknown",
              "summary": str(result_row.get(f"{prefix}_change_summary") or "")[:240],
              "new_source_urls": [u[:220] for u in urls("new_source_urls")[:4]], "changed_source_urls": [u[:220] for u in urls("changed_source_urls")[:4]],
              "not_returned_urls": [u[:220] for u in urls("not_returned_urls")[:4]], "sources": sources}
    if not record["checked_at"]:
        record["checked_at"] = result_row.get("presence_checked_at", "")
    old.append(record)
    history = old[-6:]
    value = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
    while len(value) > 4800 and len(history) > 1:
        history.pop(0)
        value = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
    if len(value) > 4800:
        history = [{"checked_at": record["checked_at"], "status": record["status"], "summary": record["summary"],
                    "new_source_urls": record["new_source_urls"][:2], "changed_source_urls": record["changed_source_urls"][:2],
                    "not_returned_urls": record["not_returned_urls"][:2], "sources": record["sources"][:1]}]
        value = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
    return value


def _advice_history(result_row: dict, previous: object) -> str:
    """Retain and compare local AI advice snapshots without implying an unavailable opinion was withdrawn."""
    history = _decode_json(previous, [])
    if not isinstance(history, list):
        history = []
    advice = _decode_json(result_row.get("dse_path_ai_advice"), {})
    status = str(result_row.get("dse_path_ai_advice_status", "unknown"))
    try:
        outcome = json.loads(result_row.get("dse_path_outcome") or "{}")
    except (ValueError, TypeError):
        outcome = {}
    checked_at = result_row.get("herald_checked_at", "")
    if isinstance(advice, dict) and advice:
        safe_advice = {key: advice.get(key) for key in ("recommended_validation", "reason", "evidence_ids", "questions", "model", "generated_at", "guardrail") if key in advice}
        try:
            sources = json.loads(result_row.get("herald_sources") or "[]")
        except (ValueError, TypeError):
            sources = []
        by_id = {str(item.get("id")): item for item in sources if isinstance(item, dict) and item.get("id")} if isinstance(sources, list) else {}
        safe_advice["sources"] = [{"id": source_id, "title": str(by_id[source_id].get("title", ""))[:140],
                                   "url": str(by_id[source_id].get("url", ""))[:300],
                                   "publication_date": by_id[source_id].get("publication_date", ""),
                                   "freshness_status": by_id[source_id].get("freshness_status", "undated")}
                                  for source_id in advice.get("evidence_ids", []) if source_id in by_id][:4]
        def signature_basis(item):
            item_sources = {source.get("id"): source.get("url", "") for source in item.get("sources", []) if isinstance(source, dict) and source.get("id")}
            def urls(ids):
                return sorted({item_sources.get(source_id, "") for source_id in ids if item_sources.get(source_id)})
            return {"recommended_validation": item.get("recommended_validation", ""), "reason": item.get("reason", ""),
                    "evidence_urls": urls(item.get("evidence_ids", [])),
                    "questions": [{"question": question.get("question", ""), "source_urls": urls(question.get("evidence_ids", []))}
                                  for question in item.get("questions", []) if isinstance(question, dict)]}
        compare_basis = signature_basis(safe_advice)
        signature = json.dumps({"path": outcome.get("path_key", "any"), "advice": compare_basis}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        prior = next((item for item in reversed(history) if isinstance(item, dict) and item.get("status") == "ready"), None)
        if prior is None:
            change = "first_advice"
        else:
            prior_advice = prior.get("advice", {})
            prior_signature = json.dumps({"path": prior.get("path_key", "any"), "advice": signature_basis(prior_advice)}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            change = "unchanged" if signature == prior_signature else "changed"
        entry = {"checked_at": checked_at or advice.get("generated_at", ""), "path_key": outcome.get("path_key", "any"),
                 "status": "ready", "change": change, "advice": safe_advice}
    else:
        entry = {"checked_at": checked_at, "path_key": outcome.get("path_key", "any"), "status": status,
                 "change": "no_new_advice_previous_snapshot_retained" if any(isinstance(item, dict) and item.get("status") == "ready" for item in history) else "no_advice_yet"}
    history.append(entry)
    history = history[-6:]
    value = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
    while len(value) > 4700 and len(history) > 1:
        history.pop(0)
        value = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
    if len(value) > 4700 and history and history[-1].get("status") == "ready":
        item = history[-1]
        item["advice"] = {key: item.get("advice", {}).get(key) for key in ("recommended_validation", "evidence_ids", "model", "generated_at")}
        value = json.dumps(history[-1:], ensure_ascii=False, separators=(",", ":"))
    return value


def run(grid_ref: str, lane: str, engine: str = "", limit: int = 25, output_detail: str = "essentials",
        overwrite: bool = False, api=None, say=lambda *_: None, **options) -> str:
    if lane not in LANES:
        raise ValueError("Choose website, herald or presence.")
    lane_limit = 50 if lane in ("herald", "presence") else 500
    if not 1 <= limit <= lane_limit:
        raise ValueError(f"Process 1 to {lane_limit} {lane} grid rows per run.")
    if output_detail not in ("essentials", "full"):
        raise ValueError("output detail must be essentials or full.")
    api = api or gridpush.connect()
    if api is None:
        raise RuntimeError("This PC is not connected to Citadel yet (run the HQ Tools setup first).")
    grid = gridpush.resolve_grid(gridpush._grids(api), grid_ref)
    columns = gridpush.columns_of(grid.get("doc"))
    rows = gridrun.read_rows(api, grid["id"])
    if not rows:
        return f"{grid.get('workbook', '')}/{grid['name']}: this grid has no rows.\n"
    source_rows = rows[:limit]
    headers = [c["label"] for c in columns]
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", suffix=".csv", prefix="grid-enrich-", dir=LISTS, delete=False) as file:
        input_path = Path(file.name)
        writer = csv.DictWriter(file, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        key_by_label = {gridpush.norm(c["label"]): c["key"] for c in columns}
        for row in source_rows:
            data = row.get("data") or {}
            writer.writerow({c["label"]: _cell(data.get(c["key"])) for c in columns})
    say(f"{grid.get('workbook', '')}/{grid['name']}: running {lane} enrichment on {len(source_rows)} live grid rows.")
    try:
        result_path, output_headers, enriched_rows = _run_lane(input_path, lane, engine, len(source_rows), output_detail, **options)
    finally:
        input_path.unlink(missing_ok=True)
    if len(enriched_rows) != len(source_rows):
        raise RuntimeError(f"The enrichment returned {len(enriched_rows)} rows for {len(source_rows)} inputs; nothing was written to the grid.")
    existing = {gridpush.norm(c["label"]): c for c in columns}
    new_headers = [h for h in output_headers if gridpush.norm(h) not in existing]
    evidence_header = f"{lane}_evidence_decisions"
    monitor_priority = [evidence_header, "dse_path_outcome", "dse_path_ai_advice", "dse_path_ai_advice_status", "dse_path_ai_advice_history", f"{lane}_monitor_history", f"{lane}_comparison_status", f"{lane}_change_summary"]
    new_headers.sort(key=lambda h: monitor_priority.index(h) if h in monitor_priority else len(monitor_priority))
    remaining = max(0, 60 - len(columns))
    omitted_columns = new_headers[remaining:]
    new_headers = new_headers[:remaining]
    added = api.rpc("hq_grid_add_columns", {"p_grid": grid["id"], "p_cols": [{"label": h, "type": "longtext" if h in {f"{lane}_monitor_history", evidence_header, "dse_path_outcome", "dse_path_ai_advice", "dse_path_ai_advice_history"} else gridpush.infer_type([r.get(h, "") for r in enriched_rows])} for h in new_headers]}, tries=2) if new_headers else []
    by_label = {gridpush.norm(c["label"]): c for c in columns}
    for column in added or []:
        by_label[gridpush.norm(column["label"])] = column
    output_to_key = {h: by_label[gridpush.norm(h)]["key"] for h in output_headers if gridpush.norm(h) in by_label}
    updates, skipped, oversized = [], 0, 0
    for source_row, result_row in zip(source_rows, enriched_rows):
        cells = {}
        data = source_row.get("data") or {}
        history_header = f"{lane}_monitor_history"
        advice_history_header = "dse_path_ai_advice_history"
        advice_history_key = output_to_key.get(advice_history_header)
        if lane == "herald" and advice_history_key:
            result_row[advice_history_header] = _advice_history(result_row, data.get(advice_history_key))
        advice_history_header = "dse_path_ai_advice_history"
        for header, key in output_to_key.items():
            if header == history_header:
                value = _monitor_history(lane, result_row, data.get(key))
            elif header == advice_history_header:
                value = _cell(result_row.get(header))
            elif header == evidence_header:
                value = _evidence_decisions(result_row, lane)
            else:
                value = _cell(result_row.get(header))
            if not value:
                if header == "dse_path_ai_advice":
                    cells[key] = ""
                continue
            if not overwrite and header not in {history_header, advice_history_header, evidence_header, "dse_path_outcome", "dse_path_ai_advice", "dse_path_ai_advice_status", f"{lane}_comparison_status", f"{lane}_change_summary", f"{lane}_new_source_urls", f"{lane}_changed_source_urls", f"{lane}_not_returned_urls", f"{lane}_previous_checked_at"} and data.get(key) not in (None, ""):
                continue
            if len(value) > 5000:
                oversized += 1
                continue
            cells[key] = value
        if cells:
            updates.append({"id": source_row["id"], "cells": cells})
        else:
            skipped += 1
    written = 0
    for offset in range(0, len(updates), 100):
        written += gridrun.save_cells(api, grid["id"], updates[offset:offset + 100])
        say(f"PROGRESS {min(offset + 100, len(updates))}/{len(updates)} failed 0 skipped {skipped}")
    omitted_note = f" {len(omitted_columns)} output columns could not be added because this grid is at its 60-column limit." if omitted_columns else ""
    return (f"FINISHED {lane} enrichment: {written} rows updated, {skipped} rows had no new values, {oversized} oversized values omitted. "
            f"Created or reused {len(output_to_key)} output columns; report saved at {result_path.relative_to(ROOT).as_posix()}.{omitted_note}\n")


def cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="dse.py grid enrich")
    parser.add_argument("grid")
    parser.add_argument("--lane", choices=sorted(LANES), default="website")
    parser.add_argument("--engine", default="")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--output-detail", choices=["essentials", "full"], default="essentials")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--icp", default="")
    parser.add_argument("--waterfall-config", default="")
    parser.add_argument("--dry-run-providers", action="store_true")
    parser.add_argument("--path", default="any")
    parser.add_argument("--profile", default="any")
    parser.add_argument("--decision-maker", default="any")
    parser.add_argument("--legal-form", default="any")
    parser.add_argument("--decision-role", default="signal_based")
    parser.add_argument("--custom-role", default="")
    parser.add_argument("--search-provider", default="duckduckgo")
    parser.add_argument("--search-budget", type=int, default=12)
    parser.add_argument("--minimum-identity-score", type=float, default=0.0)
    parser.add_argument("--no-ai", action="store_true")
    args = parser.parse_args(argv)
    options = vars(args).copy()
    grid = options.pop("grid")
    lane = options.pop("lane")
    options["dry_run"] = options.pop("dry_run_providers")
    options["use_ai"] = not options.pop("no_ai")
    try:
        print(run(grid, lane, say=lambda m: print(m, flush=True), **options), end="")
        return 0
    except (ValueError, RuntimeError) as error:
        print("grid enrich: " + (str(error)[:300]))
        return 1


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
