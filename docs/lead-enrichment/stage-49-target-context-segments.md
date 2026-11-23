# Stage 49: Segment fit reviews by requested targets

## What changed

When a Ledger review is saved, Citadel snapshots any available requested targeting inputs from that row: business profile, decision-maker target, role, legal form, path and search strategy. The local `score-ledger` command reports human fit counts and rates by research lane and each available target dimension, including coverage and the existing minimum-review caution flag. This supports questions such as which requested roles or business types tend to receive good-fit judgements within Herald, Website or Presence research.

The values are stored under the review's optional `target_context` object in `dbi.enrichment-human-review.v1`. Stage 50 adds a separate snapshot of returned research cues so requested intent can be compared with observed candidate evidence. Older review entries without the object remain valid and are omitted from segment groups; coverage counts make missing context visible. Context values are truncated to 160 characters when captured.

## Use

Export the Ledger grid with the `enrichment_review` column visible, then run:

```powershell
python dse.py eval-enrichment score-ledger my-lists\ledger-export.csv --min-decided 10
```

See `target_context_segments.review_coverage_by_dimension` and `target_context_segments.by_lane_dimension_and_value` in the JSON report.

## Interpretation and limits

These values represent requested targeting intent, not verified company type, legal form, job title, or identity. Segment rates describe the reviewed sample only; they are not causal, representative, or a recommendation to change strategy. Older reviews cannot be reconstructed with targeting context if it was not saved at review time. No new database column or Supabase migration is needed.

No automated tests were added or run.

## Files

- `dse/enrichment_eval.py`: target-context grouping in `score-ledger`.
- `dse.py eval-enrichment`: CLI entry point.
