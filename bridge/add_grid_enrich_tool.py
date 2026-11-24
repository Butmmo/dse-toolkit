"""One-off generator: live enrichment action for Ledger grid rows."""
import json
from pathlib import Path

path = Path(__file__).resolve().parent / "catalog.json"
catalog = json.loads(path.read_text(encoding="utf-8"))
tools = catalog["tools"]
tools["dse.grid_enrich"] = {
    "label": "Ledgers: enrich grid rows live", "group": "Grow",
    "help": "Runs lead enrichment directly on rows already in this Ledger grid. Choose website enrichment, technology and website-gap checks, Herald company/person signals and draft, Presence public social signals, or UK director lookup through the official Companies House register. Tech checks read each row's website and respect robots.txt. For director lookup, the grid needs a business-name column; city and address columns improve matching. The PC reads grid rows, runs the selected lane, then creates or reuses result columns and writes results back into those rows. Existing non-empty output cells stay as they are unless Replace existing values is checked. Original row order and input cells are preserved. No new leads are added and nothing is sent to Herald or posted.",
    "script": "dse.py", "args": [
        {"lit": "grid"}, {"lit": "enrich"}, {"field": "grid"}, {"opt": "--lane", "field": "lane"},
        {"opt": "--company-column", "field": "company_column"}, {"opt": "--city-column", "field": "city_column"},
        {"flag": "--fast-tech", "field": "fast_tech"},
        {"opt": "--engine", "field": "engine"}, {"opt": "--limit", "field": "limit"},
        {"opt": "--output-detail", "field": "output_detail"}, {"flag": "--overwrite", "field": "overwrite"},
        {"opt": "--icp", "field": "icp"}, {"opt": "--waterfall-config", "field": "waterfall_config"},
        {"opt": "--max-provider-spend", "field": "max_provider_spend"}, {"flag": "--allow-unknown-provider-cost", "field": "allow_unknown_provider_cost"},
        {"flag": "--dry-run-providers", "field": "dry_run_providers"}, {"opt": "--path", "field": "path"},
        {"opt": "--profile", "field": "profile"}, {"opt": "--decision-maker", "field": "decision_maker"},
        {"opt": "--legal-form", "field": "legal_form"}, {"opt": "--decision-role", "field": "decision_role"},
        {"opt": "--custom-role", "field": "custom_role"}, {"opt": "--search-provider", "field": "search_provider"},
        {"opt": "--search-budget", "field": "search_budget"}, {"opt": "--brave-cost-per-1000", "field": "brave_cost_per_1000"}, {"opt": "--brave-max-spend", "field": "brave_max_spend"}, {"opt": "--minimum-identity-score", "field": "minimum_identity_score"},
        {"flag": "--no-ai", "field": "no_ai"}],
    "fields": [
        {"name": "grid", "label": "Grid to enrich", "type": "text", "required": True, "max": 120},
        {"name": "lane", "label": "What to research on these rows", "type": "choice", "required": True, "default": "website", "choices": [
            {"value": "website", "label": "Website enrichment: contacts and company details"},
            {"value": "tech", "label": "Website technology and gaps"},
            {"value": "herald", "label": "Herald: company/person signals and email draft"},
            {"value": "presence", "label": "Presence: public professional/social signals"},
            {"value": "directors", "label": "UK: Companies House director lookup"}]},
        {"name": "company_column", "label": "Business-name column for director lookup (optional; auto-detects Company, Business or Name)", "type": "text", "required": False, "max": 60},
        {"name": "city_column", "label": "City or town column for director matching (optional; auto-detects City or Town)", "type": "text", "required": False, "max": 60},
        {"name": "fast_tech", "label": "Skip the hidden browser fallback for technology scans", "type": "bool", "default": False},
        {"name": "engine", "label": "Engine for path guidance (optional; preset from this Ledger)", "type": "text", "required": False, "max": 80},
        {"name": "limit", "label": "Most grid rows to enrich in this run", "type": "int", "required": True, "min": 1, "max": 500, "default": 25},
        {"name": "output_detail", "label": "Result columns", "type": "choice", "required": True, "default": "essentials", "choices": [
            {"value": "essentials", "label": "Essential contact and signal fields"}, {"value": "full", "label": "All available fields, including evidence and metadata"}]},
        {"name": "overwrite", "label": "Replace existing result values", "type": "bool", "default": False},
        {"name": "icp", "label": "Website words to match (optional)", "type": "text", "required": False, "max": 120},
        {"name": "waterfall_config", "label": "Optional provider waterfall JSON from this PC", "type": "file", "required": False, "glob": "enrich-waterfalls/*.json"},
        {"name": "max_provider_spend", "label": "Approved ceiling for known configured-provider charges (required for live paid calls)", "type": "float", "required": False, "min": 0, "max": 10000000},
        {"name": "allow_unknown_provider_cost", "label": "Allow configured providers with unknown prices (charges can exceed numeric estimate)", "type": "bool", "default": False},
        {"name": "dry_run_providers", "label": "Project provider calls without making them", "type": "bool", "default": False},
        {"name": "path", "label": "Herald path focus (General uses the selected Engine)", "type": "choice", "required": False, "default": "any", "choices": [
            {"value": "any", "label": "General / use Engine path"}, {"value": "smb", "label": "SMB Optimization"}, {"value": "search", "label": "Search and AI visibility"},
            {"value": "voiceai", "label": "AI Voice Receptionist"}, {"value": "automation", "label": "AI Automation Engineering"}, {"value": "revenue", "label": "Revenue Recovery"},
            {"value": "gtm", "label": "Go-to-Market Engineering"}, {"value": "authority", "label": "The Authority Engine"}, {"value": "broadcast", "label": "The Broadcast Engine"}, {"value": "ascent", "label": "The Ascent"}]},
        {"name": "profile", "label": "Herald business profile search hint", "type": "choice", "required": False, "default": "any", "choices": [
            {"value": "any", "label": "Any business"}, {"value": "franchise_group", "label": "Franchise or multi-location group"}, {"value": "local_smb", "label": "Local or owner-led SMB"},
            {"value": "saas", "label": "SaaS or software"}, {"value": "online_store", "label": "Online store"}, {"value": "enterprise", "label": "Mid-market or enterprise"}]},
        {"name": "decision_maker", "label": "Herald decision-maker path", "type": "choice", "required": False, "default": "any", "choices": [
            {"value": "any", "label": "Any"}, {"value": "owner_compact", "label": "Owner or compact team"}, {"value": "franchise_operator", "label": "Franchise operator"},
            {"value": "functional_leader", "label": "Functional leader"}, {"value": "specialist_director", "label": "Specialist director"}]},
        {"name": "legal_form", "label": "US legal form search hint", "type": "choice", "required": False, "default": "any", "choices": [
            {"value": "any", "label": "Any / unknown"}, {"value": "us_c_corp", "label": "C corporation"}, {"value": "us_s_corp", "label": "S corporation"}]},
        {"name": "decision_role", "label": "Herald role (signal-based infers several)", "type": "choice", "required": False, "default": "signal_based", "choices": [
            {"value": "signal_based", "label": "Infer from signals"}, {"value": "hr", "label": "HR / People"}, {"value": "vp_sales", "label": "VP Sales"}, {"value": "dev_hiring_manager", "label": "Development hiring manager"},
            {"value": "director", "label": "Director"}, {"value": "lead_coach", "label": "Lead coach"}, {"value": "president", "label": "President"}, {"value": "ceo", "label": "CEO"}, {"value": "coo", "label": "COO"}, {"value": "cto", "label": "CTO"}, {"value": "founder", "label": "Founder"}]},
        {"name": "custom_role", "label": "Additional role title (optional)", "type": "text", "required": False, "max": 80},
        {"name": "search_provider", "label": "Herald search provider", "type": "choice", "required": False, "default": "duckduckgo", "choices": [
            {"value": "duckduckgo", "label": "DuckDuckGo"}, {"value": "brave", "label": "Brave API (PC key; may charge)"}]},
        {"name": "search_budget", "label": "Public search queries per row", "type": "int", "min": 0, "max": 30, "default": 12},
        {"name": "brave_cost_per_1000", "label": "USD cost per 1,000 Brave requests (optional; Herald + Brave estimates only)", "type": "float", "required": False, "min": 0, "max": 100000},
        {"name": "brave_max_spend", "label": "Maximum Brave spend to approve for this run in USD (required if Brave searches may run)", "type": "float", "required": False, "min": 0, "max": 100000},
        {"name": "minimum_identity_score", "label": "Minimum identity match score (heuristic 0–1)", "type": "float", "min": 0, "max": 1, "default": 0},
        {"name": "no_ai", "label": "Only collect evidence (do not draft with local AI)", "type": "bool", "default": False}
    ],
    "timeout_min": 240, "outputs": [], "category": "enrich", "source": "The selected Ledger grid and the public sources of the chosen lane",
    "cost": "Website reads and local model use run on this PC. Optional providers and Brave use the user's own API keys/allowances. Brave grid runs require a declared rate and user-approved maximum when searches may run; the estimate is checked before work and the request cap spans saved batches. Companies House uses the user's own free API key, stays on this PC and is paced to the service's documented allowance. Estimates are not provider invoices.",
    "outputs_summary": ["Enriches existing grid rows in place", "Creates/reuses columns for the selected output fields", "Preserves original row inputs; existing result cells are kept unless replace is selected", "Website, technology, Herald, Presence and Companies House director lanes"]
}
path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("grid enrich tool added; tools:", len(tools))
