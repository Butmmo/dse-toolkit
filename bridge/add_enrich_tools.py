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
                        {"opt": "--provider", "field": "provider"}, {"opt": "--budget", "field": "budget"}],
                       [{"name": "csv", "label": "List", "type": "file", "required": True, "glob": "my-lists/*.csv", "exclude": "enriched"},
                        {"name": "icp", "label": "Words you want to find on their site (optional, comma separated)", "type": "text", "required": False, "max": 120, "pattern": r"^[A-Za-z0-9][A-Za-z0-9 ,/&'-]{0,119}$"},
                        ENG_OPT, {"name": "max", "label": "Most leads to look at in this run", "type": "int", "min": 1, "max": 2000, "default": 100},
                        {"name": "fast", "label": "Fast (skip the hidden browser: quicker, misses sites drawn by JavaScript)", "type": "bool", "default": False},
                        PROV, {"name": "budget", "label": "Most paid lookups (only with a provider)", "type": "int", "min": 0, "max": 5000, "default": 25}], 180)
T["dse.enrich_signals"] = {
    "label": "Lead signals: research and draft outreach",
    "group": "Grow",
    "help": "Researches public company, product and news results for Herald. The selected Engine automatically supplies its path's research focus; without one, choose a path. Each path prioritizes its own proof signals, likely buyer roles and commercial model, and labels findings as priority, supporting or general. These are research directions, not verified pains or budgets. Ledgers, grids and workflows retain path metadata for later review and automation. Choose a business type and role path to refine the search. DuckDuckGo is default; Brave requires your local key and can incur charges. A local Ollama model may draft evidence-based email, never send it. Public social signals remain in Presence.",
    "script": "dse.py", "args": [{"lit": "signals"}, {"field": "csv"}, {"opt": "--engine", "field": "engine"}, {"opt": "--path", "field": "path"}, {"opt": "--max", "field": "max"}, {"opt": "--profile", "field": "profile"}, {"opt": "--decision-maker", "field": "decision_maker"}, {"opt": "--decision-role", "field": "decision_role"}, {"opt": "--custom-role", "field": "custom_role"}, {"opt": "--legal-form", "field": "legal_form"}, {"opt": "--search-provider", "field": "search_provider"}, {"flag": "--no-ai", "field": "no_ai"}],
    "fields": [
        {"name": "csv", "label": "Lead CSV", "type": "file", "required": True, "glob": "my-lists/*.csv", "exclude": "researched"},
        {"name": "engine", "label": "Also save a copy to this engine (optional)", "type": "choice", "required": False, "choices_from": "engines", "choices": []},
        {"name": "path", "label": "Path focus (the selected Engine sets this automatically)", "type": "choice", "required": False, "default": "any", "choices": [
            {"value": "any", "label": "General / use Engine path"}, {"value": "smb", "label": "SMB Optimisation"}, {"value": "search", "label": "Search & AI Visibility"},
            {"value": "voiceai", "label": "AI Voice Receptionist Systems"}, {"value": "automation", "label": "AI Automation Engineering"}, {"value": "revenue", "label": "Revenue Recovery"},
            {"value": "gtm", "label": "Go-to-Market Engineering"}, {"value": "authority", "label": "The Authority Engine"}, {"value": "broadcast", "label": "The Broadcast Engine"}, {"value": "ascent", "label": "The Ascent"}]},
        {"name": "max", "label": "Most leads to research in this stage", "type": "int", "min": 1, "max": 50, "default": 25},
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
T["dse.enrich_site"] = tool("Lead enrichment: look at one website", "Reads one company website and shows what a lead list would get: emails, owner, phone, form, booking tool, score and why. Nothing is saved.",
                            [{"lit": "enrich"}, {"opt": "--site", "field": "site"}, {"opt": "--icp", "field": "icp"}, {"flag": "--fast", "field": "fast"}],
                            [{"name": "site", "label": "Website", "type": "url", "required": True},
                             {"name": "icp", "label": "Words you want to find (optional)", "type": "text", "required": False, "max": 120, "pattern": r"^[A-Za-z0-9][A-Za-z0-9 ,/&'-]{0,119}$"},
                             {"name": "fast", "label": "Fast (skip the hidden browser)", "type": "bool", "default": False}], 5)
T["dse.enrich_site"]["outputs"] = []
T["dse.enrich_providers"] = tool("Lead enrichment: which paid providers are set up", "Lists the optional paid providers on this PC and whether their key is present (the key is never shown). To add one, run at your PC: python dse.py enrich --add-provider hunter, then set your own key in a Windows user variable.",
                                 [{"lit": "enrich"}, {"flag": "--providers", "field": "go"}], [{"name": "go", "label": "Show", "type": "bool", "default": True}], 1)
T["dse.enrich_providers"]["outputs"] = []

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len([k for k in T if k.startswith("dse.enrich")]), "enrich tools,", len(T), "in all")
