# Lead enrichment, Stage 5: target profiles for the Herald research waterfall

**Date:** 21 November 2026  
**Status:** Implemented locally; not yet installed on the PC runner or deployed.

## What changed

The `dse.enrich_signals` HQ Tools form now lets the user steer searches along three separate axes:

- **Business type:** any business, franchise or multi-location group, local/owner-led SMB, SaaS/software company, online store/ecommerce business, or mid-market/enterprise company.
- **Decision-maker path:** any decision maker, owner/founder/compact team, franchise operator plus parent group, functional leader/department head, or specialised director/executive.
- **Legal-form search hint:** any/unknown, US C corporation, or US S corporation.

Each choice adds relevant queries to the existing business/product/news searches. Person research is separate from company research: when the input contains a decision-maker's first/last name, the search can include their current position/company, prior position/company and a recent-person-signal hint. A personal-profile result is kept only when its text matches all supplied name tokens and at least one company-name token. Company searches separately consider an input company signal or search for recent hiring, funding, launches, expansion and leadership changes. Up to two matched person results are reserved in the evidence bundle when available so company results cannot crowd them all out.

The CSV stores the selected targets in `enrichment_target_profile`, `enrichment_target_decision_maker`, `enrichment_target_role`, `enrichment_target_legal_form`, and `enrichment_search_strategy`; those fields describe what the user asked the tool to find, not what the business has been proven to be. Evidence is separated into `herald_company_findings` / `herald_company_sources` and `herald_person_findings` / `herald_person_sources`, while the combined `herald_*` and compatibility `research_*` fields remain. The role waterfall keeps several signal-based role hypotheses in `herald_role_candidates` and company-matched public profile results in `herald_people_candidates`. It can consider first and last name, current and previous role, current and previous company, and person- or company-level last lead signals. Search metadata keeps the query, source URL, retrieval time, matched company terms, and matched person terms where applicable.

Signal-based role discovery covers several plausible targets instead of forcing one title: for example HR and development hiring managers for hiring signals, Sales leaders for revenue signals, coaches for coaching signals, and CTO/COO/CEO/President/founder paths where the company signal suggests them. The HQ Tools form has presets and an optional custom role title, since the role catalog must remain open-ended. When a named person is supplied, the tool separately searches that person's public professional profile and recent public signals, with full-name and current/prior-company-token checks. This supports both discovering likely roles and candidate people at a company and researching a known individual in a chosen role.

The local draft model sees the target preferences but is instructed not to state the target as a fact. In particular, US C-Corp/S-Corp selections are search hints only. The result does not verify legal form or provide legal advice.

## Boundaries and next step

This slice changes search direction and keeps person/company evidence distinct, but does not yet classify companies or verify their ownership, staff size, franchise relationship, SaaS status, current/former job history, or corporate tax election. Role candidates are search hypotheses, not verified org-chart positions; public profile pages may be incomplete or mismatched. Name/company-token matching screens candidates but does not confirm identity or employment. A later stage should add evidence-backed role/person adjudication with confidence, source and timestamp, and authoritative registries for legal-form checks where available. Low-confidence cases must stay unclassified rather than being silently forced into a target group.

No Supabase SQL change is needed. HQ Tools reads the updated PC runner catalog when the runner restarts or reports its catalog again.

## Changed code

- Added `dse/business_profiles.py` with the supported target vocabularies and search-direction descriptions.
- Added CLI flags to `python dse.py signals` for business profile, decision-maker path, signal-discovered or preset roles, an open-ended custom role title, and a US legal-form search hint.
- Added the selectors and safer wording to `dse.enrich_signals` in the generated runner catalog.
- Stored target selections and search strategy beside the sourced Herald evidence in the result CSV.
- Added separate company, role-discovery, and named-person query lanes and evidence fields, including first/last name, current/previous role and company, and separate person/company signal inputs where supplied.
