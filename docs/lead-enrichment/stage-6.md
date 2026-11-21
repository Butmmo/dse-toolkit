# Lead enrichment, Stage 6: evidence-backed assessments

**Date:** 21 November 2026  
**Status:** Implemented on the feature branch; not yet installed on the PC runner.

## What changed

Added a deterministic assessment pass over the titles and snippets already retrieved by Herald. It produces separate, machine-readable assessments for the supported business archetypes, decision-maker roles, role-bearing people results, and public mentions of US C-Corp/S-Corp terms.

Each business archetype assessment includes its label, an evidence-strength status, a heuristic score, the kind of score, matched text cues, and source IDs. Role assessments list the target role, evidence status, matched cues and source IDs. Candidate people results retain their source title and URL and show which role evidence appeared in that result. All cited IDs resolve to the existing Herald source JSON and include the source URL, exact search query and retrieval timestamp.

The result CSV adds:

- herald_business_assessment
- herald_role_assessment
- herald_legal_form_assessment
- herald_assessed_at
- herald_assessment_note

The fields are preserved by the DSE importer and Engine Send Desk export, alongside the existing separated company/person evidence and role-candidate fields. The local draft prompt is explicit that the assessment is a review aid, not a verified company fact.

## Confidence and verification limits

The score is a transparent heuristic evidence score, not a calibrated probability. One matching phrase from a search snippet can be stale, ambiguous, or about another entity. Strong textual cue, some textual cues, and unclear describe only the returned text evidence. These labels do not confirm company structure, employee count, ownership, SaaS business model, ecommerce operations, a person's identity/employment, or the company's tax election.

Legal-form output is strictly a public-text mention check. It always says verification_status: not verified, regardless of whether a C-Corp/S-Corp phrase appears. This stage does not consult a legal registry or make legal claims.

## Install and release

No Supabase SQL is needed. No tests were run. git diff --check is the requested hygiene check. This stage is on the existing codex/hq-runner-id-routing branch only; it has not been installed on the PC runner. Install after review or on the next explicit runner-install request.
