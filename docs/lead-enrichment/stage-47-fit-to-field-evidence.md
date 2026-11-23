# Stage 47: Relate fit reviews to field evidence

## What changed

`score-ledger` now joins each row's latest fit review by research lane to the row's `dbi.field-result.v1` records for that same lane. The report groups field-result counts by fit judgement, lane and enrichment profile, then summarizes fields, result statuses, provider/source names, freshness statuses and verification statuses. This gives a descriptive view of what research and fields were present on leads reviewers marked good fit, not a fit or uncertain.

## Use

Export the Ledger grid with both `enrichment_review` and `field_results` visible, then run:

```powershell
python dse.py eval-enrichment score-ledger my-lists\ledger-export.csv
```

The report appears beside the export. `field_results_join.reviewed_rows_without_matching_lane_results` shows how many reviews could not be joined, commonly because that row has no field results for the reviewed lane.

## Interpretation and limits

This is a descriptive association, not a claim that fit judgements verify field values or that an enrichment field caused a good-fit outcome. It does not measure accuracy, conversion, willingness to pay, or generalize beyond the exported and reviewed rows. Same-row and same-lane matching keeps Herald, website and Presence evidence separate. Small profile groups need cautious interpretation. Data remains local; the report does not contact providers or write back to the Ledger.

No Supabase SQL is needed. No automated tests were added or run.

## Files

- `dse/enrichment_eval.py`: Ledger fit and field-result association report.
- `dse.py eval-enrichment`: CLI entry point.
