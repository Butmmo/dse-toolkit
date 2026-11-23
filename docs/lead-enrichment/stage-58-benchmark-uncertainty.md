# Stage 58: Show uncertainty and small-sample flags

## What changed

Each yes/no review rate now includes its labeled denominator, a Wilson 95% interval, and a `minimum_labeled_met` flag. The default caution threshold is 20 labeled rows per dimension and can be changed with `--min-labeled`. Unknown, blank, and invalid responses are still reported separately and do not enter the yes/no rate or its interval. The report records the threshold used.

## Use

```powershell
python dse.py eval-enrichment score my-lists\reviewed-benchmark.csv
```

Use `--min-labeled` to choose a different caution threshold for the review plan:

```powershell
python dse.py eval-enrichment score my-lists\reviewed-benchmark.csv --min-labeled 30
```

Each `review_labels` item has `labeled`, `rate`, `wilson_95.lower`, `wilson_95.upper`, `minimum_labeled_count`, and `minimum_labeled_met`. The flag is useful when reviewing `by_field_and_source` or path/profile cohorts; compare the same field and similarly selected leads.

## Limits

The Wilson interval describes sampling uncertainty for a simple binary proportion under the observed review sample. It does not adjust for repeated field observations from the same lead, selection bias, unreliable adjudication, source mismatch, or a nonrepresentative sample. Stage 59 adds descriptive paired comparisons for the same lead and field. The minimum count is a warning threshold, not a significance test or guarantee of statistical power. Do not make a provider or waterfall decision from the interval or threshold alone.

No SQL migration is needed. No automated tests were added or run.

## Files

- `dse/enrichment_eval.py`: Wilson intervals and configurable review-count flag.
- `docs/lead-enrichment/stage-57-field-source-comparison.md`: source comparison use and limits.
