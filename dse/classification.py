"""Cautious, source-linked assessments from the Herald search snippets.

Scores describe textual evidence strength only. They are not calibrated probabilities
or verified facts about a business, person, job, or legal status.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse


BUSINESS_RULES = {
    "franchise_group": {
        "label": "Franchise or multi-location group",
        "strong": (r"\bfranchis(?:e|es|ed|ing|or|ee|ees)\b", r"\bmulti[- ]unit\b", r"\bfranchise locations\b"),
        "medium": (r"\bmultiple locations\b", r"\bserving \d+ locations\b", r"\bnational locations\b"),
    },
    "local_smb": {
        "label": "Local or owner-led SMB",
        "strong": (r"\bindependent(?:ly)? owned\b", r"\bfamily[- ]owned\b", r"\bowner[- ]operated\b", r"\bsmall business\b"),
        "medium": (r"\blocally owned\b", r"\bowner[- ]led\b", r"\bserving the [\w -]+ community\b"),
    },
    "saas": {
        "label": "SaaS or software company",
        "strong": (r"\bsoftware as a service\b", r"\bsaas\b", r"\bsubscription software\b", r"\bcloud[- ]based software\b"),
        "medium": (r"\bsoftware platform\b", r"\bsoftware product\b", r"\bapi integrations\b"),
    },
    "online_store": {
        "label": "Online store or ecommerce business",
        "strong": (r"\be[- ]?commerce\b", r"\bonline store\b", r"\bshop online\b", r"\bshopify store\b"),
        "medium": (r"\badd to cart\b", r"\bcheckout\b", r"\bshop now\b", r"\bonline shopping\b"),
    },
    "enterprise": {
        "label": "Mid-market or enterprise company",
        "strong": (r"\bfortune 500\b", r"\bpublicly traded\b", r"\bsubsidiar(?:y|ies)\b", r"\b\d[\d,]{2,}\+? employees\b", r"\bglobal offices\b"),
        "medium": (r"\boperations in \d+ countries\b", r"\benterprise headquarters\b", r"\bmultinational\b"),
    },
}

ROLE_RULES = {
    "hr": (r"\bhuman resources\b", r"\bpeople operations\b", r"\bchief people officer\b", r"\bhead of people\b", r"\bHR director\b", r"\btalent acquisition\b", r"\brecruiting director\b"),
    "vp_sales": (r"\bvice president of sales\b", r"\bVP of sales\b", r"\bhead of sales\b", r"\bsales director\b", r"\bchief revenue officer\b", r"\bCRO\b"),
    "dev_hiring_manager": (r"\bengineering manager\b", r"\bsoftware development manager\b", r"\bdevelopment hiring manager\b", r"\btechnical recruiter\b", r"\bengineering recruiter\b"),
    "director": (r"\bdirector\b", r"\bdepartment head\b"),
    "lead_coach": (r"\blead coach\b", r"\bhead coach\b", r"\bcoaching director\b"),
    "president": (r"\bpresident\b",),
    "ceo": (r"\bchief executive officer\b", r"\bCEO\b"),
    "coo": (r"\bchief operating officer\b", r"\bCOO\b"),
    "cto": (r"\bchief technology officer\b", r"\bCTO\b"),
    "founder": (r"\bco-founder\b", r"\bfounder\b"),
}


def _matches(text: str, patterns: tuple[str, ...]) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE)]


def _overlap(expected: str, observed: str) -> tuple[float, list[str]]:
    ignored = {"the", "and", "for", "with", "from", "current", "last", "company", "business"}
    left = {x for x in re.findall(r"[a-z0-9]{2,}", (expected or "").casefold()) if x not in ignored}
    right = {x for x in re.findall(r"[a-z0-9]{2,}", (observed or "").casefold()) if x not in ignored}
    matched = sorted(left & right)
    return (len(matched) / len(left) if left else 0.0), matched


def _source_host(source: dict) -> str:
    return str(source.get("source_host") or urlparse(str(source.get("url", ""))).hostname or "").lower().removeprefix("www.")


def _role_title_tokens(value: str) -> set[str]:
    """Normalize common executive abbreviations and title filler for custom-role matching."""
    text = (value or "").casefold()
    expansions = (
        (r"\bchief executive officer\b", " ceo "),
        (r"\bchief operating officer\b", " coo "),
        (r"\bchief technology officer\b|\bchief technical officer\b", " cto "),
        (r"\bchief financial officer\b", " cfo "),
        (r"\bchief marketing officer\b", " cmo "),
        (r"\bchief product officer\b", " cpo "),
        (r"\bchief revenue officer\b", " cro "),
        (r"\bsenior vice president\b", " svp "),
        (r"\bexecutive vice president\b", " evp "),
        (r"\bvice president\b", " vp "),
    )
    for pattern, replacement in expansions:
        text = re.sub(pattern, replacement, text)
    filler = {"of", "the", "and", "at", "for", "a", "an"}
    return {token for token in re.findall(r"[a-z0-9]+", text) if token not in filler}


def _custom_role_cues(text: str, role: str) -> list[str]:
    expected = _role_title_tokens(role)
    observed = _role_title_tokens(text)
    if expected and expected <= observed:
        return ["normalized title match: " + " ".join(sorted(expected))]
    return []


def _assessment(strong: list[dict], medium: list[dict]) -> dict:
    evidence = strong or medium
    if not evidence:
        return {"assessment": "unclear", "confidence": 0.0, "confidence_kind": "heuristic evidence score", "evidence_ids": [], "matched_cues": [], "distinct_source_hosts": 0, "source_hosts": []}
    base = 0.78 if strong else 0.52
    hosts = sorted({x.get("source_host") for x in evidence if x.get("source_host")})
    confidence = min(0.94, base + 0.04 * max(0, len(hosts) - 1))
    return {
        "assessment": "strong textual cue" if confidence >= 0.75 else "some textual cues",
        "confidence": round(confidence, 2),
        "confidence_kind": "heuristic evidence score, not a probability",
        "evidence_ids": list(dict.fromkeys(x["id"] for x in evidence)),
        "matched_cues": list(dict.fromkeys(cue for x in evidence for cue in x["cues"])),
        "distinct_source_hosts": len(hosts), "source_hosts": hosts,
    }


def assess(signals: list[dict], roles: list[str], custom_role: str = "", legal_hint: str = "any", checked_at: str = "", context: dict | None = None) -> dict:
    """Return cautious archetype, role, and legal-form mention assessments with source IDs."""
    context_values = {"".join(ch for ch in str(key).lower() if ch.isalnum()): value for key, value in (context or {}).items()}
    def context_value(*keys: str) -> str:
        for key in keys:
            value = context_values.get("".join(ch for ch in key.lower() if ch.isalnum()))
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""
    company_sources = [s for s in signals if s.get("identity_subject") == "company"]
    person_sources = [s for s in signals if s.get("identity_subject") == "person" and s.get("identity_strength") != "insufficient"]
    business = {}
    for key, rules in BUSINESS_RULES.items():
        strong, medium = [], []
        for source in company_sources:
            source_id = str(source.get("id", ""))
            text = f"{source.get('title', '')} {source.get('snippet', '')}"
            strong_cues = _matches(text, rules["strong"])
            medium_cues = _matches(text, rules["medium"])
            if strong_cues:
                strong.append({"id": source_id, "cues": strong_cues, "source_host": _source_host(source)})
            elif medium_cues:
                medium.append({"id": source_id, "cues": medium_cues, "source_host": _source_host(source)})
        result = _assessment(strong, medium)
        result["label"] = rules["label"]
        business[key] = result

    role_keys = list(dict.fromkeys(roles))
    if custom_role.strip():
        role_keys.insert(0, "custom")
    role_results = []
    role_sources = [s for s in signals if s.get("identity_strength") != "insufficient"
                    and (str(s.get("type", "")).startswith("decision_maker_role_discovery") or s.get("identity_subject") == "person")]
    for role in role_keys:
        matches = []
        for source in role_sources:
            text = f"{source.get('title', '')} {source.get('snippet', '')}"
            cues = _custom_role_cues(text, custom_role.strip()) if role == "custom" and custom_role.strip() else _matches(text, ROLE_RULES.get(role, ()))
            if cues:
                matches.append({"id": str(source.get("id", "")), "cues": cues, "source_host": _source_host(source)})
        assessment = _assessment(matches, [])
        assessment.update({"role": role, "label": custom_role.strip() if role == "custom" else role.replace("_", " ").title()})
        assessment["candidate_status"] = "role evidence found" if matches else "not evidenced in returned snippets"
        role_results.append(assessment)

    legal_patterns = {
        "us_c_corp": (r"\bC[- ]?corporation\b", r"\bC[- ]?Corp\b", r"\bForm 1120\b"),
        "us_s_corp": (r"\bS[- ]?corporation\b", r"\bS[- ]?Corp\b", r"\bForm 1120-S\b"),
    }
    legal_mentions = {}
    for key, patterns in legal_patterns.items():
        matches = [{"id": str(source.get("id", "")), "cues": _matches(f"{source.get('title', '')} {source.get('snippet', '')}", patterns), "source_host": _source_host(source)}
                   for source in company_sources for _unused in (0,)]
        matches = [m for m in matches if m["cues"]]
        legal_mentions[key] = {"status": "unverified mention found" if matches else "no mention found", "evidence_ids": [m["id"] for m in matches], "matched_cues": list(dict.fromkeys(c for m in matches for c in m["cues"])), "distinct_source_hosts": len({m["source_host"] for m in matches if m["source_host"]}), "source_hosts": sorted({m["source_host"] for m in matches if m["source_host"]})}

    people = []
    candidate_sources = list(person_sources)
    candidate_sources.extend(
        s for s in signals
        if str(s.get("type", "")).startswith("decision_maker_role_discovery")
        and "/in/" in urlparse(str(s.get("url", ""))).path.casefold()
        and s not in candidate_sources
    )
    for source in candidate_sources:
        path = urlparse(str(source.get("url", ""))).path.casefold()
        if "/company/" in path:
            continue
        text = f"{source.get('title', '')} {source.get('snippet', '')}"
        candidate_roles = []
        for role in role_results:
            cues = _custom_role_cues(text, custom_role.strip()) if role["role"] == "custom" and custom_role.strip() else _matches(text, ROLE_RULES.get(role["role"], ()))
            if cues:
                candidate_roles.append({"role": role["role"], "label": role["label"], "matched_cues": cues})
        identity_score = float(source.get("identity_score") or 0)
        role_score = 1.0 if candidate_roles else 0.0
        current_position = context_value("current_position", "contact_title", "decision_maker_title")
        last_position = context_value("last_position", "previous_position", "decision_maker_last_position")
        current_ratio, current_terms = _overlap(current_position, text)
        last_ratio, last_terms = _overlap(last_position, text)
        query_types = {str(match.get("type", "")) for match in source.get("query_matches", [])}
        person_signal = context_value("decision_maker_last_signal", "person_last_signal", "contact_recent_signal", "person_last_lead_signal")
        company_signal = context_value("company_last_signal", "company_signal", "last_lead_signal", "last_signal")
        signal_targets = []
        if person_signal and (source.get("identity_subject") == "person" or "decision_maker_role_discovery_person_signal" in query_types):
            signal_targets.append(("person", person_signal))
        if company_signal and (source.get("identity_subject") == "company" or "decision_maker_role_discovery" in query_types):
            signal_targets.append(("company", company_signal))
        signal_matches = []
        for subject, target in signal_targets:
            ratio, matched_terms = _overlap(target, text)
            signal_matches.append({"subject": subject, "ratio": round(ratio, 2), "matched_terms": matched_terms})
        best_signal = max(signal_matches, key=lambda match: match["ratio"], default={"subject": "none", "ratio": 0.0, "matched_terms": []})
        signal_subject = best_signal["subject"]
        signal_ratio, signal_terms = best_signal["ratio"], best_signal["matched_terms"]
        has_publication_date = bool(source.get("publication_date"))
        freshness_score = float(source.get("freshness_score") or 0)
        active_weights = [(identity_score, 0.30), (role_score, 0.30)]
        if current_position:
            active_weights.append((current_ratio, 0.20))
        if last_position:
            active_weights.append((last_ratio, 0.05))
        if signal_targets:
            active_weights.append((signal_ratio, 0.15))
        if has_publication_date:
            active_weights = [(value, weight * 0.9) for value, weight in active_weights]
            active_weights.append((freshness_score, 0.10))
        total_weight = sum(weight for _, weight in active_weights)
        candidate_score = round(sum(value * weight for value, weight in active_weights) / total_weight, 2) if total_weight else 0.0
        active_weight_names = ["identity", "targeted_role"] + (["current_position"] if current_position else []) + (["previous_position"] if last_position else []) + (["lead_signal"] if signal_targets else [])
        if has_publication_date:
            active_weight_names = [*active_weight_names, "freshness"]
        effective_weights = {name: round(weight / total_weight, 3) for name, (_, weight) in zip(active_weight_names, active_weights)} if total_weight else {}
        is_company_discovery = str(source.get("type", "")).startswith("decision_maker_role_discovery")
        people.append({
            "source_id": source.get("id", ""), "title": source.get("title", ""),
            "snippet": source.get("snippet", ""), "url": source.get("url", ""),
            "source_host": _source_host(source),
            "identity_strength": source.get("identity_strength", "unknown"),
            "identity_score": round(identity_score, 2), "candidate_score": candidate_score,
            "candidate_score_kind": "heuristic review ordering, not a probability",
            "source_type": source.get("type", ""), "role_candidates": candidate_roles,
            "evidence_relevance": {
                "current_position_match": {"ratio": round(current_ratio, 2), "matched_terms": current_terms},
                "previous_position_match": {"ratio": round(last_ratio, 2), "matched_terms": last_terms},
                "lead_signal_subject": signal_subject,
                "lead_signal_matches": signal_matches,
                "publication_date": source.get("publication_date", ""),
                "date_precision": source.get("date_precision", "unknown"),
                "freshness_status": source.get("freshness_status", "undated"),
                "age_days": source.get("age_days"),
                "freshness_score": freshness_score,
                "effective_ranking_weights": effective_weights,
            },
            "review_reasons": (["company/person identity matched"] if identity_score else [])
                              + (["title or snippet matches a targeted role"] if candidate_roles else [])
                              + (["individual identity needs manual confirmation"] if is_company_discovery else []),
            "status": "role match possible" if candidate_roles else "profile result needs manual role review",
        })
    people.sort(key=lambda item: (-item["candidate_score"], item["source_id"]))
    for position, candidate in enumerate(people, 1):
        candidate["review_order"] = position
    from . import business_profiles
    signal_events = []
    for source in signals:
        subject = source.get("identity_subject")
        if subject not in ("company", "person"):
            continue
        if subject == "person" and source.get("identity_strength") == "insufficient":
            continue
        signal_events.extend(business_profiles.assess_signal_events(
            f"{source.get('title', '')} {source.get('snippet', '')}", subject=subject, source=source))
    personal_context = context_value("decision_maker_last_signal", "person_last_signal", "contact_recent_signal", "person_last_lead_signal")
    company_context = context_value("company_last_signal", "company_signal", "last_lead_signal", "last_signal")
    signal_events.extend(business_profiles.assess_signal_events(personal_context, subject="person", source={"source_type": "lead_csv_input"}))
    signal_events.extend(business_profiles.assess_signal_events(company_context, subject="company", source={"source_type": "lead_csv_input"}))
    return {
        "version": 1,
        "checked_at": checked_at,
        "basis": "Returned public search titles and snippets only. These are review cues, not verified classifications or calibrated probabilities.",
        "business_profiles": business,
        "decision_maker_roles": role_results,
        "people_candidates": people,
        "signal_events": signal_events,
        "signal_events_basis": "Matched phrases are research cues from returned snippets or lead CSV input. They are not verified events, and suggested roles are targeting guidance only.",
        "legal_form_mentions": {"verification_status": "not verified", "selected_search_hint": legal_hint, "forms": legal_mentions},
    }
