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


def _assessment(strong: list[dict], medium: list[dict]) -> dict:
    evidence = strong or medium
    if not evidence:
        return {"assessment": "unclear", "confidence": 0.0, "confidence_kind": "heuristic evidence score", "evidence_ids": [], "matched_cues": []}
    base = 0.78 if strong else 0.52
    confidence = min(0.94, base + 0.04 * max(0, len({x["id"] for x in evidence}) - 1))
    return {
        "assessment": "strong textual cue" if confidence >= 0.75 else "some textual cues",
        "confidence": round(confidence, 2),
        "confidence_kind": "heuristic evidence score, not a probability",
        "evidence_ids": list(dict.fromkeys(x["id"] for x in evidence)),
        "matched_cues": list(dict.fromkeys(cue for x in evidence for cue in x["cues"])),
    }


def assess(signals: list[dict], roles: list[str], custom_role: str = "", legal_hint: str = "any", checked_at: str = "") -> dict:
    """Return cautious archetype, role, and legal-form mention assessments with source IDs."""
    company_sources = [s for s in signals if s.get("identity_subject") == "company"]
    person_sources = [s for s in signals if s.get("identity_subject") == "person" and s.get("identity_strength") != "insufficient"]
    signal_text = {str(s.get("id", "")): f"{s.get('title', '')} {s.get('snippet', '')}"
                   for s in company_sources}
    business = {}
    for key, rules in BUSINESS_RULES.items():
        strong, medium = [], []
        for source_id, text in signal_text.items():
            strong_cues = _matches(text, rules["strong"])
            medium_cues = _matches(text, rules["medium"])
            if strong_cues:
                strong.append({"id": source_id, "cues": strong_cues})
            elif medium_cues:
                medium.append({"id": source_id, "cues": medium_cues})
        result = _assessment(strong, medium)
        result["label"] = rules["label"]
        business[key] = result

    role_keys = list(dict.fromkeys(roles))
    if custom_role.strip():
        role_keys.insert(0, "custom")
    role_results = []
    role_sources = [s for s in signals if s.get("identity_strength") != "insufficient"
                    and (s.get("type") == "decision_maker_role_discovery" or s.get("identity_subject") == "person")]
    for role in role_keys:
        patterns = (re.escape(custom_role.strip()),) if role == "custom" and custom_role.strip() else ROLE_RULES.get(role, ())
        matches = []
        for source in role_sources:
            text = f"{source.get('title', '')} {source.get('snippet', '')}"
            cues = _matches(text, patterns) if patterns else []
            if cues:
                matches.append({"id": str(source.get("id", "")), "cues": cues})
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
        matches = [{"id": str(source.get("id", "")), "cues": _matches(f"{source.get('title', '')} {source.get('snippet', '')}", patterns)}
                   for source in company_sources for _unused in (0,)]
        matches = [m for m in matches if m["cues"]]
        legal_mentions[key] = {"status": "unverified mention found" if matches else "no mention found", "evidence_ids": [m["id"] for m in matches], "matched_cues": list(dict.fromkeys(c for m in matches for c in m["cues"]))}

    people = []
    for source in person_sources:
        path = urlparse(str(source.get("url", ""))).path.casefold()
        if "/company/" in path:
            continue
        text = f"{source.get('title', '')} {source.get('snippet', '')}"
        matched = [r for r in role_results if r["role"] != "custom" and any(re.search(p, text, re.IGNORECASE) for p in ROLE_RULES.get(r["role"], ()))]
        if custom_role.strip() and re.search(re.escape(custom_role.strip()), text, re.IGNORECASE):
            matched.append(next((r for r in role_results if r["role"] == "custom"), {"role": "custom", "label": custom_role.strip()}))
        people.append({
            "source_id": source.get("id", ""), "title": source.get("title", ""), "url": source.get("url", ""),
            "role_candidates": [{"role": r["role"], "label": r["label"], "evidence_ids": r["evidence_ids"]} for r in matched],
            "status": "role match possible" if matched else "profile result needs manual role review",
        })
    return {
        "version": 1,
        "checked_at": checked_at,
        "basis": "Returned public search titles and snippets only. These are review cues, not verified classifications or calibrated probabilities.",
        "business_profiles": business,
        "decision_maker_roles": role_results,
        "people_candidates": people,
        "legal_form_mentions": {"verification_status": "not verified", "selected_search_hint": legal_hint, "forms": legal_mentions},
    }
