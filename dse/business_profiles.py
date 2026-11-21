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
