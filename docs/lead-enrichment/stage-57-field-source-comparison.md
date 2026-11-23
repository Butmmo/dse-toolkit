# Stage 57: Compare reviewed outcomes by field and source

## What changed

The evaluation report now includes `by_field_and_source`. Each entry is one field, source type, and source name cohort, with the same metrics as the main report: accepted coverage, declared cost, yes/no/unknown/blank/invalid review counts, adjudicated label rates, reviewer agreement, and freshness metadata. Stage 59 adds matched same-lead comparisons where multiple sources have results for the same field. Empty source details are grouped as `unattributed` instead of disappearing from the report.

This lets the benchmark compare how the same field performs across named providers or evidence sources without mixing unlike fields together. The source contract does not guarantee that every producer uses `source.name` as a provider name, so inspect both `source_type` and `source_name` before treating a cohort as a provider.

## Use

Complete the paired reviewer and adjudication workflow from Stage 56, then score the file:

```powershell
python dse.py eval-enrichment score my-lists\ledger-export-enrichment-review-benchmark-sample-paired-review.csv
```

Open the generated JSON report and compare entries in `by_field_and_source`. Check `fields`, `review_labels.*.labeled`, `review_responses`, and the source identity before comparing yes rates. Stage 58 adds uncertainty intervals and a configurable low-count flag to each rate. The declared cost is reported only where supplied by the field-result producer; it can be estimated and may not reflect actual provider invoices.

## Interpretation limits

This is descriptive reporting, not a provider ranking. Small denominators, uneven lead mixes, different source availability, and missing/unknown labels can make apparent differences misleading. Compare the same field and similar targets; retain the sample seed and adjudicated evidence. Do not promote or demote waterfall steps based on the source breakdown alone.

No SQL migration is needed. No automated tests were added or run.

## Files

- `dse/enrichment_eval.py`: source/field cohort metrics in the evaluation JSON.
- `docs/lead-enrichment/stage-56-reviewer-agreement.md`: paired review workflow and agreement metrics.
