# Stage 16: source-host corroboration

## What changed

Each retained search result now records its normalized source host. Business-profile and decision-maker-role assessments still keep every evidence ID and matched cue, but the extra corroboration component in their heuristic score now counts distinct hosts rather than multiple pages from the same host. Legal-form mention records also expose their source hosts.

The per-lead identity summary reports distinct company/person source hosts, and ranked candidates and outreach evidence carry the host for review. This makes repeated pages from one site visible as repeated pages rather than separate corroborating sites.

## Limits

Distinct hosts are a rough diversity measure, not proof of independent ownership or independent reporting; related sites may share an organization. A source-host count does not verify a claim. Review the source URLs and wording directly. No Supabase SQL is required. No tests were run for this slice.

## Files

- `dse/signal_enrichment.py`: normalized host metadata and host diversity in identity summaries.
- `dse/classification.py`: host-aware heuristic corroboration for profile, role, and legal-form assessments.
