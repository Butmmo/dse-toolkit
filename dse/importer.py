"""Import an export from YOUR OWN Clay, Apollo, HubSpot or spreadsheet account and turn it into a scored, checked list.

    engines/<slug>/imports/*.csv        drop your exports here (the Go-to-Market path)
    python dse.py import <engine>       check the files: which columns were understood, how many rows, the best-scoring accounts
    python dse.py daily <engine>        build the next send list from them (website check, dedupe, openers)

Nothing is scraped. The file is whatever you exported from a tool you are logged into, under that tool's terms.
Column names vary by tool, so headers are matched by meaning (Company / Organization / Account, Domain / Website,
Title / Job Title, Person Linkedin Url, Last Funding Date ...). Unknown columns are kept and ignored.

Scoring mirrors the Go-to-Market path's own signal score (what the page can show you):
  contact is a sales, revenue-ops or growth lead, or a founder .... 1      company raised money in the last 12 months .... 2
  company size 10-500 people ................................... 1      a website to check (needed to build a list) ... required
The website check then adds what a page can show (hiring for SDR/AE/RevOps, a CRM, no instant demo path). Signals a page cannot
show (slow replies, manual CRM complaints) stay yours to note by hand.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path

from .common import ROOT

ENGINES = ROOT / "engines"

# standard column -> header spellings (after lower-casing and removing everything but letters and digits)
ALIASES: dict[str, list[str]] = {
    "business": ["company", "companyname", "organization", "organizationname", "account", "accountname", "business", "employer", "companyorganization"],
    "website": ["website", "companywebsite", "websiteurl", "domain", "companydomain", "organizationwebsite", "url", "web", "site", "organizationdomain"],
    "first_name": ["firstname", "first", "givenname"],
    "last_name": ["lastname", "last", "surname", "familyname"],
    "contact_name": ["fullname", "contactname", "person", "personname", "name", "contact", "leadname"],
    "contact_title": ["title", "jobtitle", "position", "role", "personaltitle", "persontitle", "headline", "currenttitle"],
    "email": ["email", "emailaddress", "workemail", "businessemail", "contactemail", "primaryemail", "workemailaddress", "verifiedemail"],
    "linkedin": ["linkedin", "linkedinurl", "linkedinprofile", "personlinkedinurl", "profileurl", "linkedinprofileurl", "personallinkedin", "contactlinkedinurl"],
    "company_linkedin": ["companylinkedinurl", "companylinkedin", "organizationlinkedinurl"],
    "employees": ["employees", "numberofemployees", "companysize", "employeecount", "headcount", "employeesize", "ofemployees", "staffcount"],
    "industry": ["industry", "sector", "companyindustry"],
    "city": ["city", "location", "companycity", "headquarters", "hq", "personcity"],
    "country": ["country", "companycountry", "personcountry"],
    "funding_date": ["lastfundingdate", "lastraisedat", "latestfundingdate", "fundingdate", "lastfundinground", "lastroundDate".lower(), "lastraised"],
    "funding_stage": ["fundingstage", "latestfundingstage", "lastfundingtype", "fundingtype", "lastfundingstage", "stage"],
    "phone": ["phone", "phonenumber", "mobile", "directphone", "workphone"],
}
TITLE_FIT = re.compile(r"\b(head of (sales|growth|revenue|marketing|demand)|vp[, ]*(of )?(sales|growth|revenue|marketing)|vice president[, ]*(of )?(sales|growth|revenue)|chief (revenue|sales|growth|marketing)|"
                       r"cro\b|cmo\b|revops|revenue operations|sales operations|sales ops|growth lead|director of (sales|growth|revenue|demand)|demand gen|founder|co-?founder|ceo|owner|managing director|general manager)\b", re.I)


def squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def read_rows(path: Path) -> tuple[list[str], list[dict]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(text.splitlines(), dialect=dialect)
    return list(reader.fieldnames or []), [dict(r) for r in reader]


def map_headers(headers: list[str]) -> dict[str, str]:
    """standard column -> the file's header (the first exact alias wins; 'name' is used for the person only if no better one exists)."""
    sq = {squash(h): h for h in headers}
    out: dict[str, str] = {}
    for std, names in ALIASES.items():
        for n in names:
            if n in sq and sq[n] not in out.values():
                out[std] = sq[n]
                break
    return out


def clean_domain(v: str) -> str:
    v = (v or "").strip()
    if not v:
        return ""
    v = re.sub(r"^https?://", "", v, flags=re.I)
    v = re.sub(r"^www\.", "", v, flags=re.I)
    v = v.split("/")[0].split("?")[0].strip().lower()
    return v if "." in v and " " not in v else ""


def parse_date(v: str) -> dt.date | None:
    v = (v or "").strip()
    if not v:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d", "%b %Y", "%B %Y", "%Y"):
        try:
            return dt.datetime.strptime(v[:len(v)], fmt).date()
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", v)
    return dt.date.fromisoformat(m.group(1)) if m else None


def parse_employees(v: str) -> int | None:
    nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", v or "")]
    if not nums:
        return None
    return (min(nums) + max(nums)) // 2 if len(nums) > 1 else nums[0]


def normalize(path: Path) -> tuple[list[dict], dict]:
    headers, raw = read_rows(path)
    m = map_headers(headers)
    rows = []
    for r in raw:
        g = lambda k: (r.get(m[k], "") or "").strip() if k in m else ""  # noqa: E731
        first, last = g("first_name"), g("last_name")
        # a lone 'Name' column is the person when there is a Company column, and the company when there is not
        name_is_company = "business" not in m and not (first or last) and bool(g("contact_name"))
        person = "" if name_is_company else g("contact_name")
        contact = (f"{first} {last}".strip() or person)
        business = g("business") or (g("contact_name") if name_is_company else "") or (g("website") and clean_domain(g("website")).split(".")[0].title()) or ""
        rows.append({"business": business, "website": clean_domain(g("website")), "contact_name": contact, "contact_first": (first or contact.split(" ")[0] if contact else ""),
                     "contact_title": g("contact_title"), "email": g("email").lower(), "linkedin": g("linkedin"), "company_linkedin": g("company_linkedin"),
                     "employees": g("employees"), "industry": g("industry"), "city": g("city") or g("country"), "funding_date": g("funding_date"),
                     "funding_stage": g("funding_stage"), "phone": g("phone"), "_file": path.name})
        # Carry researched evidence and AI draft fields through the engine importer so Send Desk can use them.
        for field in ("herald_findings", "herald_sources", "herald_checked_at", "herald_status",
                      "herald_company_findings", "herald_company_sources", "herald_person_findings", "herald_person_sources", "herald_role_candidates", "herald_people_candidates",
                      "herald_business_assessment", "herald_role_assessment", "herald_legal_form_assessment", "herald_signal_events", "herald_assessed_at", "herald_assessment_note", "herald_identity_summary",
                      "herald_ai_review", "herald_ai_reviewed_at", "herald_ai_review_model",
                      "enrichment_target_profile", "enrichment_target_decision_maker", "enrichment_target_role", "enrichment_target_legal_form", "enrichment_target_path", "enrichment_search_strategy",
                      "research_findings", "research_sources", "research_searched_at", "research_status",
                      "presence_signals", "presence_sources", "presence_checked_at", "presence_status", "field_results",
                      "outreach_subject", "outreach_body", "outreach_evidence", "outreach_evidence_detail", "outreach_personalization_basis", "outreach_model",
                      "waterfall_experiment_id", "waterfall_experiment_variant", "waterfall_experiment_field",
                      "waterfall_experiment_providers", "waterfall_experiment_lead_id", "waterfall_config_sha256"):
            header = next((h for h in headers if squash(h) == squash(field)), None)
            if header:
                rows[-1][field] = (r.get(header) or "").strip()
    rep = {"file": path.name, "rows": len(rows), "headers": headers, "mapped": m, "unmapped": [h for h in headers if h not in m.values()],
           "no_website": sum(1 for x in rows if not x["website"]), "no_contact": sum(1 for x in rows if not (x["contact_name"] or x["email"])),
           "missing_core": [c for c in ("business", "website") if c not in m]}
    return rows, rep


def icp(row: dict, today: dt.date | None = None) -> tuple[int, list[str]]:
    """Points from what the export itself says. The website check adds the rest."""
    today = today or dt.date.today()
    pts, why = 0, []
    if TITLE_FIT.search(row.get("contact_title", "")):
        pts += 1
        why.append("contact is a sales, revenue or growth lead or a founder")
    d = parse_date(row.get("funding_date", ""))
    if d and (today - d).days <= 365:
        pts += 2
        why.append(f"raised money in the last 12 months ({d.isoformat()})")
    n = parse_employees(row.get("employees", ""))
    if n and 10 <= n <= 500:
        pts += 1
        why.append(f"about {n} people")
    return pts, why


def files(slug: str, folder: str = "imports") -> list[Path]:
    d = ENGINES / slug / folder
    return sorted(d.glob("*.csv")) if d.exists() else []


def load_all(slug: str) -> tuple[list[dict], list[dict]]:
    rows, reports = [], []
    for f in files(slug):
        r, rep = normalize(f)
        rows += r
        reports.append(rep)
    return rows, reports


def preview(slug: str) -> None:
    """Print what the importer understood from this engine's files, so a wrong column shows up before a list is built."""
    fs = files(slug)
    if not fs:
        print(f"No files yet. Export a list from your own Clay, Apollo or HubSpot account and save the CSV in:\n  {ENGINES / slug / 'imports'}\n"
              "Then run this again (or tap Build next list).")
        return
    rows, reports = load_all(slug)
    for rep in reports:
        print(f"\n{rep['file']}: {rep['rows']} rows")
        for std, h in rep["mapped"].items():
            print(f"  {std:<16} <- \"{h}\"")
        if rep["unmapped"]:
            print("  ignored columns: " + ", ".join(rep["unmapped"][:12]) + ("..." if len(rep["unmapped"]) > 12 else ""))
        for c in rep["missing_core"]:
            print(f"  PROBLEM: no {c} column found. Rename a column to '{'Company' if c == 'business' else 'Website'}' and try again.")
        print(f"  without a website: {rep['no_website']} (cannot be checked)   without a contact: {rep['no_contact']}")
    scored = sorted(((icp(r), r) for r in rows if r["website"]), key=lambda x: -x[0][0])
    print("\nBest-scoring accounts from the file alone (the website check adds more):")
    for (pts, why), r in scored[:8]:
        print(f"  {pts}  {r['business'][:34]:<34} {r['website'][:28]:<28} {', '.join(why) or '-'}")
