"""Targeting profiles for the Herald-facing business-signal research waterfall.

These are search directions chosen by the user, not verified company classifications.
Evidence review and legal-form verification are separate enrichment stages.
"""

BUSINESS_PROFILES = {
    "any": {"label": "Any business", "terms": ""},
    "franchise_group": {"label": "Franchise or multi-location group", "terms": "franchise locations parent company franchise opportunities"},
    "local_smb": {"label": "Local or owner-led SMB", "terms": "independent locally owned small business owner operated"},
    "saas": {"label": "SaaS or software company", "terms": "SaaS software product pricing integrations platform"},
    "online_store": {"label": "Online store or ecommerce business", "terms": "online store ecommerce shop products shipping"},
    "enterprise": {"label": "Mid-market or enterprise company", "terms": "corporate group subsidiaries offices executive leadership"},
}

DECISION_MAKER_PROFILES = {
    "any": {"label": "Any decision maker", "terms": ""},
    "owner_compact": {"label": "Owner, founder or compact team", "terms": "owner founder principal managing director small team"},
    "franchise_operator": {"label": "Franchise operator and parent group", "terms": "franchisee franchise owner operator parent company leadership"},
    "functional_leader": {"label": "Functional leader or department head", "terms": "head director product growth marketing operations"},
    "specialist_director": {"label": "Specialised director or executive", "terms": "director vice president chief procurement technology finance"},
}

LEGAL_FORM_PROFILES = {
    "any": {"label": "Any or unknown legal form", "terms": ""},
    "us_c_corp": {"label": "US C corporation (search only)", "terms": '"C corporation" OR "C-Corp" OR "Form 1120"'},
    "us_s_corp": {"label": "US S corporation (search only)", "terms": '"S corporation" OR "S-Corp" OR "Form 1120-S"'},
}

DECISION_ROLES = {
    "signal_based": {"label": "Infer from the lead signal", "terms": ""},
    "hr": {"label": "HR / People leader", "terms": "HR human resources people director talent acquisition"},
    "vp_sales": {"label": "VP of Sales / Sales leader", "terms": "VP sales head of sales revenue sales director"},
    "dev_hiring_manager": {"label": "Development hiring manager", "terms": "engineering manager software development hiring manager technical recruiter"},
    "director": {"label": "Relevant functional director", "terms": "director department head"},
    "lead_coach": {"label": "Lead coach", "terms": "lead coach coaching director head coach"},
    "president": {"label": "President", "terms": "president company president"},
    "ceo": {"label": "CEO / Chief Executive Officer", "terms": "CEO chief executive officer"},
    "coo": {"label": "COO / Chief Operating Officer", "terms": "COO chief operating officer operations"},
    "cto": {"label": "CTO / Chief Technology Officer", "terms": "CTO chief technology officer engineering technology"},
    "founder": {"label": "Founder", "terms": "founder co-founder owner"},
}

# Signal phrases are research cues, not proof that an event occurred.
SIGNAL_EVENT_RULES = {
    "hiring": {"label": "Hiring or talent need", "patterns": (r"\bhir(?:e|ing|es|ed)\b", r"\brecruit(?:ing|ment|er)?\b", r"\bjob opening\b", r"\bopen roles?\b"), "roles": ("hr", "dev_hiring_manager", "director")},
    "funding": {"label": "Funding or financing", "patterns": (r"\bfundrais(?:e|ing)\b", r"\bfunding\b", r"\braised?\s+(?:\$|\w+\s+)?(?:seed|series\s+[a-f])\b", r"\bseries\s+[a-f]\b", r"\bventure capital\b"), "roles": ("ceo", "founder", "president")},
    "expansion": {"label": "Market or location expansion", "patterns": (r"\bexpand(?:ing|ed|s)?\b", r"\bnew location\b", r"\bopening (?:a |an )?(?:new )?(?:office|store|location)\b", r"\bentering (?:the )?\w+ market\b"), "roles": ("coo", "ceo", "director")},
    "product_launch": {"label": "Product or service launch", "patterns": (r"\blaunch(?:ed|es|ing)?\b", r"\bnew product\b", r"\bproduct release\b", r"\bnow available\b"), "roles": ("cto", "vp_sales", "director")},
    "leadership_change": {"label": "Leadership change", "patterns": (r"\bappointed\b", r"\bnamed (?:as|the)\b", r"\bjoins? as\b", r"\bpromoted to\b", r"\bsteps? down\b", r"\bnew (?:ceo|coo|cto|president|chief executive)\b"), "roles": ("ceo", "president", "coo", "director")},
    "technology_security": {"label": "Technology or security change", "patterns": (r"\bcyber ?security\b", r"\bdata breach\b", r"\bcloud migration\b", r"\btechnology stack\b", r"\btech stack\b", r"\bimplements? (?:a )?(?:new )?(?:erp|crm|platform)\b"), "roles": ("cto", "dev_hiring_manager", "director")},
    "revenue_growth": {"label": "Revenue or sales growth", "patterns": (r"\brevenue growth\b", r"\bsales growth\b", r"\brevenue increased\b", r"\bsales increased\b", r"\bcustomer growth\b"), "roles": ("vp_sales", "ceo", "director")},
    "operations": {"label": "Operations or fulfillment", "patterns": (r"\bsupply chain\b", r"\bfulfil?ment\b", r"\bwarehouse\b", r"\boperational efficiency\b", r"\boperations? expansion\b"), "roles": ("coo", "director")},
    "regulatory_compliance": {"label": "Regulatory or compliance", "patterns": (r"\bcompliance\b", r"\bregulat(?:ion|ory)\b", r"\bcertif(?:ication|ied)\b", r"\blicen[cs]e[sd]?\b", r"\bdata protection\b", r"\baudit\b"), "roles": ("director", "coo", "ceo")},
    "customer_trust": {"label": "Customer trust or review signal", "patterns": (r"\bcustomer reviews?\b", r"\bonline reviews?\b", r"\breputation\b", r"\bcustomer satisfaction\b", r"\bsupport complaints?\b", r"\brating[s]?\b"), "roles": ("vp_sales", "director", "ceo")},
    "franchise_growth": {"label": "Franchise or multi-unit growth", "patterns": (r"\bfranchis(?:e|es|ing|or|ee|ees)\b", r"\bmulti[- ]unit\b", r"\bmultiple locations\b"), "roles": ("founder", "ceo", "coo", "president")},
    "visibility_gap": {"label": "Local or answer-engine visibility gap", "patterns": (r"\bnot appearing in (?:the )?(?:map|local) results\b", r"\bmissing from (?:the )?(?:map|local) pack\b", r"\bgoogle business profile\b", r"\blocal citations?\b", r"\bnear me search\b", r"\bnot cited by (?:ai|answer engines?)\b"), "roles": ("founder", "ceo", "director")},
    "inquiry_gap": {"label": "Inquiry or booking friction", "patterns": (r"\bunanswered inquiries\b", r"\bslow response time\b", r"\bcontact form\b", r"\bno online booking\b", r"\bbooking link\b", r"\bappointment requests?\b", r"\bform submissions?\b"), "roles": ("coo", "director", "founder")},
    "missed_call_gap": {"label": "Missed-call or after-hours coverage cue", "patterns": (r"\bmissed calls?\b", r"\bwent to voicemail\b", r"\bafter[- ]hours calls?\b", r"\bunanswered calls?\b", r"\bno one answered\b", r"\bcall answering\b"), "roles": ("coo", "director", "founder")},
    "automation_gap": {"label": "Repeatable manual-work cue", "patterns": (r"\bmanual data entry\b", r"\brepetitive (?:admin|task|process|work)\b", r"\bpaper(?:work| forms?)\b", r"\bcopy(?:ing)? (?:data|information) between\b", r"\bmanual (?:intake|reporting|invoicing)\b"), "roles": ("coo", "director", "cto")},
    "commerce_flow_gap": {"label": "Ecommerce lifecycle-flow gap", "patterns": (r"\babandoned cart\b", r"\bcart recovery\b", r"\bbrowse abandonment\b", r"\bwin[- ]back (?:email|flow|campaign)\b", r"\bno welcome (?:email|flow|sequence)\b", r"\babandoned checkout\b"), "roles": ("vp_sales", "director", "founder")},
    "pipeline_data_gap": {"label": "B2B pipeline-data or routing cue", "patterns": (r"\bmanual lead routing\b", r"\bduplicate (?:crm )?(?:records|leads|accounts)\b", r"\bcrm migration\b", r"\bstale (?:crm )?(?:data|records|leads)\b", r"\bdata hygiene\b", r"\brevenue operations\b", r"\brevops\b"), "roles": ("vp_sales", "director", "cto")},
    "authority_content_gap": {"label": "Expert authority or content-cadence cue", "patterns": (r"\bthought leadership\b", r"\bcontent cadence\b", r"\bnew (?:cohort|programme|program)\b", r"\bconsultant\b", r"\bcoach(?:ing)? programme\b", r"\bexpert speaker\b"), "roles": ("founder", "ceo", "director")},
    "audience_monetization_gap": {"label": "Podcast audience or sponsor-readiness cue", "patterns": (r"\bpodcast\b", r"\bshow notes\b", r"\bpodcast clips?\b", r"\bsponsor(?:ship)? (?:page|readiness|media kit)\b", r"\bdownloads per episode\b", r"\bemail list\b"), "roles": ("founder", "president", "director")},
    "closer_demand": {"label": "High-ticket sales closer demand cue", "patterns": (r"\b(?:sales )?closers?\b", r"\bappointment setters?\b", r"\bcommission[- ]only closers?\b", r"\bhigh[- ]ticket sales team\b", r"\blooking for closers?\b"), "roles": ("vp_sales", "founder", "ceo")},
    "high_ticket_offer": {"label": "High-ticket offer activity cue", "patterns": (r"\bhigh[- ]ticket (?:offer|programme|program|coaching)\b", r"\bapplication call\b", r"\bbook a strategy call\b", r"\bclosing calls\b", r"\bpremium coaching programme\b"), "roles": ("founder", "ceo", "vp_sales")},
}


def assess_signal_events(text: str, *, subject: str, source: dict | None = None) -> list[dict]:
    """Map a text cue to event categories and role families without asserting it is verified."""
    import re
    source = source or {}
    content = str(text or "")
    events = []
    for key, rule in SIGNAL_EVENT_RULES.items():
        matched = [pattern for pattern in rule["patterns"] if re.search(pattern, content, re.IGNORECASE)]
        if matched:
            events.append({"category": key, "label": rule["label"], "subject": subject,
                           "matched_cues": matched, "suggested_roles": list(rule["roles"]),
                           "source_id": str(source.get("id", "")), "source_type": str(source.get("type") or source.get("source_type", "")),
                           "source_host": str(source.get("source_host", "")), "url": str(source.get("url", "")),
                           "publication_date": str(source.get("publication_date", "")),
                           "freshness_status": str(source.get("freshness_status", "undated")),
                           "evidence_status": "unverified research cue"})
    return events


def infer_decision_role(signal: str, selected: str = "signal_based") -> tuple[str, str]:
    """Choose a role from the lead signal; explicit user choice always takes precedence."""
    key = infer_decision_roles(signal, selected)[0]
    return key, DECISION_ROLES[key]["terms"]


def infer_decision_roles(signal: str, selected: str = "signal_based") -> list[str]:
    """Return multiple plausible role targets so signal-based research does not overfit one title."""
    if selected != "signal_based":
        return [selected]
    text = (signal or "").casefold()
    hiring = any(n in text for n in ("hiring", "recruit", "talent", "people", "human resources"))
    technical = any(n in text for n in ("developer", "software", "engineering", "technical", "tech stack", "security"))
    roles = []
    if hiring:
        roles.append("dev_hiring_manager" if technical else "hr")
        roles.append("hr" if technical else "director")
    if any(n in text for n in ("sales", "pipeline", "revenue", "quota")):
        roles.extend(("vp_sales", "ceo", "director"))
    if any(n in text for n in ("coach", "coaching", "athlete", "training")):
        roles.extend(("lead_coach", "director"))
    if technical:
        roles.extend(("cto", "director"))
    if any(n in text for n in ("operations", "operational", "fulfilment", "process")):
        roles.extend(("coo", "director"))
    if any(n in text for n in ("startup", "early stage", "founder", "owner-led")):
        roles.extend(("founder", "ceo", "president"))
    if any(n in text for n in ("enterprise", "board", "executive leadership")):
        roles.extend(("ceo", "president", "coo"))
    for event in assess_signal_events(signal, subject="company"):
        roles.extend(event["suggested_roles"])
    return list(dict.fromkeys(roles or ["director", "ceo", "founder"]))


def row_value(row: dict, *names: str) -> str:
    """Read common CSV header spellings (e.g. `Last Position`, `last_position`)."""
    normalized = {"".join(ch for ch in str(k).lower() if ch.isalnum()): v for k, v in row.items()}
    for name in names:
        value = normalized.get("".join(ch for ch in name.lower() if ch.isalnum()))
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def normalize_profiles(business: str = "any", decision_maker: str = "any", legal_form: str = "any") -> tuple[dict, dict, dict]:
    """Return the selected profiles or reject values outside the catalog."""
    try:
        return BUSINESS_PROFILES[business], DECISION_MAKER_PROFILES[decision_maker], LEGAL_FORM_PROFILES[legal_form]
    except KeyError as exc:
        raise ValueError("Choose a business profile, decision-maker path and legal-form search from the listed options.") from exc


def strategy_text(business: str, decision_maker: str, legal_form: str, decision_role: str = "signal_based") -> str:
    bp, dm, lf = normalize_profiles(business, decision_maker, legal_form)
    role = DECISION_ROLES[decision_role]
    return f"Business target: {bp['label']}; decision-maker path: {dm['label']}; role target: {role['label']}; legal-form search: {lf['label']}. These are search preferences, not verified classifications."
