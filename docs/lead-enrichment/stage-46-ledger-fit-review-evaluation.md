# Stage 46: Evaluate Ledger human fit reviews

## What changed

The local enrichment evaluator now accepts a Ledger grid CSV export containing the `enrichment_review` JSON column. `score-ledger` reads the `dbi.enrichment-human-review.v1` history and writes a JSON summary of the latest judgement per row and research lane, grouped by lane and enrichment profile. It reports counts for `good_fit`, `not_a_fit`, and `uncertain`, along with whether review and research check times were recorded. Stage 47 extends it with same-row, same-lane `field_results` counts by judgement. Repeated reviews remain in the source history but do not give one row extra weight in the summary.

## Use

In the grid, make `enrichment_review` visible, export the rows you want to study, and run:

```powershell
python dse.py eval-enrichment score-ledger my-lists\ledger-export.csv
```

The report is written beside the CSV as `*-ledger-fit-evaluation.json`. Use `--out` to choose another output path.

## Interpretation and limits

The tool summarizes human fit decisions. It does not measure factual accuracy, campaign conversion, willingness to pay, or population-wide lead quality. It does not upload the export, contact providers, or modify the Ledger. Small lane/profile groups are descriptive only. The existing field-level yes/no evaluation remains a separate command because fit judgements do not establish whether an individual enriched field is correct.

No Supabase SQL is needed. No automated tests were added or run.

## Files

- `dse/enrichment_eval.py`: `score-ledger` command and grouping logic.
- `dse.py eval-enrichment`: CLI entry point.
