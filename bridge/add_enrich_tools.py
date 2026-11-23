"""One-off generator: adds the lead enrichment tools to catalog.json. Safe to re-run (replaces the dse.enrich* entries)."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]

ENG_OPT = {"name": "engine", "label": "Also save an import-ready copy in this engine (optional)", "type": "choice", "required": False, "choices_from": "engines", "choices": []}
PROV = {"name": "provider", "label": "Paid provider with YOUR own key (optional, empty = free only)", "type": "choice", "required": False, "choices_from": "providers", "choices": []}


def tool(label, help_, args, fields, tmo):
    return {"label": label, "group": "Grow", "help": help_, "script": "dse.py", "args": args, "fields": fields, "timeout_min": tmo, "outputs": ["my-lists/*-enriched-*.csv", "my-lists/*-enriched-*.md"]}


T["dse.enrich"] = tool("Lead enrichment: find emails, owners and phones", "Takes a list of companies (a CSV with a website or domain column, like a Clay, Apollo or HubSpot export) and reads each company's own public website, politely, for emails, the owner's name, phone, contact form, booking tool, socials and what it is built with. Every finding names the page it came from. It scores each lead from rules you can read and keeps every column you gave it. Free: no paid service is used unless you pick a provider with your own key. The key is set on your PC, never here.",
                       [{"lit": "enrich"}, {"field": "csv"}, {"opt": "--icp", "field": "icp"}, {"opt": "--engine", "field": "engine"}, {"opt": "--max", "field": "max"}, {"flag": "--fast", "field": "fast"},
                        {"opt": "--provider", "field": "provider"}, {"opt": "--waterfall-config", "field": "waterfall_config"}, {"opt": "--budget", "field": "budget"}, {"opt": "--max-provider-spend", "field": "max_provider_spend"}, {"flag": "--allow-unknown-provider-cost", "field": "allow_unknown_provider_cost"}, {"flag": "--dry-run", "field": "dry_run"}],
                       [{"name": "csv", "label": "List", "type": "file", "required": True, "glob": "my-lists/*.csv", "exclude": "enriched"},
                        {"name": "icp", "label": "Words you want to find on their site (optional, comma separated)", "type": "text", "required": False, "max": 120, "pattern": r"^[A-Za-z0-9][A-Za-z0-9 ,/&'-]{0,119}$"},
                        ENG_OPT, {"name": "max", "label": "Most leads to look at in this run", "type": "int", "min": 1, "max": 2000, "default": 100},
                        {"name": "fast", "label": "Fast (skip the hidden browser: quicker, misses sites drawn by JavaScript)", "type": "bool", "default": False},
                        PROV, {"name": "waterfall_config", "label": "Ordered email waterfall config (optional; replaces single provider)", "type": "file", "required": False, "glob": "enrich-waterfalls/*.json"},
                        {"name": "budget", "label": "Override maximum provider calls (optional)", "type": "int", "min": 0, "max": 5000},
                        {"name": "max_provider_spend", "label": "Approved ceiling for known provider charges (required for live paid calls)", "type": "float", "required": False, "min": 0, "max": 10000000},
                        {"name": "allow_unknown_provider_cost", "label": "Allow providers with unknown prices (charges can exceed the numeric estimate)", "type": "bool", "default": False},
                        {"name": "dry_run", "label": "Dry run (no optional provider requests; show projected calls)", "type": "bool", "default": False}], 180)
T["dse.enrich"].update({"category": "enrich", "source": "First-party company websites; optional configured providers",
                        "cost": "Website checks run on your PC. Live optional-provider calls require an approved ceiling for known prices and a separate acknowledgment for unknown prices; the runtime stops known-price requests before they exceed the ceiling. Estimates are not invoices.",
                        "outputs_summary": ["Website-sourced contact and business fields", "Shared per-field provenance, identity, freshness and verification records", "Per-rung attempts, cache hits, accepted/rejected candidates and errors", "Dry-run projected calls; configured price estimate only when supplied, otherwise unknown", "Enriched CSV and report"]})
T["dse.enrich_signals"] = {
    "label": "Lead signals: research and draft outreach",
    "group": "Grow",
    "help": "Researches public company, product and news results for Herald. The selected Engine automatically supplies its path's research focus; without one, choose a path. Each path prioritizes its own proof signals, likely buyer roles and commercial model, and labels findings as priority, supporting or general. These are research directions, not verified pains or budgets. Set a per-lead search-query cap and a minimum identity-match score; every query rung records returned, filtered and retained evidence in the shared field-result metadata. The score is heuristic, not a probability. Ledgers, grids and workflows retain path metadata for later review and automation. DuckDuckGo is default; Brave requires your local key and can incur charges. A local Ollama model may draft evidence-based email, never send it. Public social signals remain in Presence.",
    "script": "dse.py", "args": [{"lit": "signals"}, {"field": "csv"}, {"opt": "--engine", "field": "engine"}, {"opt": "--path", "field": "path"}, {"opt": "--max", "field": "max"}, {"opt": "--search-budget", "field": "search_budget"}, {"opt": "--brave-cost-per-1000", "field": "brave_cost_per_1000"}, {"opt": "--brave-max-spend", "field": "brave_max_spend"}, {"opt": "--minimum-identity-score", "field": "minimum_identity_score"}, {"opt": "--profile", "field": "profile"}, {"opt": "--decision-maker", "field": "decision_maker"}, {"opt": "--decision-role", "field": "decision_role"}, {"opt": "--custom-role", "field": "custom_role"}, {"opt": "--legal-form", "field": "legal_form"}, {"opt": "--search-provider", "field": "search_provider"}, {"flag": "--no-ai", "field": "no_ai"}],
    "fields": [
        {"name": "csv", "label": "Lead CSV", "type": "file", "required": True, "glob": "my-lists/*.csv", "exclude": "researched"},
        {"name": "engine", "label": "Also save a copy to this engine (optional)", "type": "choice", "required": False, "choices_from": "engines", "choices": []},
        {"name": "path", "label": "Path focus (the selected Engine sets this automatically)", "type": "choice", "required": False, "default": "any", "choices": [
            {"value": "any", "label": "General / use Engine path"}, {"value": "smb", "label": "SMB Optimisation"}, {"value": "search", "label": "Search & AI Visibility"},
            {"value": "voiceai", "label": "AI Voice Receptionist Systems"}, {"value": "automation", "label": "AI Automation Engineering"}, {"value": "revenue", "label": "Revenue Recovery"},
            {"value": "gtm", "label": "Go-to-Market Engineering"}, {"value": "authority", "label": "The Authority Engine"}, {"value": "broadcast", "label": "The Broadcast Engine"}, {"value": "ascent", "label": "The Ascent"}]},
        {"name": "max", "label": "Most leads to research in this stage", "type": "int", "min": 1, "max": 50, "default": 25},
        {"name": "search_budget", "label": "Maximum search queries per lead (in listed priority order)", "type": "int", "min": 0, "max": 30, "default": 12},
        {"name": "brave_cost_per_1000", "label": "USD cost per 1,000 Brave requests (required with Brave searches)", "type": "float", "required": False, "min": 0, "max": 100000},
        {"name": "brave_max_spend", "label": "Maximum Brave spend to approve for this run in USD (required if Brave searches may run)", "type": "float", "required": False, "min": 0, "max": 100000},
        {"name": "minimum_identity_score", "label": "Minimum identity match score (heuristic 0 to 1, not a probability)", "type": "float", "min": 0, "max": 1, "default": 0},
        {"name": "profile", "label": "Business type to prioritize (search hint, not a classification)", "type": "choice", "required": False, "default": "any", "choices": [
            {"value": "any", "label": "Any business"}, {"value": "franchise_group", "label": "Franchise or multi-location group"}, {"value": "local_smb", "label": "Local or owner-led SMB"},
            {"value": "saas", "label": "SaaS or software company"}, {"value": "online_store", "label": "Online store or ecommerce business"}, {"value": "enterprise", "label": "Mid-market or enterprise company"}]},
        {"name": "decision_maker", "label": "Decision-maker path to prioritize", "type": "choice", "required": False, "default": "any", "choices": [
            {"value": "any", "label": "Any decision maker"}, {"value": "owner_compact", "label": "Owner, founder or compact team"}, {"value": "franchise_operator", "label": "Franchise operator and parent group"},
            {"value": "functional_leader", "label": "Functional leader or department head"}, {"value": "specialist_director", "label": "Specialised director or executive"}]},
        {"name": "decision_role", "label": "Role to find (signal-based discovers several; optional to target one)", "type": "choice", "required": False, "default": "signal_based", "choices": [
            {"value": "signal_based", "label": "Infer several roles from the lead signal"}, {"value": "hr", "label": "HR / People leader"}, {"value": "vp_sales", "label": "VP of Sales / Sales leader"},
            {"value": "dev_hiring_manager", "label": "Development hiring manager"}, {"value": "director", "label": "Relevant functional director"}, {"value": "lead_coach", "label": "Lead coach"},
            {"value": "president", "label": "President"}, {"value": "ceo", "label": "CEO"}, {"value": "coo", "label": "COO"}, {"value": "cto", "label": "CTO"}, {"value": "founder", "label": "Founder"}]},
        {"name": "custom_role", "label": "Additional or custom role title (optional)", "type": "text", "required": False, "max": 80},
        {"name": "search_provider", "label": "Public search source (Brave requires PC key; API use may be chargeable)", "type": "choice", "required": False, "default": "duckduckgo", "choices": [
            {"value": "duckduckgo", "label": "DuckDuckGo (default)"}, {"value": "brave", "label": "Brave Search API (my PC-local key)"}]},
        {"name": "legal_form", "label": "US legal-form search hint only (not verified)", "type": "choice", "required": False, "default": "any", "choices": [
            {"value": "any", "label": "Any or unknown legal form"}, {"value": "us_c_corp", "label": "US C corporation"}, {"value": "us_s_corp", "label": "US S corporation"}]},
        {"name": "no_ai", "label": "Only collect signals (do not draft with local AI)", "type": "bool", "default": False}
    ],
    "timeout_min": 240, "outputs": ["my-lists/*-researched-*.csv", "my-lists/*-researched-*.md"]
}
T["dse.enrich_signals"].update({"category": "signal", "source": "Public web search; local Ollama is optional",
                                "cost": "DuckDuckGo mode has no search-provider fee. Brave requires the user's own API key, a declared price per 1,000 requests, and an approved maximum spend whenever requests may run. Requests are journaled locally; estimates do not confirm provider billing. Ollama runs locally.",
                                "outputs_summary": ["Sourced company/person signals", "Shared field-result records with evidence, identity cues and per-query waterfall metrics", "Configurable per-lead query budget and minimum identity score", "Run requests are blocked if the estimated ceiling exceeds the approved maximum", "Local provider-usage journal entry for each Brave API attempt", "Path-fit tags", "Research CSV and report"],
                                "path_keys": ["smb", "search", "voiceai", "automation", "revenue", "gtm", "authority", "broadcast", "ascent"]})
T["dse.enrich_site"] = tool("Lead enrichment: look at one website", "Reads one company website and shows what a lead list would get: emails, owner, phone, form, booking tool, score and why. Nothing is saved.",
                            [{"lit": "enrich"}, {"opt": "--site", "field": "site"}, {"opt": "--icp", "field": "icp"}, {"flag": "--fast", "field": "fast"}],
                            [{"name": "site", "label": "Website", "type": "url", "required": True},
                             {"name": "icp", "label": "Words you want to find (optional)", "type": "text", "required": False, "max": 120, "pattern": r"^[A-Za-z0-9][A-Za-z0-9 ,/&'-]{0,119}$"},
                             {"name": "fast", "label": "Fast (skip the hidden browser)", "type": "bool", "default": False}], 5)
T["dse.enrich_site"]["outputs"] = []
T["dse.enrich_site"].update({"category": "enrich", "source": "The company website you supply", "cost": "PC-run website preview; no paid provider by default.", "outputs_summary": ["One-site preview", "Nothing is saved"]})
T["dse.enrich_providers"] = tool("Lead enrichment: which paid providers are set up", "Lists the optional paid providers on this PC and whether their key is present (the key is never shown). To add one, run at your PC: python dse.py enrich --add-provider hunter, then set your own key in a Windows user variable.",
                                 [{"lit": "enrich"}, {"flag": "--providers", "field": "go"}], [{"name": "go", "label": "Show", "type": "bool", "default": True}], 1)
T["dse.enrich_providers"]["outputs"] = []
T["dse.enrich_providers"].update({"category": "source", "source": "Provider settings stored on this PC; API keys are never shown",
                                  "cost": "Status check only; does not perform a paid lookup.",
                                  "outputs_summary": ["Configured provider names and readiness"]})
T["dse.enrich_catalog"] = tool("Lead enrichment: paid-provider catalog", "Shows enrichment and signal providers that are ready, candidates, retired, or restricted, with their official pricing and documentation links. This is information only: it does not enable a provider, make a paid request, or claim current prices.",
                                [{"lit": "enrich"}, {"flag": "--catalog", "field": "go"}], [{"name": "go", "label": "Show provider catalog", "type": "bool", "default": True}], 1)
T["dse.enrich_catalog"]["outputs"] = []
T["dse.enrich_catalog"].update({"category": "source", "source": "Local reviewed provider catalog with official links",
                                "cost": "Catalog lookup only; makes no provider request.",
                                "outputs_summary": ["Provider capabilities and integration state", "Official pricing, API and policy links", "Retired or restricted provider warnings"]})
T["dse.enrich_usage"] = tool("Lead enrichment: provider usage and cost estimates", "Shows this PC's recent optional enrichment-provider API-call records, configured cost estimates and calls with unknown cost. It stores no lead names or domains and does not show vendor invoice totals.",
                              [{"lit": "enrich"}, {"flag": "--usage", "field": "go"}, {"opt": "--usage-days", "field": "days"}],
                              [{"name": "go", "label": "Show usage", "type": "bool", "default": True},
                               {"name": "days", "label": "History window in days", "type": "int", "min": 1, "max": 3650, "default": 30}], 1)
T["dse.enrich_usage"]["outputs"] = []
T["dse.enrich_usage"].update({"category": "source", "source": "Local provider-call journal on this PC",
                              "cost": "Read-only usage summary; no provider call or payment is made.",
                              "outputs_summary": ["Provider requests and outcomes", "Configured monetary estimates by currency", "Requests where monetary cost remains unknown", "Clear distinction from vendor invoices"]})
T["dse.enrich_spend_preview"] = tool("Lead enrichment: preview provider spend", "Calculates a conservative estimate from the provider prices and call caps in a local waterfall config. It does not open a lead CSV, read lead data, visit websites, call providers, or write files. Unknown provider prices are listed separately and are not covered by the numeric estimate.",
    [{"lit": "enrich"}, {"flag": "--spend-preview", "field": "go"}, {"opt": "--waterfall-config", "field": "waterfall_config"}, {"opt": "--provider", "field": "provider"}, {"opt": "--budget", "field": "budget"}, {"opt": "--max", "field": "leads"}],
    [{"name": "go", "label": "Preview only", "type": "bool", "default": True},
     {"name": "waterfall_config", "label": "Local provider waterfall JSON (optional if using one provider)", "type": "file", "required": False, "glob": "enrich-waterfalls/*.json"},
     {"name": "provider", "label": "One configured provider (optional; use instead of a waterfall file)", "type": "choice", "required": False, "choices_from": "providers", "choices": []},
     {"name": "budget", "label": "Override maximum provider calls (optional)", "type": "int", "min": 0, "max": 5000},
     {"name": "leads", "label": "Lead count to estimate for", "type": "int", "min": 1, "max": 2000, "default": 100}], 1)
T["dse.enrich_spend_preview"]["outputs"] = []
T["dse.enrich_spend_preview"].update({"category": "source", "source": "Local waterfall provider price and call-cap configuration",
    "cost": "Read-only local estimate; no lead data or provider requests.",
    "outputs_summary": ["Maximum possible calls by field", "Conservative known-price estimate and currency", "Unknown-price providers and separate acknowledgment requirement", "Not a vendor invoice"]})
if T.get("dse.presence_signals"):
    T["dse.presence_signals"].update({"category": "signal", "source": "Public professional/business social search",
                                      "cost": "PC-run public search; no paid data provider is selected by this tool.",
                                      "outputs_summary": ["Public profile/post links", "Shared field-result records with identity and freshness", "New, changed and not-returned source comparison", "Presence signals CSV"],
                                      "path_keys": ["smb", "search", "voiceai", "automation", "revenue", "authority", "broadcast", "ascent"]})

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len([k for k in T if k.startswith("dse.enrich")]), "enrich tools,", len(T), "in all")
