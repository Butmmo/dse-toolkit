# Stage 11: decision-maker candidate ranking

## What changed

Herald now ranks public profile candidates using two explicit inputs: target identity match and evidence that the result matches one of the research-specific role targets. Named-person results receive a small specificity bonus. Company role-discovery results from LinkedIn individual profile URLs are also surfaced as candidates, but clearly marked for manual individual-identity confirmation.

Each candidate carries the source ID, title, snippet, URL, identity strength and score, matched role labels/cues, heuristic review score, review reasons, and review order. `herald_people_candidates` now carries this richer assessment output into the enriched CSV and downstream engine/Send Desk flow.

## Limits

The review score is only an ordering aid, not a probability that the person is the correct decision maker. Search snippets can be wrong or stale. Role targets are derived from the selected research path and lead signal; reviewers should confirm current employer and position from the linked source before use.

No Supabase SQL is required. No tests were run for this slice.

## Files

- `dse/classification.py`: candidate scoring, matched role cues, and review ordering.
- `dse/signal_enrichment.py`: write the full candidate assessments to the lead CSV.
