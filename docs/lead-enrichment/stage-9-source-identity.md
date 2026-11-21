# Stage 9: source identity matching

## What changed

Public-search evidence is now annotated with a target identity before it can flow into lead assessments. Company results carry a company-name overlap, location overlap, and/or a direct website-domain match. Named decision-maker results must match the supplied person's name and a current or prior company context before they are retained. Results include the match type, a heuristic strength/score, matched terms, and the observed domain.

Company archetype and legal-form mention assessments now use company-matched sources only. Role assessments can use company role-discovery results and matched named-person sources. This keeps a person's profile facts from being treated as facts about their employer and makes each assessment traceable to its source IDs.

## Limits

Identity scores are explainable matching cues, not verified identity or calibrated probabilities. Search titles/snippets can be incomplete, stale, or ambiguous; direct source review is still required. Results rejected by the matching thresholds are not included in assessments. No social platform is logged into, no private data is accessed, and no outreach is sent.

No Supabase SQL is required for this slice. Source identity metadata travels with the existing enrichment-source JSON fields.

## Files

- `dse/signal_enrichment.py`: target matching and evidence metadata.
- `dse/classification.py`: subject-specific assessment inputs.
