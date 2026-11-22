"""Path-specific prospecting guidance for the nine active Citadel Engines.

These categories prioritize research. They do not prove that a business has a problem or budget.
"""

PATH_SIGNAL_PROFILES = {
    "any": {"label": "General lead research", "method": "Use the supplied business/person signals and general public evidence.",
            "pain": "No path-specific service or buyer was selected.", "buyer": "Infer a relevant role from the lead's evidence.",
            "revenue_model": "No path-specific monetization assumption.", "proof_metrics": [], "query_terms": "news hiring product launch reviews operations", "roles": ("director", "ceo", "founder"), "priority": (), "supporting": ()},
    "smb": {"label": "SMB Optimisation", "method": "Choose one local niche/city and a review or inquiry door; audit the gap directly.",
            "pain": "Review reputation or inquiry/booking friction for a local service business.", "buyer": "Owner/founder, office manager, or operations lead.",
            "revenue_model": "Start with one system, then upsell the other and bundle; report agreed monthly outcomes.", "proof_metrics": ["review volume and response", "inquiry response and bookings"],
            "query_terms": "Google reviews rating review response appointment booking contact form unanswered inquiry local service multiple locations", "roles": ("founder", "ceo", "coo", "director"),
            "priority": ("customer_trust", "inquiry_gap", "visibility_gap"), "supporting": ("franchise_growth", "expansion", "hiring")},
    "search": {"label": "Search & AI Visibility", "method": "Run a dated Near-Me and AI-answer check; inspect listings, pages, reviews and citations.",
            "pain": "A local firm is hard to find or represented inconsistently in search/maps/AI answers.", "buyer": "Owner/founder or marketing lead.",
            "revenue_model": "Monthly visibility improvements and reporting, grounded in measured search/call evidence.", "proof_metrics": ["dated map/AI answer samples", "Search Console clicks", "calls"],
            "query_terms": "Google Business Profile local map rankings near me local citations NAP service area city pages local SEO AI answers reviews", "roles": ("founder", "ceo", "director", "vp_sales"),
            "priority": ("visibility_gap", "customer_trust"), "supporting": ("expansion", "leadership_change", "product_launch")},
    "voiceai": {"label": "AI Voice Receptionist Systems", "method": "Test the public line honestly and check after-hours answering, booking and text options.",
            "pain": "Phone-led businesses may miss calls or lack a usable after-hours booking path.", "buyer": "Owner/founder, office manager, or operations lead.",
            "revenue_model": "Demonstrate and install the system; sustain value through support and monthly call/booking reporting.", "proof_metrics": ["observed call test", "calls answered", "bookings"],
            "query_terms": "missed calls voicemail after hours call answering receptionist hiring booking phone appointments", "roles": ("founder", "ceo", "coo", "director"),
            "priority": ("missed_call_gap", "inquiry_gap"), "supporting": ("hiring", "expansion", "customer_trust")},
    "automation": {"label": "AI Automation Engineering", "method": "Identify a repeated manual task, quantify its hours, then show a labeled demo and human approval.",
            "pain": "Growing teams spend time on repeatable intake, support, invoicing, forms or reporting.", "buyer": "Owner/founder or operations lead.",
            "revenue_model": "Paid workflow build plus a monthly care retainer.", "proof_metrics": ["hours saved", "workflow reliability", "approved handoffs"],
            "query_terms": "manual data entry intake forms administrative assistant customer support operations coordinator repetitive workflow invoicing reporting", "roles": ("coo", "founder", "director", "cto"),
            "priority": ("automation_gap", "inquiry_gap"), "supporting": ("hiring", "expansion", "technology_security")},
    "revenue": {"label": "Revenue Recovery", "method": "Manually audit welcome, browse, cart and win-back flows with a genuine test identity.",
            "pain": "An active online shop may be missing lifecycle messages and recoverable purchases.", "buyer": "Owner/founder, ecommerce lead or lifecycle-marketing leader.",
            "revenue_model": "Price against measured recovered revenue and report by flow monthly; treat estimates as scenarios.", "proof_metrics": ["flow coverage", "recovered revenue by flow", "repeat purchases"],
            "query_terms": "online store ecommerce abandoned cart browse abandonment welcome email win back lifecycle marketing product launch Meta ads", "roles": ("founder", "ceo", "vp_sales", "director"),
            "priority": ("commerce_flow_gap",), "supporting": ("product_launch", "revenue_growth", "customer_trust")},
    "gtm": {"label": "Go-to-Market Engineering", "method": "Review an authorized account export and observable sales motion; audit enrichment, routing and lifecycle.",
            "pain": "B2B sales teams waste effort on stale data, manual routing and CRM hygiene.", "buyer": "RevOps, sales/growth leader, or founder in a compact team.",
            "revenue_model": "Market-rate implementation project, with optional ongoing data/workflow support.", "proof_metrics": ["data quality", "routing coverage", "pipeline created"],
            "query_terms": "B2B SaaS revenue operations RevOps CRM migration lead routing sales hiring funding demo pipeline data enrichment", "roles": ("vp_sales", "director", "founder", "ceo"),
            "priority": ("pipeline_data_gap",), "supporting": ("hiring", "funding", "expansion", "revenue_growth", "technology_security")},
    "authority": {"label": "The Authority Engine", "method": "Review the expert's public positioning, content cadence and lead path; label samples and obtain permission.",
            "pain": "A real expert offer is not supported by distinctive authority content or a clear enquiry path.", "buyer": "The coach, consultant, advisor or expert who owns the offer.",
            "revenue_model": "Fewer, larger authority/content and lead-engine retainers.", "proof_metrics": ["qualified enquiries", "booked calls", "publishing consistency"],
            "query_terms": "coach consultant advisor new programme cohort launch conference speaker book expert LinkedIn content thought leadership", "roles": ("founder", "ceo", "director"),
            "priority": ("authority_content_gap",), "supporting": ("product_launch", "funding", "leadership_change", "revenue_growth")},
    "broadcast": {"label": "The Broadcast Engine", "method": "Listen to an episode and inspect clips, show notes, distribution, audience capture and sponsor readiness.",
            "pain": "An active show lacks a repeatable distribution, audience capture or sponsor system.", "buyer": "Host, producer, network or partnerships lead.",
            "revenue_model": "Recurring production/distribution and sponsor-readiness support tied to show/audience outcomes.", "proof_metrics": ["episode cadence", "downloads and owned audience", "sponsor conversations"],
            "query_terms": "podcast new episodes show notes clips sponsors sponsorship media kit newsletter downloads podcast producer hiring", "roles": ("founder", "president", "director", "vp_sales"),
            "priority": ("audience_monetization_gap",), "supporting": ("hiring", "expansion", "revenue_growth", "product_launch")},
    "ascent": {"label": "The Ascent", "method": "Vet a high-ticket offer, funnel, lead flow, terms and hiring evidence before approaching as a closer partner.",
            "pain": "An active high-ticket seller may need qualified closers, but the offer must pass ethical and commercial vetting.", "buyer": "Offer owner, sales leader or partner manager; this path recruits a partner, not a service client.",
            "revenue_model": "Commission-only income under written terms, supported by tracked calls/results and more than one vetted offer.", "proof_metrics": ["offer and terms vetted", "calls handled", "commission received"],
            "query_terms": "high ticket offer closer hiring appointment setter sales application commission coaching program sales team", "roles": ("founder", "ceo", "president", "vp_sales"),
            "priority": ("closer_demand", "high_ticket_offer"), "supporting": ("hiring", "product_launch", "revenue_growth")},
}


def profile(path_key: str = "any") -> dict:
    """Return the path guide or general targeting context for unknown/custom engines."""
    return PATH_SIGNAL_PROFILES.get(str(path_key or "any").strip().lower(), PATH_SIGNAL_PROFILES["any"])


def known_path(path_key: str = "") -> str:
    key = str(path_key or "").strip().lower()
    return key if key in PATH_SIGNAL_PROFILES and key != "any" else ""
