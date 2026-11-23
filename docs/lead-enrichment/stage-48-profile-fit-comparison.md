# Stage 48: Compare profile fit rates cautiously

## What changed

`score-ledger` now compares each lane/profile's good-fit rate among decided reviews (`good_fit` and `not_a_fit`) with the pooled rate for the other profile keys in the same lane. The JSON shows both sample sizes, the difference in percentage points, and a sample status. `uncertain` stays outside the decided-rate denominator and remains visible in the existing counts.

By default, the report marks a comparison `too_few_profile_reviews` until the profile has 10 decided reviews, or `too_few_other_profile_reviews` until the alternative-profile baseline also has 10. Set a different operational review threshold with `--min-decided N`. Reaching that threshold does not make a sample statistically representative; groups remain descriptive and may reflect review selection bias.

## Use

```powershell
python dse.py eval-enrichment score-ledger my-lists\ledger-export.csv
python dse.py eval-enrichment score-ledger my-lists\ledger-export.csv --min-decided 20
```

Check `profile_comparison.by_lane_and_profile` in the JSON report. The comparison baseline excludes the profile being measured and includes only other profile keys with fit reviews in the same lane. If there are no decided reviews in the comparison group, the rate and delta are `null`.

## Interpretation and limits

The difference is not causal and does not prescribe a profile change. A profile's human fit rate is not field accuracy, conversion, or willingness to pay. The threshold is a visible caution flag, not a confidence interval or proof of adequate statistical power. Stage 49 adds breakdowns by the role, business profile and other target inputs saved with each review. Keep review criteria and sample selection consistent when using these comparisons.

No Supabase SQL is needed. No automated tests were added or run.

## Files

- `dse/enrichment_eval.py`: `score-ledger` comparison output and `--min-decided` option.
